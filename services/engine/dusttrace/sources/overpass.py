"""OpenStreetMap schools and hospitals via the Overpass API (no key)."""

from __future__ import annotations

import httpx

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Rough headcounts for exposure weighting until real enrolment / bed data is joined in.
DEFAULT_POP = {"school": 800, "hospital": 400}


def query(bbox: list[float]) -> str:
    min_lon, min_lat, max_lon, max_lat = bbox
    b = f"{min_lat},{min_lon},{max_lat},{max_lon}"
    return f"""
[out:json][timeout:60];
(
  nwr["amenity"="school"]({b});
  nwr["amenity"="hospital"]({b});
);
out center tags;
"""


def parse(payload: dict) -> list[dict]:
    out = []
    for el in payload.get("elements") or []:
        tags = el.get("tags") or {}
        kind = {"school": "school", "hospital": "hospital"}.get(tags.get("amenity", ""))
        if not kind:
            continue
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")
        if lat is None or lon is None:
            continue
        out.append({
            "id": f"osm-{el['type']}-{el['id']}",
            "name": tags.get("name") or f"Unnamed {kind}",
            "kind": kind,
            "lat": float(lat),
            "lon": float(lon),
            "population": DEFAULT_POP[kind],
            "source": "osm",
        })
    return out


def fetch(bbox: list[float], client: httpx.Client | None = None) -> list[dict]:
    c = client or httpx.Client(timeout=90)
    r = c.post(OVERPASS_URL, data={"data": query(bbox)})
    r.raise_for_status()
    return parse(r.json())
