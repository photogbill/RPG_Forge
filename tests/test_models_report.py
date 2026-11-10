"""N9 (scanner fixes, unusable report, licence questions) and licence conditions. (Krea 2 was cut 2026-11-09.)"""
import json

import pytest

from forge import config as cfgmod, doctor, manifest, model_report
from forge.ops import safetensors_meta as sm










def test_scanner_tells_krea2_flux2_flux3_apart():
    k = sm.classify({"txtfusion.projector.weight": {}, "blocks.0.attn.wk.weight": {}}, {}, 10)
    assert (k["kind"], k["base"]) == ("unet", "krea2")
    lo = sm.classify({"diffusion_model.blocks.0.attn.wk.lora_A.weight": {}}, {"ss_base_model_version": "krea2"}, 10)
    assert (lo["kind"], lo["base"]) == ("lora", "krea2")
    f2 = sm.classify({"double_blocks.0.img_attn.qkv.weight": {}, "double_stream_modulation_img.lin.weight": {}}, {}, 10)
    assert f2["base"] == "flux2"
    f1 = sm.classify({"double_blocks.0.img_attn.qkv.weight": {}, "double_blocks.0.img_mod.lin.weight": {}}, {}, 10)
    assert f1["base"] == "flux1"




def test_model_report_groups():
    from forge.jobs.common import Context
    ctx = Context(cfg=cfgmod.load(), root=cfgmod.ROOT)
    assert model_report.classify({"file": "x.safetensors", "kind": "checkpoint", "base": "sd15"}, ctx)[0] == "no graph"
    assert model_report.classify({"file": "moss_x.safetensors", "kind": "unet", "base": "unknown"}, ctx)[0] == "no graph"
    assert model_report.classify({"file": "sd_xl_base_1.0.safetensors", "kind": "checkpoint", "base": "sdxl"}, ctx)[0] == "ok"
    assert model_report.classify({"file": "SomeDevMix-flux-dev.safetensors", "kind": "unet", "base": "flux1"}, ctx)[0] == "non-commercial"
    assert model_report.classify({"file": "flux-2-klein-base-9b.safetensors", "kind": "unet", "base": "flux2"}, ctx)[0] == "non-commercial"
    assert model_report.classify({"file": "Mystery.safetensors", "kind": "lora", "base": "sdxl"}, ctx)[0] == "licence unknown"
    assert model_report.classify({"file": "qwen_image_vae.safetensors", "kind": "vae", "base": "unknown"}, ctx)[0] == "helper"


def test_licence_questions_one_at_a_time(tmp_path, monkeypatch):
    from forge import cli
    recorded = {}
    monkeypatch.setattr(manifest, "record_licence", lambda cfg, f, n, ok, note="": recorded.update(f=f, n=n, ok=ok, note=note) or tmp_path / "l.json")
    monkeypatch.setattr(model_report, "report", lambda cfg: ("", {"licence unknown": [("A.safetensors", 1, "", ""), ("B.safetensors", 1, "", "")]}))
    answers = iter(["2", "CreativeML Open RAIL++-M", "y", "civitai page"])
    assert cli._licence_ask(cfgmod.load(), ask=lambda _: next(answers)) == 0
    assert recorded == {"f": "B.safetensors", "n": "CreativeML Open RAIL++-M", "ok": True, "note": "civitai page"}
    answers = iter(["A.safetensors", "<licence name>"])
    assert cli._licence_ask(cfgmod.load(), ask=lambda _: next(answers)) == 2       # the placeholder is refused



def test_licence_conditions_from_the_registry(tmp_path, monkeypatch):
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "models.json").write_text(json.dumps({"models": {"capped": {"files": ["dir/capped.safetensors"],
        "commercial_ok": True, "licence_condition": "revenue under US$1M/year"}}}), encoding="utf-8")
    monkeypatch.setattr(cfgmod, "ROOT", tmp_path)
    cfg = {}
    assert manifest.licence_conditions(cfg, [{"file": "capped.safetensors"}]) == ["capped.safetensors (capped): revenue under US$1M/year"]
    assert manifest.licence_conditions(cfg, [{"file": "other.safetensors"}]) == []


def test_krea2_files_are_reported_as_cut():
    from forge.jobs.common import Context
    ctx = Context(cfg=cfgmod.load(), root=cfgmod.ROOT)
    g, why = model_report.classify({"file": "cinematicFantasy_v1.safetensors", "kind": "lora", "base": "krea2"}, ctx)
    assert g == "no graph" and "cut" in why
