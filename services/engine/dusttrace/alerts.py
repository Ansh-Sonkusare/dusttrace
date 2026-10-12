"""Ward alerts (PRD F11): every alert carries an action, not just a reading.

Derived from each site's agent context and decision in a run. Alerts are logged, not sent, in the
prototype; the console shows them on the overview.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .agent import Decision, SiteContext

SEVERITY = ["critical", "action", "receptor", "sensor"]


@dataclass
class SiteState:
    ctx: SiteContext
    decision: Decision | None
    case_id: int | None
    plan_accepted: bool   # the manager accepted today's plan
    avoid_now: bool       # the current hour is an Avoid hour for this site


@dataclass
class Alert:
    kind: str
    site_id: str
    case_id: int | None
    title: str
    action: str


def _ist(ts) -> str:
    return (pd.Timestamp(ts) + pd.Timedelta(hours=5.5)).strftime("%H:%M")


def derive(states: list[SiteState]) -> list[Alert]:
    out: list[Alert] = []
    for s in states:
        c, d = s.ctx, s.decision
        if d is None:
            continue
        name = f"{c.site_id} · {c.name}"
        if "forecast_spike" in d.triggers and not c.has_relay and not s.plan_accepted:
            out.append(Alert("critical", c.site_id, s.case_id,
                             f"{name}: spike from {_ist(min(c.spike_hours))} and no misting arranged",
                             "Call the site manager to accept the plan and start misting 90 min before."))
        if c.sensor_hot_hours and s.avoid_now:
            out.append(Alert("action", c.site_id, s.case_id,
                             f"{name}: dusty work inside an Avoid window",
                             "Manager alerted to pause dusty work"
                             + (" and misting switched on remotely." if c.has_relay else " and switch on misting.")))
        if c.sensitive_avoid:
            places = sorted({n for _, n in c.sensitive_avoid})
            first = min(t for t, _ in c.sensitive_avoid)
            out.append(Alert("receptor", c.site_id, s.case_id,
                             f"{', '.join(places[:2])} downwind of {c.site_id} from {_ist(first)}",
                             "School or hospital told to close windows and run purifiers during the window."))
        if "sensor_audit" in d.triggers:
            out.append(Alert("sensor", c.site_id, s.case_id,
                             f"{name}: monitor not trusted ({round(c.trust)}/100)",
                             "Flagged for audit and added to the inspection list; its readings can't clear the site."))
    return sorted(out, key=lambda a: (SEVERITY.index(a.kind), a.site_id))
