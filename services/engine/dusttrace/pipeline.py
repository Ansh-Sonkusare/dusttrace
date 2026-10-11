"""Ingest and run steps, wired together. Each step falls back to synthetic data if a live source fails."""

from __future__ import annotations

import logging
from datetime import timedelta

import pandas as pd

from . import db, forecast, windows
from .config import Settings, load_seed
from .sources import openaq, openmeteo, overpass, synthetic

log = logging.getLogger("dusttrace")


def now_hour() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC").floor("h")


def ingest(conn, settings: Settings, mode: str = "auto", days: int = 120) -> dict:
    """Load weather (history + 3-day forecast) and station readings. Returns what was loaded and how."""
    seed = load_seed()
    ward = seed["ward"]
    now = now_hour()
    report = {"weather": None, "readings": None}

    # Weather
    wx, wx_live = None, False
    if mode in ("auto", "live"):
        try:
            past = min(days, 92)
            wx = openmeteo.fetch_forecast(ward["center_lat"], ward["center_lon"], past_days=past, forecast_days=3)
            if days > 92:
                start = (now - timedelta(days=days)).date()
                end = (now - timedelta(days=90)).date()
                hist = openmeteo.fetch_archive(ward["center_lat"], ward["center_lon"], start, end)
                wx = pd.concat([hist, wx]).drop_duplicates("ts", keep="last").sort_values("ts")
            wx_live = True
        except Exception as e:  # network blocked, API down, etc.
            if mode == "live":
                raise
            log.warning("Open-Meteo unavailable (%s); using synthetic weather", e)
    if wx is None or wx.empty:
        wx = synthetic.weather(now - timedelta(days=days), now + timedelta(hours=72))
    n = db.write_weather(conn, ward["id"], wx, now, synthetic=not wx_live)
    report["weather"] = {"rows": n, "live": wx_live}

    # Readings
    rd_live = False
    total = 0
    if mode in ("auto", "live") and settings.openaq_api_key:
        try:
            stations = openaq.find_stations(settings.openaq_api_key, _expand(ward["bbox"], 0.04))
            for st in stations:
                db.upsert_station(conn, {**st, "source": "openaq"}, ward["id"])
                frames = {}
                for param, sensor_id in st["sensors"].items():
                    df = openaq.fetch_sensor_hours(settings.openaq_api_key, sensor_id,
                                                   (now - timedelta(days=days)).to_pydatetime(), now.to_pydatetime())
                    frames[param] = df.set_index("ts")["value"]
                if not frames:
                    continue
                merged = pd.DataFrame({"pm10": frames.get("pm10"), "pm25": frames.get("pm25")})
                merged = merged.reset_index().rename(columns={"index": "ts"})
                merged["station_id"] = st["id"]
                total += db.write_readings(conn, merged, synthetic=False)
            rd_live = total > 0
        except Exception as e:
            if mode == "live":
                raise
            log.warning("OpenAQ unavailable (%s); using synthetic readings", e)
    elif mode == "live":
        raise RuntimeError("OPENAQ_API_KEY is required for live readings")
    if not rd_live:
        hist_wx = wx[wx["ts"] <= now]
        ids = [s["id"] for s in seed["stations"]]
        total = db.write_readings(conn, synthetic.readings(hist_wx, ids), synthetic=True)
    report["readings"] = {"rows": total, "live": rd_live}
    return report


def load_receptors_osm(conn, settings: Settings) -> int:
    seed = load_seed()
    recs = overpass.fetch(seed["ward"]["bbox"])
    db.upsert_receptors(conn, recs, seed["ward"]["id"])
    conn.commit()
    return len(recs)


def run(conn, settings: Settings) -> dict:
    """Train, forecast 48 h, model plumes and issue Safe-Work Windows. Writes one `runs` row."""
    ward_id = settings.ward_id
    wx = db.read_frame(conn, "select ts, wind_speed, wind_dir, blh, temp, rh, precip, synthetic from weather_hourly where ward_id=%s order by ts", (ward_id,))
    rd = db.read_frame(conn, """select r.station_id, r.ts, r.pm10, r.synthetic from readings r
                                join stations s on s.id = r.station_id where s.ward_id=%s order by r.ts""", (ward_id,))
    if wx.empty or rd.empty:
        raise RuntimeError("No weather or readings yet. Run `dusttrace ingest` first.")
    for c in ["wind_speed", "wind_dir", "blh", "temp", "rh", "precip"]:
        wx[c] = wx[c].astype(float)
    rd["pm10"] = rd["pm10"].astype(float)
    wx["ts"] = pd.to_datetime(wx["ts"], utc=True)
    rd["ts"] = pd.to_datetime(rd["ts"], utc=True)

    # Use only stations with recent data.
    t0 = rd.dropna(subset=["pm10"])["ts"].max().floor("h")
    recent = rd[rd["ts"] > t0 - pd.Timedelta(hours=24)].groupby("station_id")["pm10"].count()
    active = recent[recent >= 6].index
    rd = rd[rd["station_id"].isin(active)]

    model = forecast.train(rd[["station_id", "ts", "pm10"]], wx, settings.horizon_hours, settings.exceed_threshold)
    fc = forecast.predict(model, rd[["station_id", "ts", "pm10"]], wx, t0, settings.horizon_hours)

    data_mode = _mode(wx["synthetic"].any(), wx["synthetic"].all(), rd["synthetic"].any(), rd["synthetic"].all())
    metrics = {**model.metrics, "stations": list(active)}
    run_id = db.create_run(conn, ward_id, t0.to_pydatetime(), data_mode, "lightgbm-direct-v1", metrics)
    db.write_forecasts(conn, run_id, fc)

    ward_fc = fc[fc["station_id"] == "ward"].set_index("ts")["p_exceed"]
    future = wx[(wx["ts"] > t0) & (wx["ts"] <= t0 + pd.Timedelta(hours=settings.horizon_hours))]
    sites = db.read_frame(conn, "select id, name, activity, lat, lon, area_m2 from sites where ward_id=%s", (ward_id,))
    recs = db.read_frame(conn, "select id, name, kind, lat, lon, population from receptors where ward_id=%s", (ward_id,))
    for c in ["lat", "lon", "area_m2"]:
        sites[c] = sites[c].astype(float)
    for c in ["lat", "lon"]:
        recs[c] = recs[c].astype(float)
    hours = windows.evaluate(sites, recs, future, ward_fc, settings)
    db.write_site_hours(conn, run_id, hours)
    conn.commit()

    counts = pd.Series([h.status for h in hours]).value_counts().to_dict()
    return {"run_id": run_id, "issued_at": t0.isoformat(), "data_mode": data_mode,
            "metrics": model.metrics, "window_counts": counts, "stations": list(active)}


def _mode(wx_any, wx_all, rd_any, rd_all) -> str:
    if not wx_any and not rd_any:
        return "live"
    if wx_all and rd_all:
        return "synthetic"
    return "mixed"


def _expand(bbox, d):
    return [bbox[0] - d, bbox[1] - d, bbox[2] + d, bbox[3] + d]
