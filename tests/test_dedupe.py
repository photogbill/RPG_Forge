"""N5: a second bake-off submit queues 0 new for a finished suite; failed cells are queued again; --skip-done for
plain batches; the ETA."""
import json

from forge import config as cfgmod, dedupe, eta


def world(tmp_path):
    cfg = dict(cfgmod.load())
    cfg["paths"] = dict(cfg["paths"], jobs=str(tmp_path / "jobs"), out=str(tmp_path / "out"))
    cfg["allow_external_paths"] = True
    for s in ("pending", "running", "done", "failed", "paused"):
        (tmp_path / "jobs" / s).mkdir(parents=True, exist_ok=True)
    return cfg


def cell(cat="scene", pid="p1", ck="a.safetensors", lo=None, seed=1, **tool):
    return {"type": tool.pop("type", "render"), "batch": "bakeoff/s1", "name": f"{cat}_{pid}_{seed}", "prompt": "x",
            "checkpoint": ck, "loras": [], "seed": seed, "size": [1024, 1024],
            "meta": {"suite": "s1", "category": cat, "prompt_id": pid, "checkpoint": ck, "lora": lo, "seed": seed}, **tool}


def put(tmp_path, state, job, jid):
    (tmp_path / "jobs" / state / f"{jid}.json").write_text(json.dumps({**job, "id": jid,
        "started_at": "2026-11-09T01:00:00", "finished_at": "2026-11-09T01:00:40"}), encoding="utf-8")


def test_second_submit_is_zero_new_and_failed_requeues(tmp_path):
    cfg = world(tmp_path)
    plan = [cell(seed=1), cell(seed=2), cell(seed=3), cell(lo="L.safetensors")]
    new, skipped = dedupe.filter_new(cfg, plan, "bakeoff/s1")
    assert len(new) == 4 and skipped == {}
    put(tmp_path, "done", plan[0], "j1")
    put(tmp_path, "pending", plan[1], "j2")
    put(tmp_path, "failed", plan[2], "j3")
    put(tmp_path, "paused", plan[3], "j4")
    new, skipped = dedupe.filter_new(cfg, plan, "bakeoff/s1")
    assert [j["seed"] for j in new] == [3]                       # only the failed one goes back in
    assert skipped == {"done": 1, "pending": 1, "paused": 1} and "--force" in dedupe.describe(skipped)


def test_tool_fields_are_part_of_the_identity(tmp_path):
    cfg = world(tmp_path)
    a = cell(type="scene_paint", refine=True, face_fix=False)
    put(tmp_path, "done", a, "j1")
    b = cell(type="scene_paint", refine=True, face_fix=True)     # same picture, another treatment → a new cell
    c = cell(type="scene_paint", refine=True, face_fix=False)
    new, _ = dedupe.filter_new(cfg, [b, c])
    assert new == [b]


def test_plain_batch_by_name_and_duplicates_in_one_plan(tmp_path):
    cfg = world(tmp_path)
    j = {"type": "icon", "batch": "tools_v1", "name": "t07_icon_coolant", "prompt": "a can"}
    put(tmp_path, "done", j, "x1")
    other = {"type": "icon", "batch": "tools_v1", "name": "t08", "prompt": "b"}
    new, skipped = dedupe.filter_new(cfg, [j, other, dict(other)])
    assert new == [other] and skipped == {"done": 1, "duplicate": 1}
    loose = {"type": "icon", "prompt": "no batch, no name"}
    assert dedupe.filter_new(cfg, [loose])[0] == [loose]


def test_eta_from_history(tmp_path):
    cfg = world(tmp_path)
    for i in range(5):
        put(tmp_path, "done", {"type": "render", "batch": "b"}, f"d{i}")          # 40 s each
    put(tmp_path, "pending", {"type": "render", "batch": "bakeoff/s1"}, "p1")
    put(tmp_path, "pending", {"type": "render", "batch": "bakeoff/s1"}, "p2")
    e = eta.estimate(cfg)
    assert e["pending"] == 2 and e["seconds"] == 80 and e["batches"]["bakeoff/s1"]["jobs"] == 2
    assert "2 job(s) queued" in eta.lines(cfg)[0] and eta.human(3900) == "1 h 05 min"
