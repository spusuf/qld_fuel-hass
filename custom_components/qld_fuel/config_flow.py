import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE

from .const import DOMAIN, TOKEN, RADIUS, FUEL_TYPES, FUEL_TYPES_OPTIONS, SCAN_INTERVAL


class QldFuelConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return the options flow handler."""
        return QldFuelOptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input=None):
        """Handle the initial setup of an instance."""
        entries = self._async_current_entries()
        master_entry = next((e for e in entries if e.data.get("is_master")), None)
        errors = {}

        if user_input is not None:
            zone_id = user_input.get("zone")
            state = self.hass.states.get(zone_id)

            if not state:
                errors["zone"] = "zone_not_found"
            else:
                user_input["is_master"] = not bool(master_entry)

                if master_entry:
                    user_input[TOKEN] = master_entry.data.get(TOKEN)

                user_input[CONF_LATITUDE] = state.attributes.get("latitude")
                user_input[CONF_LONGITUDE] = state.attributes.get("longitude")

                title = f"Fuel near {state.name}"
                return self.async_create_entry(title=title, data=user_input)

        fields = {}
        if not master_entry:
            fields[vol.Required(TOKEN)] = str

        fields[vol.Required("zone", default="zone.home")] = selector.EntitySelector(
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

    async def async_step_reconfigure(self, user_input=None):
        """Handle reconfiguration of an existing entry."""
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        entries = self._async_current_entries()
        master_entry = next((e for e in entries if e.data.get("is_master")), None)
        is_master = entry and entry.data.get("is_master", False)
        errors = {}

        if user_input is not None:
            zone_id = user_input.get("zone")
            state = self.hass.states.get(zone_id)

            if not state:
                errors["zone"] = "zone_not_found"
            else:
                updates = dict(user_input)
                updates["is_master"] = is_master
                if not is_master and master_entry:
                    updates[TOKEN] = master_entry.data.get(TOKEN)

                updates[CONF_LATITUDE] = state.attributes.get("latitude")
                updates[CONF_LONGITUDE] = state.attributes.get("longitude")

                return self.async_update_reload_and_abort(
                    entry,
                    title=f"Fuel near {state.name}",
                    data=updates,
                )

        data = entry.data if entry else {}
        options = entry.options if entry else {}

        fields = {}
        if is_master:
            fields[vol.Required(TOKEN, default=data.get(TOKEN, ""))] = str

        current_zone = options.get("zone", data.get("zone", "zone.home"))
        fields[vol.Required("zone", default=current_zone)] = selector.EntitySelector(
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

    async def async_step_init(self, user_input=None):
        """Manage zone, radius, fuel type and scan interval options."""
        errors = {}

        if user_input is not None:
            zone_id = user_input.get("zone")
            state = self.hass.states.get(zone_id)

            if not state:
                errors["zone"] = "zone_not_found"
            else:
                user_input[CONF_LATITUDE] = state.attributes.get("latitude")
                user_input[CONF_LONGITUDE] = state.attributes.get("longitude")
                return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        data = self.config_entry.data

        return self.async_show_form(
            step_id="init",
            errors=errors,
            data_schema=vol.Schema({
                vol.Required("zone", default=options.get("zone", data.get("zone", "zone.home"))): selector.EntitySelector(
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