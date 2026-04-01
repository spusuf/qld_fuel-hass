# Queensland Fuel Price integration for Home Assistant
This integration is for users in Queensland, Australia and gives you sensors for the fuel stations in a (or multiple) areas and some statistics for your Home Assistant dashboards.
It utilises the Queensland Government Mandatory Fuel Price Reporting Scheme's API (mouthful, I know)

## Setup
1. You will need to request a Data Consumer Token from this form: [Publisher and Data Consumer Sign Up](https://forms.office.com/Pages/ResponsePage.aspx?id=XbdJc0AKKUSHYhmf2mnq-9XqCWIciN5Osw2Y74gWzu9UQ0pCR1dPV0FWR1ZPN0FYSEc0UEVQMkQzMyQlQCN0PWcu)
2. Install this integration via HACS [![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=spusuf&repository=qld_fuel-hass)
3. Add the integration in home assistant

### Install/config parameters

| Name | Required | Default | Range | Description |
|---|---|---|---|---|
| `subscriber_token` | Yes (master entry only) | None | N/A | Data Consumer Token from Fuel Prices QLD. |
| `location_entity` | No | None | Entity domain: `person`, `device_tracker`, `sensor` | Optional tracked entity used as the reference coordinates. |
| `zone` | Yes | `zone.home` | Entity domain: `zone` | Fallback location and display name source when `location_entity` is not provided. |
| `radius` | Yes | `5` | `1-100` km | Search radius used to include nearby stations. |
| `fuel_types` | Yes | `["12","5","3"]` | Any subset of supported fuel IDs | Fuel products to create sensors for. |
| `scan_interval` | Yes | `6` | `1-24` hours | Scheduled refresh interval for API updates. |


## Features
- Automatically creates an entry for each station within a selectable radius from your home's location (will add location selector to allow second instance scanning near work, etc)
- Allows you to select multiple fuel types you want added to home assistant
- Tracks the price for those fuel types (duh)
- Tracks the cheapest price in your defined area
- Tracks the cheapest price in Queensland
- Tracks statistics in attributes (7 & 14 day lows & averages)
- Configurable update interval

## Development quality gates
- Tests: `python -m pytest -q tests/components/qld_fuel`
- Coverage: configured in CI with `--cov-fail-under=95`
- Strict typing: `python -m mypy --config-file mypy.ini custom_components/qld_fuel`

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
The API is documented here: [API documentation](https://www.fuelpricesqld.com.au/documents/FuelPricesQLDDirectAPI(OUT)v1.6.pdf)
Sorry about the washed out screenshots, HDR on Hyprland is not yet perfect.

### To do
Add a location selector to the configuration page to allow second instance in a different location
Get non-washed out screenshots with longer term statistics

## Service action: refresh_prices

The integration exposes one Home Assistant service action:

- `qld_fuel.refresh_prices`

Use this when you want an on-demand update (for example after changing options,
or when troubleshooting stale values).

Expected behavior:

- Triggers a refresh request for all loaded QLD Fuel config entries.
- If shared API data is older than 5 minutes, the integration fetches fresh data.
- If shared API data was fetched in the last 5 minutes, entries reuse the shared
  cache and recompute from that data.

Failure behavior:

- If one or more entries fail during the service call, Home Assistant reports the
  service call as failed and includes the affected entry IDs.
- Entry-level failures are logged; successful entries can still update.

## Removal instructions

1. Go to **Settings -> Devices & Services** in Home Assistant.
2. Open **Queensland Fuel Prices**.
3. Select the config entry you want to remove.
4. Use **Delete** (three-dot menu) and confirm.
5. Optionally remove dashboards and automations that referenced those entities.

## Troubleshooting

- **Invalid token**: confirm your Data Consumer Token is current, copied exactly,
  and has no leading or trailing spaces.
- **Cannot connect**: check Home Assistant internet connectivity and retry later.
  Temporary upstream API issues can also cause this.
- **Missing zone/location coordinates**: ensure your selected `zone` or
  `location_entity` exposes valid `latitude` and `longitude` attributes.
  If no valid coordinates are available, nearby station filtering cannot be
  calculated correctly.

## Data update behavior

- `scan_interval` controls scheduled refresh frequency in hours (default `6`,
  supported range `1-24`).
- All entries share one cached raw API payload at the integration domain level.
- Shared cache freshness window is 5 minutes. Within that window, refreshes reuse
  cached API data to avoid extra upstream calls.
- After the 5-minute window expires, the next refresh fetches fresh data and
  updates the shared cache for all entries.

## Supported functions

This integration currently supports:

- Setup via Home Assistant config flow.
- Per-location fuel station sensors for selected fuel types.
- Best-price summary sensors (local, nearby tracker location, tracked areas, and
  Queensland-wide).
- Reconfiguration of location, radius, fuel types, and scan interval.
- Reauthentication when a token is no longer accepted by the API.
- Diagnostics snapshots with sensitive values redacted.
- Manual refresh via the `qld_fuel.refresh_prices` action.

## Supported devices and entities

This integration creates Home Assistant service-style devices and sensor entities:

- A service device for each configured location entry.
- A statewide service device for Queensland-level summary sensors.
- Per-station fuel price sensors for stations in range.
- Summary sensors for:
  - best local price for each selected fuel type
  - best nearby price for each selected fuel type
  - best tracked-areas price for each selected fuel type (master entry)
  - best Queensland price for each selected fuel type (master entry)

## Use cases

Common ways to use this integration:

- Compare local stations and pick the best price before refueling.
- Track fuel trends using 7-day and 14-day price attributes.
- Monitor a second area (for example near work) with another config entry.
- Drive automations and dashboard cards from cheapest-price sensors.
- Trigger an immediate refresh before trips with `qld_fuel.refresh_prices`.

## Known limitations

- Fuel price data quality and update timing depend on the upstream Queensland Fuel
  Prices API.
- If your selected `zone` or `location_entity` has no valid coordinates, nearby
  station filtering and local comparisons cannot be calculated correctly.
- Shared API payloads are cached for up to 5 minutes across entries; immediate
  back-to-back refresh requests may reuse cached data.
- A specific location source can only be configured once (duplicate location setup
  is blocked by unique entry handling).

## Discovery applicability

The Home Assistant Integration Quality Scale rules `discovery` and
`discovery-update-info` are not applicable for this integration.

Reason:

- `qld_fuel` is a cloud polling service integration that requires a user-provided
  Fuel Prices QLD Data Consumer Token.
- Entities are scoped to user-selected location context (`zone` and optional
  `location_entity`), radius, and chosen fuel products.
- There is no local network device, protocol broadcast, or hardware endpoint to
  discover automatically.
- Setup is intentionally manual through the config flow so users only install and
  configure the integration when it is relevant to their interests and location.
