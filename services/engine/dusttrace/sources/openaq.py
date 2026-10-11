"""OpenAQ v3: CPCB / MPCB station metadata and hourly PM10 / PM2.5.

Needs a free API key (https://explore.openaq.org/register), sent as the X-API-Key header.
Docs: https://docs.openaq.org/
"""

from __future__ import annotations

from datetime import datetime

import httpx
import pandas as pd

BASE = "https://api.openaq.org/v3"
PARAMS_WANTED = {"pm10", "pm25"}


def _client(api_key: str, client: httpx.Client | None) -> httpx.Client:
    return client or httpx.Client(timeout=30, headers={"X-API-Key": api_key})


def parse_locations(payload: dict) -> list[dict]:
    """Stations with the sensor ids we care about. Tolerant of missing fields."""
    out = []
    for loc in payload.get("results") or []:
        coords = loc.get("coordinates") or {}
        lat, lon = coords.get("latitude"), coords.get("longitude")
        if lat is None or lon is None:
            continue
        sensors = {}
        for s in loc.get("sensors") or []:
            name = ((s.get("parameter") or {}).get("name") or "").lower()
            if name in PARAMS_WANTED and s.get("id") is not None:
                sensors[name] = s["id"]
        if not sensors:
            continue
        out.append({
            "id": f"openaq-{loc['id']}",
            "name": loc.get("name") or f"OpenAQ {loc['id']}",
            "lat": float(lat),
            "lon": float(lon),
            "sensors": sensors,
            "provider": ((loc.get("provider") or {}).get("name")),
        })
    return out


def parse_hours(payload: dict) -> pd.DataFrame:
    """Hourly sensor values -> frame of (ts, value). ts is the start of the hour, UTC."""
    rows = []
    for r in payload.get("results") or []:
        period = r.get("period") or {}
        start = ((period.get("datetimeFrom") or {}).get("utc"))
        val = r.get("value")
        if start is None or val is None:
            continue
        rows.append((start, float(val)))
    df = pd.DataFrame(rows, columns=["ts", "value"])
    if not df.empty:
        df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.floor("h")
        df = df[(df["value"] >= 0) & (df["value"] < 2000)]  # drop sensor junk
    return df


def find_stations(api_key: str, bbox: list[float], client: httpx.Client | None = None) -> list[dict]:
    c = _client(api_key, client)
    r = c.get(f"{BASE}/locations", params={"bbox": ",".join(str(x) for x in bbox), "limit": 100})
    r.raise_for_status()
    return parse_locations(r.json())


def fetch_sensor_hours(api_key: str, sensor_id: int, start: datetime, end: datetime,
                       client: httpx.Client | None = None, max_pages: int = 20) -> pd.DataFrame:
    c = _client(api_key, client)
    frames = []
    for page in range(1, max_pages + 1):
        r = c.get(f"{BASE}/sensors/{sensor_id}/hours", params={
            "datetime_from": start.isoformat(),
            "datetime_to": end.isoformat(),
            "limit": 1000,
            "page": page,
        })
        r.raise_for_status()
        df = parse_hours(r.json())
        if df.empty:
            break
        frames.append(df)
        if len(df) < 1000:
            break
    if not frames:
        return pd.DataFrame(columns=["ts", "value"])
    return pd.concat(frames).drop_duplicates("ts").sort_values("ts")
