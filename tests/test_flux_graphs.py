"""The FLUX graph builders are pure dicts — check their shape, defaults and LoRA chains without ComfyUI."""
from forge.engines import flux2_graph, flux1_graph
from forge import bakeoff


def test_flux2_base_defaults_and_negative():
    g = flux2_graph.build("flux-2-klein-base-4b-fp8.safetensors", "a hedgehog", "blurry", 7, 1344, 768)
    assert g["1"]["class_type"] == "UNETLoader" and g["1"]["inputs"]["unet_name"].startswith("flux-2-klein-base")
    assert g["2"]["inputs"]["type"] == "flux2" and g["2"]["inputs"]["clip_name"] == "qwen_3_4b.safetensors"
    assert g["5"]["class_type"] == "CLIPTextEncode" and g["5"]["inputs"]["text"] == "blurry"
    assert g["9"]["class_type"] == "Flux2Scheduler" and g["9"]["inputs"]["steps"] == 20
    assert g["10"]["inputs"]["cfg"] == 5.0 and g["7"]["inputs"]["noise_seed"] == 7
    assert g["6"]["inputs"] == {"width": 1344, "height": 768, "batch_size": 1}


def test_flux2_distilled_zeroes_negative_and_fast():
    g = flux2_graph.build("flux-2-klein-4b-fp8.safetensors", "p", "n", 1, 1024, 1024)
    assert flux2_graph.is_distilled("flux-2-klein-4b-fp8.safetensors") and not flux2_graph.is_distilled("flux-2-klein-base-4b-fp8.safetensors")
    assert g["5"]["class_type"] == "ConditioningZeroOut"
    assert g["9"]["inputs"]["steps"] == 4 and g["10"]["inputs"]["cfg"] == 1.0


def test_flux2_lora_chain_is_model_only_and_ordered():
    g = flux2_graph.build("flux-2-klein-base-4b-fp8.safetensors", "p", "", 1, 1024, 1024,
                          loras=[{"name": "a.safetensors", "strength": 0.6}, {"name": "b.safetensors"}])
    assert g["20"]["class_type"] == "LoraLoaderModelOnly" and g["20"]["inputs"]["model"] == ["1", 0]
    assert g["21"]["inputs"]["model"] == ["20", 0] and g["21"]["inputs"]["strength_model"] == 0.8
    assert g["10"]["inputs"]["model"] == ["21", 0]


def test_flux1_split_files_and_schnell_steps():
    g = flux1_graph.build("flux1-schnell-fp8.safetensors", "p", 3, 1024, 1024, loras=[{"name": "RPGmaps_v5.safetensors"}])
    assert g["1"]["class_type"] == "UNETLoader" and g["2"]["class_type"] == "DualCLIPLoader" and g["2"]["inputs"]["type"] == "flux"
    assert g["3"]["inputs"]["vae_name"] == "ae.safetensors"
    assert g["20"]["class_type"] == "LoraLoaderModelOnly" and g["8"]["inputs"]["model"] == ["20", 0]
    assert g["8"]["inputs"]["steps"] == 4 and g["8"]["inputs"]["cfg"] == 1.0
    assert g["6"]["class_type"] == "FluxGuidance" and g["6"]["inputs"]["guidance"] == 3.5
    assert g["9"]["inputs"]["vae"] == ["3", 0]


def test_flux1_all_in_one_uses_checkpoint_and_full_lora():
    g = flux1_graph.build("flux1-dev-fp8-all.safetensors", "p", 3, 1024, 1024, all_in_one=True, loras=[{"name": "x.safetensors"}])
    assert g["1"]["class_type"] == "CheckpointLoaderSimple" and "2" not in g and "3" not in g
    assert g["20"]["class_type"] == "LoraLoader" and g["4"]["inputs"]["clip"] == ["20", 1]
    assert g["8"]["inputs"]["steps"] == 20 and g["9"]["inputs"]["vae"] == ["1", 2]


def test_bakeoff_plan_flux_suite_overrides_base_and_kinds():
    inv = [{"file": "flux-2-klein-base-4b-fp8.safetensors", "kind": "unknown", "base": "unknown"},
           {"file": "sd_xl_base_1.0.safetensors", "kind": "checkpoint", "base": "sdxl"},
           {"file": "RPGmaps_v5.safetensors", "kind": "lora", "base": "flux1"},
           {"file": "Pixel_Xl_V1.safetensors", "kind": "lora", "base": "sdxl"}]
    suite = {"suite": "t", "game": "g", "graph": "flux2_klein", "base_override": "flux2",
             "checkpoints": ["flux-2-klein-base-4b-fp8.safetensors"], "loras": "*", "include_no_lora": True,
             "steps": None, "cfg": None, "categories": {"c": {"prompts": {"p": "x"}}}}
    p = bakeoff.plan(suite, inv, {})
    assert [j["checkpoint"] for j in p["jobs"]] == ["flux-2-klein-base-4b-fp8.safetensors"]  # only the no-LoRA job
    assert all(sk["lora"] in ("RPGmaps_v5.safetensors", "Pixel_Xl_V1.safetensors") for sk in p["skipped"]) and len(p["skipped"]) == 2
    j = p["jobs"][0]
    assert j["graph"] == "flux2_klein" and j["steps"] is None and j["cfg"] is None and j["sampler"] == "euler"


def test_bakeoff_plan_sdxl_suite_unchanged():
    inv = [{"file": "sd_xl_base_1.0.safetensors", "kind": "checkpoint", "base": "sdxl"},
           {"file": "flux-2-klein-4b-fp8.safetensors", "kind": "unet", "base": "unknown"}]
    suite = {"suite": "t", "game": "g", "checkpoints": "*", "loras": [], "categories": {"c": {"prompts": {"p": "x"}}}}
    p = bakeoff.plan(suite, inv, {})
    assert [j["checkpoint"] for j in p["jobs"]] == ["sd_xl_base_1.0.safetensors"]
    assert "graph" not in p["jobs"][0] and p["jobs"][0]["steps"] == 25 and p["jobs"][0]["cfg"] == 6.0
