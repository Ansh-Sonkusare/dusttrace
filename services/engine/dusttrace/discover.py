"""Discover (PRD F2): find active construction from Sentinel-2 change, then match it to the site list.

Two clear Sentinel-2 L2A scenes about a year apart, read straight from the public cloud-optimised
GeoTIFFs (Element84 Earth Search STAC, AWS open data). A pixel counts as new construction when its
bare-soil index (BSI) rose and its vegetation index (NDVI) fell, outside clouds and shadows. Patches
of 2,500 m2 or more become candidates; a candidate within 300 m of a known site confirms that site is
active, and an unmatched one is a possible unregistered site (D6, with a second signal per D1).
"""

from __future__ import annotations

import math

import numpy as np
from scipy import ndimage

STAC_URL = "https://earth-search.aws.element84.com/v1/search"
ASSETS = ["blue", "red", "nir", "swir16", "scl"]
# Scene classification (SCL) classes to drop: saturated, shadows, cloud medium/high, cirrus, snow.
BAD_SCL = {1, 3, 8, 9, 10, 11}
BSI_GAIN, NDVI_DROP = 0.08, 0.08
MIN_AREA_M2 = 2500


def indices(b: dict) -> dict:
    blue, red, nir, swir = (b[k].astype(float) for k in ("blue", "red", "nir", "swir16"))
    with np.errstate(divide="ignore", invalid="ignore"):
        bsi = ((swir + red) - (nir + blue)) / ((swir + red) + (nir + blue))
        ndvi = (nir - red) / (nir + red)
    return {"bsi": np.nan_to_num(bsi), "ndvi": np.nan_to_num(ndvi)}


def _clear(b: dict) -> np.ndarray:
    return ~np.isin(b["scl"], list(BAD_SCL)) & (b["scl"] > 0)


def change_mask(before: dict, after: dict) -> np.ndarray:
    ib, ia = indices(before), indices(after)
    return ((ia["bsi"] - ib["bsi"] > BSI_GAIN) & (ib["ndvi"] - ia["ndvi"] > NDVI_DROP)
            & _clear(before) & _clear(after))


def candidates(mask: np.ndarray, transform, crs, min_area_m2: float = MIN_AREA_M2) -> list[dict]:
    from rasterio.transform import xy
    from rasterio.warp import transform as warp

    px = abs(transform.a * transform.e)
    labels, n = ndimage.label(mask, structure=np.ones((3, 3)))
    out = []
    for i, sl in enumerate(ndimage.find_objects(labels), start=1):
        comp = labels[sl] == i
        area = float(comp.sum() * px)
        if area < min_area_m2:
            continue
        r, c = ndimage.center_of_mass(comp)
        x, y = xy(transform, sl[0].start + r, sl[1].start + c, offset="center")
        lon, lat = warp(crs, "EPSG:4326", [x], [y])
        out.append({"lat": round(lat[0], 6), "lon": round(lon[0], 6), "area_m2": round(area)})
    return sorted(out, key=lambda c: -c["area_m2"])


def _metres(a: dict, b: dict) -> float:
    dy = (a["lat"] - b["lat"]) * 111_320
    dx = (a["lon"] - b["lon"]) * 111_320 * math.cos(math.radians(a["lat"]))
    return math.hypot(dx, dy)


def match(cands: list[dict], sites: list[dict], radius_m: float = 300) -> list[dict]:
    out = []
    for c in cands:
        near = min(sites, key=lambda s: _metres(c, s), default=None)
        hit = near is not None and _metres(c, near) <= radius_m
        out.append({**c, "site_id": near["id"] if hit else None})
    return out


def evaluate(matched: list[dict], sites: list[dict], radius_m: float = 300) -> dict:
    """Precision: share of candidates near a known active site. Recall: share of known sites found."""
    found = len(matched)
    hits = sum(1 for c in matched if c.get("site_id"))
    seen = {c["site_id"] for c in matched if c.get("site_id")}
    return {"precision": hits / found if found else 0.0, "recall": len(seen) / len(sites) if sites else 0.0,
            "found": found, "known": len(sites)}


# ---------- live fetch (network) ----------

def search(bbox: list[float], start: str, end: str, max_cloud: float = 10, client=None) -> list[dict]:
    import httpx

    from .sources import http

    c = client or httpx.Client(timeout=60)
    body = {"collections": ["sentinel-2-l2a"], "bbox": bbox, "datetime": f"{start}/{end}",
            "query": {"eo:cloud_cover": {"lt": max_cloud}}, "limit": 50,
            "sortby": [{"field": "properties.eo:cloud_cover", "direction": "asc"}]}
    r = http.request(c, "POST", STAC_URL, json=body)
    return r.json().get("features", [])


def read_bands(item: dict, bbox: list[float]) -> tuple[dict, object, object]:
    """Read the ward window of each band, resampled to the 10 m grid of the red band."""
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.warp import transform_bounds
    from rasterio.windows import from_bounds

    out, grid = {}, None
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
        with rasterio.open(item["assets"]["red"]["href"]) as ref:
            bounds = transform_bounds("EPSG:4326", ref.crs, *bbox)
            win = from_bounds(*bounds, ref.transform).round_offsets().round_lengths()
            grid = (ref.window_transform(win), ref.crs, (int(win.height), int(win.width)))
        for key in ASSETS:
            with rasterio.open(item["assets"][key]["href"]) as src:
                w = from_bounds(*bounds, src.transform)
                out[key] = src.read(1, window=w, out_shape=grid[2], boundless=True,
                                    resampling=Resampling.nearest if key == "scl" else Resampling.bilinear)
    return out, grid[0], grid[1]


def discover(bbox: list[float], sites: list[dict], after: tuple[str, str], before: tuple[str, str]) -> dict:
    """Pick the clearest scene in each period (same UTM zone), detect change, match and score."""
    a_items, b_items = search(bbox, *after), search(bbox, *before)
    if not a_items or not b_items:
        raise RuntimeError("No clear Sentinel-2 scene in one of the periods")
    a = a_items[0]
    zone = a["properties"].get("proj:epsg") or a["properties"].get("proj:code")
    b = next((x for x in b_items if (x["properties"].get("proj:epsg") or x["properties"].get("proj:code")) == zone), b_items[0])
    after_b, transform, crs = read_bands(a, bbox)
    before_b, _, _ = read_bands(b, bbox)
    cands = match(candidates(change_mask(before_b, after_b), transform, crs), sites)
    return {"after": a["id"], "before": b["id"], "candidates": cands, "score": evaluate(cands, sites)}
