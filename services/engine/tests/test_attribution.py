import numpy as np
import pandas as pd

from dusttrace import attribution, plume

T0 = pd.Timestamp("2026-01-20 00:00", tz="UTC")
STATION = {"id": "st", "name": "Chakala station", "lat": 19.11, "lon": 72.86}


def wx_from(deg, speed=2.0, hours=24, blh=400.0):
    ts = pd.date_range(T0 + pd.Timedelta(hours=1), periods=hours, freq="h", tz="UTC")
    return pd.DataFrame({"ts": ts, "wind_speed": speed, "wind_dir": float(deg), "blh": blh})


def p_high(wx, p=0.8):
    return pd.Series(p, index=pd.DatetimeIndex(wx["ts"]))


def site(id_, dlat=0.0, dlon=0.0, **kw):
    return {"id": id_, "name": f"Site {id_}", "lat": STATION["lat"] + dlat, "lon": STATION["lon"] + dlon, **kw}


def test_back_trajectory_runs_upwind():
    pts = attribution.back_trajectory(STATION["lat"], STATION["lon"], wx_from(90).iloc[:3])
    lons = [p[1] for p in pts]
    assert lons[0] == STATION["lon"] and all(b > a for a, b in zip(lons, lons[1:]))  # wind from the east: look east


def test_site_directly_upwind_outranks_one_off_axis():
    wx = wx_from(90)  # wind from the east
    sites = [site("up", dlon=0.01), site("side", dlat=0.01), site("down", dlon=-0.01)]
    exp = attribution.upwind_exposure(sites, [STATION], wx, p_high(wx))
    assert exp["up"] > 0.5 > exp["side"] and exp["down"] == 0


def test_no_spike_risk_means_no_upwind_exposure():
    wx = wx_from(90)
    exp = attribution.upwind_exposure([site("up", dlon=0.01)], [STATION], wx, p_high(wx, 0.1))
    assert exp["up"] == 0


def test_low_trust_raises_priority():
    ranked = attribution.rank([
        {"site_id": "A", "name": "A", "upwind": 0.5, "trust": 95, "has_sensor": True},
        {"site_id": "B", "name": "B", "upwind": 0.5, "trust": 30, "has_sensor": True},
    ])
    assert [r.site_id for r in ranked] == ["B", "A"]
    assert ranked[0].rank == 1 and ranked[0].score > ranked[1].score


def test_reasons_name_the_two_largest_components():
    ranked = attribution.rank([
        {"site_id": "D", "name": "Debris yard", "upwind": 0.9, "trust": None, "has_sensor": False,
         "reports": 0, "violations": 0, "upwind_station": "Chakala station", "upwind_hours": 7},
    ])
    r = ranked[0]
    assert len(r.reasons) == 2
    assert "upwind of Chakala station" in r.reasons[0] and "no dust monitor" in r.reasons[1]
    assert set(r.components) == {"upwind", "trust", "reports", "unsensored", "violations"}


def test_ranking_is_deterministic_on_ties():
    rows = [{"site_id": x, "name": x, "upwind": 0.2, "trust": 80, "has_sensor": True} for x in "CAB"]
    assert [r.site_id for r in attribution.rank(rows)] == ["A", "B", "C"]


def test_unknown_monitor_is_not_counted_as_missing():
    r = attribution.rank([{"site_id": "X", "name": "X", "upwind": 0, "trust": None, "has_sensor": False, "sensor_known": False}])[0]
    assert r.components["unsensored"] == 0 and r.score == 0


# D8 from measured data (issue #56): station hours above 100 µg/m³ to which the site's own plume, in the
# measured weather of that hour, added a material share.
NOW = pd.Timestamp("2026-10-07 12:00", tz="UTC")  # 17:30 IST


def measured_wx(deg=90.0, speed=2.0, days=10, **flags):
    ts = pd.date_range(end=NOW + pd.Timedelta(hours=48), periods=24 * days + 48, freq="h", tz="UTC")
    wx = pd.DataFrame({"ts": ts, "wind_speed": speed, "wind_dir": deg, "blh": 600.0, "synthetic": False,
                       "is_forecast": ts > NOW})
    for k, v in flags.items():
        wx[k] = v
    return wx


def readings(hours_ago, pm10=140.0, pm25=50.0, station="st", **flags):
    ts = [NOW - pd.Timedelta(hours=h) for h in hours_ago]
    df = pd.DataFrame({"station_id": station, "ts": ts, "pm10": pm10, "pm25": pm25, "synthetic": False, "filled": False})
    for k, v in flags.items():
        df[k] = v
    return df


def works(id_, dlat=0.0, dlon=0.0):
    return site(id_, dlat, dlon, area_m2=9000.0, activity="excavation")


UP = works("up", dlon=0.0025)  # about 260 m east of the station; the wind blows from the east


def test_a_measured_exceedance_counts_for_the_site_whose_plume_reached_the_station():
    sites = [UP, works("far", dlon=0.0285), works("down", dlon=-0.0025), works("side", dlat=0.009)]
    out = attribution.measured_exceedances(sites, [STATION], readings([5, 30]), measured_wx(), NOW)
    assert [h["ts"] for h in out["up"]] == [NOW - pd.Timedelta(hours=30), NOW - pd.Timedelta(hours=5)]
    h = out["up"][0]
    assert (h["station"], h["pm10"], h["wind_dir"], h["wind_speed"]) == ("Chakala station", 140.0, 90, 2.0)
    assert h["added"] >= attribution.ADDED_MIN
    assert out["far"] == [] and out["down"] == [] and out["side"] == []  # 3 km upwind adds next to nothing


def test_only_measured_readings_count_never_synthetic_or_cams_filled_hours():
    rd = pd.concat([readings([5], synthetic=True), readings([6], filled=True), readings([7], pm10=99.0)])
    assert attribution.measured_exceedances([UP], [STATION], rd, measured_wx(), NOW)["up"] == []


def test_only_measured_wind_counts_never_a_forecast_or_synthetic_wind():
    rd = readings([5])
    assert attribution.measured_exceedances([UP], [STATION], rd, measured_wx(is_forecast=True), NOW)["up"] == []
    assert attribution.measured_exceedances([UP], [STATION], rd, measured_wx(synthetic=True), NOW)["up"] == []
    gap = measured_wx()
    gap = gap[gap["ts"] != NOW - pd.Timedelta(hours=5)]  # no measured weather that hour: not guessed
    assert attribution.measured_exceedances([UP], [STATION], rd, gap, NOW)["up"] == []


def test_a_light_wind_hour_blames_no_site():
    # Below 1 m/s the hourly wind direction is too unsteady to say which side of a station a site sat on.
    for speed in (0.3, 0.8):
        assert attribution.measured_exceedances([UP], [STATION], readings([5]), measured_wx(speed=speed), NOW)["up"] == []
    assert attribution.measured_exceedances([UP], [STATION], readings([5]), measured_wx(speed=1.2), NOW)["up"]


def test_a_station_more_than_4_km_away_speaks_for_no_site():
    # A 30 ha demolition 5 km upwind, on a still night: the plume model alone would put 15+ µg/m³ on the station.
    big = site("big", dlon=0.0475, area_m2=300_000.0, activity="demolition")
    night = 15  # 02:30 IST
    met = plume.Met(1.2, 90.0, 600.0, plume.hour_ist(NOW - pd.Timedelta(hours=night)))
    x, y = plume.to_plume_frame(big["lat"], big["lon"], STATION["lat"], STATION["lon"], met)
    assert plume.concentration(np.array([x]), np.array([y]), plume.emission_g_s(300_000, "demolition"), met,
                               300_000 ** 0.5)[0] >= attribution.ADDED_MIN
    out = attribution.measured_exceedances([big], [STATION], readings([night]), measured_wx(speed=1.2), NOW)
    assert out["big"] == []


def test_a_station_hour_goes_only_to_the_sites_with_a_comparable_share():
    near = site("near", dlon=0.0025, area_m2=9000.0, activity="demolition")       # 260 m upwind
    far = site("far", dlon=0.0095, area_m2=60_000.0, activity="excavation")      # 1 km upwind, a smaller share
    twin = site("twin", dlat=0.0003, dlon=0.0025, area_m2=9000.0, activity="demolition")  # beside `near`
    out = attribution.measured_exceedances([near, far], [STATION], readings([5]), measured_wx(), NOW)
    assert len(out["near"]) == 1 and out["near"][0]["shared_with"] == 0
    assert out["far"] == []  # its plume added 15+ µg/m³ too, but less than half of what `near` added
    assert attribution.measured_exceedances([far], [STATION], readings([5]), measured_wx(), NOW)["far"]
    both = attribution.measured_exceedances([near, twin], [STATION], readings([5]), measured_wx(), NOW)
    assert both["near"][0]["shared_with"] == 1 and both["twin"][0]["shared_with"] == 1  # the evidence says so


def _network(**at_hour):
    """Station `st` and others over one hour, each given as station=pm10."""
    return pd.DataFrame({"station_id": list(at_hour), "ts": NOW - pd.Timedelta(hours=5),
                         "pm10": [float(v) for v in at_hour.values()], "pm25": [float(v) * 0.4 for v in at_hour.values()],
                         "synthetic": False})


def test_only_an_exceedance_that_stands_above_the_rest_of_the_network_is_local():
    local = attribution.local_exceedances(_network(st=150, a=60, b=70))
    assert list(local["station_id"]) == ["st"] and local["background"].iloc[0] == 65.0
    assert attribution.local_exceedances(_network(st=150, a=140, b=120)).empty  # city-wide haze, not a local source
    assert attribution.local_exceedances(_network(st=95, a=40, b=50)).empty     # not above 100 µg/m³
    assert attribution.local_exceedances(_network(st=150, a=60)).empty          # one other station can't tell


def test_nothing_after_now_or_before_the_last_seven_ist_days_is_counted():
    # 3 h after now; 07:30 IST six days ago (inside the 7 IST days); 22:30 IST seven days ago (outside)
    rd = readings([-3, 24 * 6 + 10, 24 * 6 + 19])
    out = attribution.measured_exceedances([UP], [STATION], rd, measured_wx(), NOW)
    assert [h["ts"] for h in out["up"]] == [NOW - pd.Timedelta(hours=24 * 6 + 10)]


def test_exceedance_days_are_counted_by_ist_date():
    # 19:00 and 23:00 UTC on Oct 5 fall on Oct 6 in IST (00:30 and 04:30); 08:00 UTC Oct 6 too.
    hours = [{"ts": pd.Timestamp(t, tz="UTC"), "pm10": p} for t, p in
             [("2026-10-05 17:00", 120), ("2026-10-05 19:00", 150), ("2026-10-06 08:00", 110)]]
    days = attribution.by_ist_day(hours)
    assert list(days) == ["2026-10-05", "2026-10-06"] and len(days["2026-10-06"]) == 2
