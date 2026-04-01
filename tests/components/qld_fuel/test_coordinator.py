"""Coordinator tests for qld_fuel."""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace


def _install_homeassistant_stubs() -> None:
    """Install minimal Home Assistant stubs for local unit tests."""
    if "homeassistant" in sys.modules:
        return

    ha = ModuleType("homeassistant")
    helpers = ModuleType("homeassistant.helpers")
    aiohttp_client = ModuleType("homeassistant.helpers.aiohttp_client")
    event = ModuleType("homeassistant.helpers.event")
    update_coordinator = ModuleType("homeassistant.helpers.update_coordinator")
    core = ModuleType("homeassistant.core")
    util = ModuleType("homeassistant.util")
    util_dt = ModuleType("homeassistant.util.dt")
    util_location = ModuleType("homeassistant.util.location")
    const = ModuleType("homeassistant.const")

    class UpdateFailed(Exception):
        """Update failed."""

    class DataUpdateCoordinator:
        """Minimal DataUpdateCoordinator stub."""

        def __init__(self, hass, logger, name, update_interval):
            self.hass = hass
            self.logger = logger
            self.name = name
            self.update_interval = update_interval
            self.data = {}

        def async_set_updated_data(self, data):
            self.data = data

    def callback(func):
        return func

    async def _unneeded_async_get_clientsession(hass):
        raise AssertionError("Network path should not be used by these tests")

    def _track_state_change_event(_hass, _entities, _listener):
        return lambda: None

    def _distance(lat1, lon1, lat2, lon2):
        return ((float(lat1) - float(lat2)) ** 2 + (float(lon1) - float(lon2)) ** 2) ** 0.5 * 1000

    aiohttp_client.async_get_clientsession = _unneeded_async_get_clientsession
    event.async_track_state_change_event = _track_state_change_event
    update_coordinator.DataUpdateCoordinator = DataUpdateCoordinator
    update_coordinator.UpdateFailed = UpdateFailed
    core.callback = callback
    util_dt.utcnow = lambda: None
    util_location.distance = _distance
    const.CONF_LATITUDE = "latitude"
    const.CONF_LONGITUDE = "longitude"

    sys.modules["homeassistant"] = ha
    sys.modules["homeassistant.helpers"] = helpers
    sys.modules["homeassistant.helpers.aiohttp_client"] = aiohttp_client
    sys.modules["homeassistant.helpers.event"] = event
    sys.modules["homeassistant.helpers.update_coordinator"] = update_coordinator
    sys.modules["homeassistant.core"] = core
    sys.modules["homeassistant.util"] = util
    sys.modules["homeassistant.util.dt"] = util_dt
    sys.modules["homeassistant.util.location"] = util_location
    sys.modules["homeassistant.const"] = const


def _load_coordinator_module():
    """Load coordinator.py directly, without importing package __init__."""
    _install_homeassistant_stubs()

    const_module = ModuleType("custom_components.qld_fuel.const")
    const_module.DOMAIN = "qld_fuel"
    const_module.TOKEN = "subscriber_token"
    const_module.RADIUS = "radius"
    const_module.SCAN_INTERVAL = "scan_interval"
    const_module.LOCATION_ENTITY = "location_entity"
    const_module.ZONE = "zone"
    sys.modules["custom_components.qld_fuel.const"] = const_module

    package = ModuleType("custom_components.qld_fuel")
    package.__path__ = []  # mark as package
    sys.modules["custom_components.qld_fuel"] = package

    path = Path("C:/Cursor IDE/qld_fuel-hass/custom_components/qld_fuel/coordinator.py")
    spec = importlib.util.spec_from_file_location(
        "custom_components.qld_fuel.coordinator",
        str(path),
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["custom_components.qld_fuel.coordinator"] = module
    spec.loader.exec_module(module)
    return module


class _StateMachine:
    def __init__(self, states):
        self._states = states

    def get(self, entity_id):
        return self._states.get(entity_id)


class _FakeHass:
    def __init__(self, states):
        self.states = _StateMachine(states)
        self.config = SimpleNamespace(latitude=-27.5, longitude=153.0)
        self.data = {"qld_fuel": {}}
        self._created_tasks = []

    def async_create_task(self, coro):
        self._created_tasks.append(coro)


def _state(name: str, lat: float | None, lon: float | None):
    return SimpleNamespace(name=name, attributes={"latitude": lat, "longitude": lon})


def test_resolve_entry_coords_prefers_location_entity():
    """Location entity takes precedence over zone and legacy coordinates."""
    module = _load_coordinator_module()

    hass = _FakeHass(
        {
            "person.test": _state("Test Person", -27.11, 153.11),
            "zone.home": _state("Home", -27.55, 153.55),
        }
    )
    entry = SimpleNamespace(
        data={
            "location_entity": "person.test",
            "zone": "zone.home",
            "latitude": -28.0,
            "longitude": 154.0,
            "scan_interval": 6,
        },
        options={},
        title="Fuel near Test",
    )

    coordinator = module.QldFuelDataUpdateCoordinator(hass, entry)
    lat, lon, source = coordinator._resolve_entry_coords()

    assert (lat, lon) == (-27.11, 153.11)
    assert source == "person.test"


def test_async_recompute_from_cache_updates_data():
    """Recompute path updates coordinator from cached raw data only."""
    module = _load_coordinator_module()

    hass = _FakeHass({"zone.home": _state("Home", -27.55, 153.55)})
    entry = SimpleNamespace(
        data={"zone": "zone.home", "scan_interval": 6},
        options={},
        title="Fuel near Home",
    )
    coordinator = module.QldFuelDataUpdateCoordinator(hass, entry)

    raw_data = {"sites": [{"S": "1"}], "prices": []}
    hass.data["qld_fuel"]["raw_data"] = raw_data
    coordinator._process_raw_data = lambda payload: {"processed": payload["sites"][0]["S"]}

    asyncio.run(coordinator.async_recompute_from_cache())

    assert coordinator.data == {"processed": "1"}
