from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.config_entries import ConfigEntry
from .const import DOMAIN, PLATFORMS
from .coordinator import QldFuelDataUpdateCoordinator
from .sensor import _RESERVED_DOMAIN_KEYS


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up QLD Fuel from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    coordinator = QldFuelDataUpdateCoordinator(hass, entry)

    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][entry.entry_id] = coordinator

    if entry.data.get("is_master") or "master_entry_id" not in hass.data[DOMAIN]:
        hass.data[DOMAIN]["master_entry_id"] = entry.entry_id

    if not hass.services.has_service(DOMAIN, "refresh_prices"):
        async def handle_manual_refresh(call: ServiceCall):
            for coord in hass.data[DOMAIN].values():
                if isinstance(coord, QldFuelDataUpdateCoordinator):
                    await coord.async_request_refresh()

        hass.services.async_register(DOMAIN, "refresh_prices", handle_manual_refresh)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

        if hass.data[DOMAIN].get("master_entry_id") == entry.entry_id:
            remaining = [
                k for k in hass.data[DOMAIN]
                if k not in _RESERVED_DOMAIN_KEYS
            ]
            if remaining:
                next_master = remaining[0]
                hass.data[DOMAIN]["master_entry_id"] = next_master
                coord = hass.data[DOMAIN].get(next_master)
                if isinstance(coord, QldFuelDataUpdateCoordinator):
                    hass.config_entries.async_update_entry(
                        coord.entry,
                        data={**coord.entry.data, "is_master": True},
                    )
            else:
                hass.data.pop(DOMAIN)
                if hass.services.has_service(DOMAIN, "refresh_prices"):
                    hass.services.async_remove(DOMAIN, "refresh_prices")

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)