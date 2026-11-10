"""Night 4 F8 — the model shelf report: verdicts, what still needs a file, nothing deleted."""
import json
from pathlib import Path

from forge import config as cfgmod
from forge.night4 import models_shelf as ms


def test_shelf_report(tmp_path, monkeypatch):
    sd, lo = tmp_path / "sd", tmp_path / "lo"
    sd.mkdir(); lo.mkdir()
    for f in ("ArtUniverseSDXL_v8.safetensors", "sd_xl_base_1.0.safetensors"):
        (sd / f).write_bytes(b"x" * 100)
    for f in ("SpriteSheet (1).safetensors", "Pixel_Xl_V1.safetensors", "mystery.safetensors"):
        (lo / f).write_bytes(b"x" * 100)
    for s in ("done", "pending", "paused", "running"):
        (tmp_path / "jobs" / s).mkdir(parents=True)
    (tmp_path / "jobs" / "pending" / "p.json").write_text(json.dumps({"id": "p", "loras": [{"name": "Pixel_Xl_V1.safetensors"}]}))
    (tmp_path / "jobs" / "done" / "d.json").write_text(json.dumps({"id": "d", "finished_at": "2026-11-10T01:00:00",
                                                                   "result": {"checkpoint": "ArtUniverseSDXL_v8.safetensors"}}))
    cfg = {**cfgmod.load(), "allow_external_paths": True,
           "model_dirs": {"checkpoints": [str(sd)], "loras": [str(lo)]},
           "paths": {**cfgmod.load()["paths"], "jobs": str(tmp_path / "jobs"), "out": str(tmp_path / "out"),
                     "games": str(tmp_path / "games")}}
    inv = [{"file": f, "kind": "checkpoint", "base": "sdxl"} for f in ("ArtUniverseSDXL_v8.safetensors", "sd_xl_base_1.0.safetensors")]
    inv += [{"file": f, "kind": "lora", "base": "sdxl"} for f in ("SpriteSheet (1).safetensors", "Pixel_Xl_V1.safetensors")]
    inv += [{"file": "mystery.safetensors", "kind": "lora", "base": "unknown"}]
    from forge import bakeoff
    monkeypatch.setattr(bakeoff, "inventory", lambda cfg, refresh=False: inv)
    p, r = ms.build(cfg, "tg", scan=False)
    rows = {x["file"]: x for x in json.loads(p.with_suffix(".json").read_text())}
    assert rows["SpriteSheet (1).safetensors"]["safe_to_delete"]                       # dropped for all uses, unused
    assert not rows["Pixel_Xl_V1.safetensors"]["safe_to_delete"]                       # dropped, but a queued job needs it
    assert not rows["ArtUniverseSDXL_v8.safetensors"]["safe_to_delete"] and rows["ArtUniverseSDXL_v8.safetensors"]["runs"] == 1
    assert rows["mystery.safetensors"]["safe_to_delete"] and not rows["mystery.safetensors"]["loads"]
    txt = p.read_text()
    assert "Nothing can run them here today" in txt and "nothing was deleted" in txt.lower()
    assert (sd / "sd_xl_base_1.0.safetensors").exists() and (lo / "SpriteSheet (1).safetensors").exists()
