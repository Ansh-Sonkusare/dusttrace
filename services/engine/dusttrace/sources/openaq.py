"""OpenAQ v3: CPCB / MPCB station metadata and hourly PM10 / PM2.5.

Needs a free API key (https://explore.openaq.org/register), sent as the X-API-Key header.
Docs: https://docs.openaq.org/
"""

from __future__ import annotations

from datetime import datetime, timedelta

import httpx
import pandas as pd

from . import http

BASE = "https://api.openaq.org/v3"
PARAMS_WANTED = {"pm10", "pm25"}
# OpenAQ returns 500s for long ranges, so history is fetched in windows that fit one page (limit 1000).
WINDOW = timedelta(days=30)


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
            "last": ((loc.get("datetimeLast") or {}).get("utc")),
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


def find_stations(api_key: str, bbox: list[float], client: httpx.Client | None = None,
                  active_since: datetime | None = None) -> list[dict]:
    """Stations in the bbox. With `active_since`, drop those known to have stopped reporting before it."""
    c = _client(api_key, client)
    r = http.get(c, f"{BASE}/locations", params={"bbox": ",".join(str(x) for x in bbox), "limit": 100})
    stations = parse_locations(r.json())
    if active_since is not None:
        cutoff = pd.Timestamp(active_since)
        stations = [s for s in stations if s["last"] is None or pd.Timestamp(s["last"]) >= cutoff]
    return stations


def fetch_sensor_hours(api_key: str, sensor_id: int, start: datetime, end: datetime,
                       client: httpx.Client | None = None, max_pages: int = 5) -> pd.DataFrame:
    c = _client(api_key, client)
    frames = []
    lo = start
    while lo < end:
        hi = min(lo + WINDOW, end)
        for page in range(1, max_pages + 1):
            r = http.get(c, f"{BASE}/sensors/{sensor_id}/hours", params={
                "datetime_from": lo.isoformat(),
                "datetime_to": hi.isoformat(),
                "limit": 1000,
                "page": page,
            })
            df = parse_hours(r.json())
            if not df.empty:
                frames.append(df)
            if len(df) < 1000:
                break
        lo = hi
    if not frames:
        return pd.DataFrame(columns=["ts", "value"])
    return pd.concat(frames).drop_duplicates("ts").sort_values("ts")
