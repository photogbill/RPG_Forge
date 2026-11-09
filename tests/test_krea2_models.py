"""N8 (Krea 2 graph, licence conditions, doctor) and N9 (scanner fixes, unusable report, licence questions)."""
import json

import pytest

from forge import config as cfgmod, doctor, manifest, model_report
from forge.engines import graph_ops as go, krea2_graph
from forge.ops import safetensors_meta as sm


def refs_ok(g):
    for k, n in g.items():
        for name, v in n["inputs"].items():
            if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str):
                assert v[0] in g, f"{k}.{name} → missing node {v[0]}"


def test_krea2_graph_shape_and_defaults():
    g = krea2_graph.build("krea2_turbo_fp8_scaled.safetensors", "a juke joint", "", 7, 1344, 768,
                          loras=[{"name": "cinematicFantasy_v1.safetensors", "strength": 0.7}])
    refs_ok(g)
    assert g["2"]["inputs"]["type"] == "krea2" and g["3"]["inputs"]["vae_name"] == "qwen_image_vae.safetensors"
    ks = g["6"]["inputs"]
    assert (ks["steps"], ks["cfg"], ks["sampler_name"], ks["scheduler"]) == (8, 1.0, "er_sde", "simple")
    assert g["7"]["class_type"] == "EmptySD3LatentImage" and g[ks["model"][0]]["class_type"] == "LoraLoaderModelOnly"
    raw = krea2_graph.build("krea2_raw.safetensors", "p", "", 1, 1024, 1024)
    assert (raw["6"]["inputs"]["steps"], raw["6"]["inputs"]["cfg"]) == (50, 3.5)
    with pytest.raises(ValueError):
        krea2_graph.build("k.safetensors", "p", "", 1, 64, 64, sampler="nope")


def test_krea2_takes_the_paint_stages():
    """scene_paint's upscale / refine / img2img surgery works on the Krea 2 graph (KSampler + EmptySD3LatentImage)."""
    g = krea2_graph.build("k.safetensors", "p", "", 1, 1344, 768)
    go.add_upscale(g, "RealESRGAN_x4plus.pth", 1920, 1080)
    go.add_refine(g, 0.3)
    refs_ok(g)
    assert len([n for n in g.values() if n["class_type"] == "KSampler"]) == 2
    g2 = krea2_graph.build("k.safetensors", "p", "", 1, 1344, 768)
    go.to_img2img(g2, "forge/greybox.png", 0.55, 1344, 768)
    refs_ok(g2)
    assert not go.nodes_of(g2, *go.EMPTY_LATENTS)


def test_from_job_overrides_sdxl_sampler_leak():
    g, name, extra, steps, cfg, sampler, sched = krea2_graph.from_job({"krea2": {"text_encoder": "te.safetensors"}},
        {"sampler": "dpmpp_2m", "scheduler": "karras", "steps": 30, "cfg": 3.5}, "x.safetensors", "p", "", 1, 1024, 1024, [])
    assert (name, steps, cfg, sampler, sched) == ("krea2_graph", 30, 3.5, "er_sde", "simple")
    assert extra["text_encoder"] == "te.safetensors" and g["2"]["inputs"]["clip_name"] == "te.safetensors"


def test_scanner_tells_krea2_flux2_flux3_apart():
    k = sm.classify({"txtfusion.projector.weight": {}, "blocks.0.attn.wk.weight": {}}, {}, 10)
    assert (k["kind"], k["base"]) == ("unet", "krea2")
    lo = sm.classify({"diffusion_model.blocks.0.attn.wk.lora_A.weight": {}}, {"ss_base_model_version": "krea2"}, 10)
    assert (lo["kind"], lo["base"]) == ("lora", "krea2")
    f2 = sm.classify({"double_blocks.0.img_attn.qkv.weight": {}, "double_stream_modulation_img.lin.weight": {}}, {}, 10)
    assert f2["base"] == "flux2"
    f1 = sm.classify({"double_blocks.0.img_attn.qkv.weight": {}, "double_blocks.0.img_mod.lin.weight": {}}, {}, 10)
    assert f1["base"] == "flux1"


def test_licence_conditions_are_printed_for_krea2():
    cfg = cfgmod.load()
    chain = [{"role": "checkpoint", "file": "krea2_turbo_fp8_scaled.safetensors", "commercial_ok": True}]
    conds = manifest.licence_conditions(cfg, chain)
    assert conds and "US$1M" in conds[0]
    assert manifest.licence_conditions(cfg, [{"file": "sd_xl_base_1.0.safetensors"}]) == []


def test_doctor_krea2_names_what_is_missing():
    cfg = dict(cfgmod.load())
    cfg["comfy"] = dict(cfg["comfy"], krea2={"text_encoder": "nope_te.safetensors", "vae": "nope_vae.safetensors"})
    line = doctor.krea2_report(cfg, {"UNETLoader": {}, "CLIPLoader": {"input": {"required": {"type": [["sdxl", "flux2"]]}}}})[0]
    assert "nope_te.safetensors" in line and "nope_vae.safetensors" in line and "no 'krea2' type" in line
    assert "krea2" in doctor.graph_shapes() and "CLIPLoader" in doctor.graph_shapes()["krea2"]


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
