# Data sources: what works, and the fallback for station readings

Research for issue #12, October 2026. It was written while OpenAQ's CPCB feed had been stale since **2026-10-07 14:30 UTC** for every CPCB station around K-East. As of Oct 12, only the US consulate's AirNow monitor (PM2.5 only) was current.

## What the engine uses today

| Source | What | Access | Status (Oct 12, 2026) |
|---|---|---|---|
| OpenAQ v3 | Hourly PM10 and PM2.5 at the CPCB/MPCB/BMC CAAQMS stations, with history back to 2022 | Free key, 60 requests/min | **Works, but the CPCB feed stopped on Oct 7.** History from Aug 2025 is loaded: 11 stations, about 85k hours. |
| Open-Meteo | Hourly weather and boundary-layer height, forecast and archive | No key | Works from GitHub Actions. It rate-limits shared IPs (429), so requests retry. |
| Overpass (OSM) | Schools and hospitals | No key | Works through the kumi.systems mirror; overpass-api.de resets connections. |
| OpenFreeMap | Dark vector basemap | No key | Works. CARTO's basemaps now need an API key. |

The engine copes with the stale feed (`pipeline.anchor`). Real stations anchor the forecast only while their newest reading is under 6 h old; otherwise labelled sample stations do. The overview says when real readings stopped.

## Candidates for a second live source

### data.gov.in: "Real time Air Quality Index from various locations"
- **Endpoint:** `https://api.data.gov.in/resource/3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69?api-key=…&format=json&filters[city]=Mumbai`.
- **Fields:** `country, state, city, station, pollutant_id, last_update, pollutant_min, pollutant_max, pollutant_avg`. Per the community packages, `latitude` and `longitude` appear in newer records.
- **Values:** these are CPCB's AQI inputs, i.e. **24-hour min, max and average per pollutant**, refreshed hourly. They are not hourly concentrations.
- **Access:** a free key from a data.gov.in account. The public sample key returns at most 10 records. The resource page has said "API does not exist, request API" since April 2025, so the endpoint may need the team to request it.
- **Reachability:** the build sandbox could not reach `api.data.gov.in` (the connection was closed by the proxy). It still needs a test from GitHub Actions with a real key.
- **Fit:**
  - Good for a "current level" panel and for detecting when stations are live again.
  - Not a drop-in for the hourly lag features. Hourly values could be backed out by differencing successive 24-hour averages, but that needs an unbroken series and amplifies noise.

### CPCB CCR / AQI India portal (`airquality.cpcb.gov.in`, `app.cpcbccr.com`)
- This is the source OpenAQ itself scrapes, and it holds 15-minute data.
- It is undocumented and sometimes overloaded, and CEEW has written about how slow the portal is for data users.
- Station-level downloads are manual (CCR "Advanced search", CSV). That's useful for filling gaps by hand before the Dec 1 report, not for a live feed.
- It was not reachable from the build sandbox.

### SAFAR-Mumbai
- City forecasts and station readings on a public site, with no documented API.
- The PRD uses it as the baseline to beat, not as an input.

## Recommendation
1. **Keep OpenAQ as the hourly source.** The engine already resumes automatically when the feed catches up. After an outage longer than 3 days, run the "Hourly forecast" workflow by hand with a larger `days` to backfill.
2. **Get a data.gov.in key (5 minutes) and test it from Actions.** If the endpoint answers, add it as a "current 24-h level" source for the overview and the public page, labelled as 24-h averages.
3. **For the Round 2 report,** download CCR CSVs for K-East's stations from Oct 7 onwards if OpenAQ is still behind, and load them as real readings (`write_readings(..., synthetic=False)`).

## Sources
- [data.gov.in resource page](https://data.gov.in/resource/real-time-air-quality-index-various-locations)
- [datagovindia R package vignette (field list)](https://ftp.eenet.ee/pub/cran/web/packages/datagovindia/vignettes/datagovindia_vignette.html)
- [ListenData: Real-time AQI data from data.gov.in (sample output, 10-record sample key)](https://www.listendata.com/2022/07/pollution-in-india-real-time-aqi-data.html)
- [CEEW on CPCB data access and OpenAQ](https://www.ceew.in/blogs/indias-air-pollution-democratising-air-quality-data)
- [The Wire on CPCB monitoring blackouts (2025)](https://thewire.in/environment/grap-iii-comes-into-effect-day-after-delhis-air-monitoring-blackout)
