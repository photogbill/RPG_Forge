"""Build a Krea 2 ComfyUI API graph in code (roadmap N8 / F17).

Read from the installed ComfyUI 0.44 source, not from memory:
    comfy/supported_models.py  class Krea2 — flow model (ModelType.FLUX), shift 1.15, latent format Wan21 (16 ch)
    comfy/ldm/krea2/model.py   SingleStreamDiT; accepts 4-D image latents and 5-D video latents
    comfy/text_encoders/krea2.py  Qwen3-VL-4B, 12-layer tap; nodes.py CLIPLoader has type "krea2"
    comfy/ops.py               int8_tensorwise + convrot weights load natively (no custom node) — the Civitai
                               "INT8-ConvRot" files carry `comfy_quant` keys that core reads
Files (Comfy-Org/Krea-2 on Hugging Face): diffusion model in diffusion_models/, text encoder qwen3vl_4b_*.safetensors,
VAE qwen_image_vae.safetensors (the Qwen-Image VAE — Wan 2.1 latent format).

    UNETLoader → [LoraLoaderModelOnly …] → KSampler(er_sde / simple) ← CLIPLoader(type krea2) → CLIPTextEncode ×2
    EmptySD3LatentImage (16 ch) → KSampler → VAEDecode(VAELoader qwen_image_vae) → SaveImage

Settings: Turbo (name contains "turbo") 8 steps, cfg 1.0; Raw 50 steps, cfg 3.5. A fine-tune's base is not always in
its name — the krea2 bake-off suite tries both. Licence: Krea 2 Community License — commercial use permitted while
company revenue is under US$1M/year (§2.3). A Civitai fine-tune has its own terms on top (see models/licences.json).
"""
from __future__ import annotations

SAMPLERS = ("er_sde", "euler", "euler_ancestral", "dpmpp_2m", "res_multistep", "uni_pc")
SCHEDULERS = ("simple", "normal", "beta", "sgm_uniform")
DEFAULT_TE = "qwen3vl_4b_fp8_scaled.safetensors"
DEFAULT_VAE = "qwen_image_vae.safetensors"


def is_turbo(name: str) -> bool:
    return "turbo" in name.lower()


def defaults(model: str) -> tuple[int, float]:
    return (8, 1.0) if is_turbo(model) else (50, 3.5)


def build(model: str, prompt: str, negative: str, seed: int, width: int, height: int, text_encoder: str = DEFAULT_TE,
          vae: str = DEFAULT_VAE, steps: int | None = None, cfg: float | None = None, loras: list[dict] | None = None,
          batch: int = 1, sampler: str = "er_sde", scheduler: str = "simple", weight_dtype: str = "default",
          filename_prefix: str = "forge") -> dict:
    """loras: [{"name": …, "strength": 0.8}] — model-only (a DiT LoRA has no text side)."""
    if sampler not in SAMPLERS:
        raise ValueError(f"sampler '{sampler}' not in {SAMPLERS}")
    if scheduler not in SCHEDULERS:
        raise ValueError(f"scheduler '{scheduler}' not in {SCHEDULERS}")
    d_steps, d_cfg = defaults(model)
    steps = int(steps) if steps is not None else d_steps
    cfg = float(cfg) if cfg is not None else d_cfg
    g: dict = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": model, "weight_dtype": weight_dtype}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": text_encoder, "type": "krea2", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": vae}},
    }
    model_ref = ["1", 0]
    nid = 20
    for lo in loras or []:
        g[str(nid)] = {"class_type": "LoraLoaderModelOnly", "inputs": {
            "lora_name": lo["name"], "strength_model": float(lo.get("strength", 0.8)), "model": model_ref}}
        model_ref = [str(nid), 0]
        nid += 1
    g["4"] = {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}}
    g["5"] = {"class_type": "CLIPTextEncode", "inputs": {"text": negative or "", "clip": ["2", 0]}}
    g["7"] = {"class_type": "EmptySD3LatentImage", "inputs": {"width": int(width), "height": int(height), "batch_size": int(batch)}}
    g["6"] = {"class_type": "KSampler", "inputs": {
        "seed": int(seed), "steps": steps, "cfg": cfg, "sampler_name": sampler, "scheduler": scheduler, "denoise": 1.0,
        "model": model_ref, "positive": ["4", 0], "negative": ["5", 0], "latent_image": ["7", 0]}}
    g["8"] = {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["3", 0]}}
    g["9"] = {"class_type": "SaveImage", "inputs": {"filename_prefix": filename_prefix, "images": ["8", 0]}}
    return g


def from_job(comfy_cfg: dict, job: dict, ckpt: str, prompt: str, neg: str, seed: int, w: int, h: int,
             loras: list[dict]) -> tuple[dict, str, dict, int, float, str, str]:
    """What forge/jobs/gpu.py build_graph needs for `graph: krea2` — kept here so wiring it is a three-line branch.
    Returns (graph, graph_name, extra_prov, steps, cfg, sampler, scheduler)."""
    kc = comfy_cfg.get("krea2", {})
    d_steps, d_cfg = defaults(ckpt)
    steps = int(job["steps"]) if job.get("steps") is not None else d_steps
    cfg = float(job["cfg"]) if job.get("cfg") is not None else d_cfg
    te = job.get("text_encoder") or kc.get("text_encoder", DEFAULT_TE)
    vae = job.get("vae") or kc.get("vae", DEFAULT_VAE)
    sampler = str(job.get("sampler") or kc.get("sampler", "er_sde"))
    scheduler = str(job.get("scheduler") or kc.get("scheduler", "simple"))
    if sampler in ("dpmpp_2m",) and scheduler == "karras":      # SDXL defaults leaking in from a suite
        sampler, scheduler = "er_sde", "simple"
    wdt = str(job.get("weight_dtype") or "default")
    g = build(ckpt, prompt, neg, seed, w, h, text_encoder=te, vae=vae, steps=steps, cfg=cfg, loras=loras,
              batch=int(job.get("count") or 1), sampler=sampler, scheduler=scheduler, weight_dtype=wdt)
    return g, "krea2_graph", {"text_encoder": te, "vae": vae, "weight_dtype": wdt, "turbo": is_turbo(ckpt)}, steps, cfg, sampler, scheduler
