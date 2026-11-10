"""G6: the prompt library — expansion at submit, typo refusal, never-list, loops, where-used, re-render only changed."""
import json

import pytest

from forge import prompts as pl, cli
from test_night_report import world


def lib_world(tmp_path):
    cfg, jobs, out = world(tmp_path)
    games = tmp_path / "games"
    pdir = games / "tg" / "prompts"
    pdir.mkdir(parents=True)
    (games / "tg" / "batches").mkdir()
    (pdir / "a.json").write_text(json.dumps({"blocks": {"style.house": "painted, warm", "light.dusk": "dusk light",
                                                         "place.mills": "a mill town, {{era.war}}", "era.war": "wartime"}}))
    (pdir / "never.json").write_text(json.dumps({"words": ["amano", "yoshitaka"], "lora_triggers_forbidden": ["trigz"]}))
    cfg["paths"]["games"] = str(games)
    return cfg, jobs, games


def test_expand_three_references_to_plain_text_and_record(tmp_path):
    cfg, jobs, games = lib_world(tmp_path)
    j = pl.prepare(cfg, [{"name": "a", "game": "tg", "prompt": "{{style.house}}, a gas station, {{light.dusk}}, {{place.mills}}"}])[0]
    assert j["prompt"] == "painted, warm, a gas station, dusk light, a mill town, wartime"
    assert "{{" not in j["prompt"] and j["prompt_blocks"] == ["style.house", "light.dusk", "place.mills", "era.war"]
    assert len(j["prompt_library"]) == 10 and j["prompt_template"]["prompt"].startswith("{{style.house}}")
    plain = {"name": "b", "game": "tg", "prompt": "no refs"}
    assert pl.prepare(cfg, [plain])[0] == plain


def test_refusals_typo_never_list_loop_placeholder(tmp_path):
    cfg, jobs, games = lib_world(tmp_path)
    with pytest.raises(pl.PromptError, match=r"unknown prompt block \{\{style\.hous\}\}"):
        pl.prepare(cfg, [{"name": "a", "game": "tg", "prompt": "{{style.hous}}"}])
    with pytest.raises(pl.PromptError, match="'amano'.*never-list"):
        pl.prepare(cfg, [{"name": "a", "game": "tg", "prompt": "in the manner of Amano"}])
    with pytest.raises(pl.PromptError, match="trigz"):
        pl.prepare(cfg, [{"name": "a", "game": "tg", "prompt": "x", "negative": "trigz, blur"}])
    assert pl.prepare(cfg, [{"name": "a", "game": "tg", "prompt": "samanosuke"}])         # whole words only
    with pytest.raises(pl.PromptError, match="loop"):
        pl.expand_text("{{a.x}}", {"a.x": "{{a.y}}", "a.y": "{{a.x}}"})
    with pytest.raises(pl.PromptError, match="placeholder"):
        pl.expand_text("{{a.x}}", {"a.x": "TODO write me"})


def test_submit_expands_refuses_and_skips_unchanged(tmp_path, monkeypatch):
    cfg, jobs, games = lib_world(tmp_path)
    monkeypatch.setattr(cli.cfgmod, "load", lambda *a, **k: cfg)
    b = tmp_path / "batch.json"
    b.write_text(json.dumps({"batch": "maps", "game": "tg", "defaults": {"type": "palette_snap", "game": "tg", "inputs": ["x.png"]},
                             "jobs": [{"name": "one", "prompt": "{{style.house}} one"}, {"name": "two", "prompt": "{{light.dusk}} two"}]}))
    assert cli.main(["submit", str(b)]) == 0
    queued = [json.loads(p.read_text()) for p in (jobs / "pending").glob("*.json")]
    assert sorted(q["prompt"] for q in queued) == ["dusk light two", "painted, warm one"]
    # change one block → only the job it reaches is new
    (games / "tg" / "prompts" / "a.json").write_text(json.dumps({"blocks": {"style.house": "painted, cool", "light.dusk": "dusk light",
                                                                              "place.mills": "m", "era.war": "w"}}))
    assert cli.main(["submit", str(b), "--skip-done"]) == 0
    assert len(list((jobs / "pending").glob("*.json"))) == 3
    hits = pl.where_used(cfg, "style.house")
    assert len([h for h in hits if h["where"] == "pending"]) == 2
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"type": "palette_snap", "game": "tg", "inputs": ["x"], "name": "z", "prompt": "{{nope.x}}"}))
    assert cli.main(["submit", str(bad)]) == 2
    assert len(list((jobs / "pending").glob("*.json"))) == 3
