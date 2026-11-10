"""G1: the morning report on a fixture queue — counts, causes, wall time, per-checkpoint speed, next steps."""
import json
from datetime import datetime

from PIL import Image

from forge import config as cfgmod, night_report


def world(tmp_path):
    jobs, out = tmp_path / "jobs", tmp_path / "out"
    for s in ("pending", "running", "done", "failed", "paused"):
        (jobs / s).mkdir(parents=True)
    cfg = dict(cfgmod.load())
    cfg["paths"] = dict(cfg["paths"], jobs=str(jobs), out=str(out))
    cfg["allow_external_paths"] = True
    return cfg, jobs, out


def put(jobs, out, state, jid, **kw):
    j = {"id": jid, "type": "render", "batch": "bakeoff/s1", "checkpoint": "sd_xl_base_1.0.safetensors", **kw}
    (jobs / state / f"{jid}.json").write_text(json.dumps(j), encoding="utf-8")
    if state == "done":
        (out / jid).mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (64, 36), (120, 80, 40)).save(out / jid / "card.png")


def test_night_report_counts_causes_and_next(tmp_path):
    cfg, jobs, out = world(tmp_path)
    for i in range(4):
        put(jobs, out, "done", f"D{i}", name=f"cell{i}", started_at=f"2026-11-08T22:0{i}:00",
            finished_at=f"2026-11-08T22:0{i}:40", result={"outputs": ["card.png"], "seconds": 40 + i})
    put(jobs, out, "done", "OLD", started_at="2026-11-01T22:00:00", finished_at="2026-11-01T22:01:00", result={"seconds": 9})
    for i in range(3):
        put(jobs, out, "failed", f"F{i}", name=f"bad{i}", started_at="2026-11-08T23:00:00",
            finished_at="2026-11-08T23:00:05", error=f"ValueError: invalid literal for int() with base 10: 'x{i}'\nmore")
    put(jobs, out, "pending", "P0", batch="bakeoff/s2")
    (out / "bakeoff" / "s1").mkdir(parents=True)
    (out / "bakeoff" / "s1" / "index.html").write_text("x")
    (out / "bakeoff" / "s1" / "plan.json").write_text(json.dumps({"skipped_existing": {"done": 7, "pending": 1}}))
    ht, md, rep = night_report.build(cfg, since=datetime(2026, 11, 8, 20), until=datetime(2026, 11, 9, 8))
    b = {x["name"]: x for x in rep["batches"]}
    s1 = b["bakeoff/s1"]
    assert s1["counts"] == {"done": 4, "failed": 3}                     # OLD is outside the window
    assert s1["skipped"] == 8 and s1["wall_s"] == 3605.0
    assert s1["sec_by_ckpt"]["sd_xl_base_1.0.safetensors"] == {"n": 4, "median": 41.5, "max": 43.0}
    assert len(s1["causes"]) == 1 and s1["causes"][0][1] == 3 and "base #" in s1["causes"][0][0]
    assert s1["index"] == "../bakeoff/s1/index.html" and s1["strip"] and (out / "reports" / s1["strip"]).exists()
    assert b["bakeoff/s2"]["only_waiting"]
    assert rep["slowest"][0]["seconds"] == 43
    assert rep["models"][0]["licence"] == "ok"                          # SDXL base is registered commercial-OK
    assert "bakeoff_report.bat s1" in rep["next"] and any("retry_failed" in n for n in rep["next"])
    text = md.read_text(encoding="utf-8")
    assert "failed ×3" in text and "bake-off page" in text
    assert "open the bake-off page" in ht.read_text(encoding="utf-8")


def test_cause_folds_numbers_and_takes_first_line():
    assert night_report.cause("OSError: 12 bad\ntrace") == "OSError: # bad"
    assert night_report.cause(None) == "unknown error"
