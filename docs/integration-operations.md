# QLD Fuel Integration Operations Guide

This guide keeps operational and troubleshooting details out of the primary
repository `README.md`.

## Home Assistant action

This integration registers one Home Assistant service action:

- `qld_fuel.refresh_prices`: trigger an immediate refresh for all loaded QLD
  Fuel entries.

Example service call in YAML:

```yaml
service: qld_fuel.refresh_prices
data: {}
```

## Troubleshooting

- **Invalid token during setup**: confirm your Data Consumer Token is current
  and has no extra spaces.
- **Cannot connect**: check Home Assistant internet connectivity and try again
  later.
- **No nearby stations**: increase radius or verify the selected location
  entity/zone has valid coordinates.
- **Stale values**: run the `qld_fuel.refresh_prices` action to force an
  on-demand refresh.

## Known limitations

- Fuel prices are sourced from the published Queensland Fuel Prices API and
  reflect that upstream data.
- Global API payloads are cached briefly and shared across configured entries to
  avoid excessive calls.
- A single location (zone or location entity) can only be configured once per
  integration instance.

## Removal instructions

1. Go to **Settings -> Devices & Services**.
2. Open **Queensland Fuel Prices**.
3. Select the entry you want to remove.
4. Use **Delete** (three-dot menu) and confirm.
5. Optionally remove dashboards/automations that referenced the integration
   entities.

## Developer resources

- Developer portal: [Fuel Prices QLD Developers](https://www.fuelpricesqld.com.au/#developers)
- Official Postman collection: [postmanv1.json](https://www.fuelpricesqld.com.au/documents/postmanv1.json)
- Contributor API reference: [fuel-prices-qld-api-reference.md](./fuel-prices-qld-api-reference.md)
- Published API PDF: [FuelPricesQLDDirectAPI(OUT)v1.6.pdf](https://www.fuelpricesqld.com.au/documents/FuelPricesQLDDirectAPI(OUT)v1.6.pdf)

## Developer testing

Use the repository helper script to run integration tests locally on Windows.

First run (create venv, install test dependencies, then run tests):

```powershell
.\scripts\run-tests.ps1 -Install
```

Subsequent runs:

```powershell
.\scripts\run-tests.ps1
```

Manual equivalent commands:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q tests\components\qld_fuel
```

To generate explicit local coverage evidence:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\components\qld_fuel --cov=custom_components\qld_fuel --cov-report=term-missing --cov-report=xml:coverage.xml
```

## Coverage evidence in CI

The `Test Coverage` GitHub Actions workflow runs integration tests with
`pytest-cov` and publishes:

- `coverage.xml` for machine-readable coverage metrics.
- `coverage-summary.txt` for human-readable terminal coverage output.

Download these artifacts from each workflow run for measurable evidence of test
coverage over time.

If dependency installation fails on Windows (for example while building
`greenlet`), verify Python version and architecture, then update build tools or
use a Python version with prebuilt wheels available for the dependency set.
