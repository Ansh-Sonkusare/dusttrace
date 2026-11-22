"""Simulate a DustTrace Node: send the same JSON the Arduino sketch sends, to check a deployment.

    python docs/node/simulate_node.py --url https://dusttrace-mumbai.vercel.app/api/node \
        --node node-marol-school --key "$NODE_KEY" [--minutes 5] [--offline]

--offline buffers the readings and sends them as one batch, like a node coming back online.
Prints the server's answer for each post. Uses only the standard library.
"""

from __future__ import annotations

import argparse
import json
import random
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone


def reading(ts: datetime, rng: random.Random) -> dict:
    pm25 = round(rng.uniform(25, 60))
    rh = round(rng.uniform(45, 85), 1)
    return {"ts": ts.strftime("%Y-%m-%dT%H:%M:%SZ"), "pm25": pm25, "pm10": round(pm25 * rng.uniform(1.6, 2.6)),
            "rh": rh, "temp": round(rng.uniform(24, 33), 1)}


def post(url: str, node: str, key: str, readings: list[dict]) -> tuple[int, str]:
    req = urllib.request.Request(url, data=json.dumps({"node_id": node, "readings": readings}).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def main() -> None:
    a = argparse.ArgumentParser()
    a.add_argument("--url", required=True)
    a.add_argument("--node", required=True)
    a.add_argument("--key", required=True)
    a.add_argument("--minutes", type=int, default=5)
    a.add_argument("--offline", action="store_true")
    args = a.parse_args()
    rng = random.Random(7)
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    rows = [reading(now - timedelta(minutes=m), rng) for m in range(args.minutes - 1, -1, -1)]
    for batch in ([rows] if args.offline else [[r] for r in rows]):
        print(*post(args.url, args.node, args.key, batch))


if __name__ == "__main__":
    main()
