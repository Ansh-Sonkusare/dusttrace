"""Person-exposure avoided (PRD F7's metric), and the hours each site should move its dusty work to.

Person-exposure is people x the PM10 a site adds where they are (µg/m³) x hours, in person·µg/m³·h, summed over
every school, hospital and home cell however faint the increment (`person_exposure`). The part from receptors given
15 µg/m³ or more, the `exposures` rows, is kept beside it (`person_exposure_15`) so it can be checked by hand.
People: Census 2011 spread over mapped homes for housing cells, and a fixed 800 per school and 400 per hospital.

Without DustTrace, a site does its dusty work in every hour it is allowed to, 06:00-22:00 IST (an hour must end by
22:00), whatever the forecast.
With the plan, it does the same hours of dusty work on each day, but the work of each Avoid hour moves to the cleanest
open hour of the same day: a Go or Caution hour with less person-exposure on both counts, the least dust first (Go
before Caution on a tie, then the nearest hour). Each open hour takes at most one moved hour, and the dust the moved
work makes there is counted at that hour's exposure. An Avoid hour with no better hour that day keeps its work and its
exposure, so the plan never claims what it can't move. Avoided = without - with: never negative on either count, and
zero for a site with no Avoid hour. Ward totals, and what accepted plans keep off people, are the view
`exposure_avoided_ward` (migration 0024).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import pandas as pd

from .plume import IST_OFFSET_H, hour_ist

WORK_IST = (6, 22)  # dusty work allowed 06:00-22:00 IST


def allowed(ts) -> bool:
    """A work hour starting at `ts` falls inside 06:00-22:00 IST: it starts at 06:00 or later and ends by 22:00."""
    h = hour_ist(ts)
    return WORK_IST[0] <= h and h + 1 <= WORK_IST[1]


@dataclass
class SitePlan:
    without: float = 0.0
    without_15: float = 0.0
    moves: dict = field(default_factory=dict)  # Avoid hour -> (hour its work moves to, kept off, kept off at 15+)
    stuck: list = field(default_factory=list)  # Avoid hours with no better hour that day

    @property
    def avoided(self) -> float:
        return sum(g for _, g, _ in self.moves.values())

    @property
    def avoided_15(self) -> float:
        return sum(g for _, _, g in self.moves.values())

    @property
    def with_plan(self) -> float:
        return self.without - self.avoided

    @property
    def with_15(self) -> float:
        return self.without_15 - self.avoided_15

    @property
    def pct(self) -> float | None:
        return 100 * self.avoided / self.without if self.without > 0 else None

    @property
    def pct_15(self) -> float | None:
        return 100 * self.avoided_15 / self.without_15 if self.without_15 > 0 else None


def plan_site(hours) -> SitePlan:
    """One site's plan from its forecast hours (anything with ts, status, person_exposure and person_exposure_15)."""
    work = sorted((h for h in hours if allowed(h.ts)), key=lambda h: h.ts)
    out = SitePlan(without=sum(h.person_exposure for h in work), without_15=sum(h.person_exposure_15 for h in work))
    days = defaultdict(list)
    for h in work:
        days[(h.ts + pd.Timedelta(hours=IST_OFFSET_H)).date()].append(h)
    for day in days.values():
        free = [h for h in day if h.status != "avoid"]
        for src in sorted((h for h in day if h.status == "avoid"), key=lambda h: (-h.person_exposure, h.ts)):
            better = [h for h in free if h.person_exposure < src.person_exposure
                      and h.person_exposure_15 < src.person_exposure_15]
            if not better:
                out.stuck.append(src.ts)
                continue
            best = min(better, key=lambda h: (h.person_exposure, h.person_exposure_15, h.status != "go",
                                               abs(h.ts - src.ts), h.ts))
            free.remove(best)
            out.moves[src.ts] = (best.ts, src.person_exposure - best.person_exposure,
                                 src.person_exposure_15 - best.person_exposure_15)
    out.stuck.sort()
    return out


def plan(hours) -> dict[str, SitePlan]:
    by_site = defaultdict(list)
    for h in hours:
        by_site[h.site_id].append(h)
    return {sid: plan_site(hs) for sid, hs in by_site.items()}
