# Queensland Fuel Price integration for Home Assistant
This integration is for users in Queensland, Australia and gives you sensors for the fuel stations in a (or multiple) areas and some statistics for your Home Assistant dashboards.
It utilises the Queensland Government Mandatory Fuel Price Reporting Scheme's API (mouthful, I know)

## Features
- Automatically creates an entry for each station within a selectable radius from your home's location (will add location selector to allow second instance scanning near work, etc)
- Allows you to select multiple fuel types you want added to home assistant
- Tracks the price for those fuel types (duh)
- Tracks the cheapest price in your defined area
- Tracks the cheapest price in Queensland
- Tracks statistics in attributes (7 & 14 day lows & averages)
- Configurable update interval

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

## Setup
1. You will need to request a Data Consumer Token from this form: [Publisher and Data Consumer Sign Up](https://forms.office.com/Pages/ResponsePage.aspx?id=XbdJc0AKKUSHYhmf2mnq-9XqCWIciN5Osw2Y74gWzu9UQ0pCR1dPV0FWR1ZPN0FYSEc0UEVQMkQzMyQlQCN0PWcu)
2. Install this integration via HACS (for the time being you will need to add it as a custom repository in the top right of HACS).
3. During configuration, enter your token, your vehicle's fuel type(s) and radius (if you are in a suburban area I recommend 2-4kms).



## Note
The scheme is documented here: [Fuel Prices Queensland](https://fuelpricesqld.com.au/)
The API is documented here: [API documentation](https://www.fuelpricesqld.com.au/documents/FuelPricesQLDDirectAPI(OUT)v1.6.pdf)
Sorry about the washed out screenshots, HDR on Hyprland is not yet perfect.

### To do
Add a location selector to the configuration page to allow second instance in a different location
Get non-washed out screenshots with longer term statistics
