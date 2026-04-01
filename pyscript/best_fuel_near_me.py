from math import radians, sin, cos, sqrt, atan2
from datetime import datetime

TRACKER_ENTITY = "person.kevyn_watkins"
DEFAULT_RADIUS_KM = 10.0

FUEL_TARGETS = {
    "e10": {"fuel_id": "12", "label": "E10"},
    "u91": {"fuel_id": "2", "label": "Unleaded 91"},
    "u95": {"fuel_id": "5", "label": "Unleaded 95"},
    "u98": {"fuel_id": "8", "label": "Unleaded 98"},
    "diesel": {"fuel_id": "3", "label": "Diesel"},
    "premium_diesel": {"fuel_id": "14", "label": "Premium Diesel"},
    "lpg": {"fuel_id": "4", "label": "LPG"},
    "e85": {"fuel_id": "19", "label": "E85"},
}

ENABLED_FUELS = ["e10", "u98"]

SENSOR_PREFIX = "best"
SENSOR_SUFFIX = "near_kevyn"


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return r * c


def safe_float(value):
    try:
        if value in [None, "", "unknown", "unavailable"]:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def get_tracker_coords():
    attrs = state.getattr(TRACKER_ENTITY)
    if not attrs:
        return None, None

    lat = safe_float(attrs.get("latitude"))
    lon = safe_float(attrs.get("longitude"))

    if lat is None or lon is None:
        return None, None

    return lat, lon

def is_fuel_station_entity(entity_id):
    if not entity_id.startswith("sensor."):
        return False

    attrs = state.getattr(entity_id)
    if not attrs:
        return False

    if "fuel_id" not in attrs:
        return False
    if "latitude" not in attrs:
        return False
    if "longitude" not in attrs:
        return False
    if "address" not in attrs:
        return False

    return True

def get_station_candidates(target_fuel_id, user_lat, user_lon, radius_km):
    candidates = []

    for entity_id in state.names(domain="sensor"):
        if not is_fuel_station_entity(entity_id):
            continue

        attrs = state.getattr(entity_id)
        if str(attrs.get("fuel_id")) != str(target_fuel_id):
            continue

        station_lat = safe_float(attrs.get("latitude"))
        station_lon = safe_float(attrs.get("longitude"))
        price = safe_float(state.get(entity_id))

        if station_lat is None or station_lon is None or price is None:
            continue

        distance_km = haversine_km(user_lat, user_lon, station_lat, station_lon)
        if distance_km > radius_km:
            continue

        candidates.append({
            "entity_id": entity_id,
            "price": price,
            "distance_km": round(distance_km, 2),
            "station_lat": station_lat,
            "station_lon": station_lon,
            "attrs": attrs,
        })

    candidates.sort(key=lambda x: (x["price"], x["distance_km"]))
    return candidates


def publish_result(sensor_entity_id, fuel_id, fuel_label, result, radius_km):
    now_iso = datetime.now().isoformat()

    if result is None:
        state.set(
            sensor_entity_id,
            value="unknown",
            new_attributes={
                "friendly_name": f"Best {fuel_label} Near Kevyn",
                "fuel_id": fuel_id,
                "fuel_label": fuel_label,
                "search_radius_km": radius_km,
                "source_tracker": TRACKER_ENTITY,
                "reason": "no_stations_in_range",
                "last_resolved": now_iso,
                "icon": "mdi:gas-station",
            },
        )
        return

    attrs = result["attrs"]
    station_name = attrs.get("friendly_name", result["entity_id"])

    state.set(
        sensor_entity_id,
        value=result["price"],
        new_attributes={
            "friendly_name": f"Best {fuel_label} Near Kevyn",
            "station_name": station_name,
            "station_entity_id": result["entity_id"],
            "address": attrs.get("address"),
            "fuel_id": fuel_id,
            "fuel_label": fuel_label,
            "latitude": result["station_lat"],
            "longitude": result["station_lon"],
            "distance_km": result["distance_km"],
            "search_radius_km": radius_km,
            "source_tracker": TRACKER_ENTITY,
            "difference_to_qld_cheapest": attrs.get("difference_to_qld_cheapest"),
            "7_day_low": attrs.get("7_day_low"),
            "7_day_average": attrs.get("7_day_average"),
            "14_day_low": attrs.get("14_day_low"),
            "14_day_average": attrs.get("14_day_average"),
            "last_resolved": now_iso,
            "unit_of_measurement": attrs.get("unit_of_measurement"),
            "icon": "mdi:gas-station",
        },
    )


def publish_tracker_unavailable(sensor_entity_id, fuel_id, fuel_label, radius_km):
    now_iso = datetime.now().isoformat()
    state.set(
        sensor_entity_id,
        value="unknown",
        new_attributes={
            "friendly_name": f"Best {fuel_label} Near Kevyn",
            "fuel_id": fuel_id,
            "fuel_label": fuel_label,
            "search_radius_km": radius_km,
            "source_tracker": TRACKER_ENTITY,
            "reason": "tracker_unavailable",
            "last_resolved": now_iso,
            "icon": "mdi:gas-station",
        },
    )


def recalc_all(radius_km=DEFAULT_RADIUS_KM):
    user_lat, user_lon = get_tracker_coords()

    for fuel_key in ENABLED_FUELS:
        fuel_id = FUEL_TARGETS[fuel_key]["fuel_id"]
        fuel_label = FUEL_TARGETS[fuel_key]["label"]
        sensor_entity_id = f"sensor.{SENSOR_PREFIX}_{fuel_key}_{SENSOR_SUFFIX}"

        if user_lat is None or user_lon is None:
            publish_tracker_unavailable(sensor_entity_id, fuel_id, fuel_label, radius_km)
            continue

        candidates = get_station_candidates(fuel_id, user_lat, user_lon, radius_km)
        best = candidates[0] if candidates else None
        publish_result(sensor_entity_id, fuel_id, fuel_label, best, radius_km)


@time_trigger("startup")
def fuel_best_near_me_startup():
    recalc_all()


@state_trigger(TRACKER_ENTITY)
def fuel_best_near_me_tracker_update(value=None, old_value=None):
    recalc_all()

