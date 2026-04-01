"""Coordinator tests for qld_fuel."""

from __future__ import annotations

import asyncio
import importlib.util
from datetime import datetime, timedelta
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

pytestmark = pytest.mark.no_fail_on_log_exception


def _install_homeassistant_stubs() -> None:
    """Install minimal Home Assistant stubs for local unit tests."""
    for key in list(sys.modules):
        if key == "homeassistant" or key.startswith("homeassistant."):
            sys.modules.pop(key)

    ha = ModuleType("homeassistant")
    helpers = ModuleType("homeassistant.helpers")
    aiohttp_client = ModuleType("homeassistant.helpers.aiohttp_client")
    event = ModuleType("homeassistant.helpers.event")
    update_coordinator = ModuleType("homeassistant.helpers.update_coordinator")
    issue_registry = ModuleType("homeassistant.helpers.issue_registry")
    core = ModuleType("homeassistant.core")
    util = ModuleType("homeassistant.util")
    util_dt = ModuleType("homeassistant.util.dt")
    util_location = ModuleType("homeassistant.util.location")
    const = ModuleType("homeassistant.const")
    ha.__path__ = []
    helpers.__path__ = []

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
    issue_registry.IssueSeverity = SimpleNamespace(ERROR="error")
    issue_registry.async_create_issue = lambda *args, **kwargs: None
    issue_registry.async_delete_issue = lambda *args, **kwargs: None
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
    sys.modules["homeassistant.helpers.issue_registry"] = issue_registry
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

    path = Path(__file__).resolve().parents[3] / "custom_components" / "qld_fuel" / "coordinator.py"
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


class _FakeResponse:
    def __init__(self, status, payload=None):
        self.status = status
        self._payload = payload or {}

    async def json(self):
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, _exc_type, _exc, _tb):
        return False


class _FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)

    def get(self, _url, headers=None):
        assert headers is not None
        return self._responses.pop(0)


def test_validate_token_paths():
    module = _load_coordinator_module()
    hass = _FakeHass({})

    with pytest.raises(module.QldFuelAuthError):
        asyncio.run(module.async_validate_token(hass, None))

    module.async_get_clientsession = lambda _hass: _FakeSession([_FakeResponse(401)])
    with pytest.raises(module.QldFuelAuthError):
        asyncio.run(module.async_validate_token(hass, "token"))

    module.async_get_clientsession = lambda _hass: _FakeSession([_FakeResponse(500)])
    with pytest.raises(module.QldFuelConnectionError):
        asyncio.run(module.async_validate_token(hass, "token"))

    class _BrokenSession:
        def get(self, _url, headers=None):
            raise RuntimeError("boom")

    module.async_get_clientsession = lambda _hass: _BrokenSession()
    with pytest.raises(module.QldFuelConnectionError):
        asyncio.run(module.async_validate_token(hass, "token"))


def test_resolve_entry_coords_falls_back_to_zone_then_stored_coords():
    module = _load_coordinator_module()
    hass = _FakeHass({"zone.home": _state("Home", -27.5, 153.0)})
    entry = SimpleNamespace(
        data={"zone": "zone.home", "scan_interval": 6, "latitude": -28.0, "longitude": 154.0},
        options={},
        title="Fuel near Home",
    )
    coordinator = module.QldFuelDataUpdateCoordinator(hass, entry)
    assert coordinator._resolve_entry_coords() == (-27.5, 153.0, "zone.home")

    hass = _FakeHass({})
    bad_entry = SimpleNamespace(
        data={"scan_interval": 6, "latitude": "bad", "longitude": "bad"},
        options={},
        title="Fuel near Bad",
    )
    coordinator = module.QldFuelDataUpdateCoordinator(hass, bad_entry)
    assert coordinator._resolve_entry_coords() == (None, None, None)


def test_setup_location_listener_paths_and_change_detection():
    module = _load_coordinator_module()
    calls = []

    def _track(_hass, _entities, listener):
        calls.append(listener)
        return lambda: calls.append("removed")

    module.async_track_state_change_event = _track

    hass = _FakeHass({"person.test": _state("Person", -27.5, 153.0)})
    entry = SimpleNamespace(
        data={"location_entity": "person.test", "scan_interval": 6},
        options={},
        title="Fuel",
    )
    coordinator = module.QldFuelDataUpdateCoordinator(hass, entry)

    asyncio.run(coordinator.async_setup_location_listener())
    assert coordinator._remove_location_listener is not None

    asyncio.run(coordinator.async_setup_location_listener())
    assert len(calls) == 1

    listener = calls[0]
    same_event = {"data": {"old_state": _state("P", -27.5, 153.0), "new_state": _state("P", -27.5, 153.0)}}
    listener(SimpleNamespace(**same_event))
    assert hass._created_tasks == []

    changed_event = {"data": {"old_state": _state("P", -27.5, 153.0), "new_state": _state("P", -27.4, 153.0)}}
    listener(SimpleNamespace(**changed_event))
    assert len(hass._created_tasks) == 1
    hass._created_tasks[0].close()


def test_async_update_data_fetch_and_cache_paths():
    module = _load_coordinator_module()
    now = [datetime(2026, 1, 1, 0, 0, 0)]
    module.dt_util.utcnow = lambda: now[0]
    hass = _FakeHass({"zone.home": _state("Home", -27.5, 153.0)})
    entry = SimpleNamespace(
        entry_id="entry-1",
        data={"scan_interval": 6, "subscriber_token": "token", "zone": "zone.home"},
        options={},
        title="Fuel",
    )
    coordinator = module.QldFuelDataUpdateCoordinator(hass, entry)
    coordinator._process_raw_data = lambda data: {"processed": data["sites"]}
    coordinator._fetch_from_api = lambda: asyncio.sleep(0, result={"sites": [{"S": "1"}], "prices": []})

    result = asyncio.run(coordinator._async_update_data())
    assert result["processed"] == [{"S": "1"}]
    assert "fetch_lock" in hass.data["qld_fuel"]

    now[0] = now[0] + timedelta(minutes=1)
    result2 = asyncio.run(coordinator._async_update_data())
    assert result2["processed"] == [{"S": "1"}]


def test_async_update_data_error_paths_raise_update_failed():
    module = _load_coordinator_module()
    module.dt_util.utcnow = lambda: 1000
    hass = _FakeHass({"zone.home": _state("Home", -27.5, 153.0)})
    entry = SimpleNamespace(
        entry_id="entry-1",
        data={"scan_interval": 6, "subscriber_token": "token", "zone": "zone.home"},
        options={},
        title="Fuel",
    )
    coordinator = module.QldFuelDataUpdateCoordinator(hass, entry)

    coordinator._fetch_from_api = lambda: asyncio.sleep(0, result=(_ for _ in ()).throw(module.QldFuelAuthError("bad")))
    with pytest.raises(sys.modules["homeassistant.helpers.update_coordinator"].UpdateFailed):
        asyncio.run(coordinator._async_update_data())

    coordinator._fetch_from_api = lambda: asyncio.sleep(
        0, result=(_ for _ in ()).throw(module.QldFuelConnectionError("down"))
    )
    with pytest.raises(sys.modules["homeassistant.helpers.update_coordinator"].UpdateFailed):
        asyncio.run(coordinator._async_update_data())


def test_fetch_from_api_status_and_payload_paths():
    module = _load_coordinator_module()
    hass = _FakeHass({})
    entry = SimpleNamespace(data={"subscriber_token": "token", "scan_interval": 6}, options={}, title="Fuel")
    coordinator = module.QldFuelDataUpdateCoordinator(hass, entry)

    with pytest.raises(sys.modules["homeassistant.helpers.update_coordinator"].UpdateFailed):
        coordinator.entry.data.pop("subscriber_token")
        asyncio.run(coordinator._fetch_from_api())

    coordinator.entry.data["subscriber_token"] = "token"
    module.async_get_clientsession = lambda _hass: _FakeSession(
        [
            _FakeResponse(200, {"S": [{"S": "1"}]}),
            _FakeResponse(200, {"SitePrices": [{"FuelId": "12"}]}),
        ]
    )
    payload = asyncio.run(coordinator._fetch_from_api())
    assert payload["sites"] == [{"S": "1"}]
    assert payload["prices"] == [{"FuelId": "12"}]

    module.async_get_clientsession = lambda _hass: _FakeSession([_FakeResponse(403)])
    with pytest.raises(module.QldFuelAuthError):
        asyncio.run(coordinator._fetch_from_api())

    module.async_get_clientsession = lambda _hass: _FakeSession([_FakeResponse(500)])
    with pytest.raises(module.QldFuelConnectionError):
        asyncio.run(coordinator._fetch_from_api())


def test_process_raw_data_and_filter_to_zone_branches():
    module = _load_coordinator_module()
    hass = _FakeHass({})
    entry = SimpleNamespace(data={"scan_interval": 6, "radius": 1}, options={}, title="Fuel")
    coordinator = module.QldFuelDataUpdateCoordinator(hass, entry)
    coordinator._resolve_entry_coords = lambda: (-27.5, 153.0, "zone.home")
    raw_data = {
        "sites": [
            {"S": "1", "N": "A", "A": "addr", "P": "4000", "Lat": -27.5, "Lng": 153.0},
            {"S": "2", "N": "B", "A": "addr2", "P": "4001", "Lat": "bad", "Lng": 153.1},
        ],
        "prices": [
            {"FuelId": "12", "SiteId": "1", "Price": 1999},
            {"FuelId": "12", "SiteId": "1", "Price": 0},
            {"FuelId": "5", "SiteId": "1", "Price": 1500},
        ],
    }
    processed = coordinator._process_raw_data(raw_data)
    assert "1" in processed["sites"]
    assert processed["global_cheapest"]["12"]["price"] == 199.9
    assert processed["local_cheapest"]["5"]["price"] == 150.0

    coordinator._resolve_entry_coords = lambda: (None, None, None)
    filtered = coordinator._filter_to_zone([], {}, {})
    assert filtered["sites"] == {}
    assert filtered["local_cheapest"] == {}


def test_coords_from_state_missing_and_invalid_values():
    module = _load_coordinator_module()
    assert module.QldFuelDataUpdateCoordinator._coords_from_state(None) == (None, None)
    assert module.QldFuelDataUpdateCoordinator._coords_from_state(SimpleNamespace(attributes={})) == (
        None,
        None,
    )
    assert module.QldFuelDataUpdateCoordinator._coords_from_state(
        SimpleNamespace(attributes={"latitude": "x", "longitude": 1})
    ) == (None, None)


def test_listener_without_location_and_shutdown_and_empty_cache_recompute():
    module = _load_coordinator_module()
    hass = _FakeHass({})
    entry = SimpleNamespace(data={"scan_interval": 6}, options={}, title="Fuel")
    coordinator = module.QldFuelDataUpdateCoordinator(hass, entry)
    asyncio.run(coordinator.async_setup_location_listener())
    assert coordinator._remove_location_listener is None
    asyncio.run(coordinator.async_recompute_from_cache())
    assert coordinator.data == {}
    asyncio.run(coordinator.async_shutdown())
    assert coordinator._remove_location_listener is None


def test_async_shutdown_invokes_registered_listener_cleanup():
    module = _load_coordinator_module()
    hass = _FakeHass({})
    entry = SimpleNamespace(data={"scan_interval": 6}, options={}, title="Fuel")
    coordinator = module.QldFuelDataUpdateCoordinator(hass, entry)
    called = []

    def _remove():
        called.append(True)

    coordinator._remove_location_listener = _remove
    asyncio.run(coordinator.async_shutdown())
    assert called == [True]
    assert coordinator._remove_location_listener is None


def test_async_update_data_wraps_unexpected_exception():
    module = _load_coordinator_module()
    module.dt_util.utcnow = lambda: datetime(2026, 1, 1, 0, 0, 0)
    hass = _FakeHass({"zone.home": _state("Home", -27.5, 153.0)})
    entry = SimpleNamespace(
        entry_id="entry-1",
        data={"scan_interval": 6, "subscriber_token": "token", "zone": "zone.home"},
        options={},
        title="Fuel",
    )
    coordinator = module.QldFuelDataUpdateCoordinator(hass, entry)

    async def _explode():
        raise RuntimeError("explode")

    coordinator._fetch_from_api = _explode
    with pytest.raises(sys.modules["homeassistant.helpers.update_coordinator"].UpdateFailed):
        asyncio.run(coordinator._async_update_data())


def test_filter_to_zone_skips_sites_outside_radius():
    module = _load_coordinator_module()
    hass = _FakeHass({})
    entry = SimpleNamespace(data={"scan_interval": 6, "radius": 0.1}, options={}, title="Fuel")
    coordinator = module.QldFuelDataUpdateCoordinator(hass, entry)
    coordinator._resolve_entry_coords = lambda: (-27.5, 153.0, "zone.home")
    result = coordinator._filter_to_zone(
        [{"S": "9", "Lat": -25.0, "Lng": 150.0, "N": "Far", "A": "Far", "P": "0000"}],
        {"9": [{"FuelId": "12", "Price": 150.0}]},
        {},
    )
    assert result["sites"] == {}
