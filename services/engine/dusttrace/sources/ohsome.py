"""OpenStreetMap construction sites via the ohsome API (HeiGIT), the fallback when every Overpass
mirror is down. It serves a recent OSM snapshot (weeks old, stated in each feature), not live edits.
Docs: https://docs.ohsome.org/ohsome-api/v1/
"""

from __future__ import annotations

import math

import httpx

from . import http
from .overpass import SITE_AREA, _activity

URL = "https://api.ohsome.org/v1/elements/bbox"  # each element's bounding box; /geometry is refused here
FILTER = "landuse=construction or building=construction"


def parse_sites(payload: dict) -> list[dict]:
    """Same output and ids as overpass.parse_sites, so switching source never duplicates a site."""
    out = []
    for f in payload.get("features") or []:
        p, g = f.get("properties") or {}, f.get("geometry") or {}
        kind, _, num = str(p.get("@osmId", "")).partition("/")
        if kind not in ("way", "relation") or g.get("type") != "Polygon":
            continue
        ring = g["coordinates"][0]
        lons, lats = [q[0] for q in ring], [q[1] for q in ring]
        lat, lon = (min(lats) + max(lats)) / 2, (min(lons) + max(lons)) / 2
        h = (max(lats) - min(lats)) * 111_320
        w = (max(lons) - min(lons)) * 111_320 * math.cos(math.radians(lat))
        area = 0.7 * h * w  # same rule as Overpass: outlines fill about 70% of their box
        if not SITE_AREA[0] <= area <= SITE_AREA[1]:
            continue
        tags = {k: v for k, v in p.items() if not k.startswith("@")}
        name = (tags.get("name") or "").strip()
        out.append({
            "id": f"osm-{kind}-{num}",
            "name": name or f"Construction site (OSM {kind} {num})",
            "activity": _activity(tags),
            "developer": tags.get("operator") or tags.get("developer"),
            "lat": round(lat, 6), "lon": round(lon, 6),
            "area_m2": round(area),
            "source": "osm", "demo": False,
        })
    return out


def fetch_sites(bbox: list[float], client: httpx.Client | None = None) -> list[dict]:
    c = client or httpx.Client(timeout=180)
    r = http.post(c, URL, data={"bboxes": ",".join(str(v) for v in bbox), "filter": FILTER, "properties": "tags"})
    return parse_sites(r.json())
