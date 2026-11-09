"""Configuration: one JSON file, every path relative to the repo root.

Rule 1 of this repo: nothing is written outside the repo folder unless `allow_external_paths`
is true. No AppData, no C:\\Users, no surprises — the data lives beside the code.
"""
from __future__ import annotations
import json, os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "forge.json"

DEFAULTS: dict = {
    "paths": {
        "jobs": "jobs",
        "out": "out",
        "models": "models",
        "logs": "logs",
        "palettes": "palettes",
        "games": "games",
        "comfy_root": "engines/ComfyUI",
    },
    "comfy": {
        "url": "http://127.0.0.1:8188",
        "timeout_sec": 1800,
        "poll_sec": 1.0,
        "default_workflow": "txt2img_sdxl",
        "default_checkpoint": "sd_xl_base_1.0.safetensors",
    },
    "worker": {
        "poll_sec": 2.0,
        "gpu": False,
    },
    "defaults": {
        "palette": "resurrect-64",
        "card_size": [288, 162],
        "render_scale": 4,
        "negative": "text, watermark, signature, logo, blurry, deformed, extra limbs, extra fingers, low quality",
    },
    "allow_external_paths": False,
}


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load(path: Path | None = None) -> dict:
    """Load forge.json merged over the defaults. Missing file = defaults."""
    p = path or CONFIG_PATH
    cfg = dict(DEFAULTS)
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            cfg = _merge(DEFAULTS, json.load(f))
    cfg["_root"] = str(ROOT)
    return cfg


def path_of(cfg: dict, key: str) -> Path:
    """Resolve a configured path; relative paths hang off the repo root."""
    raw = Path(cfg["paths"][key])
    p = raw if raw.is_absolute() else ROOT / raw
    p = p.resolve()
    if not cfg.get("allow_external_paths", False) and ROOT not in p.parents and p != ROOT:
        raise ValueError(f"path '{key}' = {p} is outside the repo; set allow_external_paths to permit it")
    return p


def ensure_dirs(cfg: dict) -> None:
    for key in ("jobs", "out", "models", "logs", "palettes"):
        path_of(cfg, key).mkdir(parents=True, exist_ok=True)
    jobs = path_of(cfg, "jobs")
    for sub in ("pending", "running", "done", "failed", "templates"):
        (jobs / sub).mkdir(exist_ok=True)


def game_config(cfg: dict, game: str | None) -> dict:
    """games/<game>/forge.game.json — a game's own palette, style prefix, sizes. Optional."""
    if not game:
        return {}
    p = path_of(cfg, "games") / game / "forge.game.json"
    if not p.exists():
        return {}
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)
