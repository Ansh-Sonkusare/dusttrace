import pytest

from dusttrace import config, geo, housing


def test_each_pilot_ward_has_a_seed_with_its_real_boundary():
    for wid in ("K-East", "P-North"):
        w = config.load_seed(wid)["ward"]
        assert w["id"] == wid and w["boundary"]["type"] == "Polygon" and len(w["boundary"]["coordinates"][0]) > 10
    pn = config.load_seed("P-North")
    assert pn["sites"] == [] and pn["receptors"] == []  # real data only, no demo sites
    assert config.load_seed()["ward"]["id"] == "K-East"
    with pytest.raises(KeyError):
        config.load_seed("Q-Nowhere")


def test_points_are_tested_against_the_ward_polygon_not_its_box():
    pn = config.load_seed("P-North")["ward"]
    assert geo.inside(19.1864, 72.8485, pn["boundary"])      # Malad West station area
    assert not geo.inside(19.1136, 72.8697, pn["boundary"])  # Andheri East, K-East's centre
    assert not geo.inside(19.14, 72.78, pn["boundary"])      # inside the box, but the sea
    ke = config.load_seed("K-East")["ward"]
    assert geo.inside(ke["center_lat"], ke["center_lon"], ke["boundary"])


def test_housing_counts_the_cells_inside_the_ward_polygon():
    w = config.load_seed("P-North")["ward"]
    cells = housing.grid(w["bbox"])
    inside = housing.in_ward(cells, w)
    assert 0 < len(inside) < len(cells)
    assert all(geo.inside(c["lat"], c["lon"], w["boundary"]) for c in inside)
    assert housing.CENSUS_2011["P-North"] == 941_366
