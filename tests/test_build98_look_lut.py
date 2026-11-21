"""BUILD 98 Part 9: a .cube grade into Godot's 3D colour correction (forge/look_lut.py). Made-up LUTs, tmp_path only."""
import numpy as np
import pytest

from forge import look_lut as L


def test_identity_changes_nothing():
    rgb = (np.random.default_rng(1).random((8, 9, 3)) * 255).astype(np.uint8)
    out = L.apply(L.identity(17), rgb)
    assert np.abs(out.astype(int) - rgb.astype(int)).max() <= 1


def test_cube_round_trip_and_strip_layout(tmp_path):
    lut = L.identity(5)
    lut["table"] = lut["table"] * np.array([1.0, 0.5, 1.0], np.float32)       # halve green
    L.write_cube(lut, tmp_path / "g.cube")
    back = L.read_cube(tmp_path / "g.cube")
    assert back["size"] == 5 and np.allclose(back["table"], lut["table"], atol=1e-5)
    strip = L.to_strip(back)
    assert strip.shape == (5, 25, 3)
    # slice 4 (blue full), x within = red, y = green: top-right of the last slice is red 1, green 0, blue 1
    assert tuple(strip[0, 24]) == (255, 0, 255)
    assert tuple(strip[4, 20]) == (0, 128, 255)                     # green full, halved
    out = L.apply(back, np.array([[[200, 200, 200]]], np.uint8))
    assert abs(int(out[0, 0, 1]) - 100) <= 2 and abs(int(out[0, 0, 0]) - 200) <= 2


def test_make_writes_png_and_godot_import(tmp_path):
    L.write_cube(L.identity(9), tmp_path / "town.cube")
    meta = L.make(tmp_path / "town.cube", tmp_path / "out", "linden_mills", "look/luts")
    imp = (tmp_path / "out" / "linden_mills_grade_lut.png.import").read_text(encoding="utf-8")
    assert 'importer="3d_texture"' in imp and "slices/horizontal=9" in imp and "res://look/luts/" in imp
    assert meta["size"] == 9


def test_bad_files_say_why(tmp_path):
    (tmp_path / "a.cube").write_text("LUT_1D_SIZE 4\n0 0 0\n", encoding="utf-8")
    with pytest.raises(L.LutError, match="1D"):
        L.read_cube(tmp_path / "a.cube")
    (tmp_path / "b.cube").write_text("LUT_3D_SIZE 2\n0 0 0\n", encoding="utf-8")
    with pytest.raises(L.LutError, match="8 rows"):
        L.read_cube(tmp_path / "b.cube")
