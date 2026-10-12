"""Small geometry helpers: is a point inside a ward's boundary polygon (lon/lat GeoJSON)?"""

from __future__ import annotations


def _in_ring(lat: float, lon: float, ring: list) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def inside(lat: float, lon: float, boundary: dict | None) -> bool:
    """Point in a GeoJSON Polygon (outer ring, minus holes). No boundary means no restriction."""
    if not boundary:
        return True
    rings = boundary["coordinates"]
    return _in_ring(lat, lon, rings[0]) and not any(_in_ring(lat, lon, h) for h in rings[1:])


def in_ward(lat: float, lon: float, ward: dict) -> bool:
    b = ward.get("bbox")
    if b and not (b[0] <= lon <= b[2] and b[1] <= lat <= b[3]):
        return False
    return inside(lat, lon, ward.get("boundary"))
