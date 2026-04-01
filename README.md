# Queensland Fuel Price integration for Home Assistant

This integration is for users in Queensland, Australia and gives you sensors for the fuel stations in a (or multiple) areas and some statistics for your Home Assistant dashboards.
It utilises the Queensland Government Mandatory Fuel Price Reporting Scheme's API (mouthful, I know)

## Setup

1. You will need to request a Data Consumer Token from this form: [Publisher and Data Consumer Sign Up](https://forms.office.com/Pages/ResponsePage.aspx?id=XbdJc0AKKUSHYhmf2mnq-9XqCWIciN5Osw2Y74gWzu9UQ0pCR1dPV0FWR1ZPN0FYSEc0UEVQMkQzMyQlQCN0PWcu)
2. Install this integration via HACS [![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=spusuf&repository=qld_fuel-hass)
3. Add the integration in home assistant

## Features

- Automatically creates an entry for each station within a selectable radius from your home's location (will add location selector to allow second instance scanning near work, etc)
- Allows you to select multiple fuel types you want added to home assistant
- Tracks the price for those fuel types (duh)
- Tracks the cheapest price in your defined area
- Tracks the cheapest price in Queensland
- Tracks statistics in attributes (7 & 14 day lows & averages)
- Configurable update interval

## Actions

This integration registers one Home Assistant service action:

- `qld_fuel.refresh_prices`: triggers an immediate refresh for all loaded QLD Fuel entries.

Example service call in YAML:

```yaml
service: qld_fuel.refresh_prices
data: {}
```

## Troubleshooting

- **Invalid token during setup**: confirm your Data Consumer Token is current and has no extra spaces.
- **Cannot connect**: check Home Assistant internet connectivity and try again later.
- **No nearby stations**: increase radius or verify the selected location entity/zone has valid coordinates.
- **Stale values**: run the `qld_fuel.refresh_prices` action to force an on-demand refresh.

## Known limitations

- Fuel prices are sourced from the published Queensland Fuel Prices API and reflect that upstream data.
- Global API payloads are cached briefly and shared across configured entries to avoid excessive calls.
- A single location (zone or location entity) can only be configured once per integration instance.

## Removal instructions

1. Go to **Settings -> Devices & Services**.
2. Open **Queensland Fuel Prices**.
3. Select the entry you want to remove.
4. Use **Delete** (three-dot menu) and confirm.
5. Optionally remove dashboards/automations that referenced the integration entities.

![3 fuel sensors on a dashboard](https://github.com/spusuf/qld_fuel-hass/blob/main/previews/preview2.png "3 fuel sensors with graphs on a dashboard")

Each sensor has the following attributes:

- Difference (in cents) to cheapest in QLD
- Difference (in cents) to cheapest in your defined area
- 7 day low price
- Difference between 7 day low and current
- 7 day average
- 14 day low price
- Difference between 14 day low and current
- 14 day average
- Distance (in case you want to do a price delta vs distance graph)

![Preview of a sensor with its attributes](https://github.com/spusuf/qld_fuel-hass/blob/main/previews/preview1.jpg "Preview of sensor panel")

## Note

The scheme is documented here: [Fuel Prices Queensland](https://fuelpricesqld.com.au/)
Developer resources are here: [Fuel Prices QLD Developers](https://www.fuelpricesqld.com.au/#developers)
Official Postman collection is here: [postmanv1.json](https://www.fuelpricesqld.com.au/documents/postmanv1.json)
This repository's contributor-friendly API reference is here: [docs/fuel-prices-qld-api-reference.md](docs/fuel-prices-qld-api-reference.md)
The published API PDF is here: [API documentation](https://www.fuelpricesqld.com.au/documents/FuelPricesQLDDirectAPI(OUT)v1.6.pdf)
Sorry about the washed out screenshots, HDR on Hyprland is not yet perfect.

### To do

Add a location selector to the configuration page to allow second instance in a different location
Get non-washed out screenshots with longer term statistics
