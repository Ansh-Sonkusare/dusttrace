import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from dusttrace import forecast, plume, windows
from dusttrace.config import Settings
from dusttrace.sources import openaq, openmeteo, overpass, synthetic

FIX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


# ---------- sources ----------

def test_openmeteo_parse():
    df = openmeteo.parse_hourly(load("openmeteo.json"))
    assert list(df.columns[:3]) == ["ts", "temp", "rh"]
    assert len(df) == 3
    assert str(df["ts"].dt.tz) == "UTC"
    assert df["blh"].tolist() == [210, 180, 150]


def test_openaq_parse_locations_keeps_pm_sensors_only():
    locs = openaq.parse_locations(load("openaq_locations.json"))
    assert len(locs) == 1
    assert locs[0]["id"] == "openaq-3409360"
    assert locs[0]["sensors"] == {"pm10": 11111, "pm25": 11112}


def test_openaq_parse_hours_drops_bad_values():
    df = openaq.parse_hours(load("openaq_hours.json"))
    assert df["value"].tolist() == [142.5, 120.0]


def test_overpass_parse():
    recs = overpass.parse(load("overpass.json"))
    assert [r["kind"] for r in recs] == ["school", "hospital"]
    assert recs[1]["lat"] == 19.12


# ---------- plume ----------

MET_NIGHT = plume.Met(wind_speed=1.2, wind_dir=90, blh=200, hour_ist=6.0)   # calm, from the east
MET_DAY = plume.Met(wind_speed=4.0, wind_dir=270, blh=1200, hour_ist=14.0)  # breezy, from the west


def test_concentration_falls_with_distance_and_off_axis():
    q = plume.emission_g_s(6000, "demolition")
    near = plume.concentration(np.array([200.0]), np.array([0.0]), q, MET_NIGHT, 77)[0]
    far = plume.concentration(np.array([1000.0]), np.array([0.0]), q, MET_NIGHT, 77)[0]
    side = plume.concentration(np.array([200.0]), np.array([300.0]), q, MET_NIGHT, 77)[0]
    upwind = plume.concentration(np.array([-200.0]), np.array([0.0]), q, MET_NIGHT, 77)[0]
    assert near > far > 0
    assert side < near
    assert upwind == 0


def test_calm_shallow_hours_are_worse_than_breezy_afternoons():
    q = plume.emission_g_s(6000, "demolition")
    x, y = np.array([500.0]), np.array([0.0])
    assert plume.concentration(x, y, q, MET_NIGHT, 77)[0] > 5 * plume.concentration(x, y, q, MET_DAY, 77)[0]


def test_plume_frame_round_trip_and_direction():
    lat0, lon0 = 19.11, 72.86
    # Wind from the east carries dust west: a point due west should be downwind (x > 0).
    x, y = plume.to_plume_frame(lat0, lon0, lat0, lon0 - 0.005, MET_NIGHT)
    assert x > 0 and abs(y) < 1
    lat, lon = plume.from_plume_frame(lat0, lon0, 300, 50, MET_NIGHT)
    x2, y2 = plume.to_plume_frame(lat0, lon0, lat, lon, MET_NIGHT)
    assert x2 == pytest.approx(300, abs=0.5) and y2 == pytest.approx(50, abs=0.5)


def test_footprint_polygon_is_closed_and_points_downwind():
    fp = plume.footprint(19.11, 72.86, plume.emission_g_s(6000, "demolition"), MET_NIGHT, 77, threshold=25)
    assert fp.ring[0] == fp.ring[-1]
    assert fp.length_m > 200
    lons = [p[0] for p in fp.ring]
    assert min(lons) < 72.86 - 0.002  # extends west


# ---------- Safe-Work Windows ----------

def _settings():
    return Settings(database_url="", openaq_api_key=None, ward_id="K-East")


def test_school_downwind_triggers_avoid_and_clear_afternoon_is_go():
    sites = pd.DataFrame([{"id": "A", "name": "A", "activity": "demolition", "lat": 19.11, "lon": 72.86, "area_m2": 6000}])
    recs = pd.DataFrame([{"id": "s", "name": "West School", "kind": "school", "lat": 19.11, "lon": 72.855, "population": 1000}])
    wx = pd.DataFrame({
        "ts": pd.to_datetime(["2026-10-12T00:30Z", "2026-10-12T09:00Z"]),  # 06:00 and 14:30 IST
        "wind_speed": [1.2, 4.0], "wind_dir": [90, 270], "blh": [200, 1200],
    })
    hours = windows.evaluate(sites, recs, wx, pd.Series(dtype=float), _settings())
    assert [h.status for h in hours] == ["avoid", "go"]
    assert "West School" in hours[0].reason
    assert hours[0].exposed_people == 1000


# ---------- forecast ----------

def test_forecast_beats_persistence_on_synthetic_year():
    end = pd.Timestamp("2026-10-01T00:00Z")
    wx = synthetic.weather(end - pd.Timedelta(days=400), end + pd.Timedelta(hours=72))
    rd = synthetic.readings(wx[wx["ts"] <= end], ["s1", "s2"])
    model = forecast.train(rd, wx, horizon=24)
    m = model.metrics
    assert m["mae_model"] < m["mae_persistence"]
    fc = forecast.predict(model, rd, wx, end, horizon=24)
    ward = fc[fc["station_id"] == "ward"]
    assert len(ward) == 24
    assert (ward["pm10_lo"] <= ward["pm10"]).all() and (ward["pm10"] <= ward["pm10_hi"]).all()
    assert ward["p_exceed"].between(0, 1).all()
