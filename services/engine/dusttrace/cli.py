"""Command line: `dusttrace <command>`.

  init-db   apply SQL migrations
  seed      load the ward, seed stations, demo sites and receptors
  osm       replace demo receptors with real OSM schools and hospitals (needs network)
  ingest    load weather + readings (--mode auto|live|synthetic, --days N)
  run       train, forecast 48 h, plumes, Safe-Work Windows
  backtest  replay the last N days with only past data visible (--days N)
  discover  Sentinel-2 change detection: possible unregistered sites (needs network)
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
    ing = sub.add_parser("ingest")
    ing.add_argument("--mode", choices=["auto", "live", "synthetic"], default="auto")
    ing.add_argument("--days", type=int, default=420)
    sub.add_parser("run")
    sub.add_parser("discover")
    bt = sub.add_parser("backtest")
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
        if args.cmd in ("ingest", "all"):
            print("ingest:", json.dumps(pipeline.ingest(conn, settings, args.mode, args.days)))
        if args.cmd == "discover":
            print("discover:", json.dumps(pipeline.discover_sites(conn, settings), indent=2, default=str))
        if args.cmd == "backtest":
            print("backtest:", json.dumps(pipeline.backtest(conn, settings, args.days), indent=2, default=str))
        if args.cmd in ("run", "all"):
            print("run:", json.dumps(pipeline.run(conn, settings), indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
