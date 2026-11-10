"""Make-tileable (Night 4, F7) — because Filter Forge's command-line "seamless" came back with a seam (Night 3B).

Offset the picture by half: its own wrap edges now meet in a cross through the middle, and its outer border is the
picture's middle — which wraps by construction. Then heal the cross:
  * inpaint (a GPU worker): the cross band is repainted on the job's checkpoint (forge/night3/inpaint.py)
  * blend (CPU fallback): the cross band is cross-faded with the un-offset picture, which is continuous there
The wrap seam is measured before and after with Night 3B's score (≈1 or less = seamless); a result that is worse is
refused and the input stays as it was."""
from __future__ import annotations
import json
import logging
import random
from pathlib import Path

import numpy as np
from PIL import Image

from ..jobs.common import Context, save_png, write_prov

log = logging.getLogger("forge.tileable")


class TileableError(RuntimeError):
    pass


def score(img: Image.Image) -> dict:
    from ..night3b.ffdriver import seam_score
    return seam_score(np.asarray(img.convert("RGB"), dtype=np.float64) / 255.0)


def worst(s: dict) -> float:
    return max(float(s["x"]), float(s["y"]))


def quiet_shift(a: np.ndarray) -> tuple[int, int]:
    """(dx, dy): roll amounts that put the picture's new wrap on its quietest column / row pair in the middle half
    (the new wrap IS an interior step of the original — choose an ordinary one, not an unlucky one)."""
    a = a[..., :3].astype(np.float64) if a.ndim == 3 else a.astype(np.float64)[..., None]
    h, w = a.shape[:2]

    def best(steps, n):
        lo, hi = n // 4, 3 * n // 4
        return int(lo + np.argmin(steps[lo:hi]))           # index c: the step between c-1 and c

    col = np.r_[np.inf, np.abs(np.diff(a, axis=1)).mean(axis=(0, 2))]
    row = np.r_[np.inf, np.abs(np.diff(a, axis=0)).mean(axis=(1, 2))]
    return (w - best(col, w)) % w, (h - best(row, h)) % h


def offset(img: Image.Image, dx: int | None = None, dy: int | None = None) -> Image.Image:
    a = np.asarray(img)
    dx = a.shape[1] // 2 if dx is None else dx
    dy = a.shape[0] // 2 if dy is None else dy
    return Image.fromarray(np.roll(np.roll(a, dx, axis=1), dy, axis=0), img.mode)


def cross_weight(w: int, h: int, band: float, cx: float | None = None, cy: float | None = None) -> np.ndarray:
    """1 on the cross through (cx, cy) — where the original's edges now meet — easing to 0 at ± band/2 (smoothstep)."""
    def ramp(n, c):
        c = (n - 1) / 2.0 if c is None else c - 0.5
        x = np.abs(np.arange(n) - c) / max(1.0, band * n / 2.0)
        t = np.clip(1.0 - x, 0.0, 1.0)
        return t * t * (3 - 2 * t)
    return np.maximum(ramp(w, cx)[None, :], ramp(h, cy)[:, None])


def _min_path(err: np.ndarray) -> np.ndarray:
    """Per row, the column of the cheapest top-to-bottom path through err (steps of -1/0/+1) — dynamic programming."""
    h, w = err.shape
    cost = err.copy()
    back = np.zeros((h, w), dtype=np.int8)
    for y in range(1, h):
        prev = cost[y - 1]
        left = np.r_[np.inf, prev[:-1]]
        right = np.r_[prev[1:], np.inf]
        stack = np.vstack([left, prev, right])
        k = np.argmin(stack, axis=0)
        cost[y] += stack[k, np.arange(w)]
        back[y] = k.astype(np.int8) - 1
    path = np.zeros(h, dtype=np.int64)
    path[-1] = int(np.argmin(cost[-1]))
    for y in range(h - 1, 0, -1):
        path[y - 1] = int(np.clip(path[y] + back[y, path[y]], 0, w - 1))
    return path


def _seam_weight(a: np.ndarray, o: np.ndarray, d: int, band: float, mode: str, feather: int | None = None) -> np.ndarray:
    """Weight of `a` for ONE vertical seam at column d (columns d-1 | d of `o`): 1 inside the band, 0 outside. 'cut':
    each band edge follows the minimum-error path between a and o; 'fade': a smoothstep ramp."""
    h, w = a.shape[:2]
    half = max(2, int(band * w / 2))
    lo, hi = max(1, d - half), min(w - 1, d + half)
    if mode != "cut":
        x = np.abs(np.arange(w) - (d - 0.5)) / max(1.0, half)
        t = np.clip(1.0 - x, 0.0, 1.0)
        return np.repeat((t * t * (3 - 2 * t))[None, :], h, axis=0)
    err = ((a[..., :3] - o[..., :3]) ** 2).sum(axis=2)
    pl = _min_path(err[:, lo:d]) + lo if d - lo > 1 else np.full(h, lo)
    pr = _min_path(err[:, d:hi]) + d if hi - d > 1 else np.full(h, hi)
    cols = np.arange(w)[None, :]
    m = ((cols >= pl[:, None]) & (cols < pr[:, None])).astype(np.float64)
    feather = max(3, int(0.012 * w)) if feather is None else feather       # ≈ 12 px at 1024
    if feather > 0:                                        # soften the cut along x only (keeps the band's ends clean)
        k = 2 * feather + 1
        c = np.cumsum(np.pad(m, ((0, 0), (feather + 1, feather)), mode="edge"), axis=1)
        m = (c[:, k:] - c[:, :-k]) / k
    return m


def _heal_axis(a: np.ndarray, d: int, axis: int, band: float, mode: str) -> np.ndarray:
    """Roll `a` by d along axis (the wrap is now seamless that way), then heal the seam that roll made — using `a`
    itself, which is continuous there. Both inputs wrap the same way along the other axis, so nothing reopens."""
    if axis == 0:
        return np.swapaxes(_heal_axis(np.swapaxes(a, 0, 1), d, 1, band, mode), 0, 1)
    o = np.roll(a, d, axis=1)
    m = _seam_weight(a, o, d, band, mode)[..., None]
    return m * a + (1.0 - m) * o


def blend(img: Image.Image, band: float = 0.12, mode: str = "cut") -> Image.Image:
    """Two passes (columns, then rows). mode 'cut': switch along the minimum-error path (sharp — image quilting);
    'fade': a plain cross-fade (softer; ghosts on directional textures like wood grain)."""
    src = img.convert("RGBA") if img.mode in ("RGBA", "LA") else img.convert("RGB")
    a = np.asarray(src, dtype=np.float64)
    dx, dy = quiet_shift(a)
    r = _heal_axis(a, dx, 1, band, mode)
    r = _heal_axis(r, dy, 0, band, mode)
    return Image.fromarray(np.clip(r + 0.5, 0, 255).astype(np.uint8), src.mode)


def heal_inpaint(ctx: Context, job: dict, img: Image.Image, out: Path, band: float, seed: int) -> Image.Image:
    """The blend makes the wrap seamless; the inpaint then repaints the healed bands' INTERIOR only (never the
    outer 48 px, so the wrap the blend made cannot reopen) to remove any blend softness on the job's checkpoint."""
    from ..night3 import inpaint
    healed = blend(img.convert("RGB"), band, "cut")
    a = np.asarray(img.convert("RGB"), dtype=np.float64)
    dx, dy = quiet_shift(a)
    w, h = healed.size
    half_x, half_y = max(2, int(band * w / 2)), max(2, int(band * h / 2))
    m = np.zeros((h, w), dtype=np.uint8)
    m[:, max(0, dx - half_x):dx + half_x] = 255
    m[max(0, dy - half_y):dy + half_y, :] = 255
    edge = 48
    m[:edge, :] = 0; m[-edge:, :] = 0; m[:, :edge] = 0; m[:, -edge:] = 0
    j = {**job, "prompt": job.get("prompt") or "seamless surface texture, the same material continuing",
         "denoise": float(job.get("denoise") or 0.45)}
    full, _prov, _info = inpaint.repaint_masked(ctx, j, healed, Image.fromarray(m, "L"), out, seed, tag="seam")
    return full


def make(img: Image.Image, heal: str = "blend", band: float = 0.12, ctx: Context | None = None, job: dict | None = None,
         out: Path | None = None, seed: int = -1, limit: float = 1.5) -> tuple[Image.Image | None, dict]:
    before = score(img)
    info = {"before": before, "heal": heal, "band": band}
    if worst(before) <= limit:
        info.update(after=before, skipped=f"already tiles (worst {worst(before):.2f} ≤ {limit})")
        return img, info
    if heal == "inpaint":
        seed = seed if seed >= 0 else random.randint(1, 2**31 - 2)
        res = heal_inpaint(ctx, job or {}, img, out, band, seed)
        info["seed"] = seed
    else:
        res = blend(img, band, "fade" if heal == "fade" else "cut")
    after = score(res)
    info["after"] = after
    if worst(after) > worst(before):
        info["refused"] = f"worse: seam {worst(before):.2f} → {worst(after):.2f} — the input is kept as it was"
        return None, info
    return res, info


def tiled(img: Image.Image) -> Image.Image:
    w, h = img.size
    t = Image.new(img.mode, (w * 2, h * 2))
    for dx in (0, w):
        for dy in (0, h):
            t.paste(img, (dx, dy))
    return t


def _pick(src: Path) -> Path:
    if src.is_file():
        return src
    for n in ("tile.png", "texture_final.png", "scene.png", "render.png", "icon.png"):
        if (src / n).exists():
            return src / n
    pngs = sorted(p for p in src.glob("*.png") if not p.name.startswith(("contact", "raw", "seam")))
    if not pngs:
        raise TileableError(f"no picture in {src}")
    return pngs[0]


def run(job: dict, ctx: Context, out: Path) -> dict:
    from ..ops import sheet as sh
    out = Path(out)
    src = _pick(ctx.resolve(job["input"]))
    img = Image.open(src)
    img.load()
    heal = str(job.get("heal") or "auto")
    if heal == "auto":
        heal = "inpaint" if getattr(ctx, "comfy", None) is not None and job.get("checkpoint") else "blend"
    if heal == "inpaint" and getattr(ctx, "comfy", None) is None:
        raise TileableError("heal: inpaint needs the GPU worker — use heal: blend on a CPU worker")
    res, info = make(img, heal, float(job.get("band") or 0.12), ctx, job, out, int(job.get("seed") if job.get("seed") is not None else -1),
                     float(job.get("limit") or 1.5))
    (out / "report.json").write_text(json.dumps({"input": str(src), **info}, indent=1), encoding="utf-8")
    cells = [tiled(img.convert("RGB")).resize(img.size)]
    labels = [f"before, tiled 2×2 · seam x {info['before']['x']} y {info['before']['y']}"]
    if res is not None:
        save_png(res, out / "tile.png")
        save_png(tiled(res), out / "tiled_2x2.png")
        cells.append(tiled(res.convert("RGB")).resize(img.size))
        labels.append(f"after ({info.get('skipped') and 'unchanged' or heal}), tiled 2×2 · seam x {info['after']['x']} y {info['after']['y']}")
    save_png(sh.contact_sheet(cells, labels, cols=2, cell=(512, 512), title=job.get("name")), out / "compare.png")
    lic = []
    sp = src.parent / "prov.json"
    if sp.exists():
        try:
            lic = list(json.loads(sp.read_text(encoding="utf-8")).get("licences") or [])
        except ValueError:
            pass
    if heal == "inpaint" and job.get("checkpoint"):
        lic.append({"role": "checkpoint", "file": Path(str(job["checkpoint"])).name})
    write_prov(out, job, op="tileable", inputs=[str(src)], heal=heal, measured=info, licences=lic,
               outputs=["tile.png", "tiled_2x2.png", "compare.png"] if res is not None else ["compare.png"])
    log.info("tileable %s: %s seam %.2f → %s", src.name, heal, worst(info["before"]),
             f"{worst(info['after']):.2f}" if res is not None else "refused")
    if res is None:
        raise TileableError(info["refused"])
    return {"outputs": ["tile.png", "tiled_2x2.png", "compare.png"], "before": info["before"], "after": info["after"],
            "heal": heal, "skipped": info.get("skipped")}


def tile_channels(paths: dict[str, Path], band: float = 0.12, limit: float = 1.5) -> dict:
    """For filter_forge `tileable: true`: blend EVERY channel with the same geometry so final, normal and height stay in
    register (an inpaint of the final alone would not match its normal map). Writes <file>_tile.png beside each."""
    rep = {}
    for ch, p in paths.items():
        im = Image.open(p)
        im.load()
        if im.mode.startswith("I") or im.mode == "F":          # 16-bit grey (height): scale, don't clip
            a = np.asarray(im, dtype=np.float64)
            im = Image.fromarray(np.clip(a / max(1.0, 65535.0 / 255.0 if a.max() > 255 else 1.0), 0, 255).astype(np.uint8), "L")
        res, info = make(im, "blend", band, limit=limit)            # the cut is computed per channel; see note
        if res is not None:
            dest = Path(p).with_name(Path(p).stem + "_tile.png")
            save_png(res, dest)
            info["file"] = dest.name
        rep[ch] = info
    return rep
