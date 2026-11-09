"""Shared bits for handlers: the worker context, provenance records, palette lookup, input resolution."""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image

from .. import config as cfgmod
from ..ops import palette as pal


@dataclass
class Context:
    cfg: dict
    comfy: Any = None                     # ComfyClient or None on a CPU worker
    palettes_dir: Path = field(default_factory=lambda: Path("palettes"))
    root: Path = field(default_factory=lambda: cfgmod.ROOT)
    _snappers: dict = field(default_factory=dict)

    def game(self, job: dict) -> dict:
        return cfgmod.game_config(self.cfg, job.get("game"))

    def setting(self, job: dict, key: str, default=None):
        """job field → game config → forge.json defaults → default."""
        v = job.get(key)
        if v is not None:
            return v
        g = self.game(job)
        if key in g:
            return g[key]
        return self.cfg.get("defaults", {}).get(key, default)

    def snapper(self, job: dict) -> pal.Snapper | None:
        name = self.setting(job, "palette")
        if not name:
            return None
        if name not in self._snappers:
            path = pal.find_palette(str(name), self.palettes_dir)
            self._snappers[name] = pal.Snapper(pal.load_palette(path))
        return self._snappers[name]

    def resolve(self, p: str | Path) -> Path:
        """Inputs may be relative to the repo root (jobs are written by hand; keep them short)."""
        q = Path(p)
        return q if q.is_absolute() else (self.root / q)


def style_prefix(ctx: Context, job: dict) -> str:
    return str(ctx.setting(job, "style_prefix", "") or "")


def negative(ctx: Context, job: dict) -> str:
    return str(ctx.setting(job, "negative", "") or "")


def full_prompt(ctx: Context, job: dict) -> str:
    sp = style_prefix(ctx, job).strip()
    return (sp + ", " if sp else "") + str(job["prompt"]).strip()


def write_prov(out_dir: Path, job: dict, **extra) -> Path:
    """prov.json — what made this asset. Model + licence come from models/models.json when known."""
    rec = {
        "job_id": job.get("id"),
        "type": job.get("type"),
        "name": job.get("name"),
        "batch": job.get("batch"),
        "created": datetime.now().isoformat(timespec="seconds"),
        "prompt": job.get("prompt"),
        "negative": job.get("negative"),
    }
    rec.update(extra)
    p = out_dir / "prov.json"
    with open(p, "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=1, ensure_ascii=False)
    return p


def model_licence(ctx: Context, checkpoint: str) -> dict:
    """Look the checkpoint up in models/models.json (by file name) for its licence record."""
    reg = ctx.root / "models" / "models.json"
    if not reg.exists():
        return {}
    with open(reg, "r", encoding="utf-8") as f:
        data = json.load(f)
    for name, m in data.get("models", {}).items():
        for fname in m.get("files", []):
            if Path(fname).name == Path(checkpoint).name:
                return {"model": name, "license": m.get("license"), "commercial_ok": m.get("commercial_ok")}
    return {"model": checkpoint, "license": "unknown — add it to models/models.json"}


def save_png(img: Image.Image, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG", optimize=True)
    return path
