import logging
import asyncio
import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from datetime import timedelta
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from homeassistant.util.location import distance

from .const import DOMAIN, TOKEN, RADIUS, FUEL_TYPES, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

class QldFuelDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the Fuel Price API."""

    def __init__(self, hass, entry):
        """Initialize."""
        self.entry = entry
        
        scan_interval = entry.data.get(SCAN_INTERVAL, 6)
        
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(hours=scan_interval),
        )


    async def _async_update_data(self):
        """Fetch data from API."""
        token = self.entry.data.get(TOKEN)
        if not token:
            raise UpdateFailed("Subscriber Token is missing. Please delete and re-add the integration.")
            
        headers = {"Authorization": f"FPDAPI SubscriberToken={token}"}

        session = async_get_clientsession(self.hass)

        base_url = "https://fppdirectapi-prod.fuelpricesqld.com.au"
        endpoints = {
            "sites": f"{base_url}/Subscriber/GetFullSiteDetails?countryId=21&geoRegionLevel=3&geoRegionId=1",
            # "brands": f"{base_url}/Subscriber/GetCountryBrands?countryId=21",
            # "fuel_types": f"{base_url}/Subscriber/GetCountryFuelTypes?countryId=21",
            "site_prices": f"{base_url}/Price/GetSitesPrices?countryId=21&geoRegionLevel=3&geoRegionId=1",
        }

        try:
            async with asyncio.timeout(30):
                responses = await asyncio.gather(*(session.get(url, headers=headers) for url in endpoints.values()))
                
                for r in responses:
                    if r.status != 200:
                        text = await r.text()
                        raise UpdateFailed(f"API Error {r.status}: {text}")

                json_data = await asyncio.gather(*(r.json() for r in responses))
                data_map = dict(zip(endpoints.keys(), json_data))
            
                raw_sites = data_map["sites"].get("S", [])
                raw_prices = data_map["site_prices"].get("SitePrices", [])
                
                site_lookup = {str(s["S"]): s for s in raw_sites}

                price_map = {}
                global_cheapest = {}

                for p in raw_prices:
                    price = p.get("Price", None)
                    
                    if price is None or price <= 0 or price >= 9990: continue
                    
                    price = price / 10.0
                    p["Price"] = price

                    f_id = str(p["FuelId"])

                    if f_id not in global_cheapest or price < global_cheapest[f_id]["price"]:
                        s_id = str(p["SiteId"])
                        s_info = site_lookup.get(s_id, {})
                        global_cheapest[f_id] = {
                            "price": price,
                            "site_id": s_id,
                            "name": s_info.get("N"),
                            "address": s_info.get("A"),
                            "postcode": s_info.get("P"),
                            "brand_id": s_info.get("B")
                        }
                    
                    site_id = str(p["SiteId"])
                    price_map.setdefault(site_id, []).append(p)

                return self._filter_data(raw_sites, price_map, global_cheapest)

        except Exception as err:
            _LOGGER.error(f"Error updating data: {err}")
            raise UpdateFailed(f"QLD Fuel API error: {err}")

    def _filter_data(self, sites, price_map, global_cheapest):
        filtered_sites = {}
        local_cheapest = {}
        
        home_lat, home_lon = self.hass.config.latitude, self.hass.config.longitude
        
        if home_lat is None or home_lon is None:
            raise UpdateFailed("Home latitude or longitude not set in Home Assistant config.")

        user_radius = self.entry.data[RADIUS]
        
        _LOGGER.debug(f"Filtering sites. Home: {home_lat}, {home_lon}. Radius: {user_radius}km. Total Sites: {len(sites)}")

        sites_in_radius = 0

        for i, site in enumerate(sites):
            s_id = str(site.get("S"))
            name = site.get("N")
            address = site.get("A")
            postcode = site.get("P")
            
            try:
                site_lat = float(site.get("Lat"))
                site_lon = float(site.get("Lng"))
            except (TypeError, ValueError):
                continue

            dist = distance(home_lat, home_lon, site_lat, site_lon) / 1000
            if dist <= user_radius:
                sites_in_radius += 1

                stats = {}
                site_prices = price_map.get(s_id, [])
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
                            "name": name,
                            "address": address,
                            "postcode": postcode,
                            "distance": round(dist, 1)
                        }

                filtered_sites[s_id] = {
                    "name": name,
                    "address": address,
                    "postcode": postcode,
                    "distance": round(dist, 1),
                    "prices": site_prices,
                    "stats": stats
                }
        
        if not filtered_sites:
            _LOGGER.warning(f"No fuel stations found within {user_radius}km of home (Lat: {home_lat}, Lon: {home_lon}). Sites in range: {sites_in_radius}. Verify your HA General Configuration location settings.")
            
        return {
            "sites": filtered_sites,
            "global_cheapest": global_cheapest,
            "local_cheapest": local_cheapest
        }