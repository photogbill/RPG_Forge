"""Read what a .safetensors file *is* without loading it: checkpoint or LoRA, SD1.5 or SDXL, and the
trainer's metadata (base model, resolution, the tags it was trained on → trigger-word candidates).

Only the JSON header is read (a few KB), so a 7 GB checkpoint is inspected in milliseconds. No torch.
This matters because ComfyUI will happily apply an SD1.5 LoRA to an SDXL model and simply do nothing
(it logs "lora key not loaded" and renders as if no LoRA were there) — a bake-off would then call a
dead combination "fine". Classifying first keeps the comparison honest.
"""
from __future__ import annotations
import json, re, struct
from collections import Counter
from pathlib import Path


def read_header(path: Path) -> tuple[dict, dict]:
    """→ (tensors: name → {dtype, shape, data_offsets}, metadata: the __metadata__ dict or {})."""
    with open(path, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        if n <= 0 or n > 200_000_000:
            raise ValueError(f"{path.name}: not a safetensors file (header length {n})")
        header = json.loads(f.read(n).decode("utf-8"))
    meta = header.pop("__metadata__", {}) or {}
    return header, meta


def classify(tensors: dict, meta: dict, size_bytes: int) -> dict:
    keys = list(tensors.keys())
    ks = " ".join(keys[:4000])  # enough to see the shape of the file
    out = {"kind": "unknown", "base": "unknown", "hints": []}

    # ---- kind
    is_lora = any(("lora_up" in k or "lora_down" in k or ".alpha" in k or "lora_A" in k or "lora_B" in k
                   or "hada_w1" in k or "lokr_w1" in k or "oft_" in k) for k in keys)
    has_unet_full = any(k.startswith(("model.diffusion_model.", "diffusion_model.")) for k in keys)
    has_vae = any(k.startswith(("first_stage_model.", "vae.")) for k in keys)
    if is_lora:
        out["kind"] = "lora"
        if any(("hada_w1" in k or "lokr_w1" in k) for k in keys):
            out["kind"] = "lycoris"
    elif has_unet_full and has_vae:
        out["kind"] = "checkpoint"
    elif has_unet_full:
        out["kind"] = "unet"
    elif any(k.startswith(("double_blocks.", "single_blocks.")) for k in keys):
        out["kind"] = "unet"          # a FLUX.1 diffusion model saved without the model.diffusion_model. prefix (ComfyUI split files)
    elif any(k.startswith("text_model.") or k.startswith("transformer.") for k in keys):
        out["kind"] = "text_encoder"
    elif any(k.startswith(("decoder.", "encoder.")) for k in keys) and not any(k.startswith("model.") for k in keys):
        out["kind"] = "vae"
    elif any("emb_params" in k or k == "clip_l" or k == "clip_g" for k in keys):
        out["kind"] = "embedding"

    # ---- base architecture
    base = str(meta.get("ss_base_model_version", "") or meta.get("modelspec.architecture", "") or "").lower()
    if "sdxl" in base or "stable-diffusion-xl" in base:
        out["base"] = "sdxl"
    elif "sd_v1" in base or "sd-v1" in base or "stable-diffusion-v1" in base or "sd1" in base:
        out["base"] = "sd15"
    elif "sd_v2" in base or "stable-diffusion-v2" in base:
        out["base"] = "sd2"
    elif "flux" in base:
        out["base"] = "flux"
    # FLUX.1 (dev/schnell) LoRAs: diffusers or kohya naming of the DiT blocks. They do not apply to SDXL,
    # nor to FLUX.2 klein (a different architecture) — only to FLUX.1 weights.
    if any(("single_transformer_blocks" in k or "double_blocks" in k or "single_blocks" in k
            or k.startswith("lora_transformer_") or k.startswith("transformer.")) for k in keys[:400]):
        out["base"] = "flux1"
    if out["base"] == "unknown":
        if out["kind"] == "checkpoint" or out["kind"] == "unet":
            if any("conditioner.embedders.1" in k for k in keys) or any("label_emb" in k for k in keys):
                out["base"] = "sdxl"
            elif any(k.startswith("cond_stage_model.") for k in keys):
                out["base"] = "sd15" if any("input_blocks.1.1.transformer_blocks.0.attn2.to_k.weight" in k for k in keys) else "sd15/sd2"
        elif out["kind"] in ("lora", "lycoris"):
            te2 = any(k.startswith("lora_te2_") for k in keys)
            te1 = any(k.startswith("lora_te1_") for k in keys)
            te_single = any(k.startswith("lora_te_") for k in keys)
            if te2 or te1:
                out["base"] = "sdxl"
            else:
                # SDXL UNet LoRAs have input_blocks 4/5/7/8 with transformer_blocks up to 9; SD1.5 has blocks 1,2,4,5,7,8 with 0 only
                has_deep = any(re.search(r"transformer_blocks_[2-9]", k) for k in keys)
                if has_deep:
                    out["base"] = "sdxl"
                elif te_single or any("input_blocks_1_1" in k for k in keys):
                    out["base"] = "sd15"
                else:
                    # size heuristic as a last resort
                    out["base"] = "sdxl" if size_bytes > 600_000_000 else "unknown"
    # a 2–4 GB "lora" is almost certainly a mislabelled SD1.5 checkpoint
    if out["kind"] == "checkpoint" and 1_500_000_000 < size_bytes < 5_000_000_000 and out["base"] == "unknown":
        out["base"] = "sd15 (by size)"

    # ---- hints from the trainer metadata
    for key in ("ss_sd_model_name", "ss_resolution", "ss_network_dim", "ss_network_alpha", "ss_num_train_images",
                "ss_training_comment", "modelspec.title", "modelspec.description", "modelspec.trigger_phrase",
                "ss_output_name", "ss_base_model_version"):
        if meta.get(key):
            out["hints"].append(f"{key}={str(meta[key])[:120]}")
    return out


def trigger_candidates(meta: dict, top: int = 12) -> list[str]:
    """kohya stores the training captions' tag frequencies; the most frequent tags are the words the
    LoRA responds to (often the trigger word is the one present in every image)."""
    raw = meta.get("ss_tag_frequency")
    if not raw:
        tp = meta.get("modelspec.trigger_phrase")
        return [tp] if tp else []
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return []
    c: Counter = Counter()
    for _folder, tags in data.items():
        if isinstance(tags, dict):
            for t, n in tags.items():
                c[t.strip()] += int(n)
    return [t for t, _ in c.most_common(top) if t]


def inspect(path: Path) -> dict:
    path = Path(path)
    size = path.stat().st_size
    try:
        tensors, meta = read_header(path)
    except Exception as e:  # noqa: BLE001
        return {"file": path.name, "path": str(path), "bytes": size, "error": str(e)}
    info = classify(tensors, meta, size)
    rec = {"file": path.name, "path": str(path), "bytes": size, "gb": round(size / 1e9, 2),
           "tensors": len(tensors), **info, "triggers": trigger_candidates(meta)}
    if meta.get("ss_resolution"):
        rec["resolution"] = meta["ss_resolution"]
    return rec


def scan(dirs: list[Path]) -> list[dict]:
    out = []
    for d in dirs:
        d = Path(d)
        if not d.exists():
            continue
        for p in sorted(d.rglob("*.safetensors")):
            out.append(inspect(p))
        for p in sorted(d.rglob("*.gguf")):
            size = p.stat().st_size
            name = p.name.lower()
            base = "flux1 (gguf, by name)" if "flux" in name and "klein" not in name else "unknown"
            out.append({"file": p.name, "path": str(p), "bytes": size, "gb": round(size / 1e9, 2), "kind": "unet", "base": base,
                        "triggers": [], "hints": ["GGUF — needs the ComfyUI-GGUF custom node (UnetLoaderGGUF); no header metadata read"]})
    return out


def render_markdown(records: list[dict]) -> str:
    lines = ["# Model inventory", "", "Generated by `python -m forge models scan` — header-only inspection, no weights loaded.", "",
             "| File | Kind | Base | Size | Triggers / hints |", "|---|---|---|---|---|"]
    for r in records:
        if "error" in r:
            lines.append(f"| `{r['file']}` | ? | ? | {r['bytes'] / 1e9:.2f} GB | ERROR {r['error']} |")
            continue
        extra = ", ".join(r.get("triggers", [])[:8])
        hints = "; ".join(h for h in r.get("hints", []) if h.startswith(("ss_sd_model_name", "ss_resolution", "modelspec.trigger")))
        lines.append(f"| `{r['file']}` | {r['kind']} | **{r['base']}** | {r['gb']} GB | {extra}{(' · ' + hints) if hints else ''} |")
    return "\n".join(lines) + "\n"
