from homeassistant.const import Platform

DOMAIN="qld_fuel"

TOKEN = "subscriber_token"

RADIUS = "radius"

FUEL_TYPES = "fuel_types"
FUEL_TYPES_OPTIONS = [
    {"value": "12", "label": "E10"},
    {"value": "2", "label": "Unleaded 91"},
    {"value": "5", "label": "Unleaded 95"},
    {"value": "8", "label": "Unleaded 98"},
    {"value": "3", "label": "Diesel"},
    {"value": "14", "label": "Premium Diesel"},
    {"value": "4", "label": "LPG"},
    {"value": "19", "label": "E85"},
]

SCAN_INTERVAL = "scan_interval"

PLATFORMS = [Platform.SENSOR]