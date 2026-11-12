"""2026-11-11 (William: "any images we don't need, can you delete?") — only true duplicates go: ComfyUI's own copy of each
picture (out/_comfy/forge*.png) once it is old, and the bake-off trees' copies become hard links to the job's render."""
from __future__ import annotations
import json, os, time

from forge import bakeoff, config as cfgmod
from forge.night4 import housekeeping


def _cfg(tmp_path, monkeypatch):
    cfg = cfgmod.load()
    cfg["allow_external_paths"] = True
    cfg["paths"] = dict(cfg["paths"], out=str(tmp_path / "out"), jobs=str(tmp_path / "jobs"))
    monkeypatch.setattr(cfgmod, "ROOT", tmp_path)
    (tmp_path / "jobs" / "done").mkdir(parents=True)
    return cfg


def test_prune_comfy_deletes_only_old_forge_pictures(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    d = tmp_path / "out" / "_comfy"
    d.mkdir(parents=True)
    old, new, other = d / "forge_00001_.png", d / "forge_00002_.png", d / "my_own.png"
    for f in (old, new, other):
        f.write_bytes(b"x" * 10)
    t = time.time() - 3600
    os.utime(old, (t, t))
    os.utime(other, (t, t))
    n, b = housekeeping.prune_comfy(cfg, 20)
    assert (n, b) == (1, 10) and not old.exists() and new.exists() and other.exists()


def test_dedupe_turns_filed_copies_into_links_and_new_filings_are_links(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    meta = {"suite": "s1", "category": "c", "prompt_id": "p", "checkpoint": "ck.safetensors", "lora": None, "seed": 1}
    jid = "20261111-000000-x"
    src = tmp_path / "out" / jid / "render.png"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"PNG" * 100)
    (tmp_path / "jobs" / "done" / f"{jid}.json").write_text(json.dumps({"id": jid, "batch": "bakeoff/s1", "meta": meta}))
    import shutil
    for dest in bakeoff.organized_paths("s1", meta):       # the old way: two real copies
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    r = housekeeping.dedupe(cfg)
    assert r["linked"] == 2 and r["freed"] == 600
    for dest in bakeoff.organized_paths("s1", meta):
        assert os.path.samefile(src, dest) and dest.read_bytes() == src.read_bytes()
    assert housekeeping.dedupe(cfg)["already"] == 2          # idempotent
    # filing a new render links rather than copies
    meta2 = dict(meta, seed=2)
    out = bakeoff.file_render("s1", meta2, src)
    assert all(os.path.samefile(src, p) for p in out)
