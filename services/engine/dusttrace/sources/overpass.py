"""OpenStreetMap schools and hospitals via the Overpass API (no key)."""

from __future__ import annotations

import math
import re
import time

import httpx

from . import http

# The main server resets connections under load; the mirrors serve the same data.
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
OVERPASS_URL = OVERPASS_URLS[0]

# Rough headcounts for exposure weighting until real enrolment / bed data is joined in.
DEFAULT_POP = {"school": 800, "hospital": 400}
KIND = {"school": "school", "kindergarten": "school", "hospital": "hospital"}

# In Mumbai, amenity=hospital is also used for clinics and doctors' practices. Keep places that
# admit patients; drop outpatient-only ones, and unnamed ones we can't check.
INPATIENT = re.compile(r"hospital|nursing home|maternity|nicu|\bicu\b|medical college", re.I)
OUTPATIENT = re.compile(r"dental|clinic|sonography|mammography|diagnostic|physiotherapy|^dr\.? ", re.I)
SAME_PLACE_M = 150


def query(bbox: list[float]) -> str:
    min_lon, min_lat, max_lon, max_lat = bbox
    b = f"{min_lat},{min_lon},{max_lat},{max_lon}"
    return f"""
[out:json][timeout:60];
(
  nwr["amenity"="school"]({b});
  nwr["amenity"="kindergarten"]({b});
  nwr["amenity"="hospital"]({b});
);
out center tags;
"""


def _metres(a: dict, b: dict) -> float:
    dy = (a["lat"] - b["lat"]) * 111_320
    dx = (a["lon"] - b["lon"]) * 111_320 * math.cos(math.radians(a["lat"]))
    return math.hypot(dx, dy)


def parse(payload: dict) -> list[dict]:
    out: list[dict] = []
    for el in payload.get("elements") or []:
        tags = el.get("tags") or {}
        kind = KIND.get(tags.get("amenity", ""))
        if not kind:
            continue
        name = (tags.get("name") or "").strip()
        if kind == "hospital" and (not name or not INPATIENT.search(name) or OUTPATIENT.search(name)):
            continue
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")
        if lat is None or lon is None:
            continue
        rec = {
            "id": f"osm-{el['type']}-{el['id']}",
            "name": name or f"Unnamed {kind}",
            "kind": kind,
            "lat": float(lat),
            "lon": float(lon),
            "population": DEFAULT_POP[kind],
            "source": "osm",
        }
        # The same school is often mapped as both its grounds (way) and a point (node).
        if any(o["name"].casefold() == rec["name"].casefold() and o["kind"] == kind
               and _metres(o, rec) < SAME_PLACE_M for o in out):
            continue
        out.append(rec)
    return out


def fetch(bbox: list[float], client: httpx.Client | None = None, sleep=time.sleep) -> list[dict]:
    c = client or httpx.Client(timeout=90)
    last: Exception | None = None
    for url in OVERPASS_URLS:
        try:
            r = http.post(c, url, data={"data": query(bbox)}, tries=2, sleep=sleep)
            return parse(r.json())
        except (httpx.HTTPError, ValueError) as e:
            last = e
    raise last  # type: ignore[misc]


# ---------- construction sites (issue #30) ----------

SITE_AREA = (1_000, 300_000)  # m2: smaller is noise, larger is a mapped zone, not a site


def sites_query(bbox: list[float]) -> str:
    min_lon, min_lat, max_lon, max_lat = bbox
    b = f"{min_lat},{min_lon},{max_lat},{max_lon}"
    return f"""
[out:json][timeout:60];
(
  way["landuse"="construction"]({b});
  relation["landuse"="construction"]({b});
  way["building"="construction"]({b});
);
out center tags bb;
"""


def _activity(tags: dict) -> str:
    kind = " ".join(str(tags.get(k, "")) for k in ("construction", "railway", "highway", "name")).lower()
    if "demolition" in kind:
        return "demolition"
    if any(w in kind for w in ("subway", "metro", "railway", "rail", "tunnel", "highway", "road", "flyover", "bridge")):
        return "excavation"
    return "structure"


def parse_sites(payload: dict) -> list[dict]:
    out = []
    for el in payload.get("elements") or []:
        tags, c, b = el.get("tags") or {}, el.get("center") or {}, el.get("bounds") or {}
        if not c or not b:
            continue
        h = (b["maxlat"] - b["minlat"]) * 111_320
        w = (b["maxlon"] - b["minlon"]) * 111_320 * math.cos(math.radians(c["lat"]))
        area = 0.7 * h * w  # mapped outlines fill about 70% of their bounding box
        if not SITE_AREA[0] <= area <= SITE_AREA[1]:
            continue
        name = (tags.get("name") or "").strip()
        out.append({
            "id": f"osm-{el['type']}-{el['id']}",
            "name": name or f"Construction site (OSM {el['type']} {el['id']})",
            "activity": _activity(tags),
            "developer": tags.get("operator") or tags.get("developer"),
            "lat": float(c["lat"]), "lon": float(c["lon"]),
            "area_m2": round(area),
            "source": "osm", "demo": False,
        })
    return out


def fetch_sites(bbox: list[float], client: httpx.Client | None = None, sleep=time.sleep) -> list[dict]:
    c = client or httpx.Client(timeout=120)
    last: Exception | None = None
    for url in OVERPASS_URLS:
        try:
            r = http.post(c, url, data={"data": sites_query(bbox)}, tries=2, sleep=sleep)
            return parse_sites(r.json())
        except (httpx.HTTPError, ValueError) as e:
            last = e
    raise last  # type: ignore[misc]
