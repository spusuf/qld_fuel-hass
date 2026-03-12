from datetime import timedelta
import logging

from homeassistant.components.recorder import history, get_instance
from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util
from homeassistant.util.location import distance

from .const import DOMAIN, FUEL_TYPES, FUEL_TYPES_OPTIONS

_LOGGER = logging.getLogger(__name__)

_RESERVED_DOMAIN_KEYS = {"raw_data", "last_fetch_time", "fetch_lock", "master_entry_id"}


def get_fuel_data(data_dict, f_id):
    """Helper to find fuel data by string fuel ID."""
    if not data_dict:
        return None
    return data_dict.get(str(f_id))


def _find_all_tracked_best(hass, fuel_id):
    """Return the cheapest local price and its station data across all tracked zones."""
    best_price = None
    best_station = None
    for key, coord in hass.data.get(DOMAIN, {}).items():
        if key in _RESERVED_DOMAIN_KEYS:
            continue
        if hasattr(coord, "data") and coord.data:
            local_best = get_fuel_data(coord.data.get("local_cheapest"), fuel_id)
            if local_best and local_best.get("price") is not None:
                price = float(local_best["price"])
                if best_price is None or price < best_price:
                    best_price = price
                    best_station = local_best
    return best_price, best_station


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the fuel sensors for this specific entry."""
    domain_data = hass.data[DOMAIN]
    coordinator = domain_data[entry.entry_id]
    entities = []

    is_master = (
        entry.data.get("is_master", False)
        or domain_data.get("master_entry_id") == entry.entry_id
    )
    chosen_fuels = entry.options.get(FUEL_TYPES, entry.data.get(FUEL_TYPES, []))

    sites_data = coordinator.data.get("sites", {})

    for site_id, site_data in sites_data.items():
        if not site_data.get("prices"):
            continue
        for price_info in site_data["prices"]:
            f_id = str(price_info.get("FuelId"))
            if f_id in chosen_fuels:
                entities.append(FuelPriceSensor(coordinator, site_id, f_id))

    if is_master:
        for f_id in chosen_fuels:
            entities.append(QldFuelBestPriceSensor(coordinator, f_id, "global"))
            entities.append(QldFuelBestPriceSensor(coordinator, f_id, "all_tracked"))

    for f_id in chosen_fuels:
        entities.append(QldFuelBestPriceSensor(coordinator, f_id, "local"))

    async_add_entities(entities)


class QldFuelBestPriceSensor(CoordinatorEntity, SensorEntity):
    """Sensor for reporting best prices (Global, Local, or All Tracked)."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "¢/L"

    def __init__(self, coordinator, fuel_id, scope):
        super().__init__(coordinator)
        self.fuel_id = fuel_id
        self.scope = scope

        fuel_info = next((f for f in FUEL_TYPES_OPTIONS if f["value"] == fuel_id), {"label": fuel_id})

        if scope == "global":
            self._attr_name = f"Best {fuel_info['label']} in QLD"
            self._attr_unique_id = f"{DOMAIN}_global_{fuel_id}"
        elif scope == "all_tracked":
            self._attr_name = f"Best {fuel_info['label']} in Tracked Areas"
            self._attr_unique_id = f"{DOMAIN}_tracked_{fuel_id}"
        else:
            zone_id = coordinator.entry.data.get("zone", "unknown")
            state = coordinator.hass.states.get(zone_id)
            zone_name = state.name if state else "Unknown Zone"
            self._attr_name = f"{fuel_info['label']} ({zone_name})"
            self._attr_unique_id = f"{DOMAIN}_local_{coordinator.entry.entry_id}_{fuel_id}"

        self._attr_icon = "mdi:star-circle"

    @property
    def device_info(self) -> DeviceInfo:
        if self.scope in ("global", "all_tracked"):
            return DeviceInfo(
                identifiers={(DOMAIN, "qld_statewide_global")},
                name="Queensland Fuel Prices",
                manufacturer="QLD Government",
                model="Statewide Monitor",
                entry_type=DeviceEntryType.SERVICE,
            )

        return DeviceInfo(
            identifiers={(DOMAIN, f"zone_{self.coordinator.entry.entry_id}")},
            name=self.coordinator.entry.title,
            manufacturer="QLD Fuel API",
            model="Local Zone Monitor",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self):
        if self.scope == "global":
            data = get_fuel_data(self.coordinator.data.get("global_cheapest"), self.fuel_id)
            return data.get("price") if data else None

        if self.scope == "all_tracked":
            best_price, _ = _find_all_tracked_best(self.hass, self.fuel_id)
            return best_price

        data = get_fuel_data(self.coordinator.data.get("local_cheapest"), self.fuel_id)
        return data.get("price") if data else None

    @property
    def extra_state_attributes(self):
        if self.scope == "global":
            station_data = get_fuel_data(self.coordinator.data.get("global_cheapest"), self.fuel_id)
        elif self.scope == "local":
            station_data = get_fuel_data(self.coordinator.data.get("local_cheapest"), self.fuel_id)
        else:
            _, station_data = _find_all_tracked_best(self.hass, self.fuel_id)

        if not station_data:
            return {"status": f"No data for fuel_id {self.fuel_id} in {self.scope}"}

        site_id = station_data.get("site_id")
        if site_id is None:
            return {"status": "Price found but site_id is missing"}

        raw_data = self.hass.data.get(DOMAIN, {}).get("raw_data", {})
        all_sites = raw_data.get("sites", [])
        site_raw = next((s for s in all_sites if str(s.get("S")) == str(site_id)), None)

        if not site_raw:
            return {"status": f"Site {site_id} not found in raw data"}

        h_lat = self.coordinator.entry.options.get(CONF_LATITUDE, self.coordinator.entry.data.get(CONF_LATITUDE))
        h_lon = self.coordinator.entry.options.get(CONF_LONGITUDE, self.coordinator.entry.data.get(CONF_LONGITUDE))
        s_lat = float(site_raw.get("Lat", 0))
        s_lon = float(site_raw.get("Lng", 0))

        dist_km = "N/A"
        if h_lat and h_lon and s_lat != 0:
            dist_km = round(distance(h_lat, h_lon, s_lat, s_lon) / 1000, 1)

        return {
            "station_name": site_raw.get("N", "Unknown"),
            "address": f"{site_raw.get('A', '')} {site_raw.get('P', '')}".strip(),
            "distance_km": dist_km,
        }


class FuelPriceSensor(CoordinatorEntity, SensorEntity):
    """Representation of a specific station's Fuel Price Sensor."""

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
        site_name = site["name"] if site else "Unknown"

        self._attr_name = f"{site_name} {fuel_info['label']}"
        self._attr_unique_id = f"{DOMAIN}_{coordinator.entry.entry_id}_{fuel_id}_{site_id}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"zone_{self.coordinator.entry.entry_id}")},
            name=self.coordinator.entry.title,
            manufacturer="QLD Fuel API",
            model="Local Zone Monitor",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self):
        site_data = self.coordinator.data.get("sites", {}).get(self.site_id, {})
        for p in site_data.get("prices", []):
            if str(p.get("FuelId")) == self.fuel_id:
                return p.get("Price")
        return None

    @property
    def extra_state_attributes(self):
        site = self.coordinator.data.get("sites", {}).get(self.site_id, {})
        stats = site.get("stats", {}).get(self.fuel_id, {})

        attrs = {
            "address": f"{site.get('address')} {site.get('postcode')}".strip(),
            "distance": f"{site.get('distance')} km",
            "fuel_id": self.fuel_id,
            "difference_to_qld_cheapest": stats.get("qld_delta", 0),
        }

        if self._7d_low is not None:
            attrs.update({
                "7_day_low": f"{self._7d_low} ¢/L",
                "7_day_average": f"{self._7d_avg} ¢/L",
                "days_since_7_day_low": f"{self._7d_low_days} days",
            })
        if self._14d_low is not None:
            attrs.update({
                "14_day_low": f"{self._14d_low} ¢/L",
                "14_day_average": f"{self._14d_avg} ¢/L",
                "days_since_14_day_low": f"{self._14d_low_days} days",
            })
        return attrs

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        await self._update_history()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.hass.async_create_task(self._update_history())
        super()._handle_coordinator_update()

    async def _update_history(self):
        """Query the recorder for historical lows and averages."""
        if self.hass.is_stopping:
            return

        now = dt_util.utcnow()
        start_time = now - timedelta(days=14)

        try:
            state_history = await get_instance(self.hass).async_add_executor_job(
                history.get_significant_states, self.hass, start_time, None, [self.entity_id]
            )
        except (AttributeError, ValueError) as err:
            _LOGGER.debug("Could not retrieve history for %s: %s", self.entity_id, err)
            self.async_write_ha_state()
            return

        if self.entity_id in state_history:
            valid_points = []
            for s in state_history[self.entity_id]:
                if s.state in ("unknown", "unavailable", "", None):
                    continue
                try:
                    valid_points.append((float(s.state), s.last_changed))
                except ValueError:
                    continue

            if valid_points:
                min_price = min(p[0] for p in valid_points)
                min_time = max(p[1] for p in valid_points if p[0] == min_price)

                self._14d_low = min_price
                self._14d_low_days = (now - min_time).days
                self._14d_avg = round(sum(p[0] for p in valid_points) / len(valid_points), 1)

                seven_days_ago = now - timedelta(days=7)
                recent_points = [p for p in valid_points if p[1] > seven_days_ago]

                if recent_points:
                    min_7d = min(p[0] for p in recent_points)
                    min_7d_time = max(p[1] for p in recent_points if p[0] == min_7d)
                    self._7d_low = min_7d
                    self._7d_low_days = (now - min_7d_time).days
                    self._7d_avg = round(sum(p[0] for p in recent_points) / len(recent_points), 1)

        self.async_write_ha_state()