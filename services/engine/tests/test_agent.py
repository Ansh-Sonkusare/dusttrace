"""Dust Response Agent: one test per dust rule D1-D10, plus the guard rails."""

import pandas as pd

from dusttrace import agent

NOW = pd.Timestamp("2026-11-12 12:30", tz="UTC")  # 18:00 IST
SPIKE = [NOW + pd.Timedelta(hours=h) for h in (13, 14, 15)]  # 07:00-09:00 IST tomorrow


def ctx(**kw):
    base = dict(site_id="A", name="Metro Line 7A excavation", activity="excavation", has_sensor=True,
                has_relay=True, trust=90.0, now=NOW)
    return agent.SiteContext(**{**base, **kw})


def actions(decision, which="final"):
    return {a.action: a for a in getattr(decision, which)}


def test_quiet_site_opens_no_case():
    assert agent.decide(ctx()) is None


def test_d1_single_signal_gets_no_enforcement():
    d = agent.decide(ctx(site_id="D", has_sensor=False, has_relay=False, trust=None))
    acts = actions(d)
    assert "REQUEST_SPOT_CHECK" in acts and acts["REQUEST_SPOT_CHECK"].rule == "D1"
    assert not {"ADD_TO_INSPECTION", "REGISTER_UNSENSORED_SITE", "ISSUE_NOTICE"} & set(acts)
    assert "D1" in d.what_changed and "an officer spot check" in acts["REQUEST_SPOT_CHECK"].reason


def test_d2_spike_issues_windows_and_schedules_mist_90_min_early():
    d = agent.decide(ctx(spike_hours=SPIKE, spike_receptors=["St. Xavier's School"]))
    acts = actions(d)
    assert acts["ISSUE_SAFE_WORK_WINDOW"].route == "auto" and acts["ISSUE_SAFE_WORK_WINDOW"].rule == "D2"
    mist = acts["SCHEDULE_MIST"]
    assert mist.route == "auto" and mist.at == SPIKE[0] - pd.Timedelta(minutes=90)


def test_d2_without_a_relay_asks_the_site_to_pre_wet():
    acts = actions(agent.decide(ctx(has_relay=False, spike_hours=SPIKE, spike_receptors=["School"])))
    assert acts["SCHEDULE_MIST"].route == "site" and acts["PRE_WET_SITE"].route == "site"


def test_d3_school_downwind_in_avoid_window_is_alerted():
    acts = actions(agent.decide(ctx(sensitive_avoid=[(SPIKE[0], "St. Xavier's School")])))
    assert acts["ALERT_RECEPTOR"].rule == "D3" and acts["ALERT_RECEPTOR"].route == "auto"
    assert "St. Xavier's School" in acts["ALERT_RECEPTOR"].reason
    assert "NOTIFY_RESIDENTS" in acts


def test_d4_hot_sensor_triggers_mist_now_then_pause():
    acts = actions(agent.decide(ctx(sensor_hot_hours=1)))
    assert acts["TRIGGER_MIST_NOW"].rule == "D4" and acts["TRIGGER_MIST_NOW"].route == "auto"
    assert "PAUSE_DUSTY_TASK" not in acts
    acts = actions(agent.decide(ctx(sensor_hot_hours=2, has_relay=False)))
    assert acts["TRIGGER_MIST_NOW"].route == "site" and acts["PAUSE_DUSTY_TASK"].route == "site"


def test_d5_untrusted_sensor_is_flagged_and_inspected():
    acts = actions(agent.decide(ctx(trust=28.0)))
    assert acts["FLAG_SENSOR_FOR_AUDIT"].route == "auto" and acts["FLAG_SENSOR_FOR_AUDIT"].rule == "D5"
    assert acts["ADD_TO_INSPECTION"].route == "L1" and acts["ADD_TO_INSPECTION"].status == "proposed"


def test_d6_unsensored_site_with_two_signals_is_registered():
    d = agent.decide(ctx(site_id="D", has_sensor=False, has_relay=False, trust=None, citizen_reports=2))
    acts = actions(d)
    assert acts["REGISTER_UNSENSORED_SITE"].route == "L1" and acts["REGISTER_UNSENSORED_SITE"].rule == "D6"
    assert acts["ADD_TO_INSPECTION"].route == "L1"


def test_d7_unanswered_request_escalates_and_nothing_is_assumed():
    overdue = [{"action": "REQUEST_SITE_PHOTO", "deadline": NOW - pd.Timedelta(hours=1)}]
    d = agent.decide(ctx(spike_hours=SPIKE, spike_receptors=["School"], pending_requests=overdue))
    acts = actions(d)
    assert acts["ADD_TO_INSPECTION"].rule == "D7"
    assert "none" in d.what_changed.lower() and "assumed" in d.what_changed.lower()
    assert d.expired == ["REQUEST_SITE_PHOTO"]


def test_d8_repeat_exceedances_issue_a_notice():
    acts = actions(agent.decide(ctx(exceedances_7d=3, citizen_reports=1)))
    assert acts["ISSUE_NOTICE"].route == "L1" and acts["ISSUE_NOTICE"].rule == "D8"
    acts = actions(agent.decide(ctx(ignored_windows=2, citizen_reports=1)))
    assert "ISSUE_NOTICE" in acts


def test_d8_on_one_signal_waits_for_evidence():
    acts = actions(agent.decide(ctx(exceedances_7d=3)))
    assert "ISSUE_NOTICE" not in acts and "REQUEST_SITE_PHOTO" in acts


def test_d9_stop_work_is_only_ever_a_proposal_to_l2():
    acts = actions(agent.decide(ctx(exceedances_7d=4, citizen_reports=1, confirmed_violation=True,
                                    sensitive_avoid=[(SPIKE[0], "Nanavati Hospital")])))
    stop = acts["RECOMMEND_STOP_WORK"]
    assert stop.route == "L2" and stop.rule == "D9" and stop.status == "proposed"
    assert "RECOMMEND_STOP_WORK" not in actions(agent.decide(ctx(exceedances_7d=4, citizen_reports=1)))


def test_d10_non_construction_cause_is_referred_with_no_site_action():
    d = agent.decide(ctx(spike_hours=SPIKE, spike_receptors=["School"], non_construction=True))
    acts = actions(d)
    assert acts["REFER_NON_CONSTRUCTION"].rule == "D10"
    assert d.hypotheses[0][0] == "non_construction"
    assert not {"SCHEDULE_MIST", "PAUSE_DUSTY_TASK", "ISSUE_NOTICE"} & set(acts)


def test_every_action_comes_from_the_catalog_and_cites_a_rule():
    d = agent.decide(ctx(trust=30.0, spike_hours=SPIKE, spike_receptors=["School"], sensor_hot_hours=2,
                         sensitive_avoid=[(SPIKE[0], "School")], exceedances_7d=3, citizen_reports=1))
    for a in d.initial + d.final:
        assert (a.type, a.route_options) == agent.CATALOG[a.action][:2]
        assert a.route in a.route_options and a.rule and a.reason
    assert "UPDATE_DUST_SCORE" in actions(d)


def test_hypotheses_are_probabilities():
    d = agent.decide(ctx(trust=30.0, spike_hours=SPIKE, spike_receptors=["School"]))
    assert abs(sum(p for _, p in d.hypotheses) - 1) < 0.005  # rounded to 3 dp
    assert d.hypotheses == sorted(d.hypotheses, key=lambda h: -h[1])


def test_d6_satellite_change_is_a_second_signal_for_an_unsensored_site():
    d = agent.decide(ctx(site_id="D", has_sensor=False, has_relay=False, trust=None, satellite_active=True))
    acts = actions(d)
    assert "satellite change" in d.signals
    assert acts["REGISTER_UNSENSORED_SITE"].rule == "D6" and "REQUEST_SPOT_CHECK" not in acts


def test_a_site_whose_feed_is_not_connected_is_not_treated_as_unmonitored():
    d = agent.decide(ctx(site_id="osm-way-1", has_sensor=False, sensor_known=False, has_relay=False, trust=None))
    assert d is None  # nothing triggers: unknown is not "no monitor"
    d = agent.decide(ctx(site_id="osm-way-1", has_sensor=False, sensor_known=False, has_relay=False, trust=None,
                         sensitive_avoid=[(SPIKE[0], "School")]))
    assert "unsensored_site" not in d.triggers and "site registry" not in d.signals


# F10 playbook (issue #34): cause from the PM10/PM2.5 signature, and the fix sent to the site.
RECEPTORS = ["Homes for about 900 people (estimated)"]


def top(d):
    return d.hypotheses[0][0]


def test_coarse_dust_in_working_hours_points_to_digging_or_demolition():
    d = agent.decide(ctx(activity="structure", spike_hours=SPIKE, spike_receptors=RECEPTORS, pm_signature="coarse_work"))
    base = agent.decide(ctx(activity="structure", spike_hours=SPIKE, spike_receptors=RECEPTORS))
    h, b = dict(d.hypotheses), dict(base.hypotheses)
    assert h["dry_excavation"] > b["dry_excavation"] and h["demolition"] > b["demolition"]
    assert "coarse" in d.what_changed.lower() or any("coarse" in a.reason.lower() for a in d.final)


def test_coarse_dust_at_night_points_to_truck_trackout_and_orders_a_wheel_wash():
    d = agent.decide(ctx(activity="excavation", spike_hours=SPIKE, spike_receptors=RECEPTORS, pm_signature="coarse_night"))
    assert top(d) == "truck_trackout"
    a = actions(d)["ORDER_WHEEL_WASH"]
    assert a.route == "site" and a.rule == "F10" and a.status == "sent" and "night" in a.reason


def test_fine_dust_leans_to_a_non_construction_source_without_dropping_site_actions():
    d = agent.decide(ctx(spike_hours=SPIKE, spike_receptors=RECEPTORS, pm_signature="fine"))
    base = agent.decide(ctx(spike_hours=SPIKE, spike_receptors=RECEPTORS))
    assert dict(d.hypotheses)["non_construction"] > dict(base.hypotheses)["non_construction"]
    assert "REFER_NON_CONSTRUCTION" not in actions(d)  # D10 still needs evidence beyond one station
    assert "ISSUE_SAFE_WORK_WINDOW" in actions(d)


def test_uncovered_debris_gets_a_cover_order_with_a_two_hour_deadline():
    d = agent.decide(ctx(activity="debris", has_sensor=True, sensor_hot_hours=1))
    assert top(d) == "uncovered_debris"
    a = actions(d)["ORDER_COVER_DEBRIS"]
    assert a.rule == "F10" and a.route == "site" and a.deadline == NOW + pd.Timedelta(hours=2)


def test_dry_windy_day_ahead_means_pre_wet_even_without_a_spike():
    windy = [NOW + pd.Timedelta(hours=h) for h in (14, 15)]
    d = agent.decide(ctx(activity="excavation", dry_windy_hours=windy))
    assert d is not None and "dry_windy" in d.triggers
    a = actions(d)["PRE_WET_SITE"]
    assert a.rule == "F10" and "wind" in a.reason.lower()
    assert agent.decide(ctx(activity="structure", dry_windy_hours=windy)) is None  # finishing work raises little dust


def test_playbook_actions_are_dropped_for_a_non_construction_source():
    d = agent.decide(ctx(activity="debris", sensor_hot_hours=1, non_construction=True))
    assert not {"ORDER_COVER_DEBRIS", "ORDER_WHEEL_WASH", "PRE_WET_SITE"} & set(actions(d))


def test_a_node_at_the_receptor_is_a_second_signal_that_unlocks_enforcement():
    base = dict(site_id="D", has_sensor=False, has_relay=False, trust=None)  # one signal: the site registry
    alone = actions(agent.decide(ctx(**base)))
    assert "REQUEST_SPOT_CHECK" in alone and "ADD_TO_INSPECTION" not in alone  # D1 holds enforcement back
    d = agent.decide(ctx(**base, receptor_node_hot=True))
    assert "receptor monitor" in d.signals
    assert "ADD_TO_INSPECTION" in actions(d) and "REQUEST_SPOT_CHECK" not in actions(d)


# Issue #56: D8, D9 and D10 on measured evidence, the PRD's other triggers, and closing with no action.
DAYS = [{"date": f"2026-11-{d:02d}", "station": "Chakala", "ts": NOW - pd.Timedelta(days=12 - d), "pm10": 140.0 + d,
         "pm25": 50.0, "background": 60.0, "added": 22.0, "shared_with": d % 2, "wind_dir": 250, "wind_speed": 2.1,
         "hours": [{}, {}], "cause": c}
        for d, c in ((7, "coarse"), (8, None), (10, "coarse"))]


def test_d8_notice_cites_the_measured_station_hours_and_winds_behind_it():
    d = agent.decide(ctx(exceedances_7d=3, exceedance_days=DAYS, citizen_reports=1))
    n = actions(d)["ISSUE_NOTICE"]
    assert (n.route, n.rule, n.status) == ("L1", "D8", "proposed") and d.state == "APPROVAL_ROUTING"
    assert "3 days" in n.reason and "Chakala" in n.reason and "147 µg/m³" in n.reason and "250°" in n.reason
    assert "against 60 µg/m³ at the other stations" in n.reason and "about 22 from this site's plume" in n.reason
    assert "(2 hours)" in n.reason and "shared with 1 other site" in n.reason


def test_d1_the_plume_model_and_station_attribution_are_one_line_of_evidence():
    # Both only say the wind put the site upwind; neither shows it was working. No notice on that alone.
    d = agent.decide(ctx(exceedances_7d=3, exceedance_days=DAYS, spike_hours=SPIKE, spike_receptors=["School"]))
    assert {"plume model", "station attribution"} <= set(d.signals)
    acts = actions(d)
    assert "ISSUE_NOTICE" not in acts and "REQUEST_SITE_PHOTO" in acts
    assert "ISSUE_NOTICE" in actions(agent.decide(ctx(exceedances_7d=3, satellite_active=True)))


def test_d8_two_ignored_windows_with_a_second_signal_issue_a_notice():
    acts = actions(agent.decide(ctx(ignored_windows=2, satellite_active=True)))
    assert acts["ISSUE_NOTICE"].rule == "D8" and "2 ignored Safe-Work Windows" in acts["ISSUE_NOTICE"].reason
    assert "ISSUE_NOTICE" not in actions(agent.decide(ctx(ignored_windows=1, satellite_active=True)))


def test_d9_needs_an_officer_confirmed_violation_d8_and_receptor_exposure():
    full = dict(exceedances_7d=3, confirmed_violation=True, sensitive_avoid=[(SPIKE[0], "Nanavati Hospital")])
    stop = actions(agent.decide(ctx(**full)))["RECOMMEND_STOP_WORK"]
    assert (stop.route, stop.rule, stop.status) == ("L2", "D9", "proposed")
    for missing in ({"exceedances_7d": 2}, {"confirmed_violation": False, "citizen_reports": 1}, {"sensitive_avoid": []}):
        assert "RECOMMEND_STOP_WORK" not in actions(agent.decide(ctx(**{**full, **missing}))), missing


def test_d9_counts_a_node_reading_at_a_receptor_as_exposure():
    d = agent.decide(ctx(exceedances_7d=3, confirmed_violation=True, receptor_node_hot=True))
    assert actions(d)["RECOMMEND_STOP_WORK"].route == "L2"


def test_d10_drops_the_notice_and_every_site_action_and_refers_with_the_evidence():
    fine = [{**x, "cause": "fine"} for x in DAYS]
    d = agent.decide(ctx(exceedances_7d=3, exceedance_days=fine, citizen_reports=1, confirmed_violation=True,
                         sensitive_avoid=[(SPIKE[0], "School")], spike_hours=SPIKE, spike_receptors=["School"],
                         non_construction=True))
    acts = actions(d)
    assert "ISSUE_NOTICE" in actions(d, "initial")  # what D8 alone would have done
    assert not {"ISSUE_NOTICE", "RECOMMEND_STOP_WORK", "ADD_TO_INSPECTION"} & set(acts)
    assert not {a.action for a in d.final} & agent.SITE_ACTIONS
    ref = acts["REFER_NON_CONSTRUCTION"]
    assert (ref.route, ref.rule, ref.status) == ("L1", "D10", "proposed") and "PM2.5" in ref.reason and "Chakala" in ref.reason


def test_d10_after_the_referral_is_approved_the_case_closes_with_no_action():
    d = agent.decide(ctx(exceedances_7d=3, citizen_reports=1, non_construction=True, referred=True))
    acts = actions(d)
    close = acts["CLOSE_NO_ACTION"]
    assert (close.route, close.rule, close.status, close.type) == ("auto", "D10", "done", "close")
    assert "REFER_NON_CONSTRUCTION" not in acts and d.state == "DONE"
    # anything still open for an officer keeps the case open
    overdue = [{"action": "REQUEST_SITE_PHOTO", "deadline": NOW - pd.Timedelta(hours=1)}]
    d = agent.decide(ctx(exceedances_7d=3, non_construction=True, referred=True, pending_requests=overdue))
    assert "CLOSE_NO_ACTION" not in actions(d) and d.state != "DONE"


def test_a_node_reading_at_a_school_or_hospital_and_a_satellite_find_are_triggers():
    assert "node_at_school_or_hospital" in agent.decide(ctx(sensitive_node_hot=True, receptor_node_hot=True)).triggers
    assert agent.decide(ctx(receptor_node_hot=True)) is None  # a node at homes is evidence, not a trigger
    assert "satellite_find" in agent.decide(ctx(satellite_active=True)).triggers


def test_d1_a_trigger_on_one_signal_still_gets_no_enforcement():
    for one in ({"satellite_active": True}, {"exceedances_7d": 5}, {"sensitive_node_hot": True, "receptor_node_hot": True}):
        d = agent.decide(ctx(site_id="osm-way-1", has_sensor=False, sensor_known=False, has_relay=False, trust=None, **one))
        assert not {a.action for a in d.final} & agent.ENFORCEMENT_FROM_CAUSE, one


def test_d1_a_missing_monitor_says_nothing_about_what_caused_the_dust():
    # Demo site D has no monitor ("site registry"). That supports registering it (D6), not a notice (D8).
    d = agent.decide(ctx(site_id="D", has_sensor=False, has_relay=False, trust=None, exceedances_7d=3, exceedance_days=DAYS))
    acts = actions(d)
    assert "site registry" in d.signals and "ISSUE_NOTICE" not in acts and "REQUEST_SPOT_CHECK" in acts
    assert acts["REGISTER_UNSENSORED_SITE"].rule == "D6"
    assert "station attribution" in acts["REQUEST_SPOT_CHECK"].reason
    d = agent.decide(ctx(site_id="D", has_sensor=False, has_relay=False, trust=None, exceedances_7d=3, citizen_reports=1))
    assert "ISSUE_NOTICE" in actions(d)
