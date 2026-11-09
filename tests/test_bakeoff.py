"""Model inspection, the SDXL graph builder and the bake-off planner/report."""
import json, struct, sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from forge.ops import safetensors_meta as sm  # noqa: E402
from forge.engines import sdxl_graph  # noqa: E402
from forge import bakeoff, config as cfgmod  # noqa: E402
from forge.queue import Queue  # noqa: E402


def _fake_safetensors(path: Path, keys: list[str], meta: dict | None = None, size_pad: int = 0):
    header = {k: {"dtype": "F16", "shape": [1], "data_offsets": [i * 2, i * 2 + 2]} for i, k in enumerate(keys)}
    if meta:
        header["__metadata__"] = {k: (json.dumps(v) if isinstance(v, (dict, list)) else str(v)) for k, v in meta.items()}
    blob = json.dumps(header).encode("utf-8")
    with open(path, "wb") as f:
        f.write(struct.pack("<Q", len(blob)))
        f.write(blob)
        f.write(b"\0" * (len(keys) * 2 + size_pad))


def test_inspect_classifies_sdxl_lora_sd15_lora_flux_lora_and_checkpoint(tmp_path):
    sdxl_lora = tmp_path / "a.safetensors"
    _fake_safetensors(sdxl_lora, ["lora_te1_text_model_encoder_layers_0_mlp_fc1.alpha", "lora_te2_x.lora_down.weight",
                                  "lora_unet_input_blocks_4_1_transformer_blocks_3_attn1_to_k.lora_up.weight"],
                      {"ss_base_model_version": "sdxl_base_v1-0", "ss_tag_frequency": {"img": {"tilemapstyle": 40, "no humans": 40, "tree": 12}}})
    sd15_lora = tmp_path / "b.safetensors"
    _fake_safetensors(sd15_lora, ["lora_te_text_model_encoder_layers_0_mlp_fc1.alpha",
                                  "lora_unet_input_blocks_1_1_transformer_blocks_0_attn1_to_k.lora_up.weight"])
    flux_lora = tmp_path / "c.safetensors"
    _fake_safetensors(flux_lora, ["transformer.single_transformer_blocks.0.attn.to_k.lora_A.weight",
                                  "transformer.single_transformer_blocks.0.attn.to_k.lora_B.weight"])
    ckpt = tmp_path / "d.safetensors"
    _fake_safetensors(ckpt, ["model.diffusion_model.input_blocks.0.0.weight", "first_stage_model.decoder.conv_in.weight",
                             "conditioner.embedders.1.model.ln_final.weight"])
    a, b, c, d = (sm.inspect(p) for p in (sdxl_lora, sd15_lora, flux_lora, ckpt))
    assert (a["kind"], a["base"]) == ("lora", "sdxl") and a["triggers"][0] == "tilemapstyle"
    assert (b["kind"], b["base"]) == ("lora", "sd15")
    assert (c["kind"], c["base"]) == ("lora", "flux1")
    assert (d["kind"], d["base"]) == ("checkpoint", "sdxl")
    md = sm.render_markdown([a, b, c, d])
    assert "tilemapstyle" in md and "| checkpoint |" in md


def test_sdxl_graph_lora_chain_wiring():
    g = sdxl_graph.build("ck.safetensors", "a cat", "dog", 7, 1024, 768, steps=20, cfg=5.0,
                         loras=[{"name": "l1.safetensors", "strength": 0.7}, {"name": "l2.safetensors", "strength": 0.5, "clip": 0.3}])
    assert g["1"]["class_type"] == "CheckpointLoaderSimple"
    assert g["10"]["inputs"]["model"] == ["1", 0] and g["11"]["inputs"]["model"] == ["10", 0]
    assert g["11"]["inputs"]["strength_clip"] == 0.3
    assert g["2"]["inputs"]["clip"] == ["11", 1] and g["6"]["inputs"]["model"] == ["11", 0]
    assert g["4"]["inputs"] == {"width": 1024, "height": 768, "batch_size": 1}
    plain = sdxl_graph.build("ck.safetensors", "a", "b", 1, 512, 512)
    assert plain["2"]["inputs"]["clip"] == ["1", 1] and "10" not in plain
    with pytest.raises(ValueError):
        sdxl_graph.build("ck", "a", "b", 1, 512, 512, sampler="nope")


def _inventory():
    return [
        {"file": "CK_A.safetensors", "kind": "checkpoint", "base": "sdxl", "triggers": []},
        {"file": "CK_B.safetensors", "kind": "checkpoint", "base": "sdxl", "triggers": []},
        {"file": "pix.safetensors", "kind": "lora", "base": "sdxl", "triggers": ["pixel art", "1girl"]},
        {"file": "tiles.safetensors", "kind": "lora", "base": "sdxl", "triggers": ["tilemapstyle", "no humans"]},
        {"file": "fluxmap.safetensors", "kind": "lora", "base": "flux1", "triggers": []},
        {"file": "old15.safetensors", "kind": "lora", "base": "sd15", "triggers": []},
    ]


def _suite():
    return {"suite": "t", "checkpoints": "*", "loras": "*", "seeds": [5], "lora_triggers": {"pix.safetensors": "pixel art"},
            "categories": {"tile": {"size": [512, 512], "prompts": {"asphalt": "asphalt", "grass": "grass"}},
                           "portrait": {"prompts": {"sarah": "a woman"}}}}


def test_bakeoff_plan_counts_triggers_and_skips():
    p = bakeoff.plan(_suite(), _inventory(), cfgmod.load())
    # 2 ckpts × (none + 2 compatible LoRAs) × 3 prompts × 1 seed
    assert len(p["jobs"]) == 2 * 3 * 3
    assert {s["lora"] for s in p["skipped"]} == {"fluxmap.safetensors", "old15.safetensors"}
    assert p["triggers"]["tiles.safetensors"] == "tilemapstyle" and p["triggers"]["pix.safetensors"] == "pixel art"
    tile_pix = [j for j in p["jobs"] if j["meta"]["lora"] == "pix.safetensors" and j["meta"]["prompt_id"] == "asphalt"][0]
    assert tile_pix["prompt"].startswith("pixel art, ") and tile_pix["size"] == [512, 512] and tile_pix["type"] == "render"
    assert tile_pix["loras"] == [{"name": "pix.safetensors", "strength": 0.8, "clip": 0.8}]
    # grouped by checkpoint so ComfyUI reloads less
    cks = [j["checkpoint"] for j in p["jobs"]]
    assert cks == sorted(cks)
    with pytest.raises(FileNotFoundError):
        bakeoff.plan({**_suite(), "loras": ["missing.safetensors"]}, _inventory(), cfgmod.load())


def test_bakeoff_report_builds_grid_and_html(tmp_path, monkeypatch):
    monkeypatch.setattr(cfgmod, "ROOT", tmp_path)
    q = Queue(tmp_path / "jobs", tmp_path / "out")
    p = bakeoff.plan(_suite(), _inventory(), cfgmod.load())
    ids = bakeoff.submit(p, q)
    # pretend the worker ran: first job done with an image, second failed, rest pending
    jid, job = q.claim()
    Image.new("RGB", (64, 64), (200, 40, 40)).save(q.out_dir(jid) / "render.png")
    q.finish(jid, result={"outputs": ["render.png"], "seconds": 3.2})
    jid2, _ = q.claim()
    q.finish(jid2, error="RuntimeError: CUDA out of memory")
    bakeoff.rate("t", jid, 5, "lovely")
    index = bakeoff.report("t", q)
    assert index.exists()
    html = index.read_text(encoding="utf-8")
    assert "CUDA out of memory" in html and "★5" in html
    grids = list((tmp_path / "out" / "bakeoff" / "t").glob("grid_*.png"))
    assert len(grids) == 3  # three prompts × one seed
    g = Image.open(grids[0])
    assert g.width > 170 + 3 * 256  # label column + (none + 2 LoRAs)
    summary = json.loads((tmp_path / "out" / "bakeoff" / "t" / "summary.json").read_text())
    assert summary["rendered"] == 1 and summary["failed"] == 1 and summary["total"] == len(ids)
    # the finished render is filed by model and by picture
    by_model = list((tmp_path / "out" / "bakeoff" / "t" / "by_model").rglob("*.png"))
    by_cat = list((tmp_path / "out" / "bakeoff" / "t" / "by_category").rglob("*.png"))
    assert len(by_model) == 1 and len(by_cat) == 1
    assert by_model[0].parent.parent.name == "CK_A" and by_model[0].parent.name == "_no_lora"
    assert by_cat[0].parent.parent.name in ("tile", "portrait") and by_cat[0].name.startswith("CK_A__")


def test_render_defaults_keep_batch_tag_and_count():
    from forge import schema
    job = schema.with_defaults({"type": "render", "prompt": "x", "batch": "bakeoff/suite_a"})
    assert job["batch"] == "bakeoff/suite_a" and job["count"] == 1


def test_retry_failed_moves_back_to_pending(tmp_path):
    q = Queue(tmp_path / "jobs", tmp_path / "out")
    a = q.submit({"type": "render", "name": "a", "prompt": "x", "batch": "bakeoff/s1"})
    b = q.submit({"type": "render", "name": "b", "prompt": "x", "batch": "other"})
    for _ in range(2):
        jid, _j = q.claim()
        q.finish(jid, error="ValueError: boom", tb="tb")
    assert q.status()["failed"] == 2
    assert q.retry_failed("bakeoff/") == 1
    st = q.status()
    assert st["pending"] == 1 and st["failed"] == 1
    jid, job = q.claim()
    assert jid == a and "error" not in job and job["retries"] == 1


def _tool_suite():
    pics = {"juke": "a juke joint at night", "ruin": "a ruin at dawn"}
    return {"suite": "fin", "game": None, "checkpoints": "*", "loras": [], "include_no_lora": True, "seeds": [7],
            "size": [1344, 768], "steps": 28, "job_type": "scene_paint", "detail_crop": 32, "seconds_per_render": 10,
            "job": {"target": [1920, 1080], "priority": 5},
            "categories": {"t0_plain": {"job": {"refine": False}, "prompts": pics},
                           "t1_refine": {"job": {"refine": {"denoise": 0.3}}, "seconds_per_render": 70, "prompts": pics,
                                         "detail_at": {"juke": [0.9, 0.9]}},
                           "raw": {"type": "render", "prompts": {"juke": pics["juke"]}}}}


def test_bakeoff_plan_tool_categories_carry_job_type_and_fields():
    from forge import schema
    p = bakeoff.plan(_tool_suite(), _inventory(), cfgmod.load())
    assert len(p["jobs"]) == 2 * 5                       # 2 checkpoints × (2 + 2 + 1) pictures, no LoRAs
    assert all(not schema.validate(j) for j in p["jobs"])
    t0 = [j for j in p["jobs"] if j["meta"]["category"] == "t0_plain"][0]
    t1 = [j for j in p["jobs"] if j["meta"]["category"] == "t1_refine" and j["meta"]["prompt_id"] == "juke"][0]
    raw = [j for j in p["jobs"] if j["meta"]["category"] == "raw"][0]
    assert t0["type"] == "scene_paint" and t0["refine"] is False and t0["target"] == [1920, 1080] and t0["priority"] == 5
    assert t0["style_prefix"] == "" and t0["seed"] == 7 and t0["size"] == [1344, 768] and t0["loras"] == []
    assert t1["refine"] == {"denoise": 0.3} and t1["meta"]["detail"] == {"size": 32, "at": [0.9, 0.9]}
    assert t0["meta"]["detail"]["at"] == [0.5, 0.5] and t0["meta"]["job_type"] == "scene_paint"
    assert raw["type"] == "render" and "job_type" not in raw["meta"]
    # the estimate adds up per category: 2 ckpts × (2×10 + 2×70 + 1×10) s
    assert p["estimate_min"] == round(2 * (20 + 140 + 10) / 60.0, 1)


def test_bakeoff_report_tool_jobs_across_and_detail_grids(tmp_path, monkeypatch):
    monkeypatch.setattr(cfgmod, "ROOT", tmp_path)
    q = Queue(tmp_path / "jobs", tmp_path / "out")
    p = bakeoff.plan(_tool_suite(), _inventory(), cfgmod.load())
    bakeoff.submit(p, q)
    while True:                                              # the worker "paints" everything; one job fails
        c = q.claim()
        if c is None:
            break
        jid, job = c
        if job["meta"]["category"] == "t1_refine" and job["meta"]["prompt_id"] == "ruin" and job["checkpoint"].startswith("CK_A"):
            q.finish(jid, error="RuntimeError: node FaceDetailer missing")
            continue
        name = "render.png" if job["type"] == "render" else "scene.png"
        Image.new("RGB", (192, 108), (40, 90, 200)).save(q.out_dir(jid) / name)
        q.finish(jid, result={"outputs": [name]})
    index = bakeoff.report("fin", q)
    out = tmp_path / "out" / "bakeoff" / "fin"
    html = index.read_text(encoding="utf-8")
    assert "/scene.png" in html and "/render.png" in html and "One picture across the categories" in html
    assert (out / "across_juke_nolora_7.png").exists() and (out / "detail_juke_nolora_7.png").exists()
    assert (out / "across_ruin_nolora_7.png").exists()
    a, d = Image.open(out / "across_juke_nolora_7.png"), Image.open(out / "detail_juke_nolora_7.png")
    assert a.width == 170 + 3 * (384 + 6) and d.width == 170 + 3 * (32 + 6)     # raw · t0 · t1 columns
    # scene.png is filed in both trees like a render
    assert len(list((out / "by_category" / "t0_plain" / "juke").glob("*.png"))) == 2
    summary = json.loads((out / "summary.json").read_text())
    assert summary["failed"] == 1 and summary["rendered"] == 9 and len(summary["across"]) == 4


def test_detail_crop_is_clamped_to_the_picture():
    im = Image.new("RGB", (100, 60))
    assert bakeoff.detail_crop(im, {"size": 32, "at": [0.99, 0.01]}).size == (32, 32)
    assert bakeoff.detail_crop(im, {"size": 512}).size == (100, 60)
