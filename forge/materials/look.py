"""What a reviewer looks at (BUILD 87): a material's channel files, and pictures of it under a light.

The channel files of a material sit beside its colour picture <name>.png, under the endings the texture library
already uses (forge/threed/relief.py): <name>_n.png (the normal map in use, OpenGL: x right, y up the picture, z out),
<name>_ffnormal.png / <name>_mmnormal.png (a true normal from Filter Forge / Material Maker, which relief.py puts in
use), <name>_height.png (white = high), <name>_rough.png, <name>_ao.png, <name>_metal.png, <name>_emission.png.

The pictures here are drawn in numpy — a lamp carried over a flat piece of the surface, and a ball wrapped in it — so
a channel set can be judged on any computer, with no engine and no graphics card. They are a reviewer's preview: every
one is stamped as such, because the game's own light and camera decide the game's look, not these.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ENDINGS = {"normal": "_n", "height": "_height", "roughness": "_rough", "ambient_occlusion": "_ao",
           "metallic": "_metal", "emission": "_emission"}
TRUE_NORMALS = (("_ffnormal", "Filter Forge's Normal channel"), ("_mmnormal", "Material Maker's normal"))
ALL_ENDINGS = tuple(ENDINGS.values()) + tuple(e for e, _ in TRUE_NORMALS) + ("_orm", "_mixmask", "_decal", "_decal_n", "_decal_rough")
PREVIEW_STAMP = "forge preview (numpy lamp) - not the game's look"


# ------------------------------------------------------------------ files
def load(path: Path, size: int | None = None) -> np.ndarray:
    """A picture as floats 0..1, H×W×C (C = 1, 3 or 4). 16-bit grey is read exactly."""
    im = Image.open(path)
    im.load()
    if im.mode in ("I;16", "I;16B", "I", "F"):
        a = np.asarray(im).astype(np.float64)
        a = a / (65535.0 if a.max() > 255 else 255.0)
        if size and a.shape[0] != size:
            a = np.asarray(Image.fromarray((a * 65535.0).astype(np.uint16)).resize((size, size), Image.BILINEAR)).astype(np.float64) / 65535.0
        return a[..., None]
    if im.mode not in ("RGB", "RGBA", "L"):
        im = im.convert("RGBA" if "A" in im.mode or im.mode == "P" else "RGB")
    if size and im.size != (size, size):
        im = im.resize((size, size), Image.LANCZOS)
    a = np.asarray(im).astype(np.float64) / 255.0
    return a[..., None] if a.ndim == 2 else a


def grey(a: np.ndarray) -> np.ndarray:
    """H×W from any picture array (the mean of its colour channels)."""
    if a.ndim == 2:
        return a
    return a[..., 0] if a.shape[2] == 1 else a[..., :3].mean(axis=2)


def to_image(a: np.ndarray) -> Image.Image:
    a = np.clip(a, 0.0, 1.0)
    if a.ndim == 3 and a.shape[2] == 1:
        a = a[..., 0]
    u = (a * 255.0 + 0.5).astype(np.uint8)
    return Image.fromarray(u, "L" if u.ndim == 2 else ("RGBA" if u.shape[2] == 4 else "RGB"))


def save(a: np.ndarray, path: Path, bits: int = 8) -> Path:
    """Write a picture array. bits=16 only for one-channel pictures (height), where 8 bits would show steps."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    g = a[..., 0] if (a.ndim == 3 and a.shape[2] == 1) else a
    if bits == 16 and g.ndim == 2:
        Image.fromarray((np.clip(g, 0, 1) * 65535.0 + 0.5).astype(np.uint16)).save(path)
    else:
        to_image(a).save(path)
    return path


def find_set(colour: Path) -> dict[str, Path]:
    """The channel files beside a colour picture: {"colour", "normal", "height", "roughness", "ambient_occlusion", …}.
    A true normal (Filter Forge / Material Maker) wins over <name>_n.png; `normal_from` says which was found."""
    colour = Path(colour)
    out: dict = {"colour": colour}
    for end, what in TRUE_NORMALS:
        p = colour.with_name(colour.stem + end + ".png")
        if p.is_file():
            out["normal"], out["normal_from"] = p, what
            break
    else:
        p = colour.with_name(colour.stem + "_n.png")
        if p.is_file():
            out["normal"], out["normal_from"] = p, "the normal map in use (<name>_n.png)"
    for ch, end in ENDINGS.items():
        if ch == "normal":
            continue
        p = colour.with_name(colour.stem + end + ".png")
        if p.is_file():
            out[ch] = p
    return out


def guessed_normal(rgb: np.ndarray) -> np.ndarray:
    """The fallback the library used before true channels: relief read from the picture's own light and dark."""
    from ..threed import relief
    u = (np.clip(rgb[..., :3], 0, 1) * 255.0 + 0.5).astype(np.uint8)
    return relief.relief_from_picture(u).astype(np.float64) / 255.0


def load_set(colour: Path, size: int | None = None, guess: bool = True) -> dict:
    """Arrays for every channel of a material, and `how` — where each came from. A missing channel is filled so the
    lamp pictures can still be drawn: normal guessed from brightness, roughness 0.85, occlusion 1, height flat."""
    files = find_set(colour)
    c = load(files["colour"], size)
    h, w = c.shape[:2]
    out = {"colour": c[..., :3] if c.shape[2] >= 3 else np.repeat(c, 3, axis=2), "how": {}}
    if c.shape[2] == 4:
        out["alpha"] = c[..., 3]
    if "normal" in files:
        out["normal"] = load(files["normal"], size)[..., :3]
        out["how"]["normal"] = files["normal_from"]
    elif guess:
        out["normal"] = guessed_normal(out["colour"])
        out["how"]["normal"] = "guessed from the picture's brightness (no true normal)"
    for ch, fill in (("height", 0.5), ("roughness", 0.85), ("ambient_occlusion", 1.0), ("metallic", 0.0)):
        if ch in files:
            out[ch] = grey(load(files[ch], size))
            out["how"][ch] = files[ch].name
        else:
            out[ch] = np.full((h, w), fill)
            out["how"][ch] = f"none (drawn as {fill})"
    return out


# ------------------------------------------------------------------ light
def _lin(c: np.ndarray) -> np.ndarray:
    return np.power(np.clip(c, 0.0, 1.0), 2.2)


def _srgb(c: np.ndarray) -> np.ndarray:
    return np.power(np.clip(c, 0.0, 1.0), 1.0 / 2.2)


def _unit(v: np.ndarray) -> np.ndarray:
    return v / np.maximum(np.sqrt((v * v).sum(axis=-1, keepdims=True)), 1e-9)


def _normals(n: np.ndarray) -> np.ndarray:
    """A normal-map picture → unit vectors in picture space (x right, y DOWN the picture, z out of it)."""
    v = n[..., :3] * 2.0 - 1.0
    v = np.stack([v[..., 0], -v[..., 1], np.maximum(v[..., 2], 0.05)], axis=-1)
    return _unit(v)


def _shade(albedo, nrm, rough, ao, metal, L, V, power, ambient=0.07, warm=(1.0, 0.86, 0.66)):
    """Lambert + a Blinn highlight whose width follows roughness. All arrays H×W(×3); L, V unit vectors per pixel."""
    ndl = np.clip((nrm * L).sum(axis=-1), 0.0, 1.0)
    H = _unit(L + V)
    ndh = np.clip((nrm * H).sum(axis=-1), 0.0, 1.0)
    r = np.clip(rough, 0.04, 1.0)
    shin = np.clip(2.0 / np.maximum(r ** 4, 1e-4) - 2.0, 1.0, 2000.0)
    spec = np.power(ndh, shin) * (shin + 8.0) / 25.0 * (1.0 - r) ** 2 * (ndl > 0)
    lin = _lin(albedo)
    f0 = 0.04 * (1.0 - metal[..., None]) + lin * metal[..., None]
    light = np.asarray(warm)[None, None, :] * power[..., None]
    col = lin * (1.0 - metal[..., None]) * (ambient * ao[..., None] + ndl[..., None] * light) + f0 * spec[..., None] * light
    return _srgb(1.0 - np.exp(-col * 1.9))            # a soft shoulder: dark asphalt is seen, whitewash under the lamp is not burnt out


def _fit(m: dict, size: int, tiles: float = 1.0) -> dict:
    """Every channel resized to size×size (the surface repeated `tiles` times first, for a wider piece of floor)."""
    out = {}
    for k in ("colour", "normal", "height", "roughness", "ambient_occlusion", "metallic"):
        a = m[k]
        img = to_image(a)
        if tiles and tiles != 1.0:
            n = int(np.ceil(tiles))
            big = Image.new(img.mode, (img.width * n, img.height * n))
            for i in range(n):
                for j in range(n):
                    big.paste(img, (i * img.width, j * img.height))
            img = big.crop((0, 0, int(img.width * tiles), int(img.height * tiles)))
        img = img.resize((size, size), Image.LANCZOS)
        a2 = np.asarray(img).astype(np.float64) / 255.0
        out[k] = a2
    return out


def lit_plane(m: dict, lamp: tuple[float, float] = (0.3, 0.35), height: float = 0.22, size: int = 320,
              tiles: float = 1.0, power: float = 2.4) -> np.ndarray:
    """A flat piece of the surface seen from above, lit by one small warm lamp held `height` above it at `lamp`
    (both in units of the picture's side). The lamp is close, so the light rakes: relief shows as it would by a candle."""
    f = _fit(m, size, tiles)
    ys, xs = np.mgrid[0:size, 0:size].astype(np.float64)
    px, py = (xs + 0.5) / size, (ys + 0.5) / size
    to = np.stack([lamp[0] - px, lamp[1] - py, np.full_like(px, height)], axis=-1)
    d2 = (to * to).sum(axis=-1)
    L = _unit(to)
    V = np.zeros_like(L)
    V[..., 2] = 1.0
    fall = power * (height * height) / np.maximum(d2, 1e-6)            # 1 right under the lamp, falling with distance
    return _shade(f["colour"], _normals(f["normal"]), f["roughness"], f["ambient_occlusion"], f["metallic"], L, V,
                  np.clip(fall, 0, 4.0))


def lit_ball(m: dict, size: int = 320, light: tuple[float, float, float] = (-0.55, -0.6, 0.58), turns: float = 2.0) -> np.ndarray:
    """A ball wrapped in the surface (the picture goes round it `turns` times), one light from the upper left.
    Outside the ball the picture is dark, with its own see-through channel (RGBA)."""
    ys, xs = np.mgrid[0:size, 0:size].astype(np.float64)
    x = (xs + 0.5) / size * 2.0 - 1.0
    y = (ys + 0.5) / size * 2.0 - 1.0
    rr = x * x + y * y
    inside = rr < 0.97 * 0.97
    z = np.sqrt(np.clip(0.97 * 0.97 - rr, 0.0, None))
    N = _unit(np.stack([x, y, z], axis=-1))
    lon = np.arctan2(N[..., 0], N[..., 2]) / (2 * np.pi) + 0.5
    lat = np.arcsin(np.clip(N[..., 1], -1, 1)) / np.pi + 0.5
    u, v = (lon * turns * 2.0) % 1.0, (lat * turns) % 1.0

    def samp(a):
        hh, ww = a.shape[:2]
        return a[np.clip((v * hh).astype(int), 0, hh - 1), np.clip((u * ww).astype(int), 0, ww - 1)]
    T = _unit(np.stack([N[..., 2], np.zeros_like(x), -N[..., 0]], axis=-1) + 1e-9)       # along longitude
    B = np.cross(N, T)                                                                    # down the picture
    tn = _normals(samp(m["normal"]))
    nrm = _unit(T * tn[..., 0:1] + B * tn[..., 1:2] + N * tn[..., 2:3])
    Lv = np.asarray(light, dtype=np.float64)
    Lv = Lv / np.linalg.norm(Lv)
    L = np.broadcast_to(Lv, N.shape)
    V = np.zeros_like(N)
    V[..., 2] = 1.0
    col = _shade(samp(m["colour"]), nrm, samp(m["roughness"]), samp(m["ambient_occlusion"]), samp(m["metallic"]), L, V,
                 np.full(x.shape, 1.25), ambient=0.10, warm=(1.0, 0.95, 0.88))
    out = np.zeros((size, size, 4))
    out[..., :3] = np.where(inside[..., None], col, 0.05)
    out[..., 3] = 1.0
    return out[..., :3]


# ------------------------------------------------------------------ sheets
def _font(size: int):
    from ..ops.sheet import _font as f
    return f(size)


def _ascii(t: str) -> str:
    from ..ops.sheet import _ascii as f
    return f(t)


def stamp(img: Image.Image, text: str = PREVIEW_STAMP) -> Image.Image:
    """A dark band under a picture saying what it is (never left off a preview)."""
    img = img.convert("RGB")
    band = 20
    out = Image.new("RGB", (img.width, img.height + band), (18, 18, 22))
    out.paste(img, (0, 0))
    ImageDraw.Draw(out).text((6, img.height + 3), _ascii(text), font=_font(12), fill=(200, 190, 160))
    return out


def row(images: list[Image.Image], labels: list[str], cell: int = 256, title: str | None = None) -> Image.Image:
    """One labelled row of square pictures."""
    pad, lab = 6, 18
    th = 24 if title else 0
    W = pad + len(images) * (cell + pad)
    out = Image.new("RGB", (W, th + pad + cell + lab + pad), (24, 24, 28))
    dr = ImageDraw.Draw(out)
    if title:
        dr.text((pad, 4), _ascii(title), font=_font(15), fill=(235, 230, 215))
    for i, (im, la) in enumerate(zip(images, labels)):
        x = pad + i * (cell + pad)
        out.paste(im.convert("RGB").resize((cell, cell), Image.LANCZOS), (x, th + pad))
        dr.text((x + 2, th + pad + cell + 2), _ascii(la)[: max(8, cell // 7)], font=_font(12), fill=(205, 205, 210))
    return out


def stack(rows: list[Image.Image], bg=(24, 24, 28)) -> Image.Image:
    W = max(r.width for r in rows)
    out = Image.new("RGB", (W, sum(r.height for r in rows)), bg)
    y = 0
    for r in rows:
        out.paste(r, (0, y))
        y += r.height
    return out


LAMP_PATH = ((0.12, 0.22), (0.38, 0.62), (0.64, 0.30), (0.88, 0.74))


def channel_tiles(m: dict) -> tuple[list[Image.Image], list[str]]:
    """Every channel as a picture, with where it came from."""
    how = m.get("how", {})
    ims = [to_image(m["colour"]), to_image(m["normal"]), to_image(m["height"]), to_image(m["roughness"]), to_image(m["ambient_occlusion"])]
    labs = ["colour", "normal: " + _short(how.get("normal", "")), "height: " + _short(how.get("height", "")),
            "roughness: " + _short(how.get("roughness", "")), "occlusion: " + _short(how.get("ambient_occlusion", ""))]
    if float(np.max(m["metallic"])) > 0.02:
        ims.append(to_image(m["metallic"]))
        labs.append("metal")
    return ims, labs


def _short(s: str) -> str:
    s = str(s)
    for a, b in (("guessed from the picture's brightness (no true normal)", "GUESSED"), ("Filter Forge's Normal channel", "Filter Forge"),
                 ("Material Maker's normal", "Material Maker"), ("the normal map in use (<name>_n.png)", "in use")):
        s = s.replace(a, b)
    return "none" if s.startswith("none") else s


def material_row(m: dict, name: str, cell: int = 224, note: str = "") -> Image.Image:
    """One material on a sheet: its channels, a piece of it under the lamp, and the ball."""
    ims, labs = channel_tiles(m)
    ims.append(to_image(lit_plane(m, LAMP_PATH[1], size=cell, tiles=1.0)))
    labs.append("under the lamp")
    ims.append(to_image(lit_ball(m, size=cell)))
    labs.append("ball")
    return row(ims, labs, cell=cell, title=name + (f"   {note}" if note else ""))


def moving_light(before: dict | None, after: dict, name: str, cell: int = 288, tiles: float = 1.0,
                 labels: tuple[str, str] = ("before", "after")) -> Image.Image:
    """The same piece of surface with the lamp carried across it: `before` on the top row, `after` under it."""
    rows = []
    for m, lab in ((before, labels[0]), (after, labels[1])):
        if m is None:
            continue
        ims = [to_image(lit_plane(m, lamp, size=cell, tiles=tiles)) for lamp in LAMP_PATH]
        rows.append(row(ims, [f"{lab} - lamp {i + 1} of {len(LAMP_PATH)}" for i in range(len(ims))], cell=cell,
                        title=f"{name}: {lab}" if not rows else f"{name}: {lab}"))
    return stamp(stack(rows))
