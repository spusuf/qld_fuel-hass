# Fuel Prices QLD API Reference

API version: `v1.6`  
Publisher and Data Consumer Guide date: March 2023

## Official sources

This repository document is a developer-friendly reference for contributors.
Use the official Fuel Prices QLD resources as the source of truth:

- Developer portal: <https://www.fuelpricesqld.com.au/#developers>
- Postman collection (PROD): <https://www.fuelpricesqld.com.au/documents/postmanv1.json>
- Swagger (PROD): <https://fppdirectapi-prod.fuelpricesqld.com.au/swagger/>

## Overview

The Queensland Government Fuel Price Reporting scheme requires fuel retailers in Queensland to report bowser price changes within 30 minutes.

Fuel Prices QLD (the Aggregator) provides this data to approved Data Consumers via a server-to-server API called **Fuel Prices QLD Direct API (OUT)**.

This guide is a cleaned and reformatted API reference based on the published v1.6 documentation and cross-checked against the published Postman collection.

## Key Terms

- **Data Consumer**: Entity licensed to access Fuel Prices QLD data.
- **Token / Data Consumer Token**: Subscriber credential (GUID) used to authenticate API calls.
- **Fuel Prices QLD Direct API (OUT)**: Server API providing site, region, fuel-type, and price data.

## Environments

- **Integration**: For development/testing only (non-live test data).
- **Production**: Live data for production systems.

## Protocol and Authentication

- All requests must use **HTTPS**.
- Include `Authorization: FPDAPI SubscriberToken=<DATA_CONSUMER_TOKEN>` on all requests.
- `Content-Type: application/json` is used in official Postman examples, including `GET` requests.

Token format is a GUID, for example:

```text
2FEB37D3-4326-4E30-8705-0FCE0519B6D
```

## Common HTTP Response Codes

- `200` OK
- `400` Bad Request (invalid parameter values/types)
- `401` Unauthorized (invalid or missing token)
- `403` Forbidden
- `404` Not Found
- `500` Internal Server Error

Always validate HTTP status before consuming response data.

## JSON Compatibility Guidance

Responses are JSON and may evolve in non-breaking ways:

- Fields may be added at any time.
- Field order may change.

Do not rely on JSON property order in your parser.

## API Methods

Country value used in examples:

- `countryId=21` for Australia

### 1) GetBrands

- **Method**: `GET`
- **Path**: `/Subscriber/GetCountryBrands`
- **Query params**: `countryId` (required, int)
- **Purpose**: Returns available fuel brands.
- **Recommended load**: Call once per day and cache locally.

### 2) GetCountryGeographicRegions

- **Method**: `GET`
- **Path**: `/Subscriber/GetCountryGeographicRegions`
- **Query params**: `countryId` (required, int)
- **Purpose**: Returns a flattened region hierarchy.
- **Recommended load**: Call once per day and cache locally.

### 3) GetFuelTypes

- **Method**: `GET`
- **Path**: `/Subscriber/GetCountryFuelTypes`
- **Query params**: `countryId` (required, int)
- **Purpose**: Returns fuel type IDs and names.
- **Recommended load**: Call once per day and cache locally.

### 4) GetFullSiteDetails

- **Method**: `GET`
- **Path**: `/Subscriber/GetFullSiteDetails`
- **Query params**:
  - `countryId` (required, int; `21` = Australia)
  - `geoRegionLevel` (required, int)
  - `geoRegionId` (required, int)
- **Purpose**: Returns site details for the requested region.
- **Subscription note**: Returns only data the Data Consumer is subscribed to.
- **Recommended load**: Call once per day and cache locally.

### 5) GetSitesPrices

- **Method**: `GET`
- **Path**: `/Price/GetSitesPrices`
- **Query params**:
  - `countryId` (required, int; `21` = Australia)
  - `geoRegionLevel` (required, int)
  - `geoRegionId` (required, int)
- **Purpose**: Returns fuel prices for sites in the requested region.
- **Subscription note**: Returns only data the Data Consumer is subscribed to.
- **Rate guidance**: Do not call more than once per minute.

## Postman cross-check notes

- The Postman collection item is named `GetSitePrices`, but its URL path is `/Price/GetSitesPrices`.
- For implementation and tests, treat the URL path as authoritative.
- Postman responses are not populated (`response: []`), so response-shape examples should be validated in live API testing.

## Suggested Polling Pattern

- Once daily:
  - `GetBrands`
  - `GetCountryGeographicRegions`
  - `GetFuelTypes`
  - `GetFullSiteDetails`
- Frequent price sync:
  - `GetSitesPrices` at most once per minute

## Support

- `support@fuelpricesqld.com.au`
- `(07) 3858 0027`
