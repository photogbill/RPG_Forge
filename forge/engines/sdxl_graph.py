"""Build an SDXL ComfyUI API graph in code: checkpoint → optional LoRA chain → prompts → sampler → image.

Templates (workflows/*.json) are right for exotic models; for SDXL — where the only thing that varies is
*which* checkpoint and *which* LoRAs at *what* strength — a builder is simpler and lets a bake-off ask
for any combination without a file per combination.
"""
from __future__ import annotations

# Every KSampler sampler/scheduler the vendored ComfyUI (0.44) offers — the sprite sampler sweep (2026-11-10) needs
# them all; ComfyUI itself rejects a name it does not know, so a typo still fails loudly as a failed job.
SAMPLERS = ("euler", "euler_cfg_pp", "euler_ancestral", "euler_ancestral_cfg_pp", "heun", "heunpp2", "dpm_2",
            "dpm_2_ancestral", "lms", "dpm_fast", "dpm_adaptive", "dpmpp_2s_ancestral", "dpmpp_2s_ancestral_cfg_pp",
            "dpmpp_sde", "dpmpp_sde_gpu", "dpmpp_2m", "dpmpp_2m_cfg_pp", "dpmpp_2m_sde", "dpmpp_2m_sde_gpu",
            "dpmpp_3m_sde", "dpmpp_3m_sde_gpu", "ddpm", "lcm", "ipndm", "ipndm_v", "deis", "res_multistep",
            "res_multistep_cfg_pp", "res_multistep_ancestral", "res_multistep_ancestral_cfg_pp", "gradient_estimation",
            "gradient_estimation_cfg_pp", "er_sde", "seeds_2", "seeds_3", "sa_solver", "sa_solver_pece",
            "ddim", "uni_pc", "uni_pc_bh2")
SCHEDULERS = ("normal", "karras", "exponential", "sgm_uniform", "simple", "ddim_uniform", "beta", "linear_quadratic",
              "kl_optimal")


def build(checkpoint: str, prompt: str, negative: str, seed: int, width: int, height: int, steps: int = 25,
          cfg: float = 6.0, loras: list[dict] | None = None, batch: int = 1, sampler: str = "dpmpp_2m",
          scheduler: str = "karras", filename_prefix: str = "forge", clip_skip: int = 0) -> dict:
    """loras: [{"name": "file.safetensors", "strength": 0.8, "clip": 0.8}, ...] applied in order."""
    if sampler not in SAMPLERS:
        raise ValueError(f"sampler '{sampler}' not in {SAMPLERS}")
    if scheduler not in SCHEDULERS:
        raise ValueError(f"scheduler '{scheduler}' not in {SCHEDULERS}")
    g: dict = {}
    g["1"] = {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": checkpoint}}
    model_ref, clip_ref = ["1", 0], ["1", 1]
    nid = 10
    for lo in loras or []:
        g[str(nid)] = {"class_type": "LoraLoader", "inputs": {
            "lora_name": lo["name"], "strength_model": float(lo.get("strength", 0.8)),
            "strength_clip": float(lo.get("clip", lo.get("strength", 0.8))), "model": model_ref, "clip": clip_ref}}
        model_ref, clip_ref = [str(nid), 0], [str(nid), 1]
        nid += 1
    if clip_skip and clip_skip > 0:
        g["5"] = {"class_type": "CLIPSetLastLayer", "inputs": {"stop_at_clip_layer": -int(clip_skip) - 1, "clip": clip_ref}}
        clip_ref = ["5", 0]
    g["2"] = {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": clip_ref}}
    g["3"] = {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": clip_ref}}
    g["4"] = {"class_type": "EmptyLatentImage", "inputs": {"width": int(width), "height": int(height), "batch_size": int(batch)}}
    g["6"] = {"class_type": "KSampler", "inputs": {
        "seed": int(seed), "steps": int(steps), "cfg": float(cfg), "sampler_name": sampler, "scheduler": scheduler,
        "denoise": 1.0, "model": model_ref, "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0]}}
    g["7"] = {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}}
    g["8"] = {"class_type": "SaveImage", "inputs": {"filename_prefix": filename_prefix, "images": ["7", 0]}}
    return g
