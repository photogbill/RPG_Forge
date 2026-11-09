"""Build a FLUX.2 [klein] ComfyUI API graph in code (4B base or 4B distilled).

Mirrors ComfyUI's own template (`image_flux2_klein_text_to_image.json`):
    UNETLoader (the klein diffusion model)  →  optional LoRA chain (model-only)
    CLIPLoader(qwen_3_4b, type="flux2")     →  CLIPTextEncode positive / negative (distilled: ConditioningZeroOut)
    VAELoader(flux2-vae)
    EmptyFlux2LatentImage → RandomNoise + KSamplerSelect(euler) + Flux2Scheduler(steps, w, h) + CFGGuider(cfg)
    → SamplerCustomAdvanced → VAEDecode → SaveImage

Defaults follow the template: base = 20 steps, cfg 5; distilled = 4 steps, cfg 1, negative zeroed out.
Files live in ComfyUI's diffusion_models / text_encoders / vae folders (forge.json model_dirs → extra_model_paths).
Licence note: the 4B models are Apache-2.0 (commercial OK); the 9B models are not — see models/models.json.
"""
from __future__ import annotations

SAMPLERS = ("euler", "euler_ancestral", "dpmpp_2m", "res_multistep", "uni_pc")


def is_distilled(unet_name: str) -> bool:
    """The template's naming: 'flux-2-klein-base-4b*' is the base model, 'flux-2-klein-4b*' the distilled one."""
    return "base" not in unet_name.lower()


def build(unet: str, prompt: str, negative: str, seed: int, width: int, height: int, text_encoder: str = "qwen_3_4b.safetensors",
          vae: str = "flux2-vae.safetensors", steps: int | None = None, cfg: float | None = None, loras: list[dict] | None = None,
          batch: int = 1, sampler: str = "euler", distilled: bool | None = None, filename_prefix: str = "forge",
          weight_dtype: str = "default") -> dict:
    """loras: [{"name": "file.safetensors", "strength": 0.8}, ...] applied in order with LoraLoaderModelOnly."""
    if sampler not in SAMPLERS:
        raise ValueError(f"sampler '{sampler}' not in {SAMPLERS}")
    if distilled is None:
        distilled = is_distilled(unet)
    if steps is None:
        steps = 4 if distilled else 20
    if cfg is None:
        cfg = 1.0 if distilled else 5.0
    g: dict = {}
    g["1"] = {"class_type": "UNETLoader", "inputs": {"unet_name": unet, "weight_dtype": weight_dtype}}
    g["2"] = {"class_type": "CLIPLoader", "inputs": {"clip_name": text_encoder, "type": "flux2", "device": "default"}}
    g["3"] = {"class_type": "VAELoader", "inputs": {"vae_name": vae}}
    model_ref = ["1", 0]
    nid = 20
    for lo in loras or []:
        g[str(nid)] = {"class_type": "LoraLoaderModelOnly", "inputs": {
            "lora_name": lo["name"], "strength_model": float(lo.get("strength", 0.8)), "model": model_ref}}
        model_ref = [str(nid), 0]
        nid += 1
    g["4"] = {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}}
    if distilled:
        g["5"] = {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["4", 0]}}
    else:
        g["5"] = {"class_type": "CLIPTextEncode", "inputs": {"text": negative or "", "clip": ["2", 0]}}
    g["6"] = {"class_type": "EmptyFlux2LatentImage", "inputs": {"width": int(width), "height": int(height), "batch_size": int(batch)}}
    g["7"] = {"class_type": "RandomNoise", "inputs": {"noise_seed": int(seed)}}
    g["8"] = {"class_type": "KSamplerSelect", "inputs": {"sampler_name": sampler}}
    g["9"] = {"class_type": "Flux2Scheduler", "inputs": {"steps": int(steps), "width": int(width), "height": int(height)}}
    g["10"] = {"class_type": "CFGGuider", "inputs": {"cfg": float(cfg), "model": model_ref, "positive": ["4", 0], "negative": ["5", 0]}}
    g["11"] = {"class_type": "SamplerCustomAdvanced", "inputs": {
        "noise": ["7", 0], "guider": ["10", 0], "sampler": ["8", 0], "sigmas": ["9", 0], "latent_image": ["6", 0]}}
    g["12"] = {"class_type": "VAEDecode", "inputs": {"samples": ["11", 0], "vae": ["3", 0]}}
    g["13"] = {"class_type": "SaveImage", "inputs": {"filename_prefix": filename_prefix, "images": ["12", 0]}}
    return g
