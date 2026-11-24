"""Festival calendar for the forecast (PRD F3): Mumbai festivals that bring fireworks, bonfires or processions.

Dates are IST calendar days, first and last day inclusive. Sources, checked on 23 Nov 2026:
- Maharashtra public holidays as listed by officeholidays.com/countries/india/maharashtra/<year> (from the
  state's General Administration Department notifications): Holi 14 Mar 2025, 3 Mar 2026, 22 Mar 2027;
  Ganesh Chaturthi 27 Aug 2025, 14 Sep 2026, 4 Sep 2027; Dasara 2 Oct 2025, 20 Oct 2026, 9 Oct 2027;
  Laxmi Pujan 21 Oct 2025, 8 Nov 2026, 29 Oct 2027; Bali Pratipada 22 Oct 2025, 10 Nov 2026; Bhaubeej 23 Oct 2025.
- Bhaubeej 11 Nov 2026: the extra holiday in the state's 2026 list (Sakshi Post, "Maharashtra Govt Issues 2026
  Public Holiday List, Bhaubeej Earns Additional Holiday").
- Anant Chaturdashi (the last Ganesh Visarjan): 6 Sep 2025; 25 Sep 2026 (News On Air, "Anant Chaturdashi
  celebrated across Mumbai", 25 Sep 2026); 14 Sep 2027 (drikpanchang.com).
The Diwali window runs from two days before Laxmi Pujan to Bhaubeej; the 2027 state list is not out yet, so
2027 runs to 1 Nov to hold Bali Pratipada and Bhaubeej either way. Holi starts on the Holika Dahan night before
it; 2026 sources split between 3 and 4 March, so both are in. New Year covers New Year's Eve and New Year's Day.
"""

from __future__ import annotations

from datetime import date
from typing import NamedTuple

import numpy as np
import pandas as pd


class Festival(NamedTuple):
    name: str
    first: date
    last: date


CALENDAR = [
    Festival("Holi", date(2025, 3, 13), date(2025, 3, 14)),
    Festival("Ganeshotsav", date(2025, 8, 27), date(2025, 9, 6)),
    Festival("Dasara", date(2025, 10, 2), date(2025, 10, 2)),
    Festival("Diwali", date(2025, 10, 19), date(2025, 10, 23)),
    Festival("Holi", date(2026, 3, 2), date(2026, 3, 4)),
    Festival("Ganeshotsav", date(2026, 9, 14), date(2026, 9, 25)),
    Festival("Dasara", date(2026, 10, 20), date(2026, 10, 20)),
    Festival("Diwali", date(2026, 11, 6), date(2026, 11, 11)),
    Festival("Holi", date(2027, 3, 21), date(2027, 3, 22)),
    Festival("Ganeshotsav", date(2027, 9, 4), date(2027, 9, 14)),
    Festival("Dasara", date(2027, 10, 9), date(2027, 10, 9)),
    Festival("Diwali", date(2027, 10, 27), date(2027, 11, 1)),
] + [Festival("New Year", date(y, 12, 31), date(y + 1, 1, 1)) for y in (2024, 2025, 2026, 2027)]


def flag(ts: pd.DatetimeIndex) -> np.ndarray:
    """1 for hours whose IST date falls on a festival day, else 0."""
    day = (ts + pd.Timedelta(hours=5.5)).normalize().tz_localize(None)
    out = np.zeros(len(ts), dtype=int)
    for f in CALENDAR:
        out |= ((day >= pd.Timestamp(f.first)) & (day <= pd.Timestamp(f.last))).astype(int)
    return out
