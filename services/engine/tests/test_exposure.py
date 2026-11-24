"""Person-exposure avoided (PRD F7 metric) and where to move the work. Pure functions, no database."""

import random

import pandas as pd
import pytest

from dusttrace import exposure
from dusttrace.windows import SiteHour

DAY = pd.Timestamp("2026-11-24T00:00Z")  # 05:30 IST


def hour(ist: float, status: str, pe15: float, site: str = "A", day: int = 0, faint: float = 0.0,
         outside: float = 0.0) -> SiteHour:
    """A site hour at `ist` o'clock IST: `pe15` person·µg/m³ at receptors given 15 µg/m³ or more, `faint` below that,
    and `outside` of the total from people beyond the ward's boundary."""
    ts = DAY + pd.Timedelta(days=day, hours=ist - 5.5)
    return SiteHour(site, ts, [], 0.0, 0.0, status=status, person_exposure=pe15 + faint, person_exposure_15=pe15,
                    person_exposure_ward=pe15 + faint - outside)


def at(ist: float, day: int = 0) -> pd.Timestamp:
    return DAY + pd.Timedelta(days=day, hours=ist - 5.5)


def test_avoid_work_moves_to_the_cleanest_open_hours_of_the_same_day():
    hours = [hour(8, "go", 0), hour(9, "avoid", 50_000), hour(10, "avoid", 40_000), hour(11, "caution", 5_000),
             hour(12, "go", 0), hour(13, "go", 0), hour(14, "caution", 8_000)]
    p = exposure.plan_site(hours)
    assert p.without == p.without_15 == 103_000
    # Go hours first (no dust reaches anyone), the nearest one for the worst hour.
    assert p.moves == {at(9): (at(8), 50_000, 50_000), at(10): (at(12), 40_000, 40_000)}
    assert p.avoided == 90_000 and p.with_plan == 13_000
    assert p.pct == pytest.approx(100 * 90_000 / 103_000)
    assert p.stuck == []


def test_the_cleanest_hour_counts_faint_dust_too():
    # Neither open hour gives anyone 15 µg/m³, but 13:00 spreads more faint dust over people than 15:00.
    p = exposure.plan_site([hour(9, "avoid", 50_000, faint=10_000), hour(13, "go", 0, faint=30_000),
                            hour(15, "caution", 0, faint=20_000)])
    assert p.moves == {at(9): (at(15), 40_000, 50_000)}
    assert p.without == 110_000 and p.avoided == 40_000 and p.with_plan == 70_000
    assert p.without_15 == 50_000 and p.avoided_15 == 50_000 and p.with_15 == 0


def test_a_move_never_puts_more_dust_on_people_in_total():
    # 13:00 reaches nobody at 15 µg/m³ but spreads more faint dust than the Avoid hour itself: no move.
    p = exposure.plan_site([hour(9, "avoid", 50_000), hour(13, "go", 0, faint=80_000)])
    assert p.moves == {} and p.stuck == [at(9)] and p.avoided == 0


def test_the_part_inside_the_ward_is_kept_beside_the_total():
    p = exposure.plan_site([hour(9, "avoid", 50_000, outside=30_000), hour(13, "go", 0, faint=10_000, outside=2_000),
                            hour(23, "go", 0, faint=5_000)])                  # 23:00 is not a work hour
    assert p.without == 60_000 and p.without_ward == 28_000
    assert p.avoided == 40_000 and p.avoided_ward == 12_000                   # 20,000 - 8,000 inside the ward


def test_moved_work_still_makes_dust_where_it_goes():
    # The only open hour is a Caution hour: the work moves, and its dust there is counted.
    p = exposure.plan_site([hour(9, "avoid", 50_000), hour(10, "caution", 12_000)])
    assert p.moves == {at(9): (at(10), 38_000, 38_000)}
    assert p.without == 62_000 and p.with_plan == 24_000  # 12,000 for the hour's own work + 12,000 for the moved work


def test_no_better_hour_means_the_work_stays_and_nothing_is_claimed():
    p = exposure.plan_site([hour(9, "avoid", 20_000), hour(10, "caution", 30_000), hour(11, "avoid", 25_000)])
    assert p.moves == {} and p.stuck == [at(9), at(11)]
    assert p.avoided == 0 and p.with_plan == p.without == 75_000


def test_a_site_with_no_avoid_hour_avoids_nothing():
    p = exposure.plan_site([hour(9, "caution", 20_000), hour(10, "go", 0, faint=3_000)])
    assert p.avoided == 0 and p.moves == {} and p.pct == 0
    assert exposure.plan_site([hour(9, "go", 0)]).pct is None  # nothing reaches anyone: no percentage


def test_work_moves_within_the_allowed_hours_and_the_same_day_only():
    hours = [hour(5, "go", 0), hour(22, "go", 0),                   # outside 06:00-22:00 IST: no dusty work
             hour(6, "avoid", 9_000),                               # the first allowed hour of day 0
             hour(23, "avoid", 70_000),                             # night: no dusty work to move
             hour(9, "go", 0, day=1)]                               # the next day
    p = exposure.plan_site(hours)
    assert p.without == 9_000                                       # only allowed hours count
    assert p.moves == {} and p.stuck == [at(6)]
    p = exposure.plan_site([hour(6, "avoid", 9_000), hour(21, "go", 0)])
    assert p.moves == {at(6): (at(21), 9_000, 9_000)}               # 06:00 work can go to 21:00 the same day


def test_dusty_work_ends_by_22_00():
    # The hour from 21:30 runs to 22:30, past the limit: no dusty work in it, and none moves into it.
    p = exposure.plan_site([hour(9, "avoid", 9_000), hour(21.5, "go", 0)])
    assert p.moves == {} and p.stuck == [at(9)]
    assert exposure.plan_site([hour(21.5, "avoid", 9_000), hour(5.5, "avoid", 9_000)]).without == 0
    p = exposure.plan_site([hour(9, "avoid", 9_000), hour(21, "go", 0)])  # 21:00-22:00 is the last allowed hour
    assert p.moves == {at(9): (at(21), 9_000, 9_000)}


def test_each_open_hour_takes_at_most_one_moved_hour():
    p = exposure.plan_site([hour(9, "avoid", 10_000), hour(10, "avoid", 10_000), hour(11, "go", 0)])
    assert len(p.moves) == 1 and len(p.stuck) == 1
    assert p.avoided == 10_000


def test_avoided_is_never_negative_whatever_the_hours():
    rng = random.Random(7)
    for _ in range(200):
        hours = [hour(h, rng.choice(["go", "caution", "avoid"]), rng.choice([0, 5_000, 20_000, 60_000]), day=d,
                      faint=rng.choice([0, 10_000, 90_000])) for d in (0, 1) for h in range(5, 23)]
        p = exposure.plan_site(hours)
        assert p.avoided >= 0 and p.avoided_15 >= 0 and p.with_plan <= p.without and p.with_15 <= p.without_15
        assert all(g > 0 and g15 > 0 for _, g, g15 in p.moves.values())
        assert len({dst for dst, _, _ in p.moves.values()}) == len(p.moves)


def test_plan_covers_every_site():
    plans = exposure.plan([hour(9, "avoid", 50_000), hour(10, "go", 0), hour(9, "caution", 10_000, site="B")])
    assert set(plans) == {"A", "B"} and plans["A"].avoided == 50_000 and plans["B"].avoided == 0
