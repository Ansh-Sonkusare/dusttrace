"""Dust Score (PRD F8): a public 0-100 per site, shown next to the PM readings on the site's LED board.

Higher is better. Proposed weights (PRD): sensor trust 30, spikes traced to the site 25, Safe-Work
Windows followed 20, verified citizen reports 15, inspection history 10. Proposed incentives, to be
designed with BMC: 80+ earns fewer routine inspections; below 40 goes to the top of the list.
"""

from __future__ import annotations

from dataclasses import dataclass, field

WEIGHTS = {"trust": 30, "spikes": 25, "windows": 20, "reports": 15, "inspections": 10}
GOOD, POOR = 80, 40


@dataclass
class Score:
    score: float
    band: str
    components: dict = field(default_factory=dict)  # points earned per part
    notes: list[str] = field(default_factory=list)


def band(score: float) -> str:
    return "good" if score >= GOOD else ("poor" if score < POOR else "fair")


def compute(trust: float | None, has_sensor: bool, spike_hours: int, windows_followed: float | None,
            verified_reports: int, violations: int) -> Score:
    """`spike_hours`: likely-spike hours the site sits upwind of a station (attribution).
    `windows_followed`: share of Avoid windows the site accepted a plan for, or None if unknown.
    `verified_reports`: officer-verified citizen reports, 30 days. `violations`: confirmed, 90 days."""
    notes = []
    parts = {
        "trust": (trust or 0) / 100 if has_sensor else 0.0,
        "spikes": 1 - min(spike_hours / 6, 1),
        "windows": 0.5 if windows_followed is None else max(0.0, min(windows_followed, 1.0)),
        "reports": 1 - min(verified_reports / 3, 1),
        "inspections": 1 - min(violations / 2, 1),
    }
    if not has_sensor:
        notes.append("No dust monitor, so the trust share is lost.")
    if windows_followed is None:
        notes.append("Safe-Work Windows followed: not reported yet, counted as half.")
    points = {k: round(WEIGHTS[k] * v, 1) for k, v in parts.items()}
    total = round(max(0.0, min(100.0, sum(points.values()))), 1)
    return Score(total, band(total), points, notes)
