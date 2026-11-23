"""Dust Response Agent (PRD F12): every trigger opens a case; a policy engine picks the actions.

The engine is deterministic and rule-based. Every action comes from the PRD's action catalog and
cites one of the dust rules D1-D10, with an approval route: auto, site (the site manager), L1 (ward
environment officer) or L2 (Assistant Commissioner). Guard rails carried over from the fraud agent:
- D1: no enforcement when the cause rests on one signal; ask for evidence first.
- D7: a request that isn't answered by its deadline escalates. No reply is ever assumed.
- D9: stop-work is only ever a proposal to L2, never automatic.
- D10: when a non-construction source is most likely, nothing is asked of the site; the case is referred.
Only this module creates actions (`decide`, and `verified_close` for a verified drop); nothing else in the
engine may.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

# action -> (type, allowed routes, default rule)
CATALOG: dict[str, tuple[str, tuple[str, ...], str]] = {
    "ISSUE_SAFE_WORK_WINDOW": ("preventive", ("auto",), "D2"),
    "SCHEDULE_MIST": ("preventive", ("auto", "site"), "D2"),
    "PRE_WET_SITE": ("preventive", ("site",), "D2"),
    "ALERT_RECEPTOR": ("preventive", ("auto",), "D3"),
    "NOTIFY_RESIDENTS": ("preventive", ("auto",), "D3"),
    "TRIGGER_MIST_NOW": ("corrective", ("auto", "site"), "D4"),
    "PAUSE_DUSTY_TASK": ("corrective", ("site",), "D4"),
    "ORDER_COVER_DEBRIS": ("corrective", ("site",), "F10"),
    "ORDER_WHEEL_WASH": ("corrective", ("site",), "F10"),
    "REQUEST_SITE_PHOTO": ("evidence", ("site",), "D1"),
    "REQUEST_SPOT_CHECK": ("evidence", ("L1",), "D1"),
    "FLAG_SENSOR_FOR_AUDIT": ("enforcement", ("auto",), "D5"),
    "ADD_TO_INSPECTION": ("enforcement", ("L1",), "D5"),
    "REGISTER_UNSENSORED_SITE": ("enforcement", ("L1",), "D6"),
    "ISSUE_NOTICE": ("enforcement", ("L1",), "D8"),
    "RECOMMEND_STOP_WORK": ("enforcement", ("L2",), "D9"),
    "REFER_NON_CONSTRUCTION": ("routing", ("L1",), "D10"),
    "UPDATE_DUST_SCORE": ("record", ("auto",), "every case"),
    "CLOSE_NO_ACTION": ("close", ("auto",), "D10"),
}
ENFORCEMENT_FROM_CAUSE = {"ADD_TO_INSPECTION", "REGISTER_UNSENSORED_SITE", "ISSUE_NOTICE", "RECOMMEND_STOP_WORK"}
SITE_ACTIONS = {a for a, (_, routes, _) in CATALOG.items() if "site" in routes} | {"ISSUE_SAFE_WORK_WINDOW"}
EVIDENCE_DEADLINE = pd.Timedelta(hours=3)
COVER_DEADLINE = pd.Timedelta(hours=2)   # F10: cover debris with green net within 2 hours
DUSTY_ACTIVITIES = {"excavation", "demolition", "debris"}
MIST_LEAD = pd.Timedelta(minutes=90)
# Both only say the wind put the site upwind (of a station, of a receptor); neither shows it was working.
# D1 counts them as one line of evidence.
WIND_ONLY = {"plume model", "station attribution"}
# A notice or stop-work (D8, D9) is about what caused the dust; a missing monitor says nothing about that.
NOT_A_CAUSE = {"site registry"}
# A node at a school shows the dust arrived, but only the wind and the plume tie it to this site, so for D8
# and D9 it is the same line of evidence as the other wind-only signals.
WIND_ONLY_FOR_CAUSE = WIND_ONLY | {"receptor monitor"}

CAUSES = ["dry_excavation", "demolition", "truck_trackout", "uncovered_debris", "sensor_fault",
          "non_construction", "weather_only"]
PRIORS = {
    "excavation": {"dry_excavation": 0.45, "truck_trackout": 0.25},
    "demolition": {"demolition": 0.5, "truck_trackout": 0.15},
    "debris": {"uncovered_debris": 0.5, "truck_trackout": 0.2},
    "structure": {"truck_trackout": 0.35, "dry_excavation": 0.15},
}


@dataclass
class SiteContext:
    """Everything the policy engine may look at for one site, as of `now`."""
    site_id: str
    name: str
    activity: str
    has_sensor: bool
    has_relay: bool
    trust: float | None
    now: pd.Timestamp
    spike_hours: list = field(default_factory=list)       # forecast hours with P(PM10 > 100) >= 0.6 ...
    spike_receptors: list = field(default_factory=list)   # ... when this site's plume reaches these places
    sensitive_avoid: list = field(default_factory=list)   # (ts, school/hospital) in an Avoid window
    sensor_hot_hours: int = 0          # latest working hours in a row with site sensor > 2x ambient
    citizen_reports: int = 0           # in the last 7 days
    exceedances_7d: int = 0            # days in the last 7 a real station measured PM10 > 100 with this site's plume on it
    exceedance_days: list = field(default_factory=list)  # per such day, its highest hour: station, ts, pm10, wind, cause
    ignored_windows: int = 0           # Avoid windows the site accepted and was then measured working through
    confirmed_violation: bool = False  # an officer confirmed a violation (inspection outcome)
    non_construction: bool = False     # evidence points to a non-construction source
    referred: bool = False             # an officer approved a D10 referral for this site in the last 7 days
    satellite_active: bool = False     # Sentinel-2 shows new bare ground at the site (F2)
    receptor_node_hot: bool = False    # a DustTrace Node at a receptor this site's plume reaches read PM10 > 100 (F9)
    sensitive_node_hot: bool = False   # ... and that receptor is a school or hospital
    sensor_known: bool = True          # False when the site's BMC feed isn't connected: unknown is not "none"
    pm_signature: str | None = None    # nearest real station's PM10/PM2.5 signature: coarse_work | coarse_night | fine | mixed
    pm_station: str | None = None      # that station's name, for the reasons
    dry_windy_hours: list = field(default_factory=list)  # forecast working hours, strong wind and dry ground (F10)
    pending_requests: list = field(default_factory=list)  # {"action", "deadline"} not yet answered


@dataclass
class Action:
    action: str
    route: str
    rule: str
    reason: str
    status: str = ""
    at: pd.Timestamp | None = None        # when it should happen (scheduled mist)
    deadline: pd.Timestamp | None = None  # for evidence requests

    @property
    def type(self) -> str:
        return CATALOG[self.action][0]

    @property
    def route_options(self) -> tuple[str, ...]:
        return CATALOG[self.action][1]


@dataclass
class Decision:
    site_id: str
    triggers: list[str]
    signals: list[str]
    hypotheses: list[tuple[str, float]]
    initial: list[Action]
    final: list[Action]
    what_changed: str
    state: str
    stop_reason: str
    expired: list[str] = field(default_factory=list)


def _ist(ts: pd.Timestamp) -> str:
    return (ts + pd.Timedelta(hours=5.5)).strftime("%H:%M")


def _act(action: str, reason: str, route: str | None = None, rule: str | None = None, **kw) -> Action:
    _, routes, default_rule = CATALOG[action]
    route = route or routes[0]
    assert route in routes, f"{action} cannot go by {route}"
    status = {"auto": "done", "site": "sent"}.get(route, "proposed")
    if CATALOG[action][0] == "evidence":
        status = "requested"
    return Action(action, route, rule or default_rule, reason, status, **kw)


def verified_close(reason: str) -> Action:
    """Verify (F12) found PM10 fell after the site's fix, so the case closes; the close is recorded like any action."""
    return _act("CLOSE_NO_ACTION", reason, rule="verified drop")


def hypotheses(c: SiteContext) -> list[tuple[str, float]]:
    w = {k: 0.05 for k in CAUSES}
    for k, v in PRIORS.get(c.activity, {}).items():
        w[k] += v
    if c.has_sensor and c.trust is not None and c.trust < 40:
        w["sensor_fault"] += 0.3
    if c.citizen_reports or c.sensor_hot_hours:
        for k in ("dry_excavation", "demolition", "truck_trackout", "uncovered_debris"):
            w[k] *= 1.2
    elif c.spike_hours and not c.sensitive_avoid:
        w["weather_only"] += 0.1
    if c.pm_signature == "coarse_work":    # PM10 up far more than PM2.5 in working hours
        for k in ("dry_excavation", "demolition", "uncovered_debris"):
            w[k] *= 1.6
    elif c.pm_signature == "coarse_night":  # coarse dust when heavy vehicles run
        w["truck_trackout"] *= 1.8
    elif c.pm_signature == "fine":          # combustion, not construction dust
        w["non_construction"] += 0.25
        for k in ("dry_excavation", "demolition", "truck_trackout", "uncovered_debris"):
            w[k] *= 0.8
    if c.non_construction:
        w["non_construction"] += 1.0
    total = sum(w.values())
    return sorted(((k, round(v / total, 3)) for k, v in w.items()), key=lambda kv: (-kv[1], kv[0]))


def _day(x: dict) -> str:
    """One attributed day, told by its highest station hour."""
    ts = pd.Timestamp(x["ts"]) + pd.Timedelta(hours=5.5)
    n = len(x.get("hours") or [])
    bg = f" against {round(x['background'])} µg/m³ at the other stations" if x.get("background") is not None else ""
    share = f", about {round(x['added'])} µg/m³ from this site's plume" if x.get("added") else ""
    shared = x.get("shared_with") or 0
    others = f", shared with {shared} other site{'' if shared == 1 else 's'}" if shared else ""
    return (f"{ts.day} {ts:%b} {ts:%H:%M} IST, {x['station']} {round(x['pm10'])} µg/m³{bg}{share}{others}, "
            f"wind from {round(x['wind_dir'])}° at {x['wind_speed']} m/s" + (f" ({n} hours)" if n > 1 else ""))


def lines(sig: list[str], cause: bool = False) -> list[str]:
    """Independent lines of evidence: the wind-only signals count once. With `cause`, only lines that speak
    to what caused the dust count (for D8 and D9)."""
    sig = [s for s in sig if not (cause and s in NOT_A_CAUSE)]
    wind = WIND_ONLY_FOR_CAUSE if cause else WIND_ONLY
    return [s for s in sig if s not in wind] + (["wind"] if wind & set(sig) else [])


def signals(c: SiteContext) -> list[str]:
    """Lines of evidence that this site is emitting. D1 needs two independent ones (`lines`) for enforcement."""
    s = []
    if c.spike_hours or c.sensitive_avoid:
        s.append("plume model")
    if c.sensor_hot_hours:
        s.append("site sensor")
    if c.citizen_reports:
        s.append("citizen reports")
    if c.exceedances_7d >= 3:
        s.append("station attribution")
    if c.ignored_windows >= 2:
        s.append("ignored Safe-Work Windows")
    if c.confirmed_violation:
        s.append("officer inspection")
    if c.satellite_active:
        s.append("satellite change")
    if c.receptor_node_hot:
        s.append("receptor monitor")
    if not c.has_sensor and c.sensor_known:
        s.append("site registry")
    return s


def decide(c: SiteContext) -> Decision | None:
    overdue = [r for r in c.pending_requests if pd.Timestamp(r["deadline"]) < c.now]
    triggers = []
    if c.spike_hours and c.spike_receptors:
        triggers.append("forecast_spike")
    if c.sensitive_avoid:
        triggers.append("receptor_downwind")
    if c.sensor_hot_hours:
        triggers.append("site_exceedance")
    if c.has_sensor and c.trust is not None and c.trust < 40:
        triggers.append("sensor_audit")
    if not c.has_sensor and c.sensor_known:
        triggers.append("unsensored_site")
    if c.exceedances_7d >= 3 or c.ignored_windows >= 2:
        triggers.append("repeat_exceedance")
    if c.citizen_reports:
        triggers.append("citizen_report")
    if c.sensitive_node_hot:
        triggers.append("node_at_school_or_hospital")
    if c.satellite_active:
        triggers.append("satellite_find")
    if c.dry_windy_hours and c.activity in DUSTY_ACTIVITIES:
        triggers.append("dry_windy")
    if overdue:
        triggers.append("evidence_overdue")
    if not triggers:
        return None

    sig = signals(c)
    hyp = hypotheses(c)
    receptor_exposure = bool(c.sensitive_avoid or c.spike_receptors or c.receptor_node_hot)
    acts: list[Action] = []

    if "forecast_spike" in triggers:  # D2
        first = min(c.spike_hours)
        where = ", ".join(c.spike_receptors[:2])
        acts.append(_act("ISSUE_SAFE_WORK_WINDOW", f"D2: P(PM10 > 100) ≥ 0.6 from {_ist(first)}; plume reaches {where}."))
        acts.append(_act("SCHEDULE_MIST", f"D2: mist from {_ist(first - MIST_LEAD)}, 90 min before the window"
                         + ("" if c.has_relay else "; no relay, so the site switches it on") + ".",
                         route="auto" if c.has_relay else "site", at=first - MIST_LEAD))
        if not c.has_relay:
            acts.append(_act("PRE_WET_SITE", f"D2: pre-wet before {_ist(first)}."))
    if c.sensitive_avoid:  # D3
        names = sorted({n for _, n in c.sensitive_avoid})
        first = min(t for t, _ in c.sensitive_avoid)
        acts.append(_act("ALERT_RECEPTOR", f"D3: {', '.join(names[:3])} downwind in an Avoid window from {_ist(first)}; "
                                           "close windows, run purifiers."))
        acts.append(_act("NOTIFY_RESIDENTS", "D3: nearby residents told when the plume passes."))
    if c.sensor_hot_hours:  # D4
        acts.append(_act("TRIGGER_MIST_NOW", "D4: site monitor above twice the ambient while working.",
                         route="auto" if c.has_relay else "site"))
        if c.sensor_hot_hours >= 2:
            acts.append(_act("PAUSE_DUSTY_TASK", f"D4: still above twice the ambient after {c.sensor_hot_hours} hours."))
    # F10 playbook: the fix for the most likely cause, sent to the site.
    emitting = bool(c.spike_hours or c.sensitive_avoid or c.sensor_hot_hours or c.citizen_reports
                    or c.satellite_active or c.exceedances_7d)
    cause = hyp[0][0]
    where = f" at {c.pm_station}" if c.pm_station else ""
    if emitting and cause == "truck_trackout":
        why = (f"coarse dust{where} at night, when trucks run" if c.pm_signature == "coarse_night"
               else "truck track-out is the most likely cause")
        acts.append(_act("ORDER_WHEEL_WASH", f"F10: {why}; wash wheels at the gate, cover loads and sweep the gate."))
    if emitting and cause == "uncovered_debris":
        acts.append(_act("ORDER_COVER_DEBRIS", "F10: uncovered debris is the most likely cause; cover it with green net "
                                               f"by {_ist(c.now + COVER_DEADLINE)}.", deadline=c.now + COVER_DEADLINE))
    if "dry_windy" in triggers and not any(a.action == "PRE_WET_SITE" for a in acts):
        first = min(c.dry_windy_hours)
        acts.append(_act("PRE_WET_SITE", f"F10: dry ground and strong wind from {_ist(first)}; pre-wet the site "
                                          "and keep dusty tasks short.", rule="F10"))
    if emitting and c.pm_signature == "coarse_work" and not any(a.action == "PRE_WET_SITE" for a in acts):
        acts.append(_act("PRE_WET_SITE", f"F10: coarse dust{where} in working hours points to dry digging or "
                                          "demolition; spray water while working.", rule="F10"))
    if "sensor_audit" in triggers:  # D5: the basis is the multi-check audit, not a dust cause
        acts.append(_act("FLAG_SENSOR_FOR_AUDIT", f"D5: monitor trust {round(c.trust)}/100; its readings can't clear the site."))
        acts.append(_act("ADD_TO_INSPECTION", f"D5: monitor trust {round(c.trust)}/100.", rule="D5"))
    if not c.has_sensor and c.sensor_known:  # D6
        acts.append(_act("REGISTER_UNSENSORED_SITE", "D6: active site with no dust monitor."))
        acts.append(_act("ADD_TO_INSPECTION", "D6: active site with no dust monitor.", rule="D6"))
    repeat = c.exceedances_7d >= 3 or c.ignored_windows >= 2
    if repeat:  # D8
        why = []
        if c.exceedances_7d >= 3:
            why.append(f"a real station measured PM10 above 100 µg/m³ with this site's plume on it on {c.exceedances_7d} "
                       "days in 7" + "".join(f"; {_day(x)}" for x in c.exceedance_days))
        if c.ignored_windows >= 2:
            why.append(f"{c.ignored_windows} ignored Safe-Work Windows")
        acts.append(_act("ISSUE_NOTICE", f"D8: {' and '.join(why)}."))
    if c.confirmed_violation and repeat and receptor_exposure:  # D9
        acts.append(_act("RECOMMEND_STOP_WORK", "D9: officer-confirmed violation, repeat exceedances and people downwind. "
                                                "Needs the Assistant Commissioner; never automatic."))
    acts.append(_act("UPDATE_DUST_SCORE", "Every case updates the site's Dust Score."))
    initial = list(acts)

    final, notes = list(acts), []
    if c.non_construction:  # D10: no site action; refer with the evidence
        final = [a for a in final if a.action not in SITE_ACTIONS | ENFORCEMENT_FROM_CAUSE | {"TRIGGER_MIST_NOW"}]
        fine = [x for x in c.exceedance_days if x.get("cause") == "fine"]
        why = (f"PM2.5 carried the PM10 spikes on {len(fine)} of the {len(c.exceedance_days)} days a station downwind "
               "measured above 100 µg/m³ (" + "; ".join(_day(x) for x in fine) + "), which points to burning or traffic, "
               "not construction dust" if fine else f"{hyp[0][0].replace('_', ' ')} is the most likely cause")
        if not c.referred:
            final.insert(0, _act("REFER_NON_CONSTRUCTION", f"D10: {why}; refer to MPCB or the right BMC department."))
            notes.append("D10 found a non-construction source most likely, so site actions were dropped and the case is referred.")
    else:  # D1
        blocked = [a for a in final if a.action in ENFORCEMENT_FROM_CAUSE and a.rule != "D5"
                   and len(lines(sig, cause=a.rule in ("D8", "D9"))) < 2]
        if blocked:
            final = [a for a in final if a not in blocked]
            ask = ("REQUEST_SITE_PHOTO", "a site photo") if c.has_sensor else ("REQUEST_SPOT_CHECK", "an officer spot check")
            basis = [s for s in sig if not ({a.rule for a in blocked} & {"D8", "D9"} and s in NOT_A_CAUSE)]
            one = ((" and ".join(basis) + ", which only place the site upwind") if len(basis) > 1
                   else (basis[0] if basis else "none"))
            final.insert(0, _act(ask[0], f"D1: the case rests on one signal ({one}); "
                                         f"{ask[1]} comes before any enforcement.",
                                 deadline=c.now + EVIDENCE_DEADLINE))
            notes.append(f"{', '.join(sorted({a.rule for a in blocked}))} enforcement rests on one signal "
                         f"({one}), so under D1 {ask[1]} comes first.")
    expired = []
    if overdue:  # D7
        expired = [r["action"] for r in overdue]
        if not any(a.action == "ADD_TO_INSPECTION" for a in final):
            final.insert(0, _act("ADD_TO_INSPECTION", f"D7: {', '.join(expired)} not answered by its deadline.", rule="D7"))
        notes.append(f"No reply to {', '.join(expired)} by its deadline and none was assumed, so D7 adds an L1 inspection.")
    if c.non_construction and c.referred and not any(a.status in ("proposed", "requested") for a in final):
        final.insert(0, _act("CLOSE_NO_ACTION", "D10: already referred to MPCB or the right BMC department; "
                                                "no action at the site."))
        notes.append("An officer approved the D10 referral, so the case closes with no action at the site.")

    if any(a.action == "CLOSE_NO_ACTION" for a in final):
        state, stop = "DONE", "Closed with no action at the site: referred to MPCB or the right BMC department."
    elif any(a.status == "proposed" for a in final):
        state, stop = "APPROVAL_ROUTING", "Waiting for an officer to approve or decline the proposed actions."
    elif any(a.status == "requested" for a in final):
        state, stop = "AWAITING_EVIDENCE", "Waiting for the requested evidence; nothing is assumed in the meantime."
    else:
        state, stop = "VERIFYING", "Automatic actions are out; the next readings show whether PM fell."
    return Decision(c.site_id, triggers, sig, hyp, initial, final, " ".join(notes) or "No change: every rule's action stands.",
                    state, stop, expired)
