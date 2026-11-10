"""G7: sprite tools — eight poses pack to 1152×216 with one baseline, the game's order, mirroring; previews; split."""
import numpy as np
from PIL import Image, ImageDraw

from forge.ops import sprites as sp

COLOURS = {f: (30 * i + 20, 200 - 20 * i, 90) for i, f in enumerate(sp.FACINGS)}


def pose(f, h=180, w=70, canvas=(300, 400), off=(40, 30)):
    im = Image.new("RGB", canvas, (0, 255, 0))                    # flat key background
    d = ImageDraw.Draw(im)
    x, y = off
    d.rectangle([x, y, x + w, y + h], fill=COLOURS[f])
    d.ellipse([x + w // 4, y - 30, x + 3 * w // 4, y], fill=COLOURS[f])
    return im


def test_pack_order_baseline_height_and_report(tmp_path):
    poses = {f: pose(f, h=120 + 15 * i, off=(20 + 9 * i, 40 + 7 * i)) for i, f in enumerate(sp.FACINGS)}
    for f, im in poses.items():
        im.save(tmp_path / f"sarah_{f}.png")
    sheet, rep = sp.facings_pack(sp.load_poses(tmp_path))
    assert sheet.size == (1152, 216) and rep["missing"] == [] and rep["order"] == list(sp.FACINGS)
    a = np.asarray(sheet)
    for i, f in enumerate(sp.FACINGS):
        cell = a[:, i * 144:(i + 1) * 144]
        ys, xs = np.nonzero(cell[..., 3] > 16)
        assert ys.max() + 1 == 216 - 6                            # feet on one baseline
        assert ys.max() - ys.min() + 1 in (rep["figure_height"], rep["figure_height"] - 1, rep["figure_height"] + 1)
        assert abs((xs.min() + xs.max()) / 2 - 72) <= 2           # centred on the column
        mid = cell[ys.max() - 20, int((xs.min() + xs.max()) / 2), :3]
        assert np.abs(mid.astype(int) - COLOURS[f]).max() < 12    # the game's order
    assert rep["touches_edge"] == []


def test_mirror_fills_missing_facing_and_edge_report():
    poses = {f: pose(f) for f in ("S", "SW", "W", "NW", "N")}
    sheet, rep = sp.facings_pack(poses, mirror=["W→E", "NW->NE", "SW>SE"])
    assert rep["missing"] == [] and set(rep["mirrored"]) == {"E", "NE", "SE"}
    wide = {"S": pose("S", h=60, w=280, canvas=(400, 200), off=(10, 60))}
    _, rep2 = sp.facings_pack(wide)
    assert rep2["touches_edge"] and rep2["touches_edge"][0]["facing"] == "S"
    assert sp.facing_of("hero_nw.png") == "NW" and sp.facing_of("x-sw-1.png") == "SW" and sp.facing_of("walk.png") is None


def test_previews_and_turnaround_split(tmp_path):
    sheet, _ = sp.facings_pack({f: pose(f) for f in sp.FACINGS})
    r = sp.anim_preview(sheet, tmp_path)
    assert r["layout"] == "facings" and (tmp_path / "turntable.gif").exists()
    assert Image.open(tmp_path / "turntable.gif").n_frames == 8
    rows = Image.new("RGBA", (144 * 4, 216 * 2))
    for r_ in range(2):
        for c in range(4):
            rows.alpha_composite(sheet.crop((c * 144, 0, (c + 1) * 144, 216)), (c * 144, r_ * 216))
    r2 = sp.anim_preview(rows, tmp_path / "rows")
    assert r2["layout"] == "rows" and len(r2["files"]) == 3
    turn = Image.new("RGB", (900, 300), (255, 255, 255))
    d = ImageDraw.Draw(turn)
    for x in (50, 350, 650):
        d.rectangle([x, 40, x + 150, 280], fill=(80, 60, 50))
    views = sp.turnaround_split(turn)
    assert len(views) == 3 and all(v.size == (151, 241) for v in views)
