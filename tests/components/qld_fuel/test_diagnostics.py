"""Diagnostics tests for qld_fuel."""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

pytestmark = pytest.mark.no_fail_on_log_exception


def _load_diagnostics_module():
    for key in list(sys.modules):
        if key == "homeassistant" or key.startswith("homeassistant."):
            sys.modules.pop(key)

    homeassistant = ModuleType("homeassistant")
    homeassistant.__path__ = []
    sys.modules["homeassistant"] = homeassistant

    diagnostics_comp = ModuleType("homeassistant.components.diagnostics")

    def async_redact_data(value, to_redact):
        if isinstance(value, dict):
            redacted = {}
            for key, v in value.items():
                if key in to_redact:
                    redacted[key] = "REDACTED"
                else:
                    redacted[key] = async_redact_data(v, to_redact)
            return redacted
        if isinstance(value, list):
            return [async_redact_data(v, to_redact) for v in value]
        return value

    diagnostics_comp.async_redact_data = async_redact_data
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

    path = Path("C:/Cursor IDE/qld_fuel-hass/custom_components/qld_fuel/diagnostics.py")
    spec = importlib.util.spec_from_file_location(
        "custom_components.qld_fuel.diagnostics",
        str(path),
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["custom_components.qld_fuel.diagnostics"] = module
    spec.loader.exec_module(module)
    return module, QldFuelDataUpdateCoordinator


def test_diagnostics_redacts_token_and_returns_snapshots():
    module, coordinator_cls = _load_diagnostics_module()

    entry = SimpleNamespace(
        entry_id="entry-1",
        title="Fuel near Home",
        data={"subscriber_token": "secret", "zone": "zone.home"},
        options={},
        runtime_data=coordinator_cls(
            {
                "sites": {"1": {}, "2": {}},
                "global_cheapest": {"12": {"price": 199.9}},
                "local_cheapest": {"12": {"price": 189.9}},
            }
        ),
    )
    hass = SimpleNamespace(
        data={
            "qld_fuel": {
                "last_fetch_time": "2026-04-01T00:00:00",
                "raw_data": {
                    "sites": [{"S": "1", "N": "Station 1", "P": "4000", "Lat": -27.5, "Lng": 153.0}],
                    "prices": [{"FuelId": "12", "SiteId": "1", "Price": 1999}],
                },
            }
        }
    )

    result = asyncio.run(module.async_get_config_entry_diagnostics(hass, entry))

    assert result["entry"]["data"]["subscriber_token"] == "REDACTED"
    assert result["cache"]["raw_payload_snapshot"]["sites"]["count"] == 1
    assert result["cache"]["raw_payload_snapshot"]["prices"]["count"] == 1
    assert result["coordinator"]["payload_snapshot"]["sites_count"] == 2
