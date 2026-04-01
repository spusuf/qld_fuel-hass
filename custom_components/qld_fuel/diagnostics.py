"""Diagnostics support for the QLD Fuel integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, TOKEN
from .coordinator import QldFuelDataUpdateCoordinator

_REDACT_CONFIG_KEYS = {TOKEN}
_REDACT_PAYLOAD_KEYS = {
    "Authorization",
    "authorization",
    "subscriber_token",
    "SubscriberToken",
    "token",
    "api_key",
    "password",
    "passwd",
    "client_secret",
}


def _snapshot_sites(raw_sites: list[dict[str, Any]]) -> dict[str, Any]:
    """Return a compact, sanitized snapshot of raw site payload."""
    preview = []
    for site in raw_sites[:5]:
        preview.append(
            {
                "S": site.get("S"),
                "N": site.get("N"),
                "P": site.get("P"),
                "Lat": site.get("Lat"),
                "Lng": site.get("Lng"),
            }
        )
    return {"count": len(raw_sites), "preview": preview}


def _snapshot_prices(raw_prices: list[dict[str, Any]]) -> dict[str, Any]:
    """Return a compact, sanitized snapshot of raw prices payload."""
    preview = []
    for price in raw_prices[:10]:
        preview.append(
            {
                "FuelId": price.get("FuelId"),
                "SiteId": price.get("SiteId"),
                "Price": price.get("Price"),
                "T": price.get("T"),
            }
        )
    return {"count": len(raw_prices), "preview": preview}


def _sanitize_raw_payload(raw_data: dict[str, Any] | None) -> dict[str, Any] | None:
    """Sanitize cached API payload while keeping useful troubleshooting context."""
    if not raw_data:
        return None

    sites = raw_data.get("sites", [])
    prices = raw_data.get("prices", [])
    snapshot = {
        "sites": _snapshot_sites(sites if isinstance(sites, list) else []),
        "prices": _snapshot_prices(prices if isinstance(prices, list) else []),
    }
    return async_redact_data(snapshot, _REDACT_PAYLOAD_KEYS)


def _sanitize_processed_payload(data: dict[str, Any] | None) -> dict[str, Any] | None:
    """Sanitize processed coordinator data to avoid full payload dumps."""
    if not data:
        return None

    sites = data.get("sites", {})
    global_cheapest = data.get("global_cheapest", {})
    local_cheapest = data.get("local_cheapest", {})

    sample_site_ids = list(sites.keys())[:5] if isinstance(sites, dict) else []
    sample_global_fuels = list(global_cheapest.keys())[:10] if isinstance(global_cheapest, dict) else []
    sample_local_fuels = list(local_cheapest.keys())[:10] if isinstance(local_cheapest, dict) else []

    snapshot: dict[str, Any] = {
        "sites_count": len(sites) if isinstance(sites, dict) else 0,
        "sample_site_ids": sample_site_ids,
        "global_cheapest_fuel_ids": sample_global_fuels,
        "local_cheapest_fuel_ids": sample_local_fuels,
    }
    return async_redact_data(snapshot, _REDACT_PAYLOAD_KEYS)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    domain_data = hass.data.get(DOMAIN, {})
    coordinator = entry.runtime_data

    coordinator_payload: dict[str, Any] | None = None
    if isinstance(coordinator, QldFuelDataUpdateCoordinator):
        coordinator_payload = coordinator.data

    return {
        "entry": {
            "entry_id": entry.entry_id,
            "title": entry.title,
            "data": async_redact_data(dict(entry.data), _REDACT_CONFIG_KEYS),
            "options": async_redact_data(dict(entry.options), _REDACT_CONFIG_KEYS),
        },
        "cache": {
            "last_fetch_time": domain_data.get("last_fetch_time"),
            "raw_payload_snapshot": _sanitize_raw_payload(domain_data.get("raw_data")),
        },
        "coordinator": {
            "loaded": isinstance(coordinator, QldFuelDataUpdateCoordinator),
            "payload_snapshot": _sanitize_processed_payload(coordinator_payload),
        },
    }
