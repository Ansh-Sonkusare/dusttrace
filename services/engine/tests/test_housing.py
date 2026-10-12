import pytest

from dusttrace import housing

BBOX = [72.835, 19.09, 72.91, 19.14]


def test_grid_covers_the_box_in_cells_of_about_250_m():
    cells = housing.grid(BBOX, cell_m=250)
    lat_n = len({c["bbox"][1] for c in cells})
    lon_n = len({c["bbox"][0] for c in cells})
    assert lat_n == 23 and lon_n == 32 and len(cells) == lat_n * lon_n  # 5.6 km x 7.9 km
    c = cells[0]
    assert c["bbox"][0] == pytest.approx(BBOX[0]) and c["bbox"][1] == pytest.approx(BBOX[1])
    assert (c["bbox"][3] - c["bbox"][1]) * 111_320 == pytest.approx(250, rel=0.01)
    assert c["lat"] == pytest.approx((c["bbox"][1] + c["bbox"][3]) / 2)
    assert len({c["id"] for c in cells}) == len(cells)
    assert max(x["bbox"][3] for x in cells) >= BBOX[3] and max(x["bbox"][2] for x in cells) >= BBOX[2]


def test_census_people_are_spread_over_mapped_homes():
    d = housing.people_per_m2(823_885, 8_000_000)
    assert d == pytest.approx(0.103, abs=0.001)
    with pytest.raises(ValueError):
        housing.people_per_m2(823_885, 0)


def test_cells_with_enough_homes_become_estimated_housing_receptors():
    cells = [{"id": "c0_0", "bbox": [72.85, 19.10, 72.8524, 19.1023], "lat": 19.10115, "lon": 72.8512},
             {"id": "c0_1", "bbox": [72.8524, 19.10, 72.8548, 19.1023], "lat": 19.10115, "lon": 72.8536},
             {"id": "c0_2", "bbox": [72.8548, 19.10, 72.8572, 19.1023], "lat": 19.10115, "lon": 72.856}]
    areas = {"c0_0": 40_000.0, "c0_1": 1_000.0, "c0_2": 0.0}
    recs = housing.receptors(cells, areas, people_per_m2=0.1, min_area_m2=3_000)
    assert len(recs) == 1
    r = recs[0]
    assert r["id"] == "res-c0_0" and r["kind"] == "housing" and r["source"] == "osm"
    assert r["population"] == 4_000 and r["name"] == "Homes for about 4,000 people (estimated)"
    assert (r["lat"], r["lon"]) == (19.10115, 72.8512)


def test_in_ward_cells_are_those_whose_centre_is_inside_the_ward_box():
    cells = housing.grid([72.82, 19.08, 72.93, 19.15], cell_m=250)
    inside = housing.in_box(cells, BBOX)
    assert 0 < len(inside) < len(cells)
    assert all(BBOX[0] <= c["lon"] <= BBOX[2] and BBOX[1] <= c["lat"] <= BBOX[3] for c in inside)
