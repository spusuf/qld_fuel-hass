"""Extra coverage tests for const and diagnostics helpers."""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

pytestmark = pytest.mark.no_fail_on_log_exception


def test_const_module_import_and_values():
    path = Path(__file__).resolve().parents[3] / "custom_components" / "qld_fuel" / "const.py"
    spec = importlib.util.spec_from_file_location("custom_components.qld_fuel.const_real", str(path))
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    assert module.DOMAIN == "qld_fuel"
    assert isinstance(module.FUEL_TYPES_OPTIONS, list)
    assert module.PLATFORMS == ["sensor"]


def _load_diagnostics():
    for key in list(sys.modules):
        if key == "homeassistant" or key.startswith("homeassistant.") or key.startswith("custom_components.qld_fuel"):
            sys.modules.pop(key)

    homeassistant = ModuleType("homeassistant")
    homeassistant.__path__ = []
    sys.modules["homeassistant"] = homeassistant

    diagnostics_comp = ModuleType("homeassistant.components.diagnostics")
    diagnostics_comp.async_redact_data = lambda value, _keys: value
    sys.modules["homeassistant.components.diagnostics"] = diagnostics_comp

    config_entries = ModuleType("homeassistant.config_entries")
    config_entries.ConfigEntry = object
    sys.modules["homeassistant.config_entries"] = config_entries

    core = ModuleType("homeassistant.core")
    core.HomeAssistant = object
    sys.modules["homeassistant.core"] = core

    const_module = ModuleType("custom_components.qld_fuel.const")
    const_module.DOMAIN = "qld_fuel"
    const_module.TOKEN = "subscriber_token"
    sys.modules["custom_components.qld_fuel.const"] = const_module

    coordinator_module = ModuleType("custom_components.qld_fuel.coordinator")

    class QldFuelDataUpdateCoordinator:
        def __init__(self, data):
            self.data = data

    coordinator_module.QldFuelDataUpdateCoordinator = QldFuelDataUpdateCoordinator
    sys.modules["custom_components.qld_fuel.coordinator"] = coordinator_module

    package = ModuleType("custom_components.qld_fuel")
    package.__path__ = []
    sys.modules["custom_components.qld_fuel"] = package

    path = Path(__file__).resolve().parents[3] / "custom_components" / "qld_fuel" / "diagnostics.py"
    spec = importlib.util.spec_from_file_location("custom_components.qld_fuel.diagnostics", str(path))
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["custom_components.qld_fuel.diagnostics"] = module
    spec.loader.exec_module(module)
    return module, QldFuelDataUpdateCoordinator


def test_diagnostics_sanitize_helpers_return_none_on_empty():
    module, coordinator_cls = _load_diagnostics()
    assert module._sanitize_raw_payload(None) is None
    assert module._sanitize_processed_payload(None) is None

    entry = SimpleNamespace(
        entry_id="entry-1",
        title="Fuel",
        data={},
        options={},
        runtime_data=coordinator_cls(None),
    )
    hass = SimpleNamespace(data={"qld_fuel": {}})
    result = asyncio.run(module.async_get_config_entry_diagnostics(hass, entry))
    assert result["coordinator"]["payload_snapshot"] is None
