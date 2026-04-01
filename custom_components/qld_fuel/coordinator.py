import logging
import asyncio
from datetime import timedelta
from typing import Any

from aiohttp import ClientError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.issue_registry import (
    IssueSeverity,
    async_create_issue,
    async_delete_issue,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.core import callback
from homeassistant.util import dt as dt_util
from homeassistant.util.location import distance
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE

from .const import DOMAIN, TOKEN, RADIUS, SCAN_INTERVAL, LOCATION_ENTITY, ZONE

_LOGGER = logging.getLogger(__name__)


class QldFuelAuthError(Exception):
    """Raised when token authentication fails."""


class QldFuelConnectionError(Exception):
    """Raised when the API cannot be reached."""


async def async_validate_token(hass: Any, token: str | None) -> None:
    """Validate subscriber token by calling a lightweight authenticated endpoint."""
    if not token:
        raise QldFuelAuthError("Subscriber token is missing")

    headers = {"Authorization": f"FPDAPI SubscriberToken={token}"}
    session = async_get_clientsession(hass)
    url = (
        "https://fppdirectapi-prod.fuelpricesqld.com.au/"
        "Subscriber/GetFullSiteDetails?countryId=21&geoRegionLevel=3&geoRegionId=1"
    )

    try:
        async with asyncio.timeout(30):
            async with session.get(url, headers=headers) as response:
                if response.status in (401, 403):
                    raise QldFuelAuthError(f"Auth failed with status {response.status}")
                if response.status != 200:
                    raise QldFuelConnectionError(f"API returned status {response.status}")
    except asyncio.CancelledError:
        raise
    except (QldFuelAuthError, QldFuelConnectionError):
        raise
    except (ClientError, TimeoutError) as err:
        raise QldFuelConnectionError(str(err)) from err
    except Exception as err:
        raise QldFuelConnectionError(str(err)) from err


class QldFuelDataUpdateCoordinator(DataUpdateCoordinator):  # type: ignore[misc]
    """Manage fetching data; one shared API fetch is cached across all zone instances."""

    def __init__(self, hass: Any, entry: Any) -> None:
        self.entry = entry
        self._remove_location_listener = None

        scan_interval = entry.options.get(
            SCAN_INTERVAL, entry.data.get(SCAN_INTERVAL, 6)
        )

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.title}",
            update_interval=timedelta(hours=float(scan_interval)),
        )

    def _issue_id(self, kind: str) -> str:
        """Build deterministic issue IDs for this config entry."""
        return f"{self.entry.entry_id}_{kind}"

    def _create_repair_issue(self, kind: str) -> None:
        """Create a Repairs issue for actionable runtime faults."""
        async_create_issue(
            self.hass,
            DOMAIN,
            self._issue_id(kind),
            is_fixable=(kind == "auth"),
            severity=IssueSeverity.ERROR,
            translation_key=f"{kind}_update_failed",
            translation_placeholders={"entry_title": self.entry.title},
        )

    def _clear_repair_issue(self, kind: str) -> None:
        """Clear a previously raised Repairs issue."""
        async_delete_issue(self.hass, DOMAIN, self._issue_id(kind))

    @staticmethod
    def _coords_from_state(state: Any) -> tuple[float | None, float | None]:
        """Extract and normalize lat/lon from an entity state."""
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

    def _resolve_entry_coords(self) -> tuple[float | None, float | None, str | None]:
        """Resolve coordinates from location entity, then zone, then stored values."""
        location_entity = self.entry.options.get(
            LOCATION_ENTITY, self.entry.data.get(LOCATION_ENTITY)
        )
        if location_entity:
            location_state = self.hass.states.get(location_entity)
            lat, lon = self._coords_from_state(location_state)
            if lat is not None and lon is not None:
                return lat, lon, location_entity

        zone_entity = self.entry.options.get(ZONE, self.entry.data.get(ZONE))
        if zone_entity:
            zone_state = self.hass.states.get(zone_entity)
            lat, lon = self._coords_from_state(zone_state)
            if lat is not None and lon is not None:
                return lat, lon, zone_entity

        lat = self.entry.options.get(
            CONF_LATITUDE, self.entry.data.get(CONF_LATITUDE, self.hass.config.latitude)
        )
        lon = self.entry.options.get(
            CONF_LONGITUDE, self.entry.data.get(CONF_LONGITUDE, self.hass.config.longitude)
        )
        try:
            return float(lat), float(lon), None
        except (TypeError, ValueError):
            return None, None, None

    async def async_setup_location_listener(self) -> None:
        """Track location entity changes and recompute local derived data from cache."""
        if self._remove_location_listener is not None:
            return

        location_entity = self.entry.options.get(
            LOCATION_ENTITY, self.entry.data.get(LOCATION_ENTITY)
        )
        if not location_entity:
            return

        def _location_changed(event: Any) -> None:
            new_state = event.data.get("new_state")
            old_state = event.data.get("old_state")
            new_lat, new_lon = self._coords_from_state(new_state)
            old_lat, old_lon = self._coords_from_state(old_state)
            if (new_lat, new_lon) == (old_lat, old_lon):
                return
            self.hass.async_create_task(self.async_recompute_from_cache())

        self._remove_location_listener = async_track_state_change_event(
            self.hass,
            [location_entity],
            _location_changed,
        )

    async def async_recompute_from_cache(self) -> None:
        """Recompute derived local data only, using cached API payload."""
        raw_data = self.hass.data.get(DOMAIN, {}).get("raw_data")
        if not raw_data:
            return
        self.async_set_updated_data(self._process_raw_data(raw_data))

    async def async_shutdown(self) -> None:
        """Remove listeners on unload."""
        if self._remove_location_listener is not None:
            self._remove_location_listener()
            self._remove_location_listener = None

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API or use shared cache."""
        domain_data = self.hass.data[DOMAIN]

        if "fetch_lock" not in domain_data:
            domain_data["fetch_lock"] = asyncio.Lock()

        async with domain_data["fetch_lock"]:
            last_fetch = domain_data.get("last_fetch_time")
            now = dt_util.utcnow()

            if last_fetch is None or (now - last_fetch) > timedelta(minutes=5):
                _LOGGER.debug("Shared cache expired or empty. Fetching fresh data for %s", self.entry.title)
                try:
                    raw_data = await self._fetch_from_api()
                    domain_data["raw_data"] = raw_data
                    domain_data["last_fetch_time"] = now
                    self._clear_repair_issue("auth")
                    self._clear_repair_issue("connectivity")
                except QldFuelAuthError as err:
                    self._create_repair_issue("auth")
                    raise UpdateFailed(f"Authentication failed: {err}") from err
                except QldFuelConnectionError as err:
                    self._create_repair_issue("connectivity")
                    raise UpdateFailed(f"Error communicating with API: {err}") from err
                except asyncio.CancelledError:
                    raise
                except (ClientError, TimeoutError, TypeError, ValueError, KeyError) as err:
                    raise UpdateFailed(f"Error communicating with API: {err}") from err
                except Exception as err:
                    raise UpdateFailed(f"Error communicating with API: {err}") from err
            else:
                _LOGGER.debug("Using shared cache for %s", self.entry.title)

            raw_data = domain_data["raw_data"]

        return self._process_raw_data(raw_data)

    async def _fetch_from_api(self) -> dict[str, list[dict[str, Any]]]:
        """Perform the actual HTTP requests to the QLD Fuel API."""
        token = self.entry.data.get(TOKEN)
        if not token:
            raise UpdateFailed("Subscriber Token is missing.")

        headers = {"Authorization": f"FPDAPI SubscriberToken={token}"}
        session = async_get_clientsession(self.hass)
        base_url = "https://fppdirectapi-prod.fuelpricesqld.com.au"

        async with asyncio.timeout(30):
            urls = [
                f"{base_url}/Subscriber/GetFullSiteDetails?countryId=21&geoRegionLevel=3&geoRegionId=1",
                f"{base_url}/Price/GetSitesPrices?countryId=21&geoRegionLevel=3&geoRegionId=1",
            ]

            results = []
            for url in urls:
                async with session.get(url, headers=headers) as response:
                    if response.status in (401, 403):
                        _LOGGER.error("QLD Fuel API authentication failed with status %s", response.status)
                        raise QldFuelAuthError(f"API auth error {response.status}")
                    if response.status != 200:
                        _LOGGER.error("QLD Fuel API returned status %s", response.status)
                        raise QldFuelConnectionError(f"API Error {response.status}")
                    results.append(await response.json())

            return {
                "sites": results[0].get("S", []),
                "prices": results[1].get("SitePrices", []),
            }

    def _process_raw_data(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        """Transform raw JSON into the structured dict used by sensors."""
        raw_sites = raw_data.get("sites", [])
        raw_prices = raw_data.get("prices", [])

        site_lookup = {str(s["S"]): s for s in raw_sites}
        price_map: dict[str, list[dict[str, Any]]] = {}
        global_cheapest: dict[str, dict[str, Any]] = {}

        for p in raw_prices:
            price_raw = p.get("Price")
            if price_raw is None or not (1 < price_raw < 9990):
                continue

            # Normalize to a single decimal place to avoid floating-point noise
            # showing up in recorder graphs (e.g. 244.89999999999998).
            display_price = round(float(price_raw) / 10.0, 1)
            f_id = str(p.get("FuelId"))
            s_id = str(p.get("SiteId"))

            clean_price_entry = {
                "FuelId": f_id,
                "Price": display_price,
                "SiteId": s_id,
            }

            if f_id not in global_cheapest or display_price < global_cheapest[f_id]["price"]:
                s_info = site_lookup.get(s_id, {})
                global_cheapest[f_id] = {
                    "price": display_price,
                    "site_id": s_id,
                    "name": s_info.get("N"),
                    "address": s_info.get("A"),
                    "postcode": s_info.get("P"),
                    "latitude": s_info.get("Lat"),
                    "longitude": s_info.get("Lng"),
                }

            price_map.setdefault(s_id, []).append(clean_price_entry)

        return self._filter_to_zone(raw_sites, price_map, global_cheapest)

    def _filter_to_zone(
        self,
        sites: list[dict[str, Any]],
        price_map: dict[str, list[dict[str, Any]]],
        global_cheapest: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        """Filter stations within this entry's defined radius."""
        filtered_sites = {}
        local_cheapest: dict[str, dict[str, Any]] = {}

        lat, lon, _ = self._resolve_entry_coords()
        if lat is None or lon is None:
            return {
                "sites": {},
                "global_cheapest": global_cheapest,
                "local_cheapest": {},
            }
        radius = float(self.entry.options.get(RADIUS, self.entry.data.get(RADIUS, 5)))

        for site in sites:
            s_id = str(site.get("S"))
            try:
                s_lat, s_lon = float(site["Lat"]), float(site["Lng"])
            except (KeyError, TypeError, ValueError):
                continue

            dist = distance(lat, lon, s_lat, s_lon) / 1000
            if dist > radius:
                continue

            site_prices = price_map.get(s_id, [])
            stats = {}

            for p in site_prices:
                f_id = str(p["FuelId"])
                price = p["Price"]

                stats[f_id] = {
                    "qld_delta": round(price - global_cheapest.get(f_id, {}).get("price", price), 1)
                }

                if f_id not in local_cheapest or price < local_cheapest[f_id]["price"]:
                    local_cheapest[f_id] = {
                        "price": price,
                        "site_id": s_id,
                        "name": site.get("N"),
                        "address": site.get("A"),
                        "postcode": site.get("P"),
                        "latitude": site.get("Lat"),
                        "longitude": site.get("Lng"),
                    }

            filtered_sites[s_id] = {
                "name": site.get("N"),
                "address": site.get("A"),
                "postcode": site.get("P"),
                "latitude": s_lat,
                "longitude": s_lon,
                "distance": round(dist, 1),
                "prices": site_prices,
                "stats": stats,
            }

        return {
            "sites": filtered_sites,
            "global_cheapest": global_cheapest,
            "local_cheapest": local_cheapest,
        }