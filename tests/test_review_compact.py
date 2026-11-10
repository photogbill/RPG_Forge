"""G2: compact review sheets — paging at 12, size limits, labels show only the fields that differ, index order, pairs."""
import json

from PIL import Image

from forge import review_compact as rc
from test_night_report import world


def done(jobs, out, jid, cat, ck, pid="p1", lora=None, **fields):
    j = {"id": jid, "type": "scene_paint", "batch": "bakeoff/s", "name": jid, "checkpoint": ck, "seed": 1001,
         "meta": {"suite": "s", "category": cat, "prompt_id": pid, "checkpoint": ck, "lora": lora, "seed": 1001,
                  "detail": {"size": 64, "at": [0.5, 0.5]}},
         "result": {"outputs": ["scene.png"]}, **fields}
    (jobs / "done" / f"{jid}.json").write_text(json.dumps(j), encoding="utf-8")
    (out / jid).mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1920, 1080), (40 + len(jid) * 7 % 200, 90, 140)).save(out / jid / "scene.png")


def test_paging_size_limits_and_index_order(tmp_path):
    cfg, jobs, out = world(tmp_path)
    for i in range(14):
        done(jobs, out, f"J{i:02d}", "raw", f"ck{i}.safetensors")
    done(jobs, out, "K00", "raw", "ck0.safetensors", pid="p2")
    folder, idx = rc.build_compact(cfg, "s")
    sheets = idx["sheets"]
    assert [(s["prompt"], s["page"], len(s["cells"])) for s in sheets] == [("p1", 1, 12), ("p1", 2, 2), ("p2", 1, 1)]
    assert [c["id"] for c in sheets[0]["cells"]][:3] == ["J00", "J01", "J10"] and sheets[0]["cells"][0]["n"] == 1
    for s in sheets:
        p = folder / s["sheet"]
        assert p.stat().st_size <= rc.MAX_BYTES and max(Image.open(p).size) <= 2000
    assert json.loads((folder / "review_index.json").read_text(encoding="utf-8"))["sheets"][1]["page"] == 2
    _, small = rc.build_compact(cfg, "s", prompt="p2")
    assert len(small["sheets"]) == 1


def test_labels_name_only_what_differs():
    rows = [{"checkpoint": "A.safetensors", "lora": None, "category": "t0", "meta": {"seed": 1}},
            {"checkpoint": "A.safetensors", "lora": "L.safetensors", "category": "t1", "meta": {"seed": 1}}]
    jobs = [{"refine": False, "steps": 28, "target": [1920, 1080]},
            {"refine": {"denoise": 0.3}, "steps": 28, "target": [1920, 1080], "freeu": True}]
    assert rc.differing(jobs) == ["freeu", "refine"]
    a, b = rc.labels_for(rows, jobs)
    assert a == "A · no LoRA · t0 · freeu=- · refine=off"
    assert b == "A · L · t1 · freeu=on · refine=denoise=0.3"
    assert "steps" not in a and "target" not in b


def test_pairs_by_category_with_detail_crop(tmp_path):
    cfg, jobs, out = world(tmp_path)
    for ck in ("a.safetensors", "b.safetensors"):
        done(jobs, out, f"A_{ck[0]}", "t0", ck, refine=False)
        done(jobs, out, f"B_{ck[0]}", "t1", ck, refine={"denoise": 0.3})
    folder, idx = rc.build_pairs(cfg, "s", "t0", "t1", crop=64)
    assert len(idx["sheets"]) == 2
    assert [c["side"] for c in idx["sheets"][0]["cells"]] == ["A", "B"]
    assert idx["sheets"][0]["detail"]["size"] == 64
    assert max(Image.open(folder / "pair_001.jpg").size) <= 2000
    try:
        rc.build_pairs(cfg, "s", "t0", "nope")
        assert False
    except ValueError as e:
        assert "t0, t1" in str(e)
