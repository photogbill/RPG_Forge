"""Pre-flight checks before a long run (roadmap F9): does this ComfyUI have every node the graphs need, does every
model file the queued jobs name exist, and will the biggest one fit the card?

    python -m forge doctor          (doctor.bat) — the old checks, then this report

    flux2_klein: OK · flux1 gguf: UnetLoaderGGUF missing → install_comfy_gguf.bat · face_fix: FaceDetailer missing → install_comfy_faces.bat
"""
from __future__ import annotations
import json, shutil, subprocess
from pathlib import Path

from . import config as cfgmod
from .engines import graph_ops as go, sdxl_graph, flux1_graph, flux2_graph

REMEDY = {"UnetLoaderGGUF": "install_comfy_gguf.bat", "FaceDetailer": "install_comfy_faces.bat",
          "UltralyticsDetectorProvider": "install_comfy_faces.bat"}
DEFAULT_REMEDY = "update ComfyUI (install_comfy.bat pulls the latest)"

def graph_shapes() -> dict[str, set[str]]:
    """The node types each graph kind and each paint stage needs, taken from the real builders."""
    shapes: dict[str, set[str]] = {}
    shapes["sdxl"] = go.required_nodes(sdxl_graph.build("c.safetensors", "p", "n", 1, 1024, 1024))
    shapes["flux1"] = go.required_nodes(flux1_graph.build("u.safetensors", "p", 1, 1024, 1024))
    shapes["flux1 all-in-one"] = go.required_nodes(flux1_graph.build("u.safetensors", "p", 1, 1024, 1024, all_in_one=True))
    shapes["flux1 gguf"] = go.required_nodes(flux1_graph.build("u.gguf", "p", 1, 1024, 1024))
    shapes["flux2_klein"] = go.required_nodes(flux2_graph.build("flux-2-klein-4b.safetensors", "p", "", 1, 1024, 1024))
    g = sdxl_graph.build("c.safetensors", "p", "n", 1, 1344, 768)
    before = go.required_nodes(g)
    go.add_upscale(g, "u.pth", 1920, 1080)
    shapes["upscale"] = go.required_nodes(g) - before
    before = go.required_nodes(g)
    go.add_refine(g, 0.3)
    shapes["refine"] = (go.required_nodes(g) - before) | {"VAEEncode", "KSampler"}
    shapes["repaint (img2img)"] = {"LoadImage", "ImageScale", "VAEEncode"}
    shapes["repaint flux2"] = {"SplitSigmasDenoise"}
    shapes["controlnet"] = {"ControlNetLoader", "SetUnionControlNetType", "ControlNetApplyAdvanced", "LoadImage"}
    shapes["freeu"] = {"FreeU_V2"}
    shapes["face_fix"] = {"FaceDetailer", "UltralyticsDetectorProvider"}
    return shapes


def node_report(info: dict | None) -> list[str]:
    if info is None:
        return ["· nodes: ComfyUI is not running — start it (run_worker.bat) and run doctor.bat again to check graph nodes"]
    parts = []
    for name, need in graph_shapes().items():
        missing = sorted(n for n in need if n not in info)
        if not missing:
            parts.append(f"{name}: OK")
        else:
            fix = sorted({REMEDY.get(n, DEFAULT_REMEDY) for n in missing})
            parts.append(f"{name}: {', '.join(missing)} missing → {' / '.join(fix)}")
    depth = [n for n in ("DepthAnythingV2Preprocessor", "MiDaS-DepthMapPreprocessor") if n in info]
    parts.append("depth control: OK" if depth else "depth control: no preprocessor (optional — canny needs none; install_comfy_aux.bat for depth)")
    return ["nodes: " + " · ".join(parts)]


def _all_dirs(cfg: dict, kind: str) -> list[Path]:
    dirs = list(cfgmod.model_dirs(cfg, kind))
    comfy_models = cfgmod.path_of(cfg, "comfy_root") / "models" / kind
    if comfy_models.exists():
        dirs.append(comfy_models)
    return dirs


def find_model(cfg: dict, kinds: tuple[str, ...], name: str) -> Path | None:
    for k in kinds:
        for d in _all_dirs(cfg, k):
            p = d / name
            if p.exists():
                return p
    return None


def job_models(cfg: dict, job: dict) -> list[tuple[str, tuple[str, ...], str]]:
    """(role, model-folder kinds, file name) for every model a queued job will ask ComfyUI for."""
    t = job.get("type")
    gcfg = cfgmod.game_config(cfg, job.get("game"))
    comfy = cfg.get("comfy", {})
    out = []
    if t == "pipeline":
        for st in job.get("steps") or []:
            if isinstance(st, dict):
                out += job_models(cfg, {"game": job.get("game"), **st})
        return out
    gpu_types = ("scene_card", "concept", "portrait", "prop", "tile_texture", "render", "scene_paint", "repaint", "icon", "sleeve")
    if t in gpu_types:
        ck = job.get("checkpoint") or (gcfg.get("checkpoints_by_job") or {}).get(t) or gcfg.get("checkpoint") or comfy.get("default_checkpoint")
        graph = str(job.get("graph") or "sdxl")
        kinds = ("checkpoints",) if graph == "sdxl" or job.get("all_in_one") else ("diffusion_models", "checkpoints")
        out.append(("checkpoint", kinds, ck))
        for lo in job.get("loras") or (gcfg.get("loras_by_job") or {}).get(t) or []:
            out.append(("lora", ("loras",), lo["name"]))
        if graph == "flux1" and not job.get("all_in_one"):
            fx = comfy.get("flux1", {})
            out += [("clip_l", ("text_encoders", "clip"), job.get("clip_l") or fx.get("clip_l")),
                    ("t5", ("text_encoders", "clip"), job.get("t5") or fx.get("t5")), ("vae", ("vae",), job.get("vae") or fx.get("vae"))]
        if graph == "flux2_klein":
            fx = comfy.get("flux2", {})
            te = job.get("text_encoder") or (fx.get("text_encoder_9b") if "9b" in str(ck).lower() else fx.get("text_encoder"))
            out += [("text_encoder", ("text_encoders", "clip"), te), ("vae", ("vae",), job.get("vae") or fx.get("vae"))]
    if t in ("scene_paint", "repaint", "upscale"):
        up = job.get("upscale", True) if t != "upscale" else True
        if up:
            m = (up.get("model") if isinstance(up, dict) else None) or job.get("model") or comfy.get("upscale_model")
            out.append(("upscaler", ("upscale_models",), m))
        c = job.get("control")
        if c and str(c.get("type", "canny")) != "none":
            out.append(("controlnet", ("controlnet",), c.get("model") or comfy.get("controlnet_union")))
        if job.get("face_fix"):
            ff = job["face_fix"] if isinstance(job["face_fix"], dict) else {}
            det = ff.get("detector") or comfy.get("face_detector", "bbox/face_yolov8m.pt")
            out.append(("face_detector", ("ultralytics_bbox", "ultralytics"), det.split("/", 1)[-1]))
    return [(r, k, n) for r, k, n in out if n]


def gpu_memory_gb() -> float | None:
    nvsmi = shutil.which("nvidia-smi")
    if not nvsmi:
        return None
    try:
        out = subprocess.run([nvsmi, "--query-gpu=memory.total", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10)
        return float(out.stdout.strip().splitlines()[0]) / 1024.0
    except Exception:
        return None


def queue_report(cfg: dict) -> list[str]:
    pend = sorted((cfgmod.path_of(cfg, "jobs") / "pending").glob("*.json"))
    if not pend:
        return ["models: queue is empty — nothing to check"]
    missing: dict[str, set[str]] = {}
    biggest = (0.0, "")
    checked = 0
    for p in pend:
        try:
            job = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for role, kinds, name in job_models(cfg, job):
            checked += 1
            f = find_model(cfg, kinds, name)
            if f is None:
                missing.setdefault(f"{role} {name}", set()).add(job.get("id", p.stem))
            elif role == "checkpoint":
                gb = f.stat().st_size / 1e9
                if gb > biggest[0]:
                    biggest = (gb, name)
    lines = [f"models: {len(pend)} queued job(s), {checked} model references checked"]
    if not missing:
        lines.append("✓ every model file the queue names is on disk")
    for what, ids in sorted(missing.items()):
        example = sorted(ids)[0]
        lines.append(f"✗ {what} — not in any model folder ({len(ids)} job(s), e.g. {example}); pull_quality.bat / pull_model.bat or fix the job")
    vram = gpu_memory_gb()
    if biggest[0] > 0:
        cast = float(cfg.get("comfy", {}).get("fp8_cast_over_gb", 14.0))
        if vram is None:
            lines.append(f"· biggest model {biggest[1]} {biggest[0]:.1f} GB (no nvidia-smi here to compare)")
        elif biggest[0] > vram * 0.92 and biggest[0] <= cast:
            lines.append(f"⚠ biggest model {biggest[1]} is {biggest[0]:.1f} GB on a {vram:.0f} GB card — expect offloading (slow) or OOM")
        else:
            lines.append(f"✓ biggest model {biggest[1]} {biggest[0]:.1f} GB fits a {vram:.0f} GB card" +
                         (" (cast to fp8 on load)" if biggest[0] > cast else ""))
    return lines


def report(cfg: dict, client=None) -> list[str]:
    info = None
    if client is not None and client.is_up():
        try:
            info = client.object_info()
        except Exception as e:  # noqa: BLE001
            return [f"· could not read /object_info: {e}"] + queue_report(cfg)
    return node_report(info) + queue_report(cfg)
