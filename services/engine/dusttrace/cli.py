"""Command line: `dusttrace <command>`.

  init-db   apply SQL migrations
  seed      load the ward, seed stations, demo sites and receptors
  osm       replace demo receptors with real OSM schools and hospitals (needs network)
  osm-sites add construction sites mapped in OSM inside the ward (needs network)
  osm-housing  estimated housing exposure: Census 2011 people over OSM residential land (needs network)
  ingest    load weather + readings (--mode auto|live|synthetic, --days N)
  run       train, forecast 48 h, plumes, Safe-Work Windows
  backtest  replay the last N days with only past data visible (--days N)
  discover  Sentinel-2 change detection: possible unregistered sites (needs network)
  replay-outage  verify the CAMS fill: hide 4 days before each forecast and score it (--days N)
  verify    data check: how much of the latest run is real; stores data_checks
  all       init-db, seed, ingest, run
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from . import db, pipeline
from .config import load_seed, load_settings


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(prog="dusttrace")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db")
    sub.add_parser("seed")
    sub.add_parser("osm")
    sub.add_parser("osm-sites")
    sub.add_parser("osm-housing")
    ing = sub.add_parser("ingest")
    ing.add_argument("--mode", choices=["auto", "live", "synthetic"], default="auto")
    ing.add_argument("--days", type=int, default=420)
    sub.add_parser("run")
    sub.add_parser("discover")
    sub.add_parser("verify")
    ro = sub.add_parser("replay-outage")
    ro.add_argument("--days", type=int, default=30)
    bt = sub.add_parser("backtest")
    bt.add_argument("--compare-cams", action="store_true", help="same window with and without the CAMS features (#32)")
    bt.add_argument("--days", type=int, default=60)
    al = sub.add_parser("all")
    al.add_argument("--mode", choices=["auto", "live", "synthetic"], default="auto")
    al.add_argument("--days", type=int, default=420)
    args = p.parse_args(argv)

    settings = load_settings()
    with db.connect(settings.database_url) as conn:
        if args.cmd in ("init-db", "all"):
            print("migrations:", db.migrate(conn))
        if args.cmd in ("seed", "all"):
            db.upsert_seed(conn, load_seed())
            print("seeded ward, stations, sites, receptors")
        if args.cmd == "osm":
            print("receptors from OSM:", pipeline.load_receptors_osm(conn, settings))
        if args.cmd == "osm-housing":
            h = pipeline.load_housing_osm(conn, settings)
            print(f"housing: {h['receptors']} cells, {h['residential_km2']} km² of homes in the ward, "
                  f"{h['people_per_km2_of_homes']:,} people per km² of homes; estimate in the ward "
                  f"{h['population_in_ward']:,} vs census 2011 {h['census_2011']:,}")
        if args.cmd == "osm-sites":
            print("construction sites from OSM:", pipeline.load_sites_osm(conn, settings))
        if args.cmd in ("ingest", "all"):
            print("ingest:", json.dumps(pipeline.ingest(conn, settings, args.mode, args.days)))
        if args.cmd == "replay-outage":
            print("replay:", json.dumps(pipeline.replay_outage(conn, settings, args.days), indent=2, default=str))
        if args.cmd == "verify":
            chk = pipeline.verify(conn, settings)
            sh = chk["shares"]
            print(f"run {chk['run_id']} ({chk['data_mode']}): last week's station hours "
                  f"{sh['real']:.0%} measured, {sh['filled']:.0%} filled, {sh['synthetic']:.0%} synthetic; "
                  f"weather {chk['weather_live']:.0%} live")
            for p in chk["problems"] or ["Everything in this run is real, live data."]:
                print(" -", p)
        if args.cmd == "discover":
            print("discover:", json.dumps(pipeline.discover_sites(conn, settings), indent=2, default=str))
        if args.cmd == "backtest":
            if args.compare_cams:
                print("cams feature:", json.dumps(pipeline.compare_cams(conn, settings, args.days), indent=2, default=str))
            else:
                print("backtest:", json.dumps(pipeline.backtest(conn, settings, args.days), indent=2, default=str))
        if args.cmd in ("run", "all"):
            print("run:", json.dumps(pipeline.run(conn, settings), indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
