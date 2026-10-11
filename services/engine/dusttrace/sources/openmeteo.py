"""Open-Meteo weather: recent past + 3-day forecast (forecast API) and longer history (archive API).

No API key needed. Docs: https://open-meteo.com/en/docs and https://open-meteo.com/en/docs/historical-weather-api
"""

from __future__ import annotations

from datetime import date

import httpx
import pandas as pd

from . import http

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

HOURLY_VARS = [
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "wind_speed_10m",
    "wind_direction_10m",
    "boundary_layer_height",
]

RENAME = {
    "temperature_2m": "temp",
    "relative_humidity_2m": "rh",
    "precipitation": "precip",
    "wind_speed_10m": "wind_speed",
    "wind_direction_10m": "wind_dir",
    "boundary_layer_height": "blh",
}


def parse_hourly(payload: dict) -> pd.DataFrame:
    """Turn an Open-Meteo JSON payload into a UTC-indexed hourly frame."""
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    if not times:
        return pd.DataFrame(columns=["ts", *RENAME.values()])
    df = pd.DataFrame({"ts": pd.to_datetime(times, utc=True)})
    for src, dst in RENAME.items():
        df[dst] = pd.to_numeric(pd.Series(hourly.get(src, [None] * len(times))), errors="coerce")
    return df


def fetch_forecast(lat: float, lon: float, past_days: int = 92, forecast_days: int = 3,
                   client: httpx.Client | None = None) -> pd.DataFrame:
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join(HOURLY_VARS),
        "wind_speed_unit": "ms",
        "timezone": "UTC",
        "past_days": past_days,
        "forecast_days": forecast_days,
    }
    c = client or httpx.Client(timeout=30)
    r = http.get(c, FORECAST_URL, params=params)
    return parse_hourly(r.json())


def fetch_archive(lat: float, lon: float, start: date, end: date,
                  client: httpx.Client | None = None) -> pd.DataFrame:
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join(HOURLY_VARS),
        "wind_speed_unit": "ms",
        "timezone": "UTC",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
    }
    c = client or httpx.Client(timeout=60)
    r = http.get(c, ARCHIVE_URL, params=params)
    return parse_hourly(r.json())
