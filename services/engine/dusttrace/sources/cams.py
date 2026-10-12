"""Copernicus CAMS air quality via the Open-Meteo Air Quality API (no key).

Hourly PM10 and PM2.5 from the CAMS global model for any point, past and forecast. It is model
output at about 0.4° resolution, not a measurement: DustTrace stores it separately (`cams_hourly`)
and uses it, corrected against each real station, only to fill hours when the CPCB feed is down.
Docs: https://open-meteo.com/en/docs/air-quality-api
"""

from __future__ import annotations

import httpx
import pandas as pd

from . import http

URL = "https://air-quality-api.open-meteo.com/v1/air-quality"


def parse(payload, station_ids: list[str]) -> pd.DataFrame:
    """One payload per point (a list for several points, an object for one) -> station_id, ts, pm10, pm25."""
    items = payload if isinstance(payload, list) else [payload]
    frames = []
    for sid, item in zip(station_ids, items):
        h = item.get("hourly") or {}
        if not h.get("time"):
            continue
        frames.append(pd.DataFrame({
            "station_id": sid,
            "ts": pd.to_datetime(h["time"], utc=True),
            "pm10": pd.to_numeric(pd.Series(h.get("pm10")), errors="coerce"),
            "pm25": pd.to_numeric(pd.Series(h.get("pm2_5")), errors="coerce"),
        }))
    if not frames:
        return pd.DataFrame(columns=["station_id", "ts", "pm10", "pm25"])
    return pd.concat(frames, ignore_index=True)


def fetch(stations: list[dict], start: str, end: str, client: httpx.Client | None = None,
          batch: int = 10) -> pd.DataFrame:
    """CAMS at each station's position for [start, end] (dates, YYYY-MM-DD, UTC)."""
    c = client or httpx.Client(timeout=90)
    frames = []
    for i in range(0, len(stations), batch):
        chunk = stations[i:i + batch]
        r = http.get(c, URL, params={
            "latitude": ",".join(str(s["lat"]) for s in chunk),
            "longitude": ",".join(str(s["lon"]) for s in chunk),
            "hourly": "pm10,pm2_5", "start_date": start, "end_date": end, "timezone": "UTC",
        })
        frames.append(parse(r.json(), [s["id"] for s in chunk]))
    return pd.concat(frames, ignore_index=True) if frames else parse([], [])
