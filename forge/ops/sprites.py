"""Sprite-sheet tools — the CPU half of characters (Night 3, G7).

The game's slot is fixed: 144 × 216 per frame, eight facings in the order S, SW, W, NW, N, NE, E, SE.

    facings_pack(poses, …)   single-pose images (any size; alpha, or a flat key-colour background) → one sheet:
                             background removed, every figure scaled to ONE common height, feet on one baseline,
                             centred on its column; missing facings filled by mirroring their opposite when asked
                             (`mirror=["W→E", "NW→NE", "SW→SE"]`); a report of any frame whose figure touches the cell edge
    anim_preview(sheet, …)   a sheet + its layout → one GIF per facing (frames across) and a turntable GIF of the
                             facings — to judge motion without Godot
    turnaround_split(img)    a 3-view or 8-view turnaround sheet → the separate views, found by the empty columns
                             between figures
"""
from __future__ import annotations
import re
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from .alpha import remove_flat_background

FACINGS = ("S", "SW", "W", "NW", "N", "NE", "E", "SE")
CELL = (144, 216)
OPPOSITE = {"W": "E", "E": "W", "NW": "NE", "NE": "NW", "SW": "SE", "SE": "SW", "S": "S", "N": "N"}


def to_alpha(img: Image.Image, key=None, tolerance: int = 28) -> Image.Image:
    """Keep real alpha; otherwise flood the flat background from the corners away."""
    im = img.convert("RGBA")
    a = np.asarray(im)[..., 3]
    if a.min() < 250:
        return im
    return remove_flat_background(im, key, tolerance)


def bbox(img: Image.Image, thresh: int = 16):
    a = np.asarray(img.convert("RGBA"))[..., 3]
    ys, xs = np.nonzero(a > thresh)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def facing_of(name: str) -> str | None:
    """'sarah_NW.png', 'nw.png', 'sarah-facing-sw' → the facing; longest match first so NW is not read as W."""
    stem = Path(name).stem.upper()
    for f in sorted(FACINGS, key=len, reverse=True):
        if re.search(r"(?:^|[^A-Z])" + f + r"(?:$|[^A-Z])", stem):
            return f
    return None


def parse_mirror(spec) -> list[tuple[str, str]]:
    out = []
    for s in spec or []:
        a, b = re.split(r"\s*(?:→|->|>)\s*", str(s).upper())
        if a not in FACINGS or b not in FACINGS:
            raise ValueError(f"mirror '{s}': use facings from {', '.join(FACINGS)}, e.g. 'W→E'")
        out.append((a, b))
    return out


def facings_pack(poses: dict, cell=CELL, mirror=None, figure_height: float = 0.92, baseline: int = 6,
                 key=None, tolerance: int = 28) -> tuple[Image.Image, dict]:
    """poses: {facing: Image}. Returns (sheet RGBA cell_w*8 × cell_h, report)."""
    cw, ch = int(cell[0]), int(cell[1])
    figs = {}
    for f, im in poses.items():
        f = f.upper()
        if f not in FACINGS:
            raise ValueError(f"unknown facing '{f}' (use {', '.join(FACINGS)})")
        a = to_alpha(im, key, tolerance)
        b = bbox(a)
        if b is None:
            raise ValueError(f"facing {f}: the picture is empty after background removal")
        figs[f] = a.crop(b)
    for src, dst in parse_mirror(mirror):
        if dst not in figs and src in figs:
            figs[dst] = ImageOps.mirror(figs[src])
    missing = [f for f in FACINGS if f not in figs]
    target_h = int(round(ch * float(figure_height)))
    sheet = Image.new("RGBA", (cw * len(FACINGS), ch), (0, 0, 0, 0))
    report = {"cell": [cw, ch], "order": list(FACINGS), "figure_height": target_h, "baseline_y": ch - baseline,
              "missing": missing, "touches_edge": [], "mirrored": [d for s, d in parse_mirror(mirror) if s in poses and d not in poses]}
    for i, f in enumerate(FACINGS):
        if f not in figs:
            continue
        fig = figs[f]
        k = target_h / fig.height
        nw = max(1, int(round(fig.width * k)))
        fig = fig.resize((nw, target_h), Image.LANCZOS)
        x = i * cw + (cw - nw) // 2
        y = ch - baseline - target_h
        if nw > cw:
            report["touches_edge"].append({"facing": f, "why": f"figure {nw}px wide in a {cw}px cell — it will be cut"})
        elif x - i * cw <= 1 or x + nw >= (i + 1) * cw - 1 or y <= 1:
            report["touches_edge"].append({"facing": f, "why": "figure touches the cell edge"})
        tile = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        tile.alpha_composite(fig, (max(0, x - i * cw), max(0, y))) if nw <= cw else tile.alpha_composite(fig.crop(((nw - cw) // 2, 0, (nw - cw) // 2 + cw, target_h)), (0, y))
        sheet.alpha_composite(tile, (i * cw, 0))
    return sheet, report


def load_poses(folder: Path) -> dict:
    """A folder of single poses named by facing (…_S.png, …_NW.png); if no names carry a facing and there are exactly
    eight pictures, they are taken in the game's order by file name."""
    files = sorted(p for p in Path(folder).iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"))
    named = {facing_of(p.name): p for p in files if facing_of(p.name)}
    if named:
        return {f: Image.open(p) for f, p in named.items()}
    if len(files) == 8:
        return {f: Image.open(p) for f, p in zip(FACINGS, files)}
    raise ValueError(f"{folder}: name the pictures by facing (e.g. sarah_S.png, sarah_NW.png) or give exactly eight")


def frames_of(sheet: Image.Image, cell=CELL) -> list[list[Image.Image]]:
    """rows × columns of cells."""
    cw, ch = int(cell[0]), int(cell[1])
    rows = sheet.height // ch
    cols = sheet.width // cw
    return [[sheet.crop((c * cw, r * ch, (c + 1) * cw, (r + 1) * ch)) for c in range(cols)] for r in range(rows)]


def _gif(frames: list[Image.Image], path: Path, fps: float, scale: int = 2, bg=(40, 40, 46)) -> Path:
    out = []
    for f in frames:
        b = Image.new("RGBA", f.size, bg + (255,))
        b.alpha_composite(f.convert("RGBA"))
        out.append(b.convert("RGB").resize((f.width * scale, f.height * scale), Image.NEAREST))
    path.parent.mkdir(parents=True, exist_ok=True)
    out[0].save(path, save_all=True, append_images=out[1:], duration=int(1000 / max(0.5, fps)), loop=0, disposal=2)
    return path


def anim_preview(sheet: Image.Image, out_dir: Path, cell=CELL, layout: str = "auto", fps: float = 8.0,
                 turntable_fps: float = 2.0) -> dict:
    """layout 'rows' = one facing per row, animation frames across; 'facings' = one row of the eight facings (the
    packed sheet) — only a turntable. 'auto' picks by the shape."""
    grid = frames_of(sheet, cell)
    if layout == "auto":
        layout = "facings" if len(grid) == 1 else "rows"
    out_dir = Path(out_dir)
    made = []
    if layout == "rows":
        for r, row in enumerate(grid):
            name = FACINGS[r] if r < len(FACINGS) else f"row{r}"
            made.append(str(_gif(row, out_dir / f"anim_{name}.gif", fps)))
        turn = [row[0] for row in grid]
    else:
        turn = grid[0]
    made.append(str(_gif(turn, out_dir / "turntable.gif", turntable_fps)))
    return {"layout": layout, "rows": len(grid), "cols": len(grid[0]) if grid else 0, "files": made}


def turnaround_split(img: Image.Image, min_gap: int = 6, min_width: int = 12, key=None, tolerance: int = 28) -> list[Image.Image]:
    """The views of a turnaround sheet, left to right, cut at runs of empty columns (≥ min_gap px)."""
    a = to_alpha(img, key, tolerance)
    occ = np.asarray(a)[..., 3].max(axis=0) > 16
    views, start, gap = [], None, 0
    for x, filled in enumerate(list(occ) + [False] * (min_gap + 1)):
        if filled:
            if start is None:
                start = x
            gap = 0
        elif start is not None:
            gap += 1
            if gap >= min_gap:
                end = x - gap + 1
                if end - start >= min_width:
                    v = a.crop((start, 0, end, a.height))
                    b = bbox(v)
                    views.append(v.crop(b) if b else v)
                start, gap = None, 0
    return views
