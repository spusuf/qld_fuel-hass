"""Config flow tests for qld_fuel."""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace


def _install_stubs() -> None:
    """Install minimal stubs needed to import config_flow."""
    if "homeassistant" in sys.modules:
        return

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
        return None

    coordinator_module.QldFuelAuthError = QldFuelAuthError
    coordinator_module.QldFuelConnectionError = QldFuelConnectionError
    coordinator_module.async_validate_token = async_validate_token
    sys.modules["custom_components.qld_fuel.coordinator"] = coordinator_module

    package = ModuleType("custom_components.qld_fuel")
    package.__path__ = []
    sys.modules["custom_components.qld_fuel"] = package

    path = Path("C:/Cursor IDE/qld_fuel-hass/custom_components/qld_fuel/config_flow.py")
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
