"""BUILD 77 — the ground is true: a DTED Level 0 reader of the forge's own, proved against known ground; the bakes with
their dials; the ground along a line. The pure tests write their own cells; the proof against the real data runs only
when William's DTED is where forge.json says (it is skipped, and says so, when it is not)."""
from __future__ import annotations

import json
import math
import zipfile
from pathlib import Path

import numpy as np
import pytest

from forge import cli_terrain
from forge import config as cfgmod
from forge.terrain import bake, dted, proof


def _cell(tmp_path, lat, lon, f=None, **kw):
    n = 121
    jj, ii = np.meshgrid(np.arange(n), np.arange(n))       # ii: longitude line, jj: post (south to north)
    h = f(ii, jj) if f else (100.0 + ii * 2.0 + jj * 1.0)
    ew = "e" if lon >= 0 else "w"
    ns = "n" if lat >= 0 else "s"
    return dted.write_cell(tmp_path / f"{ew}{abs(lon):03d}" / f"{ns}{abs(lat):02d}.dt0", lat, lon, h.astype(float), **kw), h


def test_sign_and_magnitude_round_trip():
    for v in (-1, -32767, 0, 32767, -86, 4401):
        w = dted.to_sign_magnitude(np.array([v]))
        assert int(dted.sign_magnitude(w.astype(np.uint16))[0]) == v
    assert int(dted.sign_magnitude(np.array([0x8001], np.uint16))[0]) == -1          # not two's complement (that would be -32767)


def test_a_synthetic_cell_is_read_back_positive_negative_and_null(tmp_path):
    def f(i, j):
        h = (i - 60.0) * 3.0 + j * 0.0
        return h
    p, h = _cell(tmp_path, 38, -80, f)
    h2 = h.copy()
    h2[10, 10] = np.nan
    dted.write_cell(p, 38, -80, h2)
    c = dted.read_cell(p.read_bytes(), p.name)
    assert c.n_lon == 121 and c.n_lat == 121 and c.dlat_s == 30.0
    assert c.grid[0, 0] == -180 and c.grid[120, 0] == 180 and np.isnan(c.grid[10, 10]) and c.nulls == 1
    assert abs(c.height(38.5, -80 + 60 / 120) - 0.0) < 1e-6
    # a null corner is left out of the average, never read as a pit
    lat = 38 + 10 * 30 / 3600 + 1e-9
    lon = -80 + 10 * 30 / 3600
    assert c.height(lat, lon) > -200


def test_a_bad_checksum_and_a_level_1_cell_are_refused(tmp_path):
    p, _ = _cell(tmp_path, 38, -80, corrupt_record=5)
    with pytest.raises(dted.DtedError, match="checksum"):
        dted.read_cell(p.read_bytes(), "x")
    q, _ = _cell(tmp_path / "l1", 38, -80, level=1)
    with pytest.raises(dted.DtedError, match="only Level 0"):
        dted.read_cell(q.read_bytes(), "y")
    (tmp_path / "lib" / "w080").mkdir(parents=True)
    (tmp_path / "lib" / "w080" / "n38.dt1").write_bytes(b"x")
    lib = dted.Library.open(tmp_path / "lib")
    assert not lib.found and lib.skipped and "only Level 0" in lib.skipped[0][1]


def test_cells_are_read_straight_from_a_zip_and_a_window_across_four_is_seamless(tmp_path):
    src = tmp_path / "src"
    plane = lambda la0, lo0: (lambda i, j: 50.0 + (lo0 + i / 120.0 + 80.0) * 100.0 + (la0 + j / 120.0 - 38.0) * 200.0)
    for la in (38, 39):
        for lo in (-80, -79):
            _cell(src, la, lo, plane(la, lo))
    z = tmp_path / "dted" / "world.zip"
    z.parent.mkdir()
    with zipfile.ZipFile(z, "w") as zz:
        for p in src.rglob("*.dt0"):
            zz.write(p, "DTED0-World-main/" + p.relative_to(src).as_posix())
    lib = dted.Library.open(tmp_path / "dted")
    assert lib.summary()["cells"] == 4
    w = lib.window(38.5, -79.5, 39.5, -78.5, posts=101)
    H = w["h"]
    assert not np.isnan(H).any() and len(w["cells"]) == 4
    # a plane stays a plane across the joins: second differences are ~0 everywhere
    # (the cells store whole metres, so a plane is a staircase of 1 m; a seam would jump by tens)
    assert np.abs(np.diff(H, 2, axis=1)).max() < 2.5 and np.abs(np.diff(H, 2, axis=0)).max() < 2.5
    h, cell = lib.height_at(39.0, -79.0)
    assert abs(h - (50 + 100 + 200)) < 1.0 and cell


def test_the_window_is_resampled_to_square_metres():
    class L(dted.Library):
        def cell(self, a, b):
            return dted.Cell(lat0=a, lon0=b, dlat_s=30, dlon_s=30, grid=np.zeros((121, 121)))
    w = L(Path(".")).window(60.0, 10.0, 61.0, 12.0, posts=200)
    rows, cols = w["h"].shape
    # at 60° north a degree of longitude is half a degree of latitude: 2° wide x 1° tall is about square
    assert abs(cols / rows - (2 * math.cos(math.radians(60.5)) * 111320) / 110574) < 0.05


def test_shrink_and_exaggerate_are_monotonic_and_detail_is_seeded():
    h = np.linspace(-50, 4000, 200)
    for ex in (1.0, 3.0, [[0, 1.0], [1000, 2.0], [4000, 4.0]]):
        e = bake.exaggerated(h, ex)
        assert (np.diff(e) >= 0).all() and (e[h <= 0] == h[h <= 0]).all()
    a = bake.detail_noise((40, 50), 6.0, seed=3)
    assert np.array_equal(a, bake.detail_noise((40, 50), 6.0, seed=3)) and not np.array_equal(a, bake.detail_noise((40, 50), 6.0, seed=4))
    assert np.abs(a).max() <= 6.0 + 1e-9


def test_a_crater_lowers_its_centre_raises_its_rim_and_touches_nothing_outside():
    X, Y = np.meshgrid(np.arange(0, 4000, 20.0), np.arange(0, 4000, 20.0))
    h = np.full(X.shape, 300.0)
    h2, m = bake.crater(h, X, Y, 2000, 2000, 400, 60, 15)
    r = np.hypot(X - 2000, Y - 2000)
    assert h2[r < 30].max() < 300 - 55 and h2[(r > 395) & (r < 420)].max() > 310
    assert (h2[r > 640] == 300).all() and not m[r > 640].any()


def test_the_profile_finds_the_highest_point_and_where_a_grade_comes_out(tmp_path):
    def ridge(i, j):                       # a north-south ridge in the middle of the cell, 900 m high at its crest
        x = (i - 60.0) / 12.0
        return 200.0 + 700.0 * np.exp(-x * x)
    _cell(tmp_path, 38, -80, ridge)
    lib = dted.Library.open(tmp_path)
    p = bake.profile(lib, (38.5, -79.97), bearing_deg=90, length_m=0.94 * 111320 * math.cos(math.radians(38.5)), step_m=200, grade=0.0)
    assert 880 <= p["highest"]["m"] <= 905 and p["comes_out"] is not None
    assert p["comes_out"]["km"] > p["highest"]["km"] and p["goes_in"]["km"] < p["highest"]["km"]
    p2 = bake.profile(lib, (38.5, -79.97), bearing_deg=90, length_m=0.94 * 111320 * math.cos(math.radians(38.5)), step_m=200, grade=0.02)
    assert p2["comes_out"]["km"] < p["comes_out"]["km"]                 # a climbing line reaches daylight sooner
    assert all(t["cover_m"] > 0 for t in p["thinnest_cover"])
    json.dumps(p)


def test_the_bakes_write_their_pictures_and_say_where_heights_came_from(tmp_path):
    _cell(tmp_path / "d", 38, -80)
    lib = dted.Library.open(tmp_path / "d")
    win = {"id": "t", "south": 38.2, "west": -79.8, "north": 38.8, "east": -79.2,
           "edits": [{"kind": "crater", "at": [38.5, -79.5], "radius_m": 3000, "depth_m": 40}]}
    hp = bake.terrain_window(lib, win, tmp_path / "o" / "t_height.png", {"posts": 64, "detail_m": 3})
    from PIL import Image
    im = Image.open(tmp_path / "o" / "t_height.png")
    assert im.mode in ("I;16", "I") and hp["source"].startswith("DTED Level 0") and hp["invented"] and hp["edits"]
    prov = json.loads((tmp_path / "o" / "t_height.json").read_text())
    assert prov["dials"]["detail_m"] == 3 and prov["window"]["south"] == 38.2
    sp = bake.terrain_shade(lib, win, tmp_path / "o" / "t_shade.png", {"posts": 64}, layers_out=tmp_path / "o" / "t_how.png")
    assert (tmp_path / "o" / "t_how.png").exists() and sp["layers"]["edited"] == "red"
    wr = bake.terrain_water(tmp_path / "o" / "t_shade.png", win, tmp_path / "no_ne", tmp_path / "o" / "t_water.png")
    assert not wr["ok"] and "ne_10m_coastline.geojson" in wr["message"]


def test_the_page_says_plainly_when_the_folder_is_absent(tmp_path):
    lib = dted.Library.open(tmp_path / "nothing_here")
    assert not lib.found and lib.summary()["cells"] == 0


REAL = cfgmod.ROOT / "local" / "dted"


@pytest.mark.skipif(not any(REAL.glob("*.zip")) and not any(REAL.rglob("*.dt0")) if REAL.exists() else True,
                    reason="William's DTED Level 0 is not in local/dted on this computer — the proof against known ground is skipped")
def test_the_reader_agrees_with_known_ground():
    t = proof.table(dted.Library.open(REAL))
    assert not t["stop"]
    by = {r["name"]: r for r in t["rows"]}
    assert by["Badwater Basin, Death Valley"]["reads_m"] < 0
    assert abs(by["Denver, Colorado (State Capitol step)"]["diff_m"]) < 60
    assert all(r["diff_m"] < 60 for r in t["rows"] if r["what"] == "summit")         # summits read low, never high
