"""Build a FLUX.1 (dev / schnell and their fine-tunes) ComfyUI API graph in code.

Two loader shapes, chosen by `all_in_one`:
    all_in_one=False (the usual split files, e.g. Kijai/flux-fp8 or a Civitai fine-tune's unet):
        UNETLoader(unet) + DualCLIPLoader(clip_l, t5xxl, type="flux") + VAELoader(ae.safetensors)
    all_in_one=True (a checkpoint with CLIP and VAE baked in, e.g. Comfy-Org/flux1-schnell's flux1-schnell-fp8.safetensors):
        CheckpointLoaderSimple(checkpoint)
Then: optional LoRA chain (LoraLoaderModelOnly on the unet; a full LoraLoader when all-in-one so the text side is
touched too) → CLIPTextEncode → FluxGuidance(guidance) → KSampler(cfg 1.0, euler/simple) → VAEDecode → SaveImage.

Defaults: dev-style = 20 steps, guidance 3.5; schnell-style (name contains 'schnell') = 4 steps, guidance 3.5 (schnell
ignores guidance but the node is harmless). cfg is 1.0 for every FLUX.1 model — negative prompts do nothing here.
Licence note: FLUX.1 [schnell] is Apache-2.0; FLUX.1 [dev] and most of its fine-tunes are under the FLUX.1 Non-Commercial
licence — experiments only, never shipped assets (models/models.json carries the flag; prov.json records it).
"""
from __future__ import annotations

SAMPLERS = ("euler", "euler_ancestral", "dpmpp_2m", "heun", "uni_pc", "deis")
SCHEDULERS = ("simple", "normal", "sgm_uniform", "beta", "karras")


def is_schnell(name: str) -> bool:
    return "schnell" in name.lower()


def build(model: str, prompt: str, seed: int, width: int, height: int, clip_l: str = "clip_l.safetensors",
          t5: str = "t5xxl_fp8_e4m3fn.safetensors", vae: str = "ae.safetensors", steps: int | None = None,
          guidance: float = 3.5, loras: list[dict] | None = None, batch: int = 1, sampler: str = "euler",
          scheduler: str = "simple", all_in_one: bool = False, filename_prefix: str = "forge", negative: str = "",
          cfg: float = 1.0, weight_dtype: str = "default") -> dict:
    """loras: [{"name": "file.safetensors", "strength": 0.8, "clip": 0.8}, ...] applied in order.
    cfg: 1.0 for distilled dev/schnell (the normal case); de-distilled fine-tunes want a real CFG (3–5) and then the
    negative prompt matters. weight_dtype: "fp8_e4m3fn" casts a bf16 unet on load (a 24 GB file fits a 16 GB card that way).
    A .gguf model goes through UnetLoaderGGUF (ComfyUI-GGUF custom node)."""
    if sampler not in SAMPLERS:
        raise ValueError(f"sampler '{sampler}' not in {SAMPLERS}")
    if scheduler not in SCHEDULERS:
        raise ValueError(f"scheduler '{scheduler}' not in {SCHEDULERS}")
    if steps is None:
        steps = 4 if is_schnell(model) else 20
    g: dict = {}
    if all_in_one:
        g["1"] = {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": model}}
        model_ref, clip_ref, vae_ref = ["1", 0], ["1", 1], ["1", 2]
    elif model.lower().endswith(".gguf"):
        g["1"] = {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": model}}
        g["2"] = {"class_type": "DualCLIPLoader", "inputs": {"clip_name1": clip_l, "clip_name2": t5, "type": "flux", "device": "default"}}
        g["3"] = {"class_type": "VAELoader", "inputs": {"vae_name": vae}}
        model_ref, clip_ref, vae_ref = ["1", 0], ["2", 0], ["3", 0]
    else:
        g["1"] = {"class_type": "UNETLoader", "inputs": {"unet_name": model, "weight_dtype": weight_dtype}}
        g["2"] = {"class_type": "DualCLIPLoader", "inputs": {"clip_name1": clip_l, "clip_name2": t5, "type": "flux", "device": "default"}}
        g["3"] = {"class_type": "VAELoader", "inputs": {"vae_name": vae}}
        model_ref, clip_ref, vae_ref = ["1", 0], ["2", 0], ["3", 0]
    nid = 20
    for lo in loras or []:
        if all_in_one:
            g[str(nid)] = {"class_type": "LoraLoader", "inputs": {
                "lora_name": lo["name"], "strength_model": float(lo.get("strength", 0.8)),
                "strength_clip": float(lo.get("clip", lo.get("strength", 0.8))), "model": model_ref, "clip": clip_ref}}
            model_ref, clip_ref = [str(nid), 0], [str(nid), 1]
        else:
            g[str(nid)] = {"class_type": "LoraLoaderModelOnly", "inputs": {
                "lora_name": lo["name"], "strength_model": float(lo.get("strength", 0.8)), "model": model_ref}}
            model_ref = [str(nid), 0]
        nid += 1
    g["4"] = {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": clip_ref}}
    g["5"] = {"class_type": "CLIPTextEncode", "inputs": {"text": negative or "", "clip": clip_ref}}
    g["6"] = {"class_type": "FluxGuidance", "inputs": {"guidance": float(guidance), "conditioning": ["4", 0]}}
    g["7"] = {"class_type": "EmptySD3LatentImage", "inputs": {"width": int(width), "height": int(height), "batch_size": int(batch)}}
    g["8"] = {"class_type": "KSampler", "inputs": {
        "seed": int(seed), "steps": int(steps), "cfg": float(cfg), "sampler_name": sampler, "scheduler": scheduler, "denoise": 1.0,
        "model": model_ref, "positive": ["6", 0], "negative": ["5", 0], "latent_image": ["7", 0]}}
    g["9"] = {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": vae_ref}}
    g["10"] = {"class_type": "SaveImage", "inputs": {"filename_prefix": filename_prefix, "images": ["9", 0]}}
    return g
