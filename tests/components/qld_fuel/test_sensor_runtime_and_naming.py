"""Sensor module tests for naming and runtime_data behavior."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

pytestmark = pytest.mark.no_fail_on_log_exception


def _load_sensor_module():
    for key in list(sys.modules):
        if key == "homeassistant" or key.startswith("homeassistant."):
            sys.modules.pop(key)

    homeassistant = ModuleType("homeassistant")
    homeassistant.__path__ = []
    sys.modules["homeassistant"] = homeassistant

    const_module = ModuleType("custom_components.qld_fuel.const")
    const_module.DOMAIN = "qld_fuel"
    const_module.FUEL_TYPES = "fuel_types"
    const_module.FUEL_TYPES_OPTIONS = [{"value": "12", "label": "E10"}]
    const_module.LOCATION_ENTITY = "location_entity"
    const_module.RADIUS = "radius"
    sys.modules["custom_components.qld_fuel.const"] = const_module

    recorder = ModuleType("homeassistant.components.recorder")
    recorder.history = SimpleNamespace(get_significant_states=lambda *_a, **_k: {})
    recorder.get_instance = lambda _hass: SimpleNamespace(
        async_add_executor_job=lambda *_a, **_k: {}
    )
    sys.modules["homeassistant.components.recorder"] = recorder

    sensor_comp = ModuleType("homeassistant.components.sensor")

    class SensorEntity:
        def async_write_ha_state(self):
            return None

    sensor_comp.SensorEntity = SensorEntity
    sensor_comp.SensorStateClass = SimpleNamespace(MEASUREMENT="measurement")
    sensor_comp.SensorDeviceClass = SimpleNamespace(TIMESTAMP="timestamp")
    sys.modules["homeassistant.components.sensor"] = sensor_comp

    core = ModuleType("homeassistant.core")
    core.callback = lambda func: func
    sys.modules["homeassistant.core"] = core

    helpers = ModuleType("homeassistant.helpers")
    helpers.__path__ = []
    sys.modules["homeassistant.helpers"] = helpers

    entity_module = ModuleType("homeassistant.helpers.entity")
    entity_module.EntityCategory = SimpleNamespace(DIAGNOSTIC="diagnostic")
    sys.modules["homeassistant.helpers.entity"] = entity_module

    entity_registry = ModuleType("homeassistant.helpers.entity_registry")
    entity_registry.async_get = lambda _hass: SimpleNamespace(
        async_get_entity_id=lambda *_a, **_k: None
    )
    entity_registry.async_entries_for_config_entry = lambda *_a, **_k: []
    sys.modules["homeassistant.helpers.entity_registry"] = entity_registry

    device_registry = ModuleType("homeassistant.helpers.device_registry")
    device_registry.DeviceEntryType = SimpleNamespace(SERVICE="service")
    device_registry.DeviceInfo = dict
    sys.modules["homeassistant.helpers.device_registry"] = device_registry

    update_coordinator = ModuleType("homeassistant.helpers.update_coordinator")

    class CoordinatorEntity:
        def __init__(self, coordinator):
            self.coordinator = coordinator
            self.hass = coordinator.hass

        async def async_added_to_hass(self):
            return None

        def _handle_coordinator_update(self):
            return None

    update_coordinator.CoordinatorEntity = CoordinatorEntity
    sys.modules["homeassistant.helpers.update_coordinator"] = update_coordinator

    dt_util = ModuleType("homeassistant.util.dt")
    dt_util.utcnow = lambda: None
    sys.modules["homeassistant.util.dt"] = dt_util

    util = ModuleType("homeassistant.util")
    util.__path__ = []
    util.dt = dt_util
    sys.modules["homeassistant.util"] = util

    util_location = ModuleType("homeassistant.util.location")
    util_location.distance = lambda *_a, **_k: 0
    sys.modules["homeassistant.util.location"] = util_location

    package = ModuleType("custom_components.qld_fuel")
    package.__path__ = []
    sys.modules["custom_components.qld_fuel"] = package

    path = Path("C:/Cursor IDE/qld_fuel-hass/custom_components/qld_fuel/sensor.py")
    spec = importlib.util.spec_from_file_location(
        "custom_components.qld_fuel.sensor",
        str(path),
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["custom_components.qld_fuel.sensor"] = module
    spec.loader.exec_module(module)
    return module


def test_sensor_module_exposes_parallel_updates_and_entity_name():
    module = _load_sensor_module()
    assert module.PARALLEL_UPDATES == 1
    assert module.QldFuelBestPriceSensor._attr_has_entity_name is True
    assert module.FuelPriceSensor._attr_has_entity_name is True
    assert module.QldFuelBestPriceSensor._attr_device_class is None
    assert module.FuelPriceSensor._attr_device_class is None


def test_best_price_sensor_marks_aggregate_scopes_as_diagnostic():
    module = _load_sensor_module()

    hass = SimpleNamespace(states=SimpleNamespace(get=lambda _entity_id: None))
    entry = SimpleNamespace(
        entry_id="entry_1",
        data={},
        options={},
        title="Home",
    )
    coordinator = SimpleNamespace(hass=hass, entry=entry)

    nearby = module.QldFuelBestPriceSensor(coordinator, "12", "nearby")
    local = module.QldFuelBestPriceSensor(coordinator, "12", "local")
    global_sensor = module.QldFuelBestPriceSensor(coordinator, "12", "global")

    assert nearby._attr_entity_category is None
    assert local._attr_entity_category is None
    assert global_sensor._attr_entity_category == "diagnostic"


def test_find_all_tracked_best_uses_entry_runtime_data():
    module = _load_sensor_module()

    entry_1 = SimpleNamespace(
        runtime_data=SimpleNamespace(data={"local_cheapest": {"12": {"price": 199.9}}})
    )
    entry_2 = SimpleNamespace(
        runtime_data=SimpleNamespace(data={"local_cheapest": {"12": {"price": 189.5}}})
    )
    hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_entries=lambda _domain: [entry_1, entry_2])
    )

    best_price, station = module._find_all_tracked_best(hass, "12")
    assert best_price == 189.5
    assert station["price"] == 189.5


def _build_coordinator(module):
    state_lookup = {
        "zone.home": SimpleNamespace(name="Home"),
        "person.me": SimpleNamespace(name="Tracker"),
    }
    hass = SimpleNamespace(
        states=SimpleNamespace(get=lambda entity_id: state_lookup.get(entity_id)),
        config_entries=SimpleNamespace(async_entries=lambda _domain: []),
        data={"qld_fuel": {"raw_data": {"sites": []}}},
        is_stopping=False,
        async_create_task=lambda coro: None,
    )
    entry = SimpleNamespace(
        entry_id="entry_1",
        data={"zone": "zone.home", "radius": 5, "location_entity": "person.me"},
        options={},
        title="Fuel near Home",
    )
    return SimpleNamespace(hass=hass, entry=entry, data={})


def test_get_fuel_data_and_location_source():
    module = _load_sensor_module()
    assert module.get_fuel_data(None, "12") is None
    assert module.get_fuel_data({"12": {"price": 1}}, "12") == {"price": 1}
    entry = SimpleNamespace(data={"location_entity": "person.me"}, options={})
    assert module._resolve_location_source(entry) == "person.me"
    entry = SimpleNamespace(data={}, options={"location_entity": 42})
    assert module._resolve_location_source(entry) is None


def test_remove_stale_entities_removes_only_matching_prefix():
    module = _load_sensor_module()
    removed = []
    registry = SimpleNamespace(async_remove=lambda entity_id: removed.append(entity_id))
    module.er.async_get = lambda _hass: registry
    module.er.async_entries_for_config_entry = lambda _registry, _entry_id: [
        SimpleNamespace(unique_id="qld_fuel_entry_1_12_1", entity_id="sensor.keep"),
        SimpleNamespace(unique_id="qld_fuel_entry_1_12_2", entity_id="sensor.remove"),
        SimpleNamespace(unique_id="other_prefix", entity_id="sensor.other"),
    ]
    module._remove_stale_entities(
        SimpleNamespace(),
        SimpleNamespace(entry_id="entry_1"),
        {"qld_fuel_entry_1_12_1"},
    )
    assert removed == ["sensor.remove"]


def test_remove_stale_entities_skips_entries_without_unique_id():
    module = _load_sensor_module()
    removed = []
    registry = SimpleNamespace(async_remove=lambda entity_id: removed.append(entity_id))
    module.er.async_get = lambda _hass: registry
    module.er.async_entries_for_config_entry = lambda *_a, **_k: [
        SimpleNamespace(unique_id=None, entity_id="sensor.none"),
    ]
    module._remove_stale_entities(SimpleNamespace(), SimpleNamespace(entry_id="entry_1"), set())
    assert removed == []


def test_last_api_response_sensor_reads_shared_fetch_time():
    module = _load_sensor_module()
    coordinator = _build_coordinator(module)
    ts = datetime(2026, 4, 1, 0, 0, 0, tzinfo=timezone.utc)
    coordinator.hass.data["qld_fuel"]["last_fetch_time"] = ts
    coordinator.last_update_success = True
    sensor = module.QldFuelLastApiResponseSensor(coordinator)
    assert sensor.native_value == ts
    assert sensor.extra_state_attributes["last_update_success"] is True
    assert sensor._attr_unique_id == "qld_fuel_entry_1_last_api_response"


def test_async_setup_entry_creates_entities_for_master_and_local():
    module = _load_sensor_module()
    coordinator = _build_coordinator(module)
    coordinator.data = {
        "sites": {
            "1": {"name": "Station 1", "prices": [{"FuelId": "12", "Price": 199.9}]},
            "2": {"prices": []},
        }
    }
    coordinator.entry.data["fuel_types"] = ["12"]
    hass = coordinator.hass
    hass.data["qld_fuel"]["master_entry_id"] = "entry_1"
    coordinator.entry.runtime_data = coordinator
    added = []
    asyncio.run(module.async_setup_entry(hass, coordinator.entry, lambda entities: added.extend(entities)))
    assert added
    names = {entity._attr_unique_id for entity in added}
    assert "qld_fuel_global_12" in names
    assert "qld_fuel_tracked_12" in names
    assert "qld_fuel_entry_1_last_api_response" in names


def test_best_price_sensor_native_values_and_attributes():
    module = _load_sensor_module()
    coordinator = _build_coordinator(module)
    coordinator.data = {
        "global_cheapest": {"12": {"price": 199.9, "site_id": "1"}},
        "local_cheapest": {"12": {"price": 189.9, "site_id": "1"}},
    }
    coordinator.hass.data["qld_fuel"]["raw_data"]["sites"] = [
        {"S": "1", "N": "Station 1", "A": "Main", "P": "4000", "Lat": -27.5, "Lng": 153.0}
    ]
    coordinator._resolve_entry_coords = lambda: (-27.5, 153.0, "zone.home")
    global_sensor = module.QldFuelBestPriceSensor(coordinator, "12", "global")
    assert global_sensor.native_value == 199.9
    attrs = global_sensor.extra_state_attributes
    assert attrs["station_name"] == "Station 1"

    local_sensor = module.QldFuelBestPriceSensor(coordinator, "12", "local")
    assert local_sensor.native_value == 189.9
    nearby_sensor = module.QldFuelBestPriceSensor(coordinator, "12", "nearby")
    nearby_attrs = nearby_sensor.extra_state_attributes
    assert nearby_attrs["reason"] == "ok"

    global_device = global_sensor.device_info
    assert global_device["name"] == "Queensland Fuel Prices"
    local_device = local_sensor.device_info
    assert local_device["name"] == "Fuel near Home"


def test_best_price_sensor_all_tracked_native_value_and_attributes():
    module = _load_sensor_module()
    coordinator = _build_coordinator(module)
    entry_1 = SimpleNamespace(runtime_data=SimpleNamespace(data={"local_cheapest": {"12": {"price": 170.0, "site_id": "1"}}}))
    entry_2 = SimpleNamespace(runtime_data=SimpleNamespace(data={"local_cheapest": {"12": {"price": 160.0, "site_id": "2"}}}))
    coordinator.hass.config_entries = SimpleNamespace(async_entries=lambda _domain: [entry_1, entry_2])
    sensor = module.QldFuelBestPriceSensor(coordinator, "12", "all_tracked")
    assert sensor.native_value == 160.0
    attrs = sensor.extra_state_attributes
    assert attrs["status"].startswith("Site")


def test_best_price_sensor_handles_missing_station_data_paths():
    module = _load_sensor_module()
    coordinator = _build_coordinator(module)
    coordinator.data = {"local_cheapest": {}, "global_cheapest": {}}
    sensor = module.QldFuelBestPriceSensor(coordinator, "12", "nearby")
    attrs = sensor.extra_state_attributes
    assert attrs["reason"] == "no_stations_in_range"

    coordinator.data = {"local_cheapest": {"12": {"price": 1.0}}, "global_cheapest": {}}
    sensor2 = module.QldFuelBestPriceSensor(coordinator, "12", "local")
    assert sensor2.extra_state_attributes["status"] == "Price found but site_id is missing"

    sensor3 = module.QldFuelBestPriceSensor(coordinator, "12", "global")
    assert sensor3.extra_state_attributes["status"].startswith("No data")

    assert sensor2._find_station_entity_id({}) is None


def test_fuel_price_sensor_values_attributes_and_history():
    module = _load_sensor_module()
    now = datetime(2026, 4, 1, 0, 0, 0)
    module.dt_util.utcnow = lambda: now
    coordinator = _build_coordinator(module)
    coordinator.data = {
        "sites": {
            "1": {
                "name": "Station 1",
                "address": "Main",
                "postcode": "4000",
                "latitude": -27.5,
                "longitude": 153.0,
                "distance": 1.2,
                "prices": [{"FuelId": "12", "Price": 199.9}],
                "stats": {"12": {"qld_delta": 2.1}},
            }
        }
    }
    sensor = module.FuelPriceSensor(coordinator, "1", "12")
    sensor.entity_id = "sensor.station_1"
    assert sensor.native_value == 199.9
    assert sensor.device_info["name"] == "Fuel near Home"
    attrs = sensor.extra_state_attributes
    assert attrs["difference_to_qld_cheapest"] == 2.1
    assert "Location" in attrs

    points = [
        SimpleNamespace(state="199.9", last_changed=now - timedelta(days=1)),
        SimpleNamespace(state="189.9", last_changed=now - timedelta(days=3)),
        SimpleNamespace(state="bad", last_changed=now - timedelta(days=2)),
    ]
    async def _executor(*_a, **_k):
        return {"sensor.station_1": points}

    module.get_instance = lambda _hass: SimpleNamespace(async_add_executor_job=_executor)
    asyncio.run(sensor._update_history())
    assert sensor._14d_low == 189.9
    assert sensor._7d_low == 189.9

    attrs2 = sensor.extra_state_attributes
    assert "7_day_low" in attrs2
    assert "14_day_low" in attrs2


def test_fuel_price_sensor_native_value_missing_fuel_returns_none():
    module = _load_sensor_module()
    coordinator = _build_coordinator(module)
    coordinator.data = {"sites": {"1": {"name": "Station 1", "prices": [{"FuelId": "5", "Price": 150.0}]}}}
    sensor = module.FuelPriceSensor(coordinator, "1", "12")
    assert sensor.native_value is None


def test_fuel_price_sensor_history_error_and_stop_paths():
    module = _load_sensor_module()
    module.dt_util.utcnow = lambda: datetime(2026, 4, 1, 0, 0, 0)
    coordinator = _build_coordinator(module)
    sensor = module.FuelPriceSensor(coordinator, "1", "12")
    sensor.entity_id = "sensor.station_1"
    coordinator.hass.is_stopping = True
    asyncio.run(sensor._update_history())
    coordinator.hass.is_stopping = False

    class _ErrInstance:
        async def async_add_executor_job(self, *_a, **_k):
            raise ValueError("no history")

    module.get_instance = lambda _hass: _ErrInstance()
    asyncio.run(sensor._update_history())


def test_fuel_price_sensor_added_and_coordinator_update_hooks():
    module = _load_sensor_module()
    module.dt_util.utcnow = lambda: datetime(2026, 4, 1, 0, 0, 0)
    coordinator = _build_coordinator(module)
    scheduled = []
    coordinator.hass.async_create_task = lambda coro: scheduled.append(coro)
    sensor = module.FuelPriceSensor(coordinator, "1", "12")
    sensor.entity_id = "sensor.station_1"

    async def _fake_history():
        return None

    sensor._update_history = _fake_history
    asyncio.run(sensor.async_added_to_hass())
    sensor._handle_coordinator_update()
    assert len(scheduled) == 1
    scheduled[0].close()


def test_history_ignores_unavailable_points():
    module = _load_sensor_module()
    now = datetime(2026, 4, 1, 0, 0, 0)
    module.dt_util.utcnow = lambda: now
    coordinator = _build_coordinator(module)
    sensor = module.FuelPriceSensor(coordinator, "1", "12")
    sensor.entity_id = "sensor.station_1"

    points = [
        SimpleNamespace(state="unavailable", last_changed=now - timedelta(days=1)),
        SimpleNamespace(state="190.0", last_changed=now - timedelta(days=2)),
    ]

    async def _executor(*_a, **_k):
        return {"sensor.station_1": points}

    module.get_instance = lambda _hass: SimpleNamespace(async_add_executor_job=_executor)
    asyncio.run(sensor._update_history())
    assert sensor._14d_low == 190.0
