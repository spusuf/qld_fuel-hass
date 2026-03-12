import logging
import asyncio
from datetime import timedelta

from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from homeassistant.util.location import distance
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE

from .const import DOMAIN, TOKEN, RADIUS, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


class QldFuelDataUpdateCoordinator(DataUpdateCoordinator):
    """Manage fetching data; one shared API fetch is cached across all zone instances."""

    def __init__(self, hass, entry):
        self.entry = entry

        scan_interval = entry.options.get(
            SCAN_INTERVAL, entry.data.get(SCAN_INTERVAL, 6)
        )

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.title}",
            update_interval=timedelta(hours=float(scan_interval)),
        )

    async def _async_update_data(self):
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
                except Exception as err:
                    raise UpdateFailed(f"Error communicating with API: {err}") from err
            else:
                _LOGGER.debug("Using shared cache for %s", self.entry.title)

            raw_data = domain_data["raw_data"]

        return self._process_raw_data(raw_data)

    async def _fetch_from_api(self):
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
                    if response.status != 200:
                        _LOGGER.error("QLD Fuel API returned status %s", response.status)
                        raise UpdateFailed(f"API Error {response.status}")
                    results.append(await response.json())

            return {
                "sites": results[0].get("S", []),
                "prices": results[1].get("SitePrices", []),
            }

    def _process_raw_data(self, raw_data):
        """Transform raw JSON into the structured dict used by sensors."""
        raw_sites = raw_data.get("sites", [])
        raw_prices = raw_data.get("prices", [])

        site_lookup = {str(s["S"]): s for s in raw_sites}
        price_map = {}
        global_cheapest = {}

        for p in raw_prices:
            price_raw = p.get("Price")
            if price_raw is None or not (1 < price_raw < 9990):
                continue

            display_price = float(price_raw) / 10.0
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
                }

            price_map.setdefault(s_id, []).append(clean_price_entry)

        return self._filter_to_zone(raw_sites, price_map, global_cheapest)

    def _filter_to_zone(self, sites, price_map, global_cheapest):
        """Filter stations within this entry's defined radius."""
        filtered_sites = {}
        local_cheapest = {}

        lat = self.entry.options.get(CONF_LATITUDE, self.entry.data.get(CONF_LATITUDE, self.hass.config.latitude))
        lon = self.entry.options.get(CONF_LONGITUDE, self.entry.data.get(CONF_LONGITUDE, self.hass.config.longitude))
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
                    }

            filtered_sites[s_id] = {
                "name": site.get("N"),
                "address": site.get("A"),
                "postcode": site.get("P"),
                "distance": round(dist, 1),
                "prices": site_prices,
                "stats": stats,
            }

        return {
            "sites": filtered_sites,
            "global_cheapest": global_cheapest,
            "local_cheapest": local_cheapest,
        }