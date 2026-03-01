from datetime import timedelta
import logging

from homeassistant.components.recorder import history, get_instance
from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN, FUEL_TYPES, FUEL_TYPES_OPTIONS

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the fuel sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []
    chosen_fuels = entry.data.get(FUEL_TYPES, [])
    
    _LOGGER.debug(f"Setting up sensors. Chosen fuels: {chosen_fuels}")
    
    registry = er.async_get(hass)
    existing_entries = er.async_entries_for_config_entry(registry, entry.entry_id)
    valid_unique_ids = set()

    sites_data = coordinator.data.get("sites", {})

    for site_id, site_data in sites_data.items():
        if not site_data.get("prices"):
            continue
        for price_info in site_data["prices"]:
            f_id = str(price_info.get("FuelId"))
            if f_id in chosen_fuels:
                unique_id = f"{site_id}_{f_id}"
                valid_unique_ids.add(unique_id)
                entities.append(FuelPriceSensor(coordinator, site_id, f_id))
    
    for f_id in chosen_fuels:
        # Cheapest QLD
        entities.append(QldFuelBestPriceSensor(coordinator, f_id, "global"))
        valid_unique_ids.add(f"best_price_global_{f_id}")
        
        # Cheapest Local
        entities.append(QldFuelBestPriceSensor(coordinator, f_id, "local"))
        valid_unique_ids.add(f"best_price_local_{f_id}")

    # Remove entities that are no longer valid (e.g. outside new radius)
    for entity_entry in existing_entries:
        if entity_entry.unique_id not in valid_unique_ids:
            _LOGGER.debug(f"Removing old entity: {entity_entry.entity_id}")
            registry.async_remove(entity_entry.entity_id)

    # Clean up orphaned devices
    from homeassistant.helpers import device_registry as dr
    device_registry = dr.async_get(hass)
    devices = dr.async_entries_for_config_entry(device_registry, entry.entry_id)
    for device in devices:
        device_entities = er.async_entries_for_device(registry, device.id, include_disabled_entities=True)
        if not device_entities:
            _LOGGER.debug(f"Removing orphaned device: {device.name}")
            device_registry.async_remove_device(device.id)
    
    _LOGGER.debug(f"Adding {len(entities)} fuel price sensors")
    async_add_entities(entities)

class QldFuelBestPriceSensor(CoordinatorEntity, SensorEntity):
    """Sensor for reporting best prices (Global or Local)."""
    
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "¢/L"

    def __init__(self, coordinator, fuel_id, scope):
        super().__init__(coordinator)
        self.fuel_id = fuel_id
        self.scope = scope
        
        fuel_info = next((f for f in FUEL_TYPES_OPTIONS if f["value"] == fuel_id), {"label": fuel_id})
        scope_label = "QLD" if scope == "global" else "Local"
        
        self._attr_name = f"Best {fuel_info['label']} ({scope_label})"
        self._attr_unique_id = f"best_price_{scope}_{fuel_id}"
        self._attr_icon = "mdi:star-circle"
        
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"best_{scope}")},
            "name": f"Best Prices {scope_label}",
            "manufacturer": "QLD Government",
        }

    @property
    def native_value(self):
        data_key = "global_cheapest" if self.scope == "global" else "local_cheapest"
        data = self.coordinator.data.get(data_key, {}).get(self.fuel_id)
        if data:
            return data.get("price")
        return None

    @property
    def extra_state_attributes(self):
        data_key = "global_cheapest" if self.scope == "global" else "local_cheapest"
        data = self.coordinator.data.get(data_key, {}).get(self.fuel_id)
        if data:
            return {
                "station_name": data.get("name"),
                "address": f"{data.get('address')} {data.get('postcode')}"
            }
        return {}

class FuelPriceSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Fuel Price Sensor with historical attributes."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "¢/L"

    def __init__(self, coordinator, site_id, fuel_id):
        super().__init__(coordinator)
        self.site_id = site_id
        self.fuel_id = fuel_id
        self._attr_icon = "mdi:gas-station"
        
        self._14d_low = None
        self._14d_low_days = None
        self._14d_avg = None
        self._7d_low = None
        self._7d_low_days = None
        self._7d_avg = None

        fuel_info = next((f for f in FUEL_TYPES_OPTIONS if f["value"] == fuel_id), {"label": fuel_id})
        site = coordinator.data.get("sites", {}).get(site_id)
        site_name = site['name'] if site else "Unknown"
        
        self._attr_name = f"{site_name} {fuel_info['label']}"
        self._attr_unique_id = f"{fuel_id}_{site_id}"
        
        self._attr_device_info = {
            "identifiers": {(DOMAIN, site_id)},
            "name": site_name,
            "manufacturer": "QLD Government",
        }

    @property
    def native_value(self):
        """Return the current price from coordinator data."""
        site_data = self.coordinator.data.get("sites", {}).get(self.site_id, {})
        for p in site_data.get("prices", []):
            if str(p.get("FuelId")) == self.fuel_id:
                return p.get("Price")
        
        return None

    @property
    def available(self) -> bool:
        """Available only if price is within feasible range (not 0 or 999)."""
        val = self.native_value
        return val is not None and 0 < val < 9990

    async def async_added_to_hass(self):
        """Handle entity which is about to be added to Hass."""
        await super().async_added_to_hass()
        await self._update_history()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update history stats whenever coordinator gets new data."""
        self.hass.async_create_task(self._update_history())
        super()._handle_coordinator_update()

    async def _update_history(self):
        """Query the recorder for historical lows and averages."""
        now = dt_util.utcnow()
        start_time = now - timedelta(days=14)
        
        if not self.hass.is_stopping:
            try:
                state_history = await get_instance(self.hass).async_add_executor_job(
                    history.get_significant_states, self.hass, start_time, None, [self.entity_id]
                )
            except (AttributeError, ValueError):
                return
            
            if self.entity_id in state_history:
                valid_points = []
                for s in state_history[self.entity_id]:
                    if s.state in ("unknown", "unavailable", "", None):
                        continue
                    try:
                        val = float(s.state)
                        valid_points.append((val, s.last_changed))
                    except ValueError:
                        continue

                if valid_points:
                    min_price, min_time = min(valid_points, key=lambda x: x[0])
                    self._14d_low = min_price
                    self._14d_low_days = (now - min_time).days
                    
                    prices_14d = [p[0] for p in valid_points]
                    self._14d_avg = round(sum(prices_14d) / len(prices_14d), 1)

                    seven_days_ago = now - timedelta(days=7)
                    recent_points_with_time = [p for p in valid_points if p[1] > seven_days_ago]
                    
                    if recent_points_with_time:
                        prices_7d = [p[0] for p in recent_points_with_time]
                        self._7d_avg = round(sum(prices_7d) / len(prices_7d), 1)
                        
                        min_7d_price, min_7d_time = min(recent_points_with_time, key=lambda x: x[0])
                        self._7d_low = min_7d_price
                        self._7d_low_days = (now - min_7d_time).days
        
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self):
        """Attributes for advanced price comparison."""
        site = self.coordinator.data.get("sites", {}).get(self.site_id, {})
        current_price = self.native_value
        if current_price is None:
            current_price = 0
        else:
            current_price = float(current_price)
        
        # Cross-integration comparison
        all_fuel_entities = self.hass.states.async_all("sensor")
        same_fuel_prices = []
        for s in all_fuel_entities:
            if s.state not in ("unknown", "unavailable"):
                try:
                    price = float(s.state)
                    if s.attributes.get("fuel_id") == self.fuel_id and s.entity_id != self.entity_id:
                         same_fuel_prices.append(price)
                except ValueError:
                    continue
        defined_delta = round(current_price - min(same_fuel_prices), 1) if same_fuel_prices else 0

        stats = site.get("stats", {}).get(self.fuel_id, {})

        attributes = {
            "difference_to_qld_cheapest": stats.get("qld_delta", 0),
            "difference_to_region_cheapest": defined_delta,
            "address": f"{site.get('address')} {site.get('postcode')}",
            "distance": f"{site.get('distance')} km",
            "fuel_id": self.fuel_id
        }

        if self._7d_low:
            attributes["7_day_low"] = f"{self._7d_low} ¢/L"
            attributes["7_day_low_difference"] = f"{round(current_price - self._7d_low, 1)} ¢/L"
        
        if self._14d_low:
            attributes["14_day_low"] = f"{self._14d_low} ¢/L"
            attributes["14_day_low_difference"] = f"{round(current_price - self._14d_low, 1)} ¢/L"
            
        if self._7d_avg:
            attributes["7_day_average"] = f"{self._7d_avg} ¢/L"
            attributes["difference_to_7_day_average"] = f"{round(current_price - self._7d_avg, 1)} ¢/L"
            
        if self._14d_avg:
            attributes["14_day_average"] = f"{self._14d_avg} ¢/L"
            attributes["difference_to_14_day_average"] = f"{round(current_price - self._14d_avg, 1)} ¢/L"

        if self._7d_low_days is not None:
             attributes["days_since_7_day_low"] = f"{self._7d_low_days} days"
        if self._14d_low_days is not None:
            attributes["days_since_14_day_low"] = f"{self._14d_low_days} days"

        return attributes