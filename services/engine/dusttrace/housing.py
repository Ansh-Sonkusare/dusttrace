"""Real housing exposure (issue #31): census population spread over mapped residential land.

The ward's Census 2011 population is divided by the residential land mapped in OpenStreetMap
(`landuse=residential`) to get people per square metre of homes. Each ~250 m grid cell then gets
its share from the residential area inside it (clipped by the ohsome API), so plumes meet homes
where they are. Populations are estimates and labelled so.
"""

from __future__ import annotations

import math

from . import geo

# Census of India 2011, Primary Census Abstract, Mumbai Suburban, Greater Mumbai (M Corp.) wards
# 1249, 1255 and 1256 = K/E: 164,831 + 393,391 + 265,663. Via data.opencity.in "Mumbai - Ward wise
# Census Data". The 2011 figure is the latest ward-level census; today's population is higher.
# P/N: wards 1561-1566 = 10,121 + 168,576 + 120,217 + 391,381 + 247,521 + 3,550, same source.
CENSUS_2011 = {"K-East": 823_885, "P-North": 941_366}
CELL_M = 250
MIN_AREA_M2 = 3_000  # a cell needs at least this much mapped housing to count as a receptor


def grid(bbox: list[float], cell_m: int = CELL_M) -> list[dict]:
    """Cells of about `cell_m` metres covering the box, from its south-west corner."""
    min_lon, min_lat, max_lon, max_lat = bbox
    dlat = cell_m / 111_320
    dlon = cell_m / (111_320 * math.cos(math.radians((min_lat + max_lat) / 2)))
    n_lat = math.ceil(round((max_lat - min_lat) / dlat, 9))
    n_lon = math.ceil(round((max_lon - min_lon) / dlon, 9))
    cells = []
    for i in range(n_lat):
        for j in range(n_lon):
            b = [min_lon + j * dlon, min_lat + i * dlat, min_lon + (j + 1) * dlon, min_lat + (i + 1) * dlat]
            cells.append({"id": f"c{i}_{j}", "bbox": b, "lat": (b[1] + b[3]) / 2, "lon": (b[0] + b[2]) / 2})
    return cells


def in_ward(cells: list[dict], ward: dict) -> list[dict]:
    """Cells whose centre is inside the ward's boundary polygon (its box when it has none)."""
    return [c for c in cells if geo.in_ward(c["lat"], c["lon"], ward)]


def in_box(cells: list[dict], bbox: list[float]) -> list[dict]:
    return [c for c in cells if bbox[0] <= c["lon"] <= bbox[2] and bbox[1] <= c["lat"] <= bbox[3]]


def people_per_m2(population: int, residential_m2: float) -> float:
    if residential_m2 <= 0:
        raise ValueError("No residential land mapped: can't spread the census population.")
    return population / residential_m2


def receptors(cells: list[dict], areas: dict, people_per_m2: float, min_area_m2: float = MIN_AREA_M2,
              ward_id: str = "K-East") -> list[dict]:
    """One housing receptor per cell with enough mapped homes, at the cell centre. Ids carry the ward:
    every ward's grid starts at c0_0."""
    out = []
    for c in cells:
        a = float(areas.get(c["id"]) or 0.0)
        if a < min_area_m2:
            continue
        pop = int(round(a * people_per_m2, -1))
        out.append({"id": f"res-{ward_id.lower()}-{c['id']}", "name": f"Homes for about {pop:,} people (estimated)", "kind": "housing",
                    "lat": round(c["lat"], 6), "lon": round(c["lon"], 6), "population": pop, "source": "osm"})
    return out
