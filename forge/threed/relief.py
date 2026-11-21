"""Relief for the texture library (BUILD 63, part 8c) — every library picture gets a normal map beside it, so a surface
answers a lamp: board gaps go dark, grain catches a raking light. The look's rule 4 ("a surface answers the light").

    python -m forge 3d relief <folder or pictures…> [--force] [--strength 6] [--broad 0.0]

For each picture <name>.png/.jpg it writes <name>_n.png beside it (an OpenGL-style normal map: x right, y up the
picture, z out — what a game engine reads). The height is read from the picture's own light and dark with a HIGH-PASS,
so the slow changes of tone across a picture (a lighter plank, a stain) do not become slopes — only grain and gaps do
(Fable's look proof, tools/make_textures.py relief_from_picture, 2026-11-16; here without scipy: the blur is done by
FFT, which wraps at the edges as a tiling texture should).

Where a better relief already exists it wins and is recorded: a Filter Forge render of the same pick's Normal channel
(<name>_ffnormal.png beside the picture — the Filter Forge driver writes it when the pick's preset has a Normal
channel), or a Material Maker export (<name>_mmnormal.png). An existing <name>_n.png is never overwritten without
--force. Every decision goes in relief.json in the folder: which pictures, from what, when.

Nothing here names a game or makes a look decision: the pictures are the library's; only their relief is read.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
from PIL import Image

PICTURES = (".png", ".jpg", ".jpeg", ".webp")
BETTER = (("_ffnormal", "Filter Forge Normal channel"), ("_mmnormal", "Material Maker normal"))
SKIP_ENDINGS = ("_n", "_ffnormal", "_mmnormal", "_rough", "_height", "_ao",
                "_metal", "_emission", "_orm", "_mixmask", "_decal")      # BUILD 87: the rest of a channel set, and its by-products


def _lum(rgb: np.ndarray) -> np.ndarray:
    return rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114


def blur_wrap(a: np.ndarray, sigma: float) -> np.ndarray:
    """A gaussian blur that wraps round the edges (a tiling picture's left edge meets its right), by FFT."""
    if sigma <= 0:
        return a.copy()
    h, w = a.shape
    fy = np.fft.fftfreq(h)[:, None]
    fx = np.fft.fftfreq(w)[None, :]
    g = np.exp(-2.0 * (np.pi ** 2) * (sigma ** 2) * (fx * fx + fy * fy))
    return np.real(np.fft.ifft2(np.fft.fft2(a) * g)).astype(np.float32)


def normal_from_height(h: np.ndarray, strength: float) -> np.ndarray:
    """Height (tiles) -> an OpenGL-style normal map (x right, y up the picture, z out), 8 bits."""
    dx = (np.roll(h, -1, axis=1) - np.roll(h, 1, axis=1)) * 0.5
    dy = (np.roll(h, -1, axis=0) - np.roll(h, 1, axis=0)) * 0.5          # + = higher further down the picture
    nx, ny, nz = -dx * strength, dy * strength, np.ones_like(h)
    ln = np.sqrt(nx * nx + ny * ny + nz * nz)
    n = np.stack([nx / ln, ny / ln, nz / ln], axis=-1)
    return ((n * 0.5 + 0.5) * 255.0 + 0.5).astype(np.uint8)


def relief_from_picture(rgb: np.ndarray, fine: float = 1.0, broad: float = 0.0, strength: float = 6.0) -> np.ndarray:
    """The proof's recipe: fine grain and gaps (a high-pass of the picture's light and dark), plus a little of its broad
    shapes if asked. A flat picture gives a flat normal map (0.5, 0.5, 1)."""
    lum = _lum(rgb.astype(np.float32) / 255.0)
    h = (blur_wrap(lum, 0.7) - blur_wrap(lum, 10.0)) * fine
    if broad:
        h = h + (blur_wrap(lum, 3.0) - blur_wrap(lum, 40.0)) * broad
    return normal_from_height(h, strength * 20.0)


def wanted(folder: Path) -> list[Path]:
    """The library pictures in a folder that are not themselves relief or another channel."""
    out = []
    for p in sorted(folder.iterdir()):
        if p.is_file() and p.suffix.lower() in PICTURES and not p.stem.endswith(SKIP_ENDINGS):
            out.append(p)
    return out


def make_one(picture: Path, force: bool = False, strength: float = 6.0, broad: float = 0.0) -> dict:
    """<name>_n.png beside one picture. Returns {picture, relief, source, written}."""
    picture = Path(picture)
    dest = picture.with_name(picture.stem + "_n.png")
    for end, what in BETTER:
        better = picture.with_name(picture.stem + end + ".png")
        if better.is_file():
            if force or not dest.is_file() or dest.stat().st_mtime < better.stat().st_mtime:
                Image.open(better).convert("RGB").save(dest)
                return {"picture": picture.name, "relief": dest.name, "source": what, "written": True}
            return {"picture": picture.name, "relief": dest.name, "source": what, "written": False}
    if dest.is_file() and not force:
        return {"picture": picture.name, "relief": dest.name, "source": "kept (already there)", "written": False}
    rgb = np.asarray(Image.open(picture).convert("RGB"))
    Image.fromarray(relief_from_picture(rgb, broad=broad, strength=strength)).save(dest)
    return {"picture": picture.name, "relief": dest.name, "source": "read from the picture (high-pass)", "written": True}


def run(targets: list, force: bool = False, strength: float = 6.0, broad: float = 0.0) -> dict:
    """Relief for folders and pictures; one relief.json a folder records what was decided. Returns a report."""
    done: list[dict] = []
    folders: dict[Path, list[dict]] = {}
    for t in targets:
        t = Path(t)
        pics = wanted(t) if t.is_dir() else ([t] if t.is_file() else [])
        for p in pics:
            r = make_one(p, force=force, strength=strength, broad=broad)
            done.append(r)
            folders.setdefault(p.parent, []).append(r)
    for folder, rows in folders.items():
        led = folder / "relief.json"
        try:
            old = json.loads(led.read_text(encoding="utf-8")) if led.is_file() else {}
        except Exception:  # noqa: BLE001
            old = {}
        pics = old.get("pictures", {}) if isinstance(old.get("pictures"), dict) else {}
        when = time.strftime("%Y-%m-%d %H:%M")
        for r in rows:
            if r["written"] or r["picture"] not in pics:
                pics[r["picture"]] = {"relief": r["relief"], "from": r["source"], "when": when}
        led.write_text(json.dumps({"_what": "Relief (normal maps) for this folder's pictures — forge/threed/relief.py, BUILD 63. "
                                            "'from' says where each came from; a Filter Forge Normal render or a Material Maker "
                                            "normal beside a picture wins over one read from the picture.",
                                   "pictures": pics}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    written = sum(1 for r in done if r["written"])
    return {"ok": True, "pictures": len(done), "written": written, "kept": len(done) - written, "rows": done}
