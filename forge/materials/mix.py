"""No repeats, and wear as a layer (BUILD 87, Part 3).

mix    Three seeds of one ground — the same material rendered three times with three variations — laid over each other
       and chosen between, point by point, by a smooth noise that wraps: the result tiles over `repeat` times the
       width, and inside that width the eye finds no tile. Where a height map exists the higher surface wins the edge
       between two seeds, so gravel overlaps gravel instead of fading through it. The mask is written too
       (<name>_mixmask.png: red, green, blue = each seed's share) for an engine that would rather mix live.
decal  One picture of scorch, cracks, grime or rust becomes a layer: colour with see-through, its own normal map and
       roughness, fading to nothing at its edge. Laid over a ground it is that place's wear; lifted, the place is
       mended — the ground underneath was never changed.
ground A place's ground drawn from its plan's rectangles, with or without a list of decals on it, and looked at from a
       standing height under one fixed light: the same ground twice, only the layer different.

All numpy; nothing here uses the graphics card.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

from .. import config as cfgmod
from . import look

CHANNELS = ("colour", "normal", "height", "roughness", "ambient_occlusion", "metallic")


# ------------------------------------------------------------------ noise that wraps
def wrap_noise(size: int, blobs: float, seed: int) -> np.ndarray:
    """A smooth random field, size×size, values spread evenly over 0..1, that tiles: about `blobs` light and dark
    patches across. Made in the frequency domain, so the wrap is exact."""
    rng = np.random.default_rng(int(seed))
    f = np.fft.fftfreq(size) * size
    fx, fy = np.meshgrid(f, f)
    r = np.sqrt(fx * fx + fy * fy)
    env = np.exp(-((r - blobs) ** 2) / (2.0 * max(0.6, blobs * 0.45) ** 2)) * (r > 0)
    spec = (rng.normal(size=(size, size)) + 1j * rng.normal(size=(size, size))) * env
    a = np.real(np.fft.ifft2(spec))
    ranks = np.argsort(np.argsort(a.ravel())).reshape(a.shape)              # an even spread, whatever the field's shape
    return (ranks / float(a.size - 1)).astype(np.float32)


def shares(size: int, n: int, blobs: float, seed: int, softness: float, heights: list[np.ndarray] | None = None) -> np.ndarray:
    """n×size×size: how much of each seed shows at each point (they add up to 1). Higher surface wins a close call."""
    score = np.stack([wrap_noise(size, blobs, seed + 101 * i) for i in range(n)])
    if heights is not None:
        score = score + 0.35 * np.stack([h.astype(np.float32) - 0.5 for h in heights])
    t = max(0.01, float(softness) * 0.25)
    e = np.exp((score - score.max(axis=0, keepdims=True)) / t)
    return (e / e.sum(axis=0, keepdims=True)).astype(np.float32)


def _tile(a: np.ndarray, repeat: int, shift: tuple[int, int]) -> np.ndarray:
    a = np.roll(np.roll(a, shift[0], axis=1), shift[1], axis=0)
    reps = (repeat, repeat) + ((1,) if a.ndim == 3 else ())
    return np.tile(a, reps)


def mix_sets(sets: list[dict], repeat: int = 2, seed: int = 7, blobs: float = 3.0, softness: float = 0.18) -> tuple[dict, np.ndarray]:
    """Mix material sets (as look.load_set gives them, all one size) into one of `repeat` times the width.
    Returns (the mixed set, the shares as an H×W×3 picture)."""
    n = len(sets)
    if n < 2:
        raise ValueError("a mix needs at least two seeds of the material (three is the rule)")
    s = sets[0]["colour"].shape[0]
    if any(m["colour"].shape[:2] != (s, s) for m in sets):
        raise ValueError("the seeds are not all the same size (and square)")
    big = s * int(repeat)
    shifts = [((i * s) // 3, (i * s * 2) // 5) for i in range(n)]              # so two seeds' features never coincide
    heights = [_tile(m["height"].astype(np.float32), repeat, sh) for m, sh in zip(sets, shifts)]
    have_h = any(float(m["height"].std()) > 1e-4 for m in sets)
    w = shares(big, n, float(blobs), int(seed), float(softness), heights if have_h else None)
    out: dict = {"how": {}}
    for ch in CHANNELS:
        acc = None
        for i, (m, sh) in enumerate(zip(sets, shifts)):
            t = _tile(m[ch].astype(np.float32), repeat, sh)
            part = t * (w[i][..., None] if t.ndim == 3 else w[i])
            acc = part if acc is None else acc + part
        if ch == "normal":
            v = acc * 2.0 - 1.0
            v /= np.maximum(np.sqrt((v * v).sum(axis=-1, keepdims=True)), 1e-6)
            acc = v * 0.5 + 0.5
        out[ch] = acc
        out["how"][ch] = f"mixed from {n} seeds"
    mask = np.zeros((big, big, 3), dtype=np.float32)
    for i in range(min(3, n)):
        mask[..., i] = w[i]
    return out, mask


def repeat_score(colour: np.ndarray, period: int) -> float:
    """How loudly a picture repeats at `period` pixels: the correlation of its brightness with itself moved by that
    much (1 = an exact repeat, about 0 = none)."""
    g = look.grey(colour).astype(np.float64)
    a, b = g - g.mean(), np.roll(g, period, axis=1) - g.mean()
    den = float(np.sqrt((a * a).sum() * (b * b).sum()))
    return round(float((a * b).sum() / den), 4) if den > 0 else 0.0


def mix_job(job: dict, ctx, out: Path) -> dict:
    """The material_mix job handler."""
    from ..jobs.common import save_png, write_prov
    out = Path(out)
    root = Path(getattr(ctx, "root", None) or cfgmod.ROOT)
    paths = [p if (p := Path(str(x))).is_absolute() else root / p for x in job["inputs"]]
    for p in paths:
        if not p.is_file():
            raise FileNotFoundError(f"seed picture not found: {p}")
    notes = []
    if len(paths) != 3:
        notes.append(f"{len(paths)} seeds given; the rule is three")
    sets = [look.load_set(p, int(job["size"]) if job.get("size") else None) for p in paths]
    for p, m in zip(paths, sets):
        if str(m["how"].get("normal", "")).startswith("guessed"):
            notes.append(f"{p.name} has no true normal map beside it: its relief is guessed from brightness")
    repeat = int(job.get("repeat") or 2)
    mixed, mask = mix_sets(sets, repeat, int(job.get("seed") or 7), float(job.get("blobs") or 3.0), float(job.get("softness") or 0.18))
    slot = str(job.get("slot_name") or "mix")
    s = sets[0]["colour"].shape[0]
    files = {"colour": f"{slot}.png"}
    look.save(mixed["colour"], out / files["colour"])
    for ch, end, bits in (("normal", "_n", 8), ("height", "_height", 16), ("roughness", "_rough", 8), ("ambient_occlusion", "_ao", 8), ("metallic", "_metal", 8)):
        if ch == "metallic" and float(mixed[ch].max()) <= 0.02:
            continue
        if ch == "height" and float(mixed[ch].std()) < 1e-4:
            continue
        files[ch] = f"{slot}{end}.png"
        look.save(mixed[ch], out / files[ch], bits)
    files["mask"] = f"{slot}_mixmask.png"
    look.save(mask, out / files["mask"])
    measured = {"repeat_of_one_seed": repeat_score(np.tile(sets[0]["colour"], (repeat, repeat, 1)), s),
                "repeat_of_the_mix": repeat_score(mixed["colour"], s), "size": mixed["colour"].shape[0], "repeat": repeat}
    one = look.to_image(np.tile(sets[0]["colour"], (repeat * 2, repeat * 2, 1))).resize((512, 512), Image.LANCZOS)
    mx = look.to_image(np.tile(mixed["colour"], (2, 2, 1))).resize((512, 512), Image.LANCZOS)
    lit = look.to_image(look.lit_plane(mixed, look.LAMP_PATH[1], size=512, tiles=1.0))
    sheet = look.row([one, mx, look.to_image(mask).resize((512, 512)), lit],
                     [f"one seed, tiled (repeats: {measured['repeat_of_one_seed']})", f"the mix, same ground (repeats: {measured['repeat_of_the_mix']})",
                      "who shows where (red, green, blue)", "the mix under the lamp"], cell=384, title=str(job.get("name") or slot))
    save_png(look.stamp(sheet), out / "contact.png")
    write_prov(out, job, op="material_mix", inputs=[str(p) for p in paths], repeat=repeat, measured=measured, notes=notes,
               licences_note="a mix carries the licences of the pictures it was mixed from (their own prov.json)")
    return {"outputs": list(files.values()) + ["contact.png"], "measured": measured, "notes": notes}


# ------------------------------------------------------------------ decals
def edge_fade(h: int, w: int, edge: float) -> np.ndarray:
    """1 in the middle, easing to 0 at every border over `edge` of the side — a decal never ends in a straight line."""
    def ramp(n):
        x = (np.arange(n) + 0.5) / n
        t = np.clip(np.minimum(x, 1.0 - x) / max(edge, 1e-6), 0.0, 1.0)
        return t * t * (3 - 2 * t)
    return np.outer(ramp(h), ramp(w))


def streaks(size: int, seed: int = 3, count: int = 26) -> np.ndarray:
    """Runs: stains that start somewhere near the top and trail downward, thinning (rust under a bolt, soot under a sill)."""
    rng = np.random.default_rng(int(seed))
    a = np.zeros((size, size), dtype=np.float64)
    ys = np.arange(size)[:, None]
    xs = np.arange(size)[None, :]
    for _ in range(int(count)):
        x0, y0 = rng.uniform(0.08, 0.92) * size, rng.uniform(0.02, 0.45) * size
        length, width = rng.uniform(0.2, 0.75) * size, rng.uniform(0.006, 0.03) * size
        down = np.clip((ys - y0) / length, 0.0, 1.0)
        wob = np.sin(ys / size * rng.uniform(4, 11) + rng.uniform(0, 6)) * width * 0.6
        body = np.exp(-((xs - x0 - wob) ** 2) / (2.0 * (width * (1.0 - 0.6 * down)) ** 2))
        a = np.maximum(a, body * (ys >= y0) * (1.0 - down) ** 1.3 * rng.uniform(0.5, 1.0))
    return a


def alpha_of(pic: np.ndarray, how: str, seed: int = 3) -> np.ndarray:
    """How solid the decal is at each point, 0..1."""
    lum = look.grey(pic[..., :3])
    if how == "alpha":
        if pic.shape[2] < 4:
            raise ValueError("alpha_from 'alpha': the picture has no see-through channel")
        return pic[..., 3].copy()
    border = np.concatenate([lum[0], lum[-1], lum[:, 0], lum[:, -1]])
    bg = float(np.median(border))
    if how == "dark":
        lo = float(np.percentile(lum, 1))
        return np.clip((bg - lum) / max(bg - lo, 1e-3), 0.0, 1.0)
    if how == "light":
        hi = float(np.percentile(lum, 99))
        return np.clip((lum - bg) / max(hi - bg, 1e-3), 0.0, 1.0)
    if how == "key":
        key = np.concatenate([pic[0, :, :3], pic[-1, :, :3], pic[:, 0, :3], pic[:, -1, :3]]).mean(axis=0)
        d = np.sqrt(((pic[..., :3] - key) ** 2).sum(axis=2))
        return np.clip(d / max(float(np.percentile(d, 99)), 1e-3), 0.0, 1.0)
    if how == "streaks":
        return streaks(lum.shape[0], seed) if lum.shape[0] == lum.shape[1] else streaks(max(lum.shape), seed)[: lum.shape[0], : lum.shape[1]]
    raise ValueError(f"alpha_from '{how}': one of alpha, dark, light, key, streaks")


def make_decal(pic: np.ndarray, alpha_from: str = "dark", strength: float = 1.0, edge: float = 0.18, tint=None,
               relief: str = "cut", depth: float = 6.0, height: np.ndarray | None = None, normal: np.ndarray | None = None,
               roughness: np.ndarray | None = None, rough_value: float = 0.9, seed: int = 3) -> dict:
    """{"colour" H×W×4, "normal" H×W×4, "roughness" H×W, "how"}: a decal from one picture.
    tint: a colour for the whole decal (soot is black whatever the picture's smoke was).
    relief: 'cut' (the solid parts are cut INTO the ground: cracks, scratches), 'raised' (they lie ON it: ash, mud),
    'picture' (read from the picture's own light and dark), 'flat', or a true `height` / `normal` given."""
    from ..threed import relief as R
    h, w = pic.shape[:2]
    a = np.clip(alpha_of(pic, alpha_from, seed) * float(strength), 0.0, 1.0) * edge_fade(h, w, float(edge))
    rgb = pic[..., :3] if tint is None else np.broadcast_to(np.asarray(tint, dtype=np.float64), (h, w, 3)) * (0.75 + 0.25 * look.grey(pic[..., :3])[..., None])
    how = {"alpha": alpha_from, "colour": "the picture's own" if tint is None else "one colour (tint), shaded by the picture"}
    if normal is not None:
        n = normal[..., :3]
        how["normal"] = "a true normal map given"
    else:
        if height is not None:
            hh = look.grey(height)
            how["normal"] = "from a true height map given"
        elif relief in ("cut", "raised"):
            hh = R.blur_wrap((a if relief == "raised" else -a).astype(np.float32), 1.2)
            how["normal"] = f"from the decal's own shape ({relief})"
        elif relief == "picture":
            lum = look.grey(pic[..., :3]).astype(np.float32)
            hh = R.blur_wrap(lum, 0.7) - R.blur_wrap(lum, 10.0)
            how["normal"] = "read from the picture's light and dark"
        else:
            hh = np.zeros((h, w), dtype=np.float32)
            how["normal"] = "flat"
        n = R.normal_from_height(np.asarray(hh, dtype=np.float32), float(depth)).astype(np.float64) / 255.0
    flat = np.array([0.5, 0.5, 1.0])
    reach = np.clip(R.blur_wrap(a.astype(np.float32), 2.0) * 2.5, 0.0, 1.0).astype(np.float64)   # a little wider than the colour:
    n = flat + (n - flat) * reach[..., None]                                 # both lips of a crack catch the light
    r = look.grey(roughness) if roughness is not None else np.full((h, w), float(rough_value))
    return {"colour": np.concatenate([np.clip(rgb, 0, 1), a[..., None]], axis=2),
            "normal": np.concatenate([n, reach[..., None]], axis=2), "roughness": r, "how": how}


def decal_job(job: dict, ctx, out: Path) -> dict:
    """The material_decal job handler."""
    from ..jobs.common import save_png, write_prov
    out = Path(out)
    root = Path(getattr(ctx, "root", None) or cfgmod.ROOT)

    def res(x):
        p = Path(str(x))
        return p if p.is_absolute() else root / p
    src = res(job["input"])
    if not src.is_file():
        raise FileNotFoundError(f"decal picture not found: {src}")
    size = int(job["size"]) if job.get("size") else None
    pic = look.load(src, size)
    if pic.shape[2] == 1:
        pic = np.repeat(pic, 3, axis=2)
    extra = {k: look.load(res(job[k]), pic.shape[0]) for k in ("height", "normal", "roughness") if job.get(k)}
    d = make_decal(pic, str(job.get("alpha_from") or "dark"), float(job.get("strength") or 1.0), float(job.get("edge") or 0.18),
                   job.get("tint"), str(job.get("relief") or "cut"), float(job.get("depth") or 6.0), extra.get("height"),
                   extra.get("normal"), extra.get("roughness"), float(job.get("rough_value") or 0.9), int(job.get("seed") or 3))
    slot = str(job.get("slot_name") or "wear")
    look.save(d["colour"], out / f"{slot}_decal.png")
    look.save(d["normal"], out / f"{slot}_decal_n.png")
    look.save(d["roughness"], out / f"{slot}_decal_rough.png")
    cover = float((d["colour"][..., 3] > 0.05).mean())
    info = {"from": src.name, "how": d["how"], "covers": round(cover, 3), "size": list(pic.shape[:2])}
    (out / "decal.json").write_text(json.dumps(info, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    s = pic.shape[0]
    ground = flat_ground(s, (0.34, 0.33, 0.32))
    worn = lay(ground, [{"decal": d, "at": (0.5, 0.5), "size": 1.0}])
    chk = _checker(s)
    alone = chk * (1 - d["colour"][..., 3:4]) + d["colour"][..., :3] * d["colour"][..., 3:4]
    sheet = look.row([look.to_image(alone), look.to_image(d["normal"][..., :3]), look.to_image(look.lit_plane(ground, look.LAMP_PATH[1], size=384)),
                      look.to_image(look.lit_plane(worn, look.LAMP_PATH[1], size=384))],
                     ["the decal alone", "its normal map", "a plain ground under the lamp", "the same ground wearing it"], cell=320,
                     title=f"{job.get('name') or slot}: covers {cover:.0%} of its square")
    save_png(look.stamp(sheet), out / "contact.png")
    notes = [] if cover > 0.005 else ["the decal is almost empty: try another alpha_from"]
    write_prov(out, job, op="material_decal", inputs=[str(src)], how=d["how"], covers=round(cover, 3), notes=notes,
               licences_note="a decal carries the licence of the picture it was cut from (its own prov.json)")
    return {"outputs": [f"{slot}_decal.png", f"{slot}_decal_n.png", f"{slot}_decal_rough.png", "decal.json", "contact.png"],
            "covers": round(cover, 3), "how": d["how"], "notes": notes}


def _checker(s: int, cell: int = 32) -> np.ndarray:
    ys, xs = np.mgrid[0:s, 0:s]
    c = (((ys // cell) + (xs // cell)) % 2) * 0.12 + 0.28
    return np.repeat(c[..., None], 3, axis=2)


def flat_ground(s: int, rgb=(0.5, 0.5, 0.5), rough: float = 0.85) -> dict:
    n = np.zeros((s, s, 3))
    n[...] = (0.5, 0.5, 1.0)
    return {"colour": np.broadcast_to(np.asarray(rgb, dtype=np.float64), (s, s, 3)).copy(), "normal": n, "height": np.full((s, s), 0.5),
            "roughness": np.full((s, s), rough), "ambient_occlusion": np.ones((s, s)), "metallic": np.zeros((s, s)), "how": {}}


def load_decal(colour_file: Path) -> dict:
    """A decal written by decal_job, from its <name>_decal.png."""
    colour_file = Path(colour_file)
    c = look.load(colour_file)
    stem = colour_file.stem
    n = colour_file.with_name(stem + "_n.png")
    r = colour_file.with_name(stem + "_rough.png")
    return {"colour": c, "normal": look.load(n) if n.is_file() else None,
            "roughness": look.grey(look.load(r)) if r.is_file() else np.full(c.shape[:2], 0.9)}


def _place(img: np.ndarray, px: int, turn: float) -> np.ndarray:
    im = look.to_image(img).resize((px, px), Image.LANCZOS)
    if turn:
        im = im.rotate(float(turn), resample=Image.BICUBIC, expand=False)
    a = np.asarray(im).astype(np.float64) / 255.0
    return a if a.ndim == 3 else a[..., None]


def lay(ground: dict, decals: list[dict]) -> dict:
    """The ground wearing its decals. Each: {"decal": a decal dict, "at": (x, y) of its centre and "size": its side, both
    in units of the ground's width, "turn": degrees, "opacity": 0..1}. The ground itself is not changed."""
    out = {k: (v.copy() if isinstance(v, np.ndarray) else dict(v)) for k, v in ground.items()}
    H, W = out["colour"].shape[:2]
    for d in decals:
        dec = d["decal"]
        px = max(4, int(round(float(d.get("size", 1.0)) * W)))
        turn = float(d.get("turn", 0.0))
        col = _place(dec["colour"], px, turn)
        nor = _place(dec["normal"], px, turn) if dec.get("normal") is not None else None
        rgh = _place(dec["roughness"], px, turn)[..., 0]
        x0 = int(round(float(d["at"][0]) * W - px / 2))
        y0 = int(round(float(d["at"][1]) * H - px / 2))
        ys, xs = np.arange(y0, y0 + px), np.arange(x0, x0 + px)
        ok_y, ok_x = (ys >= 0) & (ys < H), (xs >= 0) & (xs < W)
        if not ok_y.any() or not ok_x.any():
            continue
        gy, gx = ys[ok_y], xs[ok_x]
        sub = np.ix_(ok_y, ok_x)
        a = col[..., 3][sub] * float(d.get("opacity", 1.0))
        gi = np.ix_(gy, gx)
        out["colour"][gi] = out["colour"][gi] * (1 - a[..., None]) + col[..., :3][sub] * a[..., None]
        out["roughness"][gi] = out["roughness"][gi] * (1 - a) + rgh[sub] * a
        if nor is not None:
            na = nor[..., 3][sub] * float(d.get("opacity", 1.0)) if nor.shape[2] == 4 else a
            dn = nor[..., :3][sub] * 2 - 1
            if turn:                                              # the picture was turned, so its slopes must be too
                t = math.radians(turn)
                dx, dy = dn[..., 0] * math.cos(t) + dn[..., 1] * math.sin(t), -dn[..., 0] * math.sin(t) + dn[..., 1] * math.cos(t)
                dn = np.stack([dx, dy, dn[..., 2]], axis=-1)
            g = out["normal"][gi] * 2 - 1
            v = g + (dn - np.array([0.0, 0.0, 1.0])) * na[..., None]       # add the decal's tilt to the ground's own
            v /= np.maximum(np.sqrt((v * v).sum(axis=-1, keepdims=True)), 1e-6)
            out["normal"][gi] = v * 0.5 + 0.5
    return out


# ------------------------------------------------------------------ a place's ground, with and without its layer
def ground_from_plan(plan: dict, materials: dict[str, dict], window: tuple[float, float, float, float], px_per_m: float = 48.0,
                     tile_m: dict[str, float] | None = None, default_tile_m: float = 3.0) -> tuple[dict, list[str]]:
    """Draw a place plan's ground (its `background`, then its `ground` rectangles in order) for a window (x, y, w, h in
    metres). `materials` {plan word: a material set}; a word with no set is drawn mid-grey and named in the notes."""
    x0, y0, ww, wh = window
    W, H = int(round(ww * px_per_m)), int(round(wh * px_per_m))
    out = flat_ground(1, (0.4, 0.4, 0.4))
    out = {k: (np.repeat(np.repeat(v, H, axis=0), W, axis=1) if isinstance(v, np.ndarray) else v) for k, v in out.items()}
    notes: list[str] = []
    ys, xs = np.mgrid[0:H, 0:W]
    wx, wy = x0 + (xs + 0.5) / px_per_m, y0 + (ys + 0.5) / px_per_m

    def fill(mat: str, sel: np.ndarray) -> None:
        m = materials.get(mat)
        if m is None:
            if f"no material for '{mat}'" not in " ".join(notes):
                notes.append(f"no material for '{mat}': drawn mid-grey")
            out["colour"][sel] = (0.42, 0.42, 0.42)
            return
        t = float((tile_m or {}).get(mat, default_tile_m))
        s = m["colour"].shape[0]
        u = ((wx[sel] / t) % 1.0 * s).astype(int) % s
        v = ((wy[sel] / t) % 1.0 * s).astype(int) % s
        for ch in CHANNELS:
            out[ch][sel] = m[ch][v, u]
    fill(str(plan.get("background") or "grass"), np.ones((H, W), dtype=bool))
    for g in plan.get("ground") or []:
        if "rect" in g:
            rx, ry, rw, rh = (float(v) for v in g["rect"])
            sel = (wx >= rx) & (wx < rx + rw) & (wy >= ry) & (wy < ry + rh)
        elif "ellipse" in g:                                       # [cx, cy, rx, ry], as the place plans write it
            cx, cy, ex, ey = (float(v) for v in g["ellipse"])
            sel = ((wx - cx) / max(ex, 1e-6)) ** 2 + ((wy - cy) / max(ey, 1e-6)) ** 2 <= 1.0
        elif "poly" in g:
            sel = _in_poly(wx, wy, [(float(a), float(b)) for a, b in g["poly"]])
        else:
            continue
        if sel.any():
            fill(str(g.get("mat")), sel)
    return out, notes


def _in_poly(x: np.ndarray, y: np.ndarray, pts: list[tuple[float, float]]) -> np.ndarray:
    """Which points are inside a polygon (even-odd rule)."""
    inside = np.zeros(x.shape, dtype=bool)
    n = len(pts)
    for i in range(n):
        (x1, y1), (x2, y2) = pts[i], pts[(i + 1) % n]
        if y1 == y2:
            continue
        cross = ((y1 > y) != (y2 > y)) & (x < (x2 - x1) * (y - y1) / (y2 - y1) + x1)
        inside ^= cross
    return inside


def lay_in_metres(ground: dict, window, decals: list[dict], library: dict[str, dict]) -> dict:
    """Decals placed in the plan's metres: [{"decal": name, "at": [x, y], "size_m": side, "turn", "opacity"}]."""
    x0, y0, ww, _wh = window
    H, W = ground["colour"].shape[:2]
    placed = []
    for d in decals:
        dec = library.get(str(d.get("decal")))
        if dec is None:
            continue
        placed.append({"decal": dec, "at": ((float(d["at"][0]) - x0) / ww, (float(d["at"][1]) - y0) / ww * W / H),
                       "size": float(d.get("size_m", 2.0)) / ww, "turn": float(d.get("turn", 0.0)), "opacity": float(d.get("opacity", 1.0))})
    return lay(ground, placed)


def ground_view(ground: dict, window, stand: tuple[float, float], eye_m: float, looks_at: tuple[float, float],
                size: tuple[int, int] = (1280, 720), fov_deg: float = 58.0, sun=(-0.45, -0.35, 0.82), sky=(0.60, 0.66, 0.74)) -> np.ndarray:
    """The ground seen by someone standing on it: a camera at `stand` (metres, plan coordinates), `eye_m` up, looking
    at `looks_at` on the ground. One fixed sun; beyond the window and above the horizon is plain sky. H×W×3."""
    x0, y0, ww, wh = window
    GH, GW = ground["colour"].shape[:2]
    ppm = GW / ww
    W, H = size
    cam = np.array([stand[0], stand[1], eye_m], dtype=np.float64)
    fwd = np.array([looks_at[0], looks_at[1], 0.0]) - cam
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, np.array([0.0, 0.0, 1.0]))
    right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    f = 0.5 * W / math.tan(math.radians(fov_deg) / 2)
    ys, xs = np.mgrid[0:H, 0:W].astype(np.float64)
    d = fwd[None, None, :] * f + right[None, None, :] * (xs - W / 2 + 0.5)[..., None] - up[None, None, :] * (ys - H / 2 + 0.5)[..., None]
    d /= np.linalg.norm(d, axis=-1, keepdims=True)
    hit = d[..., 2] < -1e-4
    t = np.where(hit, -cam[2] / np.where(hit, d[..., 2], -1.0), 0.0)
    gx, gy = cam[0] + d[..., 0] * t, cam[1] + d[..., 1] * t
    u, v = (gx - x0) * ppm, (gy - y0) * ppm
    inside = hit & (u >= 0) & (u < GW - 1) & (v >= 0) & (v < GH - 1)
    # far ground covers many texels a pixel: read it from a smaller copy (three levels), or it would sparkle
    foot = np.where(inside, t / f * ppm / np.maximum(-d[..., 2], 0.02), 1.0)
    level = np.clip(np.floor(np.log2(np.maximum(foot, 1.0))), 0, 3).astype(int)
    img = np.zeros((H, W, 3))
    img[...] = sky
    Lv = np.asarray(sun, dtype=np.float64)
    Lv /= np.linalg.norm(Lv)
    for lv in range(4):
        sel = inside & (level == lv)
        if not sel.any():
            continue
        k = 2 ** lv
        m = {}
        for ch in CHANNELS:
            a = ground[ch]
            if k > 1:
                hh, ww2 = (a.shape[0] // k) * k, (a.shape[1] // k) * k
                a = a[:hh, :ww2].reshape(hh // k, k, ww2 // k, k, *a.shape[2:]).mean(axis=(1, 3))
            m[ch] = a
        vi = np.clip((v[sel] / k).astype(int), 0, m["colour"].shape[0] - 1)
        ui = np.clip((u[sel] / k).astype(int), 0, m["colour"].shape[1] - 1)
        n = m["normal"][vi, ui] * 2 - 1
        nrm = np.stack([n[:, 0], -n[:, 1], np.maximum(n[:, 2], 0.05)], axis=-1)            # picture y runs down = plan +y
        nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
        V = -d[sel]
        L = np.broadcast_to(Lv * np.array([1.0, 1.0, 1.0]), nrm.shape)
        col = look._shade(m["colour"][vi, ui][None], nrm[None], m["roughness"][vi, ui][None], m["ambient_occlusion"][vi, ui][None],
                          m["metallic"][vi, ui][None], L[None], V[None], np.full((1, nrm.shape[0]), 1.15), ambient=0.22,
                          warm=(1.0, 0.97, 0.92))[0]
        fog = np.clip(t[sel] / 160.0, 0.0, 0.55)[..., None]
        img[sel] = col * (1 - fog) + np.asarray(sky) * fog
    return img
