"""G3: tiled refine — plan coverage/overlap/no slivers, merge keeps flat flat and gradients gradients, seam score."""
import numpy as np
from PIL import Image

from forge.ops import bigtiles as bt


def covered(rects, W, H):
    m = np.zeros((H, W), bool)
    for x0, y0, x1, y1 in rects:
        m[y0:y1, x0:x1] = True
    return m.all()


def test_plan_covers_overlaps_and_has_no_slivers():
    for (W, H), tile, ov in [((6144, 3072), (1344, 768), 128), ((3840, 2160), (1536, 1152), 128),
                             ((3456, 2112), (1344, 768), 160), ((1000, 500), (1344, 768), 128), ((1400, 768), (1344, 768), 128)]:
        rects = bt.plan((W, H), tile, ov)
        assert covered(rects, W, H)
        tw, th = min(tile[0], W), min(tile[1], H)
        assert all((r[2] - r[0], r[3] - r[1]) == (tw, th) for r in rects)          # every tile full size: no slivers
        assert all(0 <= r[0] and 0 <= r[1] and r[2] <= W and r[3] <= H for r in rects)
        xs, ys = sorted({r[0] for r in rects}), sorted({r[1] for r in rects})
        for a, b in zip(xs, xs[1:]):
            assert a + tw - b >= ov                                                 # overlap at least as asked
        for a, b in zip(ys, ys[1:]):
            assert a + th - b >= ov
    assert len(bt.plan((3840, 2160), (1536, 1152), 128)) == 6


def test_merge_flat_stays_flat_and_gradient_stays_gradient():
    flat = Image.new("RGB", (900, 500), (90, 140, 200))
    rects = bt.plan(flat.size, (400, 300), 96)
    assert np.array_equal(np.asarray(bt.merge(bt.split(flat, rects), rects, flat.size)), np.asarray(flat))
    x = np.tile(np.linspace(0, 255, 900), (500, 1))
    grad = Image.fromarray(np.stack([x, x[:, ::-1], np.full_like(x, 60)], 2).astype(np.uint8))
    m = np.asarray(bt.merge(bt.split(grad, rects), rects, grad.size)).astype(int)
    assert np.abs(m - np.asarray(grad).astype(int)).max() <= 1
    assert (np.diff(m[:, :, 0], axis=1) >= 0).all()                                  # still monotonic left→right
    # deterministic
    assert np.array_equal(m, np.asarray(bt.merge(bt.split(grad, rects), rects, grad.size)).astype(int))


def test_seam_score_zero_when_tiles_agree_and_rises_when_they_do_not():
    img = bt.test_picture((800, 400))
    rects = bt.plan(img.size, (500, 400), 128)
    same = bt.seams(bt.split(img, rects), rects)
    assert len(same) == 1 and same[0]["score"] == 0 and same[0]["dir"] == "h"
    tiles = bt.split(img, rects)
    tiles[1] = Image.fromarray(np.clip(np.asarray(tiles[1]).astype(int) + 30, 0, 255).astype(np.uint8))
    s = bt.seams(tiles, rects)[0]
    assert s["colour"] > 25 and s["score"] > 10


def test_demo_merge_hides_the_joins_better_than_pasting():
    img = bt.test_picture((1600, 900))
    merged, rects, seam_list, naive = bt.demo(img, (700, 500), 128)
    ref = np.asarray(bt.fake_repaint(img)).astype(float)                              # the filter on the whole picture
    err_m = np.abs(np.asarray(merged).astype(float) - ref).mean()
    err_n = np.abs(np.asarray(naive).astype(float) - ref).mean()
    assert err_m <= err_n and err_m < 2.0
    assert bt.seam_sheet(merged, rects, seam_list).size[0] <= 2000
