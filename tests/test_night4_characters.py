"""Night 4 F1 handler + F2 registry, inheritance, character_set (fake ComfyUI)."""
import io
import json
import shutil
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from forge import config as cfgmod, schema
from forge.jobs.common import Context
import n4_fixtures as fx


def _ctx(root, comfy=None):
    cfg = cfgmod.load()
    return Context(cfg=cfg, comfy=comfy, palettes_dir=cfgmod.ROOT / "palettes", root=root)


def _game(tmp_path, asym=True):
    g = tmp_path / "games" / "tg"
    (g / "characters").mkdir(parents=True)
    (g / "prompts").mkdir()
    (g / "characters" / "ana.json").write_text(json.dumps({
        "id": "ana", "asymmetric": asym, "default_variant": "a",
        "variants": {"a": {"prompt": "{{char.ana}}", "negative": "blurry", "checkpoint": "ArtUniverseSDXL_v8.safetensors",
                           "sampler": "dpmpp_2m", "scheduler": "karras", "steps": 28, "seed": 7, "size": [64, 96],
                           "sheet_loras": ["SpriteSheet.safetensors"], "wanted": {"portrait_moods": ["calm", "glad"]}},
                     "b": {"prompt": "ana in red", "seed": 9}}}), encoding="utf-8")
    (g / "prompts" / "lib.json").write_text(json.dumps({"blocks": {
        "char.ana": "a woman with short hair", "mood.calm": "calm face", "mood.glad": "glad face",
        "pose.portrait": "head and shoulders", "pose.battle": "fighting stance", "pose.turnaround": "three views",
        "mood.todo": "TODO later"}}), encoding="utf-8")
    cfg = {**cfgmod.load(), "allow_external_paths": True, "paths": {**cfgmod.load()["paths"], "games": str(tmp_path / "games")}}
    return cfg


def test_intake_handler_first_run_then_edited_mapping(tmp_path):
    from forge.night4 import intake_job
    sheet = tmp_path / "sheet.png"
    fx.painted_checker().save(sheet)
    ctx = _ctx(tmp_path)
    out = tmp_path / "o1"; out.mkdir()
    job = schema.with_defaults({"id": "i1", "type": "sprite_intake", "input": str(sheet), "character": "ana", "game": "tg",
                                "tool": "Some Tool 1.0"})
    res = intake_job.run(job, ctx, out)
    assert res["first_run"] and res["found"] == 5 and res["missing"] == ["NE", "E", "SE"]
    for f in ("sheet.png", "numbers.png", "turntable.gif", "edges.md", "report.json", "prov.json"):
        assert (out / f).exists(), f
    assert Image.open(out / "sheet.png").size == (1152, 216)
    mp = Path(res["mapping"])
    assert mp.parent.name == "ana" and mp.name == "sheet.intake.json"
    prov = json.loads((out / "prov.json").read_text(encoding="utf-8"))
    assert prov["licences"][0]["role"] == "outside_tool" and prov["licences"][0]["commercial_ok"] is None
    # a person fixes the mapping: mirror and skip one
    m = json.loads(mp.read_text(encoding="utf-8"))
    m["mirror"] = ["W→E"]; m["figures"][0]["skip"] = True
    mp.write_text(json.dumps(m), encoding="utf-8")
    out2 = tmp_path / "o2"; out2.mkdir()
    res2 = intake_job.run({**job, "id": "i2"}, ctx, out2)
    assert not res2["first_run"] and "S" in res2["missing"] and "E" not in res2["missing"]
    assert any("no registry entry" in w for w in res2["warnings"])   # no registry in this temp root


def test_intake_warns_on_mirroring_an_asymmetric_character(tmp_path):
    from forge.night4 import intake_job
    cfg = _game(tmp_path)
    sheet = tmp_path / "s.png"; fx.clean_grid().save(sheet)
    ctx = Context(cfg=cfg, root=tmp_path)
    out = tmp_path / "o"; out.mkdir()
    job = schema.with_defaults({"id": "i", "type": "sprite_intake", "input": str(sheet), "character": "ana", "game": "tg"})
    res = intake_job.run(job, ctx, out)
    assert not any("asymmetric" in w for w in res["warnings"])
    assert any("not named" in w for w in res["warnings"])            # no tool → approve will ask
    mp = Path(res["mapping"]); m = json.loads(mp.read_text()); m["mirror"] = ["W→E"]; m["figures"][6]["facing"] = None
    mp.write_text(json.dumps(m))
    out2 = tmp_path / "o2"; out2.mkdir()
    res2 = intake_job.run({**job, "id": "i2"}, ctx, out2)
    assert any("asymmetric" in w for w in res2["warnings"])


def test_registry_inheritance_job_keys_win(tmp_path):
    from forge.night4 import characters as chm
    cfg = _game(tmp_path)
    j = chm.resolve(cfg, {"type": "render", "character": "ana", "game": "tg", "steps": 40})
    assert j["prompt"] == "{{char.ana}}" and j["seed"] == 7 and j["steps"] == 40 and j["variant"] == "a"
    assert j["checkpoint"] == "ArtUniverseSDXL_v8.safetensors" and j["character_registry"]
    j2 = chm.resolve(cfg, {"type": "render", "character": "ana", "variant": "b", "game": "tg",
                           "prompt": "{{character}}, waving"})
    assert j2["prompt"] == "ana in red, waving" and j2["seed"] == 9
    with pytest.raises(chm.CharacterError):
        chm.resolve(cfg, {"type": "render", "character": "ana", "variant": "zzz", "game": "tg"})
    with pytest.raises(chm.CharacterError):
        chm.resolve(cfg, {"type": "render", "character": "nobody", "game": "tg"})
    probs = chm.check(cfg, "tg")
    assert not any("ana/a" in p and "not in the prompt library" in p for p in probs)


def test_charset_expand_refuses_todo_and_expands_plain_text(tmp_path):
    from forge.night4 import charset
    cfg = _game(tmp_path)
    j = charset.expand_set(cfg, {"type": "character_set", "character": "ana", "game": "tg"})
    parts = [r["part"] for r in j["renders"]]
    assert parts == ["mood:calm", "mood:glad", "battle", "turnaround"]
    assert all("{{" not in r["prompt"] for r in j["renders"])
    assert all(r["seed"] == 7 for r in j["renders"])                  # one face
    assert j["renders"][-1]["loras"][-1]["name"] == "SpriteSheet.safetensors"
    assert "mood.calm" in j["prompt_blocks"] and "prompt" not in j
    with pytest.raises(charset.CharsetError, match="placeholder"):
        charset.expand_set(cfg, {"type": "character_set", "character": "ana", "game": "tg", "moods": ["todo"]})
    assert schema.validate(j) == []


class SheetComfy:
    """Answers a render with magenta, except a wide one (the turnaround) which gets a 3-figure sheet."""
    url, timeout, poll = "http://fake", 10, 0.1

    def __init__(self):
        from test_paint import FAKE_INFO
        self.graphs, self.info = [], FAKE_INFO

    def is_up(self): return True
    def object_info(self): return self.info
    def upload_image(self, path, subfolder="forge", name=None): return f"forge/{Path(path).name}"

    def run_by_node(self, g):
        return {"9": self.run(g)}

    def run(self, g):
        self.graphs.append(g)
        wide = any(n["class_type"] == "EmptyLatentImage" and n["inputs"]["width"] > n["inputs"]["height"] for n in g.values())
        im = fx.white_backdrop() if wide else Image.new("RGB", (64, 96), (255, 0, 255))
        b = io.BytesIO(); im.save(b, "PNG"); return [b.getvalue()]


def test_character_set_end_to_end_fake_comfy(tmp_path, monkeypatch):
    from forge.night4 import charset
    cfg = _game(tmp_path)
    fake = SheetComfy()
    ctx = Context(cfg=cfg, comfy=fake, palettes_dir=cfgmod.ROOT / "palettes", root=tmp_path)
    job = charset.expand_set(cfg, {"id": "cs1", "type": "character_set", "character": "ana", "game": "tg"})
    out = tmp_path / "out" / "cs1"; out.mkdir(parents=True)
    res = charset.run(schema.with_defaults(job), ctx, out)
    assert (out / "moods" / "calm.png").exists() and (out / "battle.png").exists() and (out / "turnaround.png").exists()
    assert (out / "sheet.png").exists() and Image.open(out / "sheet.png").size == (1152, 216)
    assert (out / "contact.png").exists()
    seeds = set()
    for g in fake.graphs:
        for n in g.values():
            if n["class_type"] == "KSampler":
                seeds.add(n["inputs"]["seed"])
    assert seeds == {7}
    prov = json.loads((out / "prov.json").read_text(encoding="utf-8"))
    assert {l["file"] for l in prov["licences"]} >= {"ArtUniverseSDXL_v8.safetensors", "SpriteSheet.safetensors"}


def test_submit_shim_resolves_characters(tmp_path, monkeypatch):
    """Wiring day W5: `submit` itself resolves characters (the Night 4 shim is retired) — the queue sees the resolved
    and expanded jobs."""
    from forge import cli, cli_night4
    from forge.queue import Queue
    cfg = {**_game(tmp_path), "incoming_dir": str(tmp_path / "_incoming")}
    seen = {}
    monkeypatch.setattr(Queue, "submit_batch", lambda self, data: seen.setdefault("data", data) and ["J1", "J2"])
    b = tmp_path / "b.json"
    b.write_text(json.dumps({"batch": "x", "defaults": {"game": "tg"},
                             "jobs": [{"type": "render", "character": "ana", "prompt": "{{character}}, waving"},
                                      {"type": "render", "prompt": "plain"}]}), encoding="utf-8")
    assert cli.cmd_submit(cfg, [str(b)]) == 0
    jobs = seen["data"]["jobs"]
    assert jobs[0]["prompt"] == "a woman with short hair, waving" and jobs[0]["seed"] == 7      # registry + library
    assert jobs[0]["variant"] == "a" and jobs[0]["character_registry"]
    assert jobs[1]["prompt"] == "plain" and "character" not in jobs[1]
    assert "submit" not in cli_night4.COMMANDS                                                  # the shim is retired
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"type": "render", "game": "tg", "character": "nobody", "prompt": "x"}), encoding="utf-8")
    assert cli.cmd_submit(cfg, [str(bad)]) == 2                                                 # refused like a PromptError


def test_stubs_from_wanted_never_overwrite(tmp_path):
    from forge.night4 import characters as chm
    cfg = _game(tmp_path)
    g = tmp_path / "games" / "tg"
    (g / "forge.game.json").write_text(json.dumps({"game_root": str(tmp_path / "nogame")}))
    (g / "wanted.json").write_text(json.dumps({"items": {
        "placeholder/hero_ana": {"kind": "sprite_sheet"}, "placeholder/hero_bob": {"kind": "sprite_sheet"},
        "placeholder/portrait_bob": {"kind": "portrait"}}}))
    made = chm.stubs(cfg, "tg")
    assert made == ["bob"]
    bob = json.loads((g / "characters" / "bob.json").read_text())
    assert bob["variants"]["default"]["wanted"] == {"field_sheet": "placeholder/hero_bob", "portrait": "placeholder/portrait_bob"}


def test_ask_mapping_fixes_by_answers(tmp_path):
    from forge import cli_night4
    from forge.night4 import intake as it
    img = fx.painted_checker(); det = it.detect(img)
    sheet = tmp_path / "s.png"; img.save(sheet)
    mp = tmp_path / "s.intake.json"
    mp.write_text(json.dumps(it.new_mapping(sheet, det, "ana", None)))
    answers = iter(["n", "", "w 1", "-", "nope", "N", "", "y"])
    said = []
    changed = cli_night4.ask_mapping(mp, "ana", True, ask=lambda q: (said.append(q), next(answers))[1], out=said.append)
    m = json.loads(mp.read_text())
    f = {e["n"]: e for e in m["figures"]}
    assert changed and m["checked_by_person"]
    assert f[2]["facing"] == "W" and f[2]["frame"] == 1 and f[3]["skip"] and f[4]["facing"] == "N"
    assert any("CAREFUL" in q for q in said) and m["mirror"]
