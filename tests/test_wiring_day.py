"""BUILD 16 — the wiring day (W6–W9): items that touch files the running worker reloads."""
from __future__ import annotations
import json, logging, os, time
from datetime import datetime, timedelta
from pathlib import Path
import sys

import numpy as np
import pytest

from forge import config as cfgmod


def test_w6_the_log_rolls_over_at_midnight(tmp_path):
    from forge.log import DailyFileHandler
    now = [datetime(2026, 11, 11, 23, 59, 50)]
    h = DailyFileHandler(tmp_path, clock=lambda: now[0])
    h.setFormatter(logging.Formatter("%(message)s"))
    lg = logging.getLogger("forge.test_w6")
    lg.propagate = False
    lg.addHandler(h)
    lg.setLevel(logging.INFO)
    try:
        lg.info("before midnight")
        now[0] += timedelta(seconds=20)
        lg.info("after midnight")
    finally:
        lg.removeHandler(h)
        h.close()
    a = (tmp_path / "forge_2026-11-11.log").read_text(encoding="utf-8")
    b = (tmp_path / "forge_2026-11-12.log").read_text(encoding="utf-8")
    assert "before midnight" in a and "after midnight" not in a
    assert "after midnight" in b and "before midnight" not in b


@pytest.mark.skipif(not hasattr(time, "tzset"), reason="time.tzset is Linux-only — on Windows the clock is local already")
def test_w7_job_ids_in_local_time_in_the_linux_vm(tmp_path, monkeypatch):
    cfgp = tmp_path / "forge.json"
    cfgp.write_text(json.dumps({"timezone": "Asia/Tokyo"}), encoding="utf-8")
    old = os.environ.get("TZ")
    try:
        monkeypatch.setattr(os, "name", "posix")
        cfgmod.load(cfgp)
        assert os.environ["TZ"] == "Asia/Tokyo" and time.tzname[0] == "JST"
        monkeypatch.setattr(os, "name", "nt")                        # Windows: untouched
        os.environ["TZ"] = "UTC"; time.tzset()
        cfgp.write_text(json.dumps({"timezone": "Asia/Tokyo"}), encoding="utf-8")
        cfgmod.load(cfgp)
        assert os.environ["TZ"] == "UTC"
    finally:
        if old is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = old
        time.tzset()


# --- W10: the intake on real JPEG sheets
def _jpeg(eye=False):
    import io as _io
    import numpy as np
    from PIL import Image
    import n4_fixtures as fx
    bg = Image.new("RGB", (900, 420), (255, 255, 255))
    im = fx.paste_all(bg, [fx.figure(360, fx.COLOURS[i], pocket=True, eye=eye) for i in range(3)], [(60 + i * 280, 30) for i in range(3)])
    arr = np.asarray(im.convert("RGB")).astype(np.int32)
    arr = arr + np.random.default_rng(5).integers(-5, 6, arr.shape)
    b = _io.BytesIO()
    Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).save(b, "JPEG", quality=80)
    b.seek(0)
    return Image.open(b).convert("RGBA")


def test_w10_the_intake_clears_jpeg_gaps_by_the_rule_and_obeys_a_person():
    from forge.night4 import intake as it
    img = _jpeg()
    bd = it.backdrop(img)
    raw, _ = it.foreground(img, bd, auto_pockets=False)        # what detect sees: the gaps are still "figure"
    auto, _ = it.foreground(img, bd)                            # nobody decided: the rule clears them
    kept, _ = it.foreground(img, bd, holes=[])                  # a person kept every gap as figure
    assert int((raw & ~auto).sum()) > 1000                      # three arm gaps cleared
    assert np.array_equal(kept, raw)                            # the person's choice wins over the rule
    det = it.detect(img)
    assert len(det["figures"]) == 3 and np.array_equal(det["_fg"], raw)
    # a person marks one gap: exactly that one goes
    lab_ids = set()
    from forge.night4 import cc
    near = it._near(np.asarray(img)[..., :3], bd["keys"], int(bd["tolerance"]))
    lab, _n = cc.label(near, 4)
    ys, xs = np.nonzero(raw & ~auto)
    one = [int(xs[0]), int(ys[0])]
    marked, _ = it.foreground(img, bd, holes=[one])
    gone = raw & ~marked
    assert gone.any() and int(gone.sum()) < int((raw & ~auto).sum())


def test_w10_an_eye_is_not_taken_for_a_gap():
    from forge.night4 import intake as it
    import n4_fixtures as fx
    img = fx.white_backdrop().convert("RGBA")
    bd = it.backdrop(img)
    raw, _ = it.foreground(img, bd, auto_pockets=False)
    auto, _ = it.foreground(img, bd)
    lab, n = __import__("forge.night4.cc", fromlist=["cc"]).label(raw & ~auto, 8)
    boxes = __import__("forge.night4.cc", fromlist=["cc"]).boxes(lab, n)
    assert all((b["bbox"][3] - b["bbox"][1]) > 20 for b in boxes), boxes     # nothing eye-sized was cleared


def test_w10_cut_off_only_at_the_sheet_edge_or_a_narrowed_box():
    from PIL import Image
    from forge.night4 import intake as it
    rgba = Image.new("RGBA", (200, 100), (0, 0, 0, 0))
    fg = np.zeros((100, 200), bool)
    fg[20:80, 50:90] = True                                     # a figure in the middle of the sheet
    fg[30:100, 150:200] = True                                  # one that runs off the right and bottom edges
    a = np.asarray(rgba).copy(); a[fg] = (200, 50, 50, 255); rgba = Image.fromarray(a, "RGBA")
    bd = {"kind": "alpha", "keys": [], "tolerance": 30}
    _f, info = it.cut(rgba, fg, [50, 20, 90, 80], bd, [50, 20, 90, 80])          # tight detected box
    assert info["touches_box"] == []                                            # was "left, right, top" before
    _f, info = it.cut(rgba, fg, [150, 30, 200, 100], bd, [150, 30, 200, 100])
    assert info["touches_box"] == ["right (sheet edge)", "bottom (sheet edge)"]
    _f, info = it.cut(rgba, fg, [60, 20, 90, 80], bd, [50, 20, 90, 80])          # a person narrowed the left side
    assert info["touches_box"] == ["left (box narrowed)"]
    _f, info = it.cut(rgba, fg, [60, 20, 90, 80], bd)                            # an old mapping: no bbox_found
    assert info["touches_box"] == []
