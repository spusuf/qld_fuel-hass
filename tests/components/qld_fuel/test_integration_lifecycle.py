"""Lifecycle tests for qld_fuel __init__ module."""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import pytest

pytestmark = pytest.mark.no_fail_on_log_exception


def _load_init_module():
    for key in list(sys.modules):
        if key == "homeassistant" or key.startswith("homeassistant."):
            sys.modules.pop(key)

    homeassistant = ModuleType("homeassistant")
    homeassistant.__path__ = []
    sys.modules["homeassistant"] = homeassistant

    const_module = ModuleType("custom_components.qld_fuel.const")
    const_module.DOMAIN = "qld_fuel"
    const_module.PLATFORMS = ["sensor"]
    sys.modules["custom_components.qld_fuel.const"] = const_module

    coordinator_module = ModuleType("custom_components.qld_fuel.coordinator")

    class QldFuelDataUpdateCoordinator:
        def __init__(self, hass, entry):
            self.hass = hass
            self.entry = entry
            self.data = {}
            self.shutdown_called = False
            self.refresh_calls = 0

        async def async_config_entry_first_refresh(self):
            return None

        async def async_setup_location_listener(self):
            return None

        async def async_request_refresh(self):
            self.refresh_calls += 1

        async def async_shutdown(self):
            self.shutdown_called = True

    coordinator_module.QldFuelDataUpdateCoordinator = QldFuelDataUpdateCoordinator
    sys.modules["custom_components.qld_fuel.coordinator"] = coordinator_module

    homeassistant_core = ModuleType("homeassistant.core")
    homeassistant_core.HomeAssistant = object
    homeassistant_core.ServiceCall = object
    sys.modules["homeassistant.core"] = homeassistant_core

    homeassistant_exceptions = ModuleType("homeassistant.exceptions")

    class HomeAssistantError(Exception):
        """HomeAssistantError stub."""

    homeassistant_exceptions.HomeAssistantError = HomeAssistantError
    sys.modules["homeassistant.exceptions"] = homeassistant_exceptions

    homeassistant_config_entries = ModuleType("homeassistant.config_entries")
    homeassistant_config_entries.ConfigEntry = object
    sys.modules["homeassistant.config_entries"] = homeassistant_config_entries

    package = ModuleType("custom_components.qld_fuel")
    package.__path__ = []
    sys.modules["custom_components.qld_fuel"] = package

    path = Path("C:/Cursor IDE/qld_fuel-hass/custom_components/qld_fuel/__init__.py")
    spec = importlib.util.spec_from_file_location("custom_components.qld_fuel", str(path))
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["custom_components.qld_fuel"] = module
    spec.loader.exec_module(module)
    return module


class _Services:
    def __init__(self):
        self._handlers = {}

    def has_service(self, domain, service):
        return (domain, service) in self._handlers

    def async_register(self, domain, service, handler):
        self._handlers[(domain, service)] = handler

    def async_remove(self, domain, service):
        self._handlers.pop((domain, service), None)


class _ConfigEntries:
    def __init__(self, entries):
        self._entries = entries
        self._unload_ok = True
        self.updated_entries = []
        self.reload_calls = []

    async def async_forward_entry_setups(self, _entry, _platforms):
        return None

    async def async_unload_platforms(self, _entry, _platforms):
        return self._unload_ok

    def async_entries(self, _domain):
        return self._entries

    def async_update_entry(self, entry, data=None):
        self.updated_entries.append((entry, data))
        entry.data = data or entry.data

    async def async_reload(self, _entry_id):
        self.reload_calls.append(_entry_id)
        return None


def _make_entry(entry_id: str, is_master: bool):
    entry = SimpleNamespace(
        entry_id=entry_id,
        title=f"Fuel near {entry_id}",
        data={"is_master": is_master},
        runtime_data=None,
    )
    entry.add_update_listener = lambda _listener: (lambda: None)
    entry.async_on_unload = lambda _cb: None
    return entry


def test_setup_entry_sets_runtime_data_and_registers_service():
    module = _load_init_module()
    entry = _make_entry("entry-1", True)
    hass = SimpleNamespace(
        data={},
        services=_Services(),
        config_entries=_ConfigEntries([entry]),
    )

    result = asyncio.run(module.async_setup_entry(hass, entry))

    assert result is True
    assert entry.runtime_data is not None
    assert hass.data["qld_fuel"]["master_entry_id"] == "entry-1"
    assert hass.services.has_service("qld_fuel", "refresh_prices")


def test_unload_entry_clears_runtime_data_and_domain_when_last_entry():
    module = _load_init_module()
    entry = _make_entry("entry-1", True)
    hass = SimpleNamespace(
        data={"qld_fuel": {"master_entry_id": "entry-1"}},
        services=_Services(),
        config_entries=_ConfigEntries([entry]),
    )

    asyncio.run(module.async_setup_entry(hass, entry))
    assert entry.runtime_data is not None

    result = asyncio.run(module.async_unload_entry(hass, entry))

    assert result is True
    assert entry.runtime_data is None
    assert "qld_fuel" not in hass.data


def test_refresh_service_runs_for_all_loaded_entries():
    module = _load_init_module()
    entry_one = _make_entry("entry-1", True)
    entry_two = _make_entry("entry-2", False)
    hass = SimpleNamespace(
        data={},
        services=_Services(),
        config_entries=_ConfigEntries([entry_one, entry_two]),
    )

    asyncio.run(module.async_setup_entry(hass, entry_one))
    asyncio.run(module.async_setup_entry(hass, entry_two))

    handler = hass.services._handlers[("qld_fuel", "refresh_prices")]
    asyncio.run(handler(SimpleNamespace()))

    assert entry_one.runtime_data.refresh_calls == 1
    assert entry_two.runtime_data.refresh_calls == 1


def test_refresh_service_reports_failures_but_continues_refreshing_others():
    module = _load_init_module()
    entry_one = _make_entry("entry-1", True)
    entry_two = _make_entry("entry-2", False)
    hass = SimpleNamespace(
        data={},
        services=_Services(),
        config_entries=_ConfigEntries([entry_one, entry_two]),
    )

    asyncio.run(module.async_setup_entry(hass, entry_one))
    asyncio.run(module.async_setup_entry(hass, entry_two))
    entry_one.runtime_data.async_request_refresh = _failing_refresh

    handler = hass.services._handlers[("qld_fuel", "refresh_prices")]

    asyncio.run(handler(SimpleNamespace()))

    assert entry_two.runtime_data.refresh_calls == 1


async def _failing_refresh():
    raise RuntimeError("boom")


def test_iter_runtime_coordinators_skips_non_coordinators():
    module = _load_init_module()
    valid_entry = _make_entry("entry-1", True)
    invalid_entry = _make_entry("entry-2", False)
    invalid_entry.runtime_data = object()
    hass = SimpleNamespace(
        data={},
        services=_Services(),
        config_entries=_ConfigEntries([valid_entry, invalid_entry]),
    )
    asyncio.run(module.async_setup_entry(hass, valid_entry))
    found = list(module._iter_runtime_coordinators(hass))
    assert len(found) == 1


def test_setup_entry_does_not_reregister_existing_service():
    module = _load_init_module()
    entry = _make_entry("entry-1", True)
    services = _Services()
    services._handlers[("qld_fuel", "refresh_prices")] = lambda _call: None
    hass = SimpleNamespace(data={}, services=services, config_entries=_ConfigEntries([entry]))
    asyncio.run(module.async_setup_entry(hass, entry))
    assert len(services._handlers) == 1


def test_refresh_service_unknown_entry_id_on_missing_entry_attr():
    module = _load_init_module()
    entry = _make_entry("entry-1", True)
    hass = SimpleNamespace(
        data={},
        services=_Services(),
        config_entries=_ConfigEntries([entry]),
    )
    asyncio.run(module.async_setup_entry(hass, entry))
    entry.runtime_data.entry = SimpleNamespace()
    entry.runtime_data.async_request_refresh = _failing_refresh
    handler = hass.services._handlers[("qld_fuel", "refresh_prices")]
    asyncio.run(handler(SimpleNamespace()))


def test_unload_entry_false_does_not_clear_runtime():
    module = _load_init_module()
    entry = _make_entry("entry-1", True)
    config_entries = _ConfigEntries([entry])
    config_entries._unload_ok = False
    hass = SimpleNamespace(
        data={"qld_fuel": {"master_entry_id": "entry-1"}},
        services=_Services(),
        config_entries=config_entries,
    )
    asyncio.run(module.async_setup_entry(hass, entry))
    assert asyncio.run(module.async_unload_entry(hass, entry)) is False
    assert entry.runtime_data is not None


def test_unload_master_promotes_next_entry():
    module = _load_init_module()
    master = _make_entry("entry-1", True)
    other = _make_entry("entry-2", False)
    hass = SimpleNamespace(
        data={"qld_fuel": {"master_entry_id": "entry-1"}},
        services=_Services(),
        config_entries=_ConfigEntries([master, other]),
    )
    asyncio.run(module.async_setup_entry(hass, master))
    asyncio.run(module.async_setup_entry(hass, other))
    assert asyncio.run(module.async_unload_entry(hass, master)) is True
    assert hass.data["qld_fuel"]["master_entry_id"] == "entry-2"
    assert hass.config_entries.updated_entries


def test_reload_and_remove_device_helpers():
    module = _load_init_module()
    entry = _make_entry("entry-1", True)
    config_entries = _ConfigEntries([entry])
    hass = SimpleNamespace(data={}, services=_Services(), config_entries=config_entries)
    asyncio.run(module.async_reload_entry(hass, entry))
    assert config_entries.reload_calls == ["entry-1"]
    assert asyncio.run(module.async_remove_config_entry_device(hass, entry, object())) is True
