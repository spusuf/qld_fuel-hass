"""Config flow tests for qld_fuel."""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

pytestmark = pytest.mark.no_fail_on_log_exception


_STUBBED_MODULE_PREFIXES = (
    "homeassistant",
    "custom_components.qld_fuel",
    "voluptuous",
)


@pytest.fixture(autouse=True)
def _restore_stubbed_modules():
    """Keep module stubs isolated to each test case."""
    original = {
        name: module
        for name, module in sys.modules.items()
        if any(name == prefix or name.startswith(f"{prefix}.") for prefix in _STUBBED_MODULE_PREFIXES)
    }
    yield
    for name in list(sys.modules):
        if any(name == prefix or name.startswith(f"{prefix}.") for prefix in _STUBBED_MODULE_PREFIXES):
            sys.modules.pop(name, None)
    sys.modules.update(original)


def _install_stubs() -> None:
    """Install minimal stubs needed to import config_flow."""
    for key in list(sys.modules):
        if key == "homeassistant" or key.startswith("homeassistant."):
            sys.modules.pop(key)

    ha = ModuleType("homeassistant")
    config_entries = ModuleType("homeassistant.config_entries")
    core = ModuleType("homeassistant.core")
    helpers = ModuleType("homeassistant.helpers")
    selector = ModuleType("homeassistant.helpers.selector")
    const = ModuleType("homeassistant.const")
    voluptuous = ModuleType("voluptuous")

    class AbortFlow(Exception):
        """Abort flow stub."""

    class _BaseFlow:
        _configured_ids: set[str] = set()

        def __init__(self):
            self.hass = None
            self.context = {}
            self._unique_id = None
            self._entries = []

        def _async_current_entries(self):
            return self._entries

        async def async_set_unique_id(self, unique_id):
            self._unique_id = unique_id

        def _abort_if_unique_id_configured(self):
            if self._unique_id in self._configured_ids:
                raise AbortFlow("already_configured")
            self._configured_ids.add(self._unique_id)

        def async_create_entry(self, *, title, data):
            return {"type": "create_entry", "title": title, "data": data}

        def async_show_form(self, *, step_id, data_schema=None, errors=None):
            return {"type": "form", "step_id": step_id, "errors": errors or {}}

        def async_abort(self, *, reason):
            return {"type": "abort", "reason": reason}

        def async_update_reload_and_abort(self, entry, *, title, data):
            entry.data = data
            entry.title = title
            return {"type": "abort", "reason": "reconfigure_successful"}

        def _get_reauth_entry(self):
            return SimpleNamespace(entry_id="entry-1")

    class ConfigFlow(_BaseFlow):
        def __init_subclass__(cls, **kwargs):
            return None

    class OptionsFlow(_BaseFlow):
        pass

    def callback(func):
        return func

    class EntitySelectorConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class EntitySelector:
        def __init__(self, cfg):
            self.cfg = cfg

    class NumberSelectorConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class NumberSelector:
        def __init__(self, cfg):
            self.cfg = cfg

    class SelectSelectorConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class SelectSelector:
        def __init__(self, cfg):
            self.cfg = cfg

    def Required(key, default=None):
        return key

    def Optional(key, default=None):
        return key

    class Schema:
        def __init__(self, value):
            self.value = value

    config_entries.ConfigFlow = ConfigFlow
    config_entries.ConfigEntry = object
    config_entries.ConfigFlowResult = dict
    config_entries.OptionsFlow = OptionsFlow
    config_entries.AbortFlow = AbortFlow
    core.callback = callback
    selector.EntitySelectorConfig = EntitySelectorConfig
    selector.EntitySelector = EntitySelector
    selector.NumberSelectorConfig = NumberSelectorConfig
    selector.NumberSelector = NumberSelector
    selector.SelectSelectorConfig = SelectSelectorConfig
    selector.SelectSelector = SelectSelector
    const.CONF_LATITUDE = "latitude"
    const.CONF_LONGITUDE = "longitude"
    voluptuous.Required = Required
    voluptuous.Optional = Optional
    voluptuous.Schema = Schema

    sys.modules["homeassistant"] = ha
    sys.modules["homeassistant.config_entries"] = config_entries
    sys.modules["homeassistant.core"] = core
    sys.modules["homeassistant.helpers"] = helpers
    sys.modules["homeassistant.helpers.selector"] = selector
    sys.modules["homeassistant.const"] = const
    sys.modules["voluptuous"] = voluptuous


def _load_config_flow_module():
    """Load config_flow.py directly with stubs."""
    _install_stubs()

    const_module = ModuleType("custom_components.qld_fuel.const")
    const_module.DOMAIN = "qld_fuel"
    const_module.TOKEN = "subscriber_token"
    const_module.RADIUS = "radius"
    const_module.FUEL_TYPES = "fuel_types"
    const_module.FUEL_TYPES_OPTIONS = [{"value": "12", "label": "E10"}]
    const_module.SCAN_INTERVAL = "scan_interval"
    const_module.LOCATION_ENTITY = "location_entity"
    const_module.ZONE = "zone"
    sys.modules["custom_components.qld_fuel.const"] = const_module

    coordinator_module = ModuleType("custom_components.qld_fuel.coordinator")

    class QldFuelAuthError(Exception):
        pass

    class QldFuelConnectionError(Exception):
        pass

    async def async_validate_token(_hass, token):
        if token == "bad":
            raise QldFuelAuthError("bad token")
        if token == "offline":
            raise QldFuelConnectionError("offline")
        return None

    coordinator_module.QldFuelAuthError = QldFuelAuthError
    coordinator_module.QldFuelConnectionError = QldFuelConnectionError
    coordinator_module.async_validate_token = async_validate_token
    sys.modules["custom_components.qld_fuel.coordinator"] = coordinator_module

    package = ModuleType("custom_components.qld_fuel")
    package.__path__ = []
    sys.modules["custom_components.qld_fuel"] = package

    path = Path(__file__).resolve().parents[3] / "custom_components" / "qld_fuel" / "config_flow.py"
    spec = importlib.util.spec_from_file_location(
        "custom_components.qld_fuel.config_flow",
        str(path),
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["custom_components.qld_fuel.config_flow"] = module
    spec.loader.exec_module(module)
    return module


class _States:
    def __init__(self, values):
        self._values = values

    def get(self, entity_id):
        return self._values.get(entity_id)


def _state(name: str, lat: float | None, lon: float | None):
    return SimpleNamespace(name=name, attributes={"latitude": lat, "longitude": lon})


def test_user_step_creates_entry_when_token_valid():
    """User step creates entry when location and token validate."""
    module = _load_config_flow_module()
    module.QldFuelConfigFlow._configured_ids.clear()
    flow = module.QldFuelConfigFlow()
    flow.hass = SimpleNamespace(states=_States({"zone.home": _state("Home", -27.5, 153.0)}))
    flow._entries = []

    result = asyncio.run(
        flow.async_step_user(
            {
                "subscriber_token": "good",
                "zone": "zone.home",
                "radius": 5,
                "fuel_types": ["12"],
                "scan_interval": 6,
            }
        )
    )

    assert result["type"] == "create_entry"
    assert result["title"] == "Fuel near Home"
    assert result["data"]["is_master"] is True


def test_user_step_shows_invalid_auth_error():
    """Invalid token returns invalid_auth on the form."""
    module = _load_config_flow_module()
    module.QldFuelConfigFlow._configured_ids.clear()
    flow = module.QldFuelConfigFlow()
    flow.hass = SimpleNamespace(states=_States({"zone.home": _state("Home", -27.5, 153.0)}))
    flow._entries = []

    result = asyncio.run(
        flow.async_step_user(
            {
                "subscriber_token": "bad",
                "zone": "zone.home",
                "radius": 5,
                "fuel_types": ["12"],
                "scan_interval": 6,
            }
        )
    )

    assert result["type"] == "form"
    assert result["step_id"] == "user"
    assert result["errors"]["base"] == "invalid_auth"


def test_user_step_reports_zone_not_found():
    """Missing zone entity reports zone_not_found."""
    module = _load_config_flow_module()
    module.QldFuelConfigFlow._configured_ids.clear()
    flow = module.QldFuelConfigFlow()
    flow.hass = SimpleNamespace(states=_States({}))
    flow._entries = []

    result = asyncio.run(
        flow.async_step_user(
            {
                "subscriber_token": "good",
                "zone": "zone.missing",
                "radius": 5,
                "fuel_types": ["12"],
                "scan_interval": 6,
            }
        )
    )

    assert result["type"] == "form"
    assert result["step_id"] == "user"
    assert result["errors"]["zone"] == "zone_not_found"


def test_user_step_aborts_when_unique_location_already_configured():
    """Second flow with same location unique id aborts as already configured."""
    module = _load_config_flow_module()
    module.QldFuelConfigFlow._configured_ids.clear()
    flow1 = module.QldFuelConfigFlow()
    flow1.hass = SimpleNamespace(states=_States({"zone.home": _state("Home", -27.5, 153.0)}))
    flow1._entries = []
    asyncio.run(
        flow1.async_step_user(
            {
                "subscriber_token": "good",
                "zone": "zone.home",
                "radius": 5,
                "fuel_types": ["12"],
                "scan_interval": 6,
            }
        )
    )

    flow2 = module.QldFuelConfigFlow()
    flow2.hass = SimpleNamespace(states=_States({"zone.home": _state("Home", -27.5, 153.0)}))
    flow2._entries = []

    abort_cls = sys.modules["homeassistant.config_entries"].AbortFlow
    try:
        asyncio.run(
            flow2.async_step_user(
                {
                    "subscriber_token": "good",
                    "zone": "zone.home",
                    "radius": 5,
                    "fuel_types": ["12"],
                    "scan_interval": 6,
                }
            )
        )
    except abort_cls as err:
        assert "already_configured" in str(err)
    else:
        raise AssertionError("Expected flow to abort for duplicate unique ID")


def test_coords_from_state_handles_missing_and_invalid_values():
    module = _load_config_flow_module()
    assert module.QldFuelConfigFlow._coords_from_state(None) == (None, None)
    assert module.QldFuelConfigFlow._coords_from_state(SimpleNamespace(attributes={})) == (
        None,
        None,
    )
    bad_state = SimpleNamespace(attributes={"latitude": "x", "longitude": 153.0})
    assert module.QldFuelConfigFlow._coords_from_state(bad_state) == (None, None)
    good_state = SimpleNamespace(attributes={"latitude": "-27.5", "longitude": "153.0"})
    assert module.QldFuelConfigFlow._coords_from_state(good_state) == (-27.5, 153.0)


def test_build_location_unique_id_prefers_location_then_zone_then_coords():
    module = _load_config_flow_module()
    flow = module.QldFuelConfigFlow()
    assert flow._build_location_unique_id({"location_entity": "person.test"}, -27.5, 153.0) == (
        "location:person.test"
    )
    assert flow._build_location_unique_id({"zone": "zone.home"}, -27.5, 153.0) == "zone:zone.home"
    assert flow._build_location_unique_id({}, -27.5, 153.0) == "coords:-27.500000,153.000000"


def test_resolve_location_reports_location_missing_then_zone_missing():
    module = _load_config_flow_module()
    flow = module.QldFuelConfigFlow()
    flow.hass = SimpleNamespace(states=_States({}))
    errors = {}
    lat, lon, name = flow._resolve_location(
        {"location_entity": "person.missing", "zone": "zone.missing"}, errors
    )
    assert (lat, lon, name) == (None, None, None)
    assert errors["location_entity"] == "location_entity_not_found"
    assert errors["zone"] == "zone_not_found"


def test_user_step_uses_master_token_when_master_exists():
    module = _load_config_flow_module()
    module.QldFuelConfigFlow._configured_ids.clear()
    master_entry = SimpleNamespace(data={"is_master": True, "subscriber_token": "shared"})
    flow = module.QldFuelConfigFlow()
    flow.hass = SimpleNamespace(states=_States({"zone.home": _state("Home", -27.5, 153.0)}))
    flow._entries = [master_entry]

    result = asyncio.run(
        flow.async_step_user(
            {
                "zone": "zone.home",
                "radius": 5,
                "fuel_types": ["12"],
                "scan_interval": 6,
            }
        )
    )

    assert result["type"] == "create_entry"
    assert result["data"]["is_master"] is False
    assert result["data"]["subscriber_token"] == "shared"


def test_user_step_shows_cannot_connect_error():
    module = _load_config_flow_module()
    module.QldFuelConfigFlow._configured_ids.clear()
    flow = module.QldFuelConfigFlow()
    flow.hass = SimpleNamespace(states=_States({"zone.home": _state("Home", -27.5, 153.0)}))
    flow._entries = []

    result = asyncio.run(
        flow.async_step_user(
            {
                "subscriber_token": "offline",
                "zone": "zone.home",
                "radius": 5,
                "fuel_types": ["12"],
                "scan_interval": 6,
            }
        )
    )

    assert result["type"] == "form"
    assert result["errors"]["base"] == "cannot_connect"


def test_reauth_confirm_invalid_auth_and_cannot_connect():
    module = _load_config_flow_module()
    flow = module.QldFuelConfigFlow()
    flow.hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_get_entry=lambda _entry_id: None),
    )
    flow.context = {"entry_id": "entry-1"}

    bad = asyncio.run(flow.async_step_reauth_confirm({"subscriber_token": "bad"}))
    assert bad["type"] == "form"
    assert bad["errors"]["base"] == "invalid_auth"

    offline = asyncio.run(flow.async_step_reauth_confirm({"subscriber_token": "offline"}))
    assert offline["type"] == "form"
    assert offline["errors"]["base"] == "cannot_connect"


def test_reauth_confirm_updates_entry_when_present():
    module = _load_config_flow_module()
    entry = SimpleNamespace(data={"subscriber_token": "old"})
    calls = []

    def _update_entry(updated_entry, data):
        calls.append((updated_entry, data))

    flow = module.QldFuelConfigFlow()
    flow.hass = SimpleNamespace(
        config_entries=SimpleNamespace(
            async_get_entry=lambda _entry_id: entry,
            async_update_entry=_update_entry,
        ),
    )
    flow.context = {"entry_id": "entry-1"}

    result = asyncio.run(flow.async_step_reauth_confirm({"subscriber_token": "good"}))
    assert result["type"] == "abort"
    assert result["reason"] == "reauth_successful"
    assert calls
    assert calls[0][1]["subscriber_token"] == "good"


def test_reconfigure_updates_data_and_preserves_non_master_token():
    module = _load_config_flow_module()
    entry = SimpleNamespace(
        data={"is_master": False, "subscriber_token": "child-token"},
        options={},
        title="Old title",
    )
    master = SimpleNamespace(data={"is_master": True, "subscriber_token": "master-token"})
    flow = module.QldFuelConfigFlow()
    flow.context = {"entry_id": "entry-2"}
    flow.hass = SimpleNamespace(
        states=_States({"zone.home": _state("Home", -27.6, 153.1)}),
        config_entries=SimpleNamespace(async_get_entry=lambda _entry_id: entry),
    )
    flow._entries = [master, entry]

    result = asyncio.run(
        flow.async_step_reconfigure(
            {
                "zone": "zone.home",
                "radius": 3,
                "fuel_types": ["12"],
                "scan_interval": 2,
            }
        )
    )

    assert result["type"] == "abort"
    assert entry.data["subscriber_token"] == "master-token"
    assert entry.data["is_master"] is False
    assert entry.data["latitude"] == -27.6
    assert entry.title == "Fuel near Home"


def test_options_flow_init_error_and_success_paths():
    module = _load_config_flow_module()
    config_entry = SimpleNamespace(
        data={"zone": "zone.home", "radius": 5, "fuel_types": ["12"], "scan_interval": 6},
        options={},
    )
    flow = module.QldFuelOptionsFlowHandler(config_entry)
    flow.hass = SimpleNamespace(states=_States({}))

    missing = asyncio.run(
        flow.async_step_init(
            {
                "zone": "zone.missing",
                "radius": 5,
                "fuel_types": ["12"],
                "scan_interval": 6,
            }
        )
    )
    assert missing["type"] == "form"
    assert missing["errors"]["zone"] == "zone_not_found"

    flow.hass = SimpleNamespace(states=_States({"zone.home": _state("Home", -27.5, 153.0)}))
    ok = asyncio.run(
        flow.async_step_init(
            {
                "zone": "zone.home",
                "radius": 5,
                "fuel_types": ["12"],
                "scan_interval": 6,
            }
        )
    )
    assert ok["type"] == "create_entry"
    assert ok["data"]["latitude"] == -27.5


def test_async_get_options_flow_and_reauth_step():
    module = _load_config_flow_module()
    entry = SimpleNamespace()
    options_flow = module.QldFuelConfigFlow.async_get_options_flow(entry)
    assert isinstance(options_flow, module.QldFuelOptionsFlowHandler)

    flow = module.QldFuelConfigFlow()
    called = []

    async def _reauth_confirm():
        called.append(True)
        return {"type": "form", "step_id": "reauth_confirm"}

    flow.async_step_reauth_confirm = _reauth_confirm
    result = asyncio.run(flow.async_step_reauth({"subscriber_token": "x"}))
    assert result["step_id"] == "reauth_confirm"
    assert flow.context["entry_id"] == "entry-1"
    assert called


def test_resolve_location_handles_missing_location_coordinates():
    module = _load_config_flow_module()
    flow = module.QldFuelConfigFlow()
    flow.hass = SimpleNamespace(
        states=_States(
            {
                "person.test": _state("Tracker", None, 153.0),
                "zone.home": _state("Home", -27.5, 153.0),
            }
        )
    )
    errors = {}
    lat, lon, name = flow._resolve_location(
        {"location_entity": "person.test", "zone": "zone.home"},
        errors,
    )
    assert (lat, lon, name) == (-27.5, 153.0, "Home")
    assert errors["location_entity"] == "location_entity_missing_coordinates"


def test_resolve_location_rejects_zone_without_coordinates():
    module = _load_config_flow_module()
    flow = module.QldFuelConfigFlow()
    flow.hass = SimpleNamespace(states=_States({"zone.home": _state("Home", None, None)}))
    errors = {}
    lat, lon, name = flow._resolve_location({"zone": "zone.home"}, errors)
    assert (lat, lon, name) == (None, None, None)
    assert errors["zone"] == "zone_not_found"


def test_reconfigure_form_for_master_with_existing_location_entity():
    module = _load_config_flow_module()
    entry = SimpleNamespace(
        data={"is_master": True, "subscriber_token": "token", "location_entity": "person.a"},
        options={"location_entity": "person.a", "zone": "zone.home"},
        title="Fuel near Home",
    )
    flow = module.QldFuelConfigFlow()
    flow.context = {"entry_id": "entry-1"}
    flow.hass = SimpleNamespace(config_entries=SimpleNamespace(async_get_entry=lambda _entry_id: entry))
    flow._entries = [entry]
    result = asyncio.run(flow.async_step_reconfigure(None))
    assert result["type"] == "form"
    assert result["step_id"] == "reconfigure"


def test_options_flow_coords_and_resolve_location_branches():
    module = _load_config_flow_module()
    entry = SimpleNamespace(data={"zone": "zone.home"}, options={})
    flow = module.QldFuelOptionsFlowHandler(entry)
    assert flow._coords_from_state(None) == (None, None)
    assert flow._coords_from_state(SimpleNamespace(attributes={})) == (None, None)
    assert flow._coords_from_state(SimpleNamespace(attributes={"latitude": "x", "longitude": 1})) == (
        None,
        None,
    )
    flow.hass = SimpleNamespace(
        states=_States(
            {
                "person.bad": _state("Bad", None, None),
                "zone.bad": _state("BadZone", None, None),
            }
        )
    )
    errors = {}
    assert flow._resolve_location({"location_entity": "person.bad", "zone": "zone.bad"}, errors) == (
        None,
        None,
    )
    assert errors["location_entity"] == "location_entity_missing_coordinates"
    assert errors["zone"] == "zone_not_found"


def test_resolve_location_returns_location_entity_coordinates_when_valid():
    module = _load_config_flow_module()
    flow = module.QldFuelConfigFlow()
    flow.hass = SimpleNamespace(
        states=_States(
            {
                "person.good": _state("Tracker", -27.51, 153.01),
                "zone.home": _state("Home", -27.5, 153.0),
            }
        )
    )
    errors = {}
    lat, lon, name = flow._resolve_location(
        {"location_entity": "person.good", "zone": "zone.home"},
        errors,
    )
    assert (lat, lon, name) == (-27.51, 153.01, "Tracker")
    assert errors == {}


def test_options_flow_resolve_location_success_and_location_missing():
    module = _load_config_flow_module()
    entry = SimpleNamespace(data={"zone": "zone.home"}, options={})
    flow = module.QldFuelOptionsFlowHandler(entry)
    flow.hass = SimpleNamespace(states=_States({"person.good": _state("Tracker", -27.5, 153.0)}))
    errors = {}
    assert flow._resolve_location({"location_entity": "person.good", "zone": "zone.missing"}, errors) == (
        -27.5,
        153.0,
    )
    errors = {}
    assert flow._resolve_location({"location_entity": "person.missing", "zone": "zone.missing"}, errors) == (
        None,
        None,
    )
    assert errors["location_entity"] == "location_entity_not_found"
