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


def _channel(p: Path) -> tuple[np.ndarray, str, float]:
    """A channel file as floats 0..255 (h, w, c), with the mode to write it back in and its top value (255, or 65535
    for a 16-bit grey height map — kept whole, not crushed to 8 bits)."""
    im = Image.open(p)
    im.load()
    if im.mode.startswith("I") or im.mode == "F":
        a = np.asarray(im, dtype=np.float64)
        top = 65535.0 if a.max() > 255 else 255.0
        return (a * (255.0 / top))[..., None], ("I;16" if top > 255 else "L"), top
    src = im if im.mode in ("RGB", "RGBA", "L") else im.convert("RGBA" if im.mode in ("LA", "PA") or "transparency" in im.info else "RGB")
    a = np.asarray(src, dtype=np.float64)
    return (a if a.ndim == 3 else a[..., None]), src.mode, 255.0


def _as_image(a: np.ndarray, mode: str, top: float) -> Image.Image:
    if mode == "I;16":
        return Image.fromarray(np.clip(a[..., 0] * (top / 255.0) + 0.5, 0, top).astype(np.uint16))
    b = np.clip(a + 0.5, 0, 255).astype(np.uint8)
    return Image.fromarray(b[..., 0] if mode == "L" else b, mode)


def tile_channels(paths: dict[str, Path], band: float = 0.12, limit: float = 1.5, lead: str | None = None) -> dict:
    """For filter_forge `tileable: true`: heal EVERY channel with ONE geometry — the roll and the two cut paths found
    on the lead picture (`final`, else the first) — so final, normal and height stay on each other. Writes
    <file>_tile.png beside each; a 16-bit height stays 16-bit; a normal map is made unit length again after the blend.

    Until 2026-11-20 this healed each channel by itself (`make` once a channel): each found its own quietest column and
    its own cut, and each decided by itself whether it needed healing at all — so a set came back out of register.
    Its test passed because it gave both channels the same picture. One set, one decision: if the lead already tiles
    every channel is copied as it is; if healing made the lead worse, nothing is written and the set stays as it was."""
    if not paths:
        return {}
    lead = lead if lead in paths else ("final" if "final" in paths else next(iter(paths)))
    chans = {ch: _channel(Path(p)) for ch, p in paths.items()}
    a = chans[lead][0]
    size = a.shape[:2]
    before = {ch: score(_as_image(*c).convert("RGB")) for ch, c in chans.items()}
    rep = {ch: {"before": before[ch], "heal": "blend", "band": band, "lead": lead} for ch in paths}
    if worst(before[lead]) <= limit:
        for ch, p in paths.items():
            dest = Path(p).with_name(Path(p).stem + "_tile.png")
            dest.write_bytes(Path(p).read_bytes())
            rep[ch].update(after=before[ch], file=dest.name,
                           skipped=f"the set already tiles (the lead, {lead}: worst {worst(before[lead]):.2f} <= {limit})")
        return rep
    dx, dy = quiet_shift(a)
    m1 = _seam_weight(a, np.roll(a, dx, axis=1), dx, band, "cut")
    r = m1[..., None] * a + (1.0 - m1[..., None]) * np.roll(a, dx, axis=1)
    rs = np.swapaxes(r, 0, 1)
    m2 = _seam_weight(rs, np.roll(rs, dy, axis=1), dy, band, "cut")
    healed = {}
    for ch, (c, mode, top) in chans.items():
        if c.shape[:2] != size:
            rep[ch]["refused"] = f"its size ({c.shape[1]}x{c.shape[0]}) is not the lead's ({size[1]}x{size[0]}) - left as it was"
            continue
        s1 = m1[..., None] * c + (1.0 - m1[..., None]) * np.roll(c, dx, axis=1)
        t = np.swapaxes(s1, 0, 1)
        s2 = np.swapaxes(m2[..., None] * t + (1.0 - m2[..., None]) * np.roll(t, dy, axis=1), 0, 1)
        if "normal" in ch.lower() and s2.shape[2] >= 3:          # a blend of two unit vectors is shorter than one
            v = s2[..., :3] / 127.5 - 1.0
            v = v / np.maximum(np.sqrt((v * v).sum(axis=-1, keepdims=True)), 1e-9)
            s2 = np.concatenate([(v + 1.0) * 127.5, s2[..., 3:]], axis=-1)
        healed[ch] = _as_image(s2, mode, top)
    after_lead = score(healed[lead].convert("RGB"))
    if worst(after_lead) > worst(before[lead]):
        for ch in paths:
            rep[ch].update(after=after_lead if ch == lead else None,
                           refused=f"worse: the lead's seam {worst(before[lead]):.2f} -> {worst(after_lead):.2f} - the set is kept as it was")
        return rep
    for ch, img in healed.items():
        dest = Path(paths[ch]).with_name(Path(paths[ch]).stem + "_tile.png")
        save_png(img, dest)
        rep[ch].update(after=score(img.convert("RGB")), file=dest.name, shift=[int(dx), int(dy)])
    return rep
