import numpy as np
import pandas as pd
import pytest

from dusttrace import audit
from dusttrace.sources import synthetic

T0 = pd.Timestamp("2026-01-20 12:00", tz="UTC")  # winter, dry season
CENTRE = (19.1136, 72.8697)
STATION = audit.Station("s1", "Test station", 19.117, 72.866)  # about 1 km east of site A


@pytest.fixture(scope="module")
def env():
    wx = synthetic.weather(T0 - pd.Timedelta(days=15), T0)
    rd = synthetic.readings(wx, ["s1"])
    pm = rd.set_index("ts")["pm10"].interpolate(limit_direction="both")
    return wx, audit.Ambient((STATION,), pm.to_frame("s1"))


def spec(fault="none", sensor_id="A-1", **kw):
    kw.setdefault("calibrated_on", T0.floor("D") - pd.Timedelta(days=10))
    return audit.SensorSpec(sensor_id=sensor_id, site_id="A", site_lat=19.117, site_lon=72.856,
                            area_m2=8000, activity="excavation", fault=fault, **kw)


def run(env, fault, **kw):
    wx, amb = env
    s = spec(fault, **kw)
    sim = audit.simulate([s], amb, wx, T0)
    return audit.score(s, sim, amb, wx, T0)


def failed(result):
    return {name for name, c in result.checks.items() if not c["ok"]}


def test_healthy_sensor_is_trusted(env):
    r = run(env, "none")
    assert failed(r) == set()
    assert r.score == 100 and r.band == "trusted"


def test_flatline_is_caught(env):
    r = run(env, "flatline")
    assert "flatline" in failed(r)
    assert r.band != "trusted"


def test_dropout_is_caught(env):
    r = run(env, "dropout")
    assert "dropout" in failed(r)
    assert r.band != "trusted"


def test_too_clean_sensor_is_untrusted(env):
    r = run(env, "too_clean")
    assert {"neighbour", "placement"} <= failed(r)
    assert r.band == "untrusted" and r.score < 40
    assert any("downwind" in x for x in r.reasons)


def test_drift_is_caught(env):
    assert "drift" in failed(run(env, "drift"))


def test_humidity_bias_is_caught(env):
    assert "humidity" in failed(run(env, "rh_bias"))


def test_reasons_are_plain_sentences(env):
    r = run(env, "too_clean")
    assert r.reasons and all(x[0].isupper() and x.endswith(".") for x in r.reasons)


def test_simulated_readings_are_deterministic(env):
    wx, amb = env
    a = audit.simulate([spec()], amb, wx, T0)
    b = audit.simulate([spec()], amb, wx, T0 - pd.Timedelta(hours=3))
    both = a.merge(b, on=["sensor_id", "ts"])
    assert len(both) > 100 and (both["pm10_x"] - both["pm10_y"]).abs().max() < 1e-6


def test_checks_without_enough_data_pass_and_store_as_null(env):
    wx, amb = env
    s = spec("none")
    r = audit.score(s, audit.simulate([s], amb, wx, T0).iloc[0:0], amb, wx, T0)  # no readings at all
    assert r.checks["drift"]["value"] is None and r.checks["drift"]["ok"]
    assert r.checks["neighbour"]["value"] is None and r.checks["neighbour"]["ok"]
    assert not r.checks["dropout"]["ok"]  # but a silent sensor is still offline


# ---------- ambient from the nearest real station ----------

def test_sensor_is_built_from_its_nearest_station(env):
    wx, _ = env
    idx = pd.DatetimeIndex(wx["ts"])
    near = audit.Station("near", "Near station", 19.118, 72.858)
    far = audit.Station("far", "Far station", 19.20, 72.95)
    amb = audit.Ambient((far, near), pd.DataFrame({"near": 40.0, "far": 160.0}, index=idx))
    s = spec()
    sim = audit.simulate([s], amb, wx, T0)
    night = sim[audit._night(pd.DatetimeIndex(sim["ts"]))]
    assert night["pm10"].median() == pytest.approx(40, rel=0.1)
    assert amb.nearest(*s.position) == near


def _two_stations(wx):
    idx = pd.DatetimeIndex(wx["ts"])
    near = audit.Station("near", "Near station", 19.118, 72.858)
    far = audit.Station("far", "Far station", 19.20, 72.95)
    return idx, near, far, pd.DataFrame({"near": 40.0, "far": 160.0}, index=idx)


def test_a_station_that_stopped_reporting_is_not_the_sensors_station(env):
    wx, _ = env
    idx, near, far, pm = _two_stations(wx)
    pm.loc[idx > idx[0] + pd.Timedelta(days=4), "near"] = np.nan  # its PM10 channel went silent
    amb = audit.Ambient((near, far), pm)
    s = spec()
    assert amb.nearest(*s.position) == far
    sim = audit.simulate([s], amb, wx, T0)
    night = sim[audit._night(pd.DatetimeIndex(sim["ts"]))]
    assert night["pm10"].median() == pytest.approx(160, rel=0.1)  # never its last value carried forward


def test_hours_the_station_missed_come_from_the_next_station(env):
    wx, _ = env
    idx, near, far, pm = _two_stations(wx)
    gap = (idx > T0 - pd.Timedelta(hours=30)) & (idx <= T0 - pd.Timedelta(hours=18))
    pm.loc[gap, "near"] = np.nan
    station, series = audit.Ambient((near, far), pm).at(19.118, 72.858, idx)
    assert station == near
    assert (series[gap] == 160).all() and (series[~gap] == 40).all()


def test_the_ambient_says_where_each_hour_came_from(env):
    wx, _ = env
    idx, near, far, pm = _two_stations(wx)
    pm.loc[(idx > T0 - pd.Timedelta(hours=30)) & (idx <= T0 - pd.Timedelta(hours=18)), "near"] = np.nan  # 12 h
    pm.loc[(idx > T0 - pd.Timedelta(hours=10)) & (idx <= T0 - pd.Timedelta(hours=7)), ["near", "far"]] = np.nan  # 3 h
    week = pd.date_range(end=T0, periods=168, freq="h")
    assert audit.Ambient((near, far), pm).sources(near, week) == {
        "hours": 168, "measured": 153, "next_station": 12, "interpolated": 3}


# ---------- neighbour check on the same wind ----------

def _windy(env, from_station_share=0.4):
    """The test weather, with the wind either from the station's side (east) or from the sea (west)."""
    wx, amb = env
    wx = wx.copy()
    from_station = (np.arange(len(wx)) % 10) < 10 * from_station_share
    wx["wind_dir"] = np.where(from_station, 90.0, 270.0)
    wx["wind_speed"] = 3.0
    return wx, amb, from_station


def _readings(s, wx, amb, factor):
    st = amb.pm10["s1"].reindex(pd.DatetimeIndex(wx["ts"])).to_numpy()
    return pd.DataFrame({"sensor_id": s.sensor_id, "site_id": s.site_id, "ts": wx["ts"],
                         "pm10": st * factor, "pm25": st * factor * 0.4, "rh": wx["rh"], "fault": "none"})


def test_sensor_low_on_the_stations_wind_fails_and_names_the_station(env):
    wx, amb, from_station = _windy(env)
    s = spec()
    rd = _readings(s, wx, amb, np.where(from_station, 0.5, 1.1))  # low only when it breathes the station's air
    r = audit.score(s, rd, amb, wx, T0)
    assert not r.checks["neighbour"]["ok"]
    assert "Test station" in r.checks["neighbour"]["reason"]


def test_sensor_low_on_a_cleaner_wind_is_not_flagged(env):
    wx, amb, from_station = _windy(env)
    s = spec()
    rd = _readings(s, wx, amb, np.where(from_station, 1.1, 0.5))  # sea air reaches it before the station
    r = audit.score(s, rd, amb, wx, T0)
    assert r.checks["neighbour"]["ok"]


# ---------- working-hours signature tied to Sentinel-2 ----------

def _no_rise(env):
    wx, amb = env
    return wx, amb, _readings(spec(), wx, amb, 1.0)  # tracks the station exactly: no site dust at all


def test_no_rise_on_a_site_active_in_imagery_fails(env):
    wx, amb, rd = _no_rise(env)
    r = audit.score(spec(imagery="2026-01-14"), rd, amb, wx, T0)
    assert not r.checks["work_signature"]["ok"]
    assert "Sentinel-2" in r.checks["work_signature"]["reason"] and "14 Jan 2026" in r.checks["work_signature"]["reason"]


def test_no_rise_without_imagery_costs_nothing(env):
    wx, amb, rd = _no_rise(env)
    r = audit.score(spec(), rd, amb, wx, T0)
    c = r.checks["work_signature"]
    assert c["ok"] and c["imagery"] is None and c["value"] is not None  # measured, but not counted
    assert "work_signature" not in failed(r)


def test_working_site_active_in_imagery_passes(env):
    assert "work_signature" not in failed(run(env, "none", imagery="2026-01-14"))


# ---------- calibration date ----------

def test_sensor_calibrated_over_two_months_ago_fails(env):
    r = run(env, "none", calibrated_on=T0.floor("D") - pd.DateOffset(months=2, days=5))
    assert failed(r) == {"calibration"}
    assert "2 months" in r.checks["calibration"]["reason"]


def test_sensor_calibrated_last_month_passes(env):
    r = run(env, "none", calibrated_on=T0.floor("D") - pd.DateOffset(months=1))
    assert r.checks["calibration"]["ok"] and r.checks["calibration"]["value"] == 31
    assert r.checks["calibration"]["on"] == "2025-12-20"  # the date this audit used, kept with it


def test_a_calibration_date_after_the_audited_week_fails_as_unknown(env):
    r = run(env, "none", calibrated_on=T0.floor("D") + pd.Timedelta(days=3))
    c = r.checks["calibration"]
    assert not c["ok"] and c["value"] is None and "after the audited week" in c["reason"]


def test_simulated_calibration_is_monthly_and_fixed_in_time():
    a = audit.simulated_calibration("A-1", T0)
    assert T0 - pd.Timedelta(days=30) < a <= T0
    assert audit.simulated_calibration("A-1", T0 + pd.Timedelta(hours=5)) in (a, a + pd.Timedelta(days=30))
    assert audit.simulated_calibration("A-1", a + pd.Timedelta(days=29)) == a


# ---------- Isolation Forest on residuals against neighbours ----------

def test_dusttrace_nodes_join_the_neighbours_the_forest_compares_with(env):
    wx, amb = env
    s = spec()
    sim = audit.simulate([s], amb, wx, T0)
    alone = audit.residuals([s], sim, amb, wx, T0)
    assert (alone["r_peers"] == alone["r_station"]).all()  # no other sensor: the station stands in
    node = 2 * amb.pm10["s1"].rename("node-x").to_frame()
    with_node = audit.residuals([s], sim, amb, wx, T0, nodes=node)
    assert np.allclose(with_node["r_peers"], with_node["r_station"] - np.log(2), atol=1e-6)


def test_forest_flags_a_too_clean_sensor_and_not_a_healthy_one(env):
    wx, amb = env
    ref = audit.reference(amb, wx, T0, CENTRE)
    specs = [spec("none", "ok-1", bearing_deg=200), spec("too_clean", "bad-1", bearing_deg=200),
             spec("none", "ok-2", bearing_deg=300)]
    sim = audit.simulate(specs, amb, wx, T0)
    share, bar = audit.outlier_share(ref, audit.residuals(specs, sim, amb, wx, T0))
    assert share["bad-1"] > bar
    assert share["ok-1"] <= bar and share["ok-2"] <= bar


@pytest.fixture(scope="module")
def bench(env):
    wx, amb = env
    return audit.benchmark(amb, wx, T0, CENTRE)


def test_benchmark_reports_rules_forest_and_both(bench):
    assert bench["n"] == 50 and sum(bench["sensors"].values()) == 50 and bench["sensors"]["none"] == 9
    assert set(bench["methods"]) == {"rules", "forest", "both"}
    for v in bench["methods"].values():
        assert set(v["detected"]) == set(audit.FAULTS) and 0 <= v["precision"] <= 1 and 0 <= v["recall"] <= 1
    rules = bench["methods"]["rules"]
    assert rules["precision"] >= 0.9 and rules["recall"] >= 0.85
    assert bench["methods"]["both"]["recall"] >= max(rules["recall"], bench["methods"]["forest"]["recall"])
    assert bench["methods"]["forest"]["detected"]["too_clean"] == 1.0
    assert bench["imagery_active"] == 26  # every other fault rotation active in imagery: both cases scored
    assert bench["stations"] == {"s1": {"name": "Test station", "sensors": 50, "hours": 168, "measured": 168,
                                         "next_station": 0, "interpolated": 0}}


def test_a_humidity_fault_in_dry_air_never_shows_in_the_readings(env):
    wx, amb = env
    dry = wx.assign(rh=50.0)
    specs = [spec("rh_bias", "wet-1"), spec("flatline", "stuck-1")]
    shown = audit.fault_shown(audit.simulate(specs, amb, dry, T0), T0)
    assert shown == {"wet-1": False, "stuck-1": True}
    assert audit.fault_shown(audit.simulate(specs[:1], amb, wx, T0), T0) == {"wet-1": True}  # humid winter nights


def test_benchmark_counts_the_faults_that_showed(bench):
    assert set(bench["shown"]) == set(audit.FAULTS) - {"none"}
    assert all(0 <= bench["shown"][f] <= bench["sensors"][f] for f in bench["shown"])
    assert bench["shown"]["too_clean"] == bench["sensors"]["too_clean"]


def test_benchmark_is_reproducible(env, bench):
    wx, amb = env
    assert audit.benchmark(amb, wx, T0, CENTRE) == bench
