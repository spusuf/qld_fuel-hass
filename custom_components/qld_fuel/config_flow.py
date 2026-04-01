import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE

from .const import (
    DOMAIN,
    TOKEN,
    RADIUS,
    FUEL_TYPES,
    FUEL_TYPES_OPTIONS,
    SCAN_INTERVAL,
    LOCATION_ENTITY,
    ZONE,
)
from .coordinator import async_validate_token, QldFuelAuthError, QldFuelConnectionError


class QldFuelConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return the options flow handler."""
        return QldFuelOptionsFlowHandler(config_entry)

    @staticmethod
    def _coords_from_state(state):
        """Extract latitude/longitude from a state object."""
        if not state:
            return None, None

        lat = state.attributes.get("latitude")
        lon = state.attributes.get("longitude")
        if lat is None or lon is None:
            return None, None

        try:
            return float(lat), float(lon)
        except (TypeError, ValueError):
            return None, None

    def _resolve_location(self, user_input, errors):
        """Resolve coordinates from location entity first, then zone."""
        location_entity_id = user_input.get(LOCATION_ENTITY)
        if location_entity_id:
            location_state = self.hass.states.get(location_entity_id)
            if not location_state:
                errors[LOCATION_ENTITY] = "location_entity_not_found"
            else:
                lat, lon = self._coords_from_state(location_state)
                if lat is not None and lon is not None:
                    return lat, lon, location_state.name
                errors[LOCATION_ENTITY] = "location_entity_missing_coordinates"

        zone_id = user_input.get(ZONE)
        zone_state = self.hass.states.get(zone_id)
        if not zone_state:
            errors[ZONE] = "zone_not_found"
            return None, None, None

        lat, lon = self._coords_from_state(zone_state)
        if lat is None or lon is None:
            errors[ZONE] = "zone_not_found"
            return None, None, None

        return lat, lon, zone_state.name

    @staticmethod
    def _build_location_unique_id(user_input, lat, lon):
        """Build a stable unique ID for this configured location."""
        location_entity_id = user_input.get(LOCATION_ENTITY)
        if location_entity_id:
            return f"location:{location_entity_id}"

        zone_id = user_input.get(ZONE)
        if zone_id:
            return f"zone:{zone_id}"

        return f"coords:{lat:.6f},{lon:.6f}"

    async def async_step_user(self, user_input=None):
        """Handle the initial setup of an instance."""
        entries = self._async_current_entries()
        master_entry = next((e for e in entries if e.data.get("is_master")), None)
        errors = {}

        if user_input is not None:
            lat, lon, location_name = self._resolve_location(user_input, errors)
            if lat is not None and lon is not None:
                await self.async_set_unique_id(self._build_location_unique_id(user_input, lat, lon))
                self._abort_if_unique_id_configured()
                user_input["is_master"] = not bool(master_entry)

                if master_entry:
                    user_input[TOKEN] = master_entry.data.get(TOKEN)
                else:
                    try:
                        await async_validate_token(self.hass, user_input.get(TOKEN))
                    except QldFuelAuthError:
                        errors["base"] = "invalid_auth"
                    except QldFuelConnectionError:
                        errors["base"] = "cannot_connect"

                if not errors:
                    user_input[CONF_LATITUDE] = lat
                    user_input[CONF_LONGITUDE] = lon

                    title = f"Fuel near {location_name}"
                    return self.async_create_entry(title=title, data=user_input)

        fields = {}
        if not master_entry:
            fields[vol.Required(TOKEN)] = str

        fields[vol.Optional(LOCATION_ENTITY)] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["person", "device_tracker", "sensor"])
        )
        fields[vol.Required(ZONE, default="zone.home")] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain="zone")
        )
        fields[vol.Required(RADIUS, default=5)] = selector.NumberSelector(
            selector.NumberSelectorConfig(min=1, max=100, step=1, unit_of_measurement="km")
        )
        fields[vol.Required(FUEL_TYPES, default=["12", "5", "3"])] = selector.SelectSelector(
            selector.SelectSelectorConfig(options=FUEL_TYPES_OPTIONS, multiple=True)
        )
        fields[vol.Required(SCAN_INTERVAL, default=6)] = selector.NumberSelector(
            selector.NumberSelectorConfig(min=1, max=24, step=1, unit_of_measurement="hours")
        )

        return self.async_show_form(step_id="user", data_schema=vol.Schema(fields), errors=errors)

    async def async_step_reauth(self, entry_data):
        """Handle flow initiated by reauthentication."""
        self.context["entry_id"] = self._get_reauth_entry().entry_id
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        """Prompt for and validate a new subscriber token."""
        errors = {}
        if user_input is not None:
            token = user_input.get(TOKEN)
            try:
                await async_validate_token(self.hass, token)
            except QldFuelAuthError:
                errors["base"] = "invalid_auth"
            except QldFuelConnectionError:
                errors["base"] = "cannot_connect"
            else:
                entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
                if entry:
                    self.hass.config_entries.async_update_entry(
                        entry,
                        data={**entry.data, TOKEN: token},
                    )
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(TOKEN): str}),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input=None):
        """Handle reconfiguration of an existing entry."""
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        entries = self._async_current_entries()
        master_entry = next((e for e in entries if e.data.get("is_master")), None)
        is_master = entry and entry.data.get("is_master", False)
        errors = {}

        if user_input is not None:
            lat, lon, location_name = self._resolve_location(user_input, errors)
            if lat is not None and lon is not None:
                updates = dict(user_input)
                updates["is_master"] = is_master
                if not is_master and master_entry:
                    updates[TOKEN] = master_entry.data.get(TOKEN)

                updates[CONF_LATITUDE] = lat
                updates[CONF_LONGITUDE] = lon

                return self.async_update_reload_and_abort(
                    entry,
                    title=f"Fuel near {location_name}",
                    data=updates,
                )

        data = entry.data if entry else {}
        options = entry.options if entry else {}

        fields = {}
        if is_master:
            fields[vol.Required(TOKEN, default=data.get(TOKEN, ""))] = str

        current_location_entity = options.get(LOCATION_ENTITY, data.get(LOCATION_ENTITY))
        location_entity_key = vol.Optional(LOCATION_ENTITY)
        if current_location_entity:
            location_entity_key = vol.Optional(LOCATION_ENTITY, default=current_location_entity)
        fields[location_entity_key] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["person", "device_tracker", "sensor"])
        )
        current_zone = options.get(ZONE, data.get(ZONE, "zone.home"))
        fields[vol.Required(ZONE, default=current_zone)] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain="zone")
        )
        fields[vol.Required(RADIUS, default=options.get(RADIUS, data.get(RADIUS, 5)))] = selector.NumberSelector(
            selector.NumberSelectorConfig(min=1, max=100, step=1, unit_of_measurement="km")
        )
        fields[vol.Required(FUEL_TYPES, default=options.get(FUEL_TYPES, data.get(FUEL_TYPES, ["12", "5", "3"])))] = selector.SelectSelector(
            selector.SelectSelectorConfig(options=FUEL_TYPES_OPTIONS, multiple=True)
        )
        fields[vol.Required(SCAN_INTERVAL, default=options.get(SCAN_INTERVAL, data.get(SCAN_INTERVAL, 6)))] = selector.NumberSelector(
            selector.NumberSelectorConfig(min=1, max=24, step=1, unit_of_measurement="hours")
        )

        return self.async_show_form(step_id="reconfigure", data_schema=vol.Schema(fields), errors=errors)


class QldFuelOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for QLD Fuel."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    @staticmethod
    def _coords_from_state(state):
        """Extract latitude/longitude from a state object."""
        if not state:
            return None, None

        lat = state.attributes.get("latitude")
        lon = state.attributes.get("longitude")
        if lat is None or lon is None:
            return None, None

        try:
            return float(lat), float(lon)
        except (TypeError, ValueError):
            return None, None

    def _resolve_location(self, user_input, errors):
        """Resolve coordinates from location entity first, then zone."""
        location_entity_id = user_input.get(LOCATION_ENTITY)
        if location_entity_id:
            location_state = self.hass.states.get(location_entity_id)
            if not location_state:
                errors[LOCATION_ENTITY] = "location_entity_not_found"
            else:
                lat, lon = self._coords_from_state(location_state)
                if lat is not None and lon is not None:
                    return lat, lon
                errors[LOCATION_ENTITY] = "location_entity_missing_coordinates"

        zone_id = user_input.get(ZONE)
        zone_state = self.hass.states.get(zone_id)
        if not zone_state:
            errors[ZONE] = "zone_not_found"
            return None, None

        lat, lon = self._coords_from_state(zone_state)
        if lat is None or lon is None:
            errors[ZONE] = "zone_not_found"
            return None, None

        return lat, lon

    async def async_step_init(self, user_input=None):
        """Manage zone, radius, fuel type and scan interval options."""
        errors = {}

        if user_input is not None:
            lat, lon = self._resolve_location(user_input, errors)
            if lat is not None and lon is not None:
                user_input[CONF_LATITUDE] = lat
                user_input[CONF_LONGITUDE] = lon
                return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        data = self.config_entry.data

        return self.async_show_form(
            step_id="init",
            errors=errors,
            data_schema=vol.Schema({
                (
                    vol.Optional(LOCATION_ENTITY, default=options.get(LOCATION_ENTITY, data.get(LOCATION_ENTITY)))
                    if options.get(LOCATION_ENTITY, data.get(LOCATION_ENTITY))
                    else vol.Optional(LOCATION_ENTITY)
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["person", "device_tracker", "sensor"])
                ),
                vol.Required(ZONE, default=options.get(ZONE, data.get(ZONE, "zone.home"))): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="zone")
                ),
                vol.Required(RADIUS, default=options.get(RADIUS, data.get(RADIUS, 5))): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1, max=100, step=1, unit_of_measurement="km")
                ),
                vol.Required(FUEL_TYPES, default=options.get(FUEL_TYPES, data.get(FUEL_TYPES, ["12", "5", "3"]))): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=FUEL_TYPES_OPTIONS, multiple=True)
                ),
                vol.Required(SCAN_INTERVAL, default=options.get(SCAN_INTERVAL, data.get(SCAN_INTERVAL, 6))): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1, max=24, step=1, unit_of_measurement="hours")
                ),
            })
        )