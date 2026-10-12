import numpy as np
import pytest
from rasterio.transform import from_origin

from dusttrace import discover

# A 100 x 100 px (1 km) patch of UTM 43N around Andheri East, 10 m pixels.
TRANSFORM = from_origin(276000, 2117000, 10, 10)
CRS = "EPSG:32643"


def scene(bare=None, cloud=None):
    """Vegetated scene; `bare` (rows, cols) slices become bare soil; `cloud` slices are flagged cloudy."""
    shape = (100, 100)
    b = {"blue": np.full(shape, 400.0), "red": np.full(shape, 300.0), "nir": np.full(shape, 3000.0),
         "swir16": np.full(shape, 1500.0), "scl": np.full(shape, 4)}  # SCL 4 = vegetation
    if bare is not None:
        for k, v in {"blue": 1200.0, "red": 1600.0, "nir": 2000.0, "swir16": 3200.0}.items():
            b[k][bare] = v
        b["scl"][bare] = 5  # bare soil
    if cloud is not None:
        b["scl"][cloud] = 9  # cloud, high probability
    return b


def test_bare_soil_index_rises_and_ndvi_falls_on_cleared_ground():
    veg, bare = discover.indices(scene()), discover.indices(scene(bare=(slice(0, 100), slice(0, 100))))
    assert bare["bsi"].mean() > veg["bsi"].mean() + 0.2
    assert bare["ndvi"].mean() < veg["ndvi"].mean() - 0.3


def test_change_mask_finds_new_clearing_and_ignores_clouds():
    before = scene()
    after = scene(bare=(slice(20, 30), slice(40, 55)), cloud=(slice(60, 80), slice(0, 100)))
    after["blue"][60:80, :] = 5000.0  # a bright cloud would look like change if not masked
    m = discover.change_mask(before, after)
    assert m[20:30, 40:55].all()
    assert not m[60:80, :].any()
    assert m.sum() == 10 * 15


def test_candidates_are_patches_big_enough_with_positions_and_areas():
    m = np.zeros((100, 100), dtype=bool)
    m[20:30, 40:55] = True   # 150 px = 15,000 m2
    m[90:92, 5:7] = True     # 4 px = 400 m2: too small
    cands = discover.candidates(m, TRANSFORM, CRS)
    assert len(cands) == 1
    c = cands[0]
    assert c["area_m2"] == 15000
    assert 19.0 < c["lat"] < 19.2 and 72.7 < c["lon"] < 73.0


def test_matching_and_scoring_against_known_sites():
    cands = [{"lat": 19.1170, "lon": 72.8560, "area_m2": 9000}, {"lat": 19.1300, "lon": 72.8900, "area_m2": 4000}]
    sites = [{"id": "A", "lat": 19.1172, "lon": 72.8563}, {"id": "Z", "lat": 19.1000, "lon": 72.8400}]
    matched = discover.match(cands, sites, radius_m=300)
    assert [c["site_id"] for c in matched] == ["A", None]
    score = discover.evaluate(matched, sites, radius_m=300)
    assert score == pytest.approx({"precision": 0.5, "recall": 0.5, "found": 2, "known": 2})
