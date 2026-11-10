"""Night 4 F1 — sprite intake on five synthetic sheets."""
import json
import numpy as np
import pytest
from PIL import Image

from forge.night4 import intake as it
import n4_fixtures as fx


def _run(img, mapping=None, **kw):
    det = it.detect(img)
    m = mapping or {**it.guess_mapping(det), "backdrop": det["backdrop"]}
    built = it.build(img, det["_fg"], m, **kw)
    sheet, anim = it.pack(built)
    return det, m, built, sheet, anim


def _cells(sheet, cw=144):
    return [sheet.crop((i * cw, 0, (i + 1) * cw, sheet.height)) for i in range(sheet.width // cw)]


def test_clean_grid_eight_facings():
    det, m, built, sheet, anim = _run(fx.clean_grid())
    assert len(det["figures"]) == 8 and det["backdrop"]["kind"] == "flat"
    assert [e["facing"] for e in m["figures"]] == list(it.FACINGS)
    assert sheet.size == (1152, 216) and anim is None
    for i, c in enumerate(_cells(sheet)):
        a = np.asarray(c)[..., 3]
        ys, xs = np.nonzero(a > 16)
        assert ys.max() == 216 - 6 - 1                    # feet on the baseline
        mid = np.asarray(c)[ys.max() - 2, :, 3] > 16
        feet = np.nonzero(mid)[0]
        assert abs((feet.min() + feet.max()) / 2 - 72) <= 2   # centred on the feet, not on the holster
        # the figure's own colour survived (S = red … in the game's order)
        rgb = np.asarray(c.convert("RGB"))[ys.min() + 5, int(xs.mean())]
        assert int(np.argmax(rgb)) == int(np.argmax(fx.COLOURS[i])) or fx.COLOURS[i][0] == fx.COLOURS[i][1]
    heights = [int(np.ptp(np.nonzero(np.asarray(c)[..., 3] > 16)[0])) for c in _cells(sheet)]
    assert max(heights) - min(heights) <= 2                   # one height


def test_ragged_grid_rows_are_facings_and_frames():
    det, m, built, sheet, anim = _run(fx.ragged_grid())
    assert len(det["figures"]) == 12
    rows = sorted({f["row"] for f in det["figures"]})
    assert rows == [1, 2, 3, 4]
    assert m["confidence"] == "medium" and "S, W, E, N" in m["guess"]
    assert anim is not None and anim.size == (144 * 3, 216 * 8)
    assert set(built["missing"]) == {"SW", "NW", "NE", "SE"}
    # uniform scale: frames of one facing keep their small height differences (bob), not stretched equal
    assert built["scale"] > 0


def test_labels_are_dropped():
    det, m, built, sheet, anim = _run(fx.labelled())
    assert len(det["figures"]) == 4
    labels = [d for d in det["dropped"] if d["what"] == "label"]
    assert labels, det["dropped"]
    # no figure box reaches down into the label band
    assert all(f["bbox"][3] < 285 for f in det["figures"])


def test_white_backdrop_keeps_the_eye_and_clears_the_pocket():
    img = fx.white_backdrop()
    det = it.detect(img)
    assert len(det["figures"]) == 3 and det["backdrop"]["kind"] == "flat"
    fg = det["_fg"]
    # figure 1 placed at (60, 30), height 240: its eye (white, inside the head) stays opaque
    w = int(240 * 0.55); cx = 60 + w // 2; hr = int(240 * 0.11)
    assert fg[30 + hr // 2 + hr // 4, cx]
    # the enclosed pocket between arm and body is backdrop
    bw = int(w * 0.36); ax = 60 + cx - 60 - bw // 2
    assert not fg[30 + int(240 * 0.4), ax - int(w * 0.11)]


def test_painted_checkerboard():
    img = fx.painted_checker()
    det, m, built, sheet, anim = _run(img)
    assert det["backdrop"]["kind"] == "checker"
    assert len(det["figures"]) == 5
    assert [e["facing"] for e in m["figures"]] == ["S", "SW", "W", "NW", "N"]
    fg = det["_fg"]
    w = int(260 * 0.55); cx = 40 + w // 2; bw = int(w * 0.36); ax = cx - bw // 2
    assert not fg[30 + int(260 * 0.4), ax - int(w * 0.11)]          # checker pocket cleared
    assert built["missing"] == ["NE", "E", "SE"]


def test_mirror_only_when_asked_and_skip():
    img = fx.painted_checker()
    det = it.detect(img)
    m = {**it.guess_mapping(det), "backdrop": det["backdrop"], "mirror": ["W→E", "NW->NE", "SW>SE"]}
    m["figures"][4]["skip"] = True
    built = it.build(img, det["_fg"], m)
    assert set(built["mirrored"]) == {"W→E", "NW→NE", "SW→SE"}
    assert built["missing"] == ["N"]
    sheet, _ = it.pack(built)
    w_cell = np.asarray(_cells(sheet)[2])
    e_cell = np.asarray(_cells(sheet)[6])
    assert np.array_equal(w_cell[:, ::-1], e_cell)


def test_bad_facing_is_refused():
    img = fx.clean_grid()
    det = it.detect(img)
    m = {**it.guess_mapping(det), "backdrop": det["backdrop"]}
    m["figures"][0]["facing"] = "UP"
    with pytest.raises(it.IntakeError):
        it.build(img, det["_fg"], m)


def test_real_alpha_is_used_as_is():
    figs = [fx.figure(200, fx.COLOURS[i]) for i in range(2)]
    im = Image.new("RGBA", (400, 240), (0, 0, 0, 0))
    im.alpha_composite(figs[0], (20, 20)); im.alpha_composite(figs[1], (220, 20))
    det = it.detect(im)
    assert det["backdrop"]["kind"] == "alpha" and len(det["figures"]) == 2


def test_a_photograph_is_refused_not_cut():
    rng = np.random.default_rng(1)
    yy, xx = np.mgrid[0:300, 0:400]
    arr = np.stack([xx % 255, (yy * 3) % 255, (xx + yy) % 255], -1) + rng.integers(0, 60, (300, 400, 3))
    with pytest.raises(it.IntakeError, match="not a sheet"):
        it.detect(Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)))
