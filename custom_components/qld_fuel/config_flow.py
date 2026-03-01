import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector
from .const import DOMAIN, TOKEN, RADIUS, FUEL_TYPES, FUEL_TYPES_OPTIONS, SCAN_INTERVAL

class QldFuelConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the Fuel Price API."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step where the user enters their token."""
        errors = {}

        if user_input is not None:
            return self.async_create_entry(
                title="QLD Fuel Price Service", 
                data=user_input
            )

        data_schema = vol.Schema({
            vol.Required(TOKEN): str,
            vol.Required(RADIUS, default=5): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=100,
                    step=1,
                    unit_of_measurement="km",
                    mode="box",
                )
            ),
            vol.Required(FUEL_TYPES, default=["12", "5", "3"]): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=FUEL_TYPES_OPTIONS,
                    multiple=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(SCAN_INTERVAL, default=6): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=24,
                    step=1,
                    unit_of_measurement="hours",
                    mode="box",
                )
            ),
        })

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input=None):
        """Handle reconfiguration."""
        errors = {}
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])

        if user_input is not None:
            new_data = entry.data.copy()
            new_data.update(user_input)
            return self.async_update_reload_and_abort(entry, data=new_data)

        data_schema = vol.Schema({
            vol.Required(RADIUS, default=entry.data.get(RADIUS, 5)): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=100,
                    step=1,
                    unit_of_measurement="km",
                    mode="box",
                )
            ),
            vol.Required(FUEL_TYPES, default=entry.data.get(FUEL_TYPES, ["12", "5", "3"])): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=FUEL_TYPES_OPTIONS,
                    multiple=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(SCAN_INTERVAL, default=entry.data.get(SCAN_INTERVAL, 6)): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=24,
                    step=1,
                    unit_of_measurement="hours",
                    mode="box",
                )
            ),
        })

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=data_schema,
            errors=errors,
        )