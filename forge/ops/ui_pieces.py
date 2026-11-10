"""UI pieces (Night 3, G12): a painted panel → a nine-slice Godot can stretch; one button → four states.

    nine_slice(img, margins=None, scale=1.0, snap=3)  → (piece RGBA, margins {left, top, right, bottom}, report)
        trimmed to its content; corners/edges found by comparing each column/row with the panel's middle (or given);
        the centre made tileable; margins rounded up to a multiple of `snap` (the game draws its UI on 640×360 ×3,
        so whole UI pixels stay whole). The JSON is Godot NinePatchRect's patch_margin_* fields.
    stretch_preview(piece, margins, sizes)            the piece drawn as a NinePatchRect would draw it at each size —
                                                      corners copied 1:1, edges and centre stretched
    button_states(img)                                normal / hover / pressed / disabled, by tone only (no shift)
No look is chosen here: the input picture is commissioned separately.
"""
from __future__ import annotations
import math
import numpy as np
from PIL import Image, ImageEnhance

from .alpha import remove_flat_background


def _content(img: Image.Image, key=None) -> Image.Image:
    """Trim to the content. An opaque picture is kept whole unless `key` is given ("auto" = the corner colour, or an
    (r, g, b)): a frame's own border usually touches the corners, and flooding it away would eat the frame."""
    im = img.convert("RGBA")
    if key is not None and np.asarray(im)[..., 3].min() >= 250:
        im = remove_flat_background(im, None if key == "auto" else tuple(key))
    b = im.getbbox()
    return im.crop(b) if b else im


def detect_margins(img: Image.Image, tol: float = 6.0, min_margin: int = 2) -> dict:
    """Scan in from each edge until the column (row) looks like the panel's middle column (row) — that is where the
    corner/edge art stops and the plain stretchable part begins."""
    a = np.asarray(img.convert("RGBA"), dtype=np.float64)
    h, w = a.shape[:2]

    def scan(lines, ref, n):
        for i in range(n // 2):
            if np.abs(lines(i) - ref).mean() <= tol:
                # must stay plain for a few more lines (texture can dip below tol once)
                if all(np.abs(lines(j) - ref).mean() <= tol * 1.5 for j in range(i, min(n // 2, i + 4))):
                    return max(min_margin, i)
        return n // 3
    mid_col = a[:, w // 2]
    mid_row = a[h // 2]
    left = scan(lambda i: a[:, i], mid_col, w)
    right = scan(lambda i: a[:, w - 1 - i], mid_col, w)
    top = scan(lambda i: a[i], mid_row, h)
    bottom = scan(lambda i: a[h - 1 - i], mid_row, h)
    return {"left": int(left), "top": int(top), "right": int(right), "bottom": int(bottom)}


def _snap(m: dict, k: int, size) -> dict:
    w, h = size
    out = {s: int(math.ceil(v / k) * k) if k > 1 else int(v) for s, v in m.items()}
    out["left"] = min(out["left"], w // 2 - 1); out["right"] = min(out["right"], w - out["left"] - 1)
    out["top"] = min(out["top"], h // 2 - 1); out["bottom"] = min(out["bottom"], h - out["top"] - 1)
    return out


def _tileable_centre(piece: Image.Image, m: dict) -> Image.Image:
    from .tiles import make_seamless
    w, h = piece.size
    box = (m["left"], m["top"], w - m["right"], h - m["bottom"])
    if box[2] - box[0] < 8 or box[3] - box[1] < 8:
        return piece
    c = piece.crop(box)
    rgb = make_seamless(c.convert("RGB"), 0.25)
    rgba = rgb.convert("RGBA")
    rgba.putalpha(c.getchannel("A"))
    out = piece.copy()
    out.paste(rgba, box[:2])
    return out


def nine_slice(img: Image.Image, margins: dict | None = None, scale: float = 1.0, snap: int = 3, tileable: bool = True,
               key=None):
    piece = _content(img, key)
    if scale and abs(scale - 1.0) > 1e-6:
        piece = piece.resize((max(3, round(piece.width * scale)), max(3, round(piece.height * scale))), Image.LANCZOS)
    found = margins is None
    m = detect_margins(piece) if found else {k: int(round(margins[k] * (scale or 1))) for k in ("left", "top", "right", "bottom")}
    m = _snap(m, int(snap or 1), piece.size)
    if tileable:
        piece = _tileable_centre(piece, m)
    rep = {"size": list(piece.size), "margins": m, "detected": found, "snap": snap,
           "godot": {"patch_margin_left": m["left"], "patch_margin_top": m["top"], "patch_margin_right": m["right"],
                     "patch_margin_bottom": m["bottom"], "axis_stretch_horizontal": "tile_fit" if tileable else "stretch",
                     "axis_stretch_vertical": "tile_fit" if tileable else "stretch"}}
    return piece, m, rep


def draw_nine(piece: Image.Image, m: dict, size) -> Image.Image:
    W, H = int(size[0]), int(size[1])
    w, h = piece.size
    L, T, R, B = m["left"], m["top"], m["right"], m["bottom"]
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    xs_src = [0, L, w - R, w]
    ys_src = [0, T, h - B, h]
    xs_dst = [0, L, W - R, W]
    ys_dst = [0, T, H - B, H]
    for i in range(3):
        for j in range(3):
            sb = (xs_src[i], ys_src[j], xs_src[i + 1], ys_src[j + 1])
            db = (xs_dst[i], ys_dst[j], xs_dst[i + 1], ys_dst[j + 1])
            if sb[2] <= sb[0] or sb[3] <= sb[1] or db[2] <= db[0] or db[3] <= db[1]:
                continue
            part = piece.crop(sb)
            if part.size != (db[2] - db[0], db[3] - db[1]):
                part = part.resize((db[2] - db[0], db[3] - db[1]), Image.LANCZOS)
            out.alpha_composite(part, db[:2])
    return out


def stretch_preview(piece: Image.Image, m: dict, sizes=None) -> Image.Image:
    w, h = piece.size
    sizes = sizes or [(int(w * 1.6), int(h * 0.8)), (int(w * 2.6), int(h * 1.5)), (int(w * 1.1), int(h * 2.4))]
    pics = [draw_nine(piece, m, s) for s in sizes]
    W = sum(p.width for p in pics) + 20 * (len(pics) + 1)
    H = max(p.height for p in pics) + 40
    canvas = Image.new("RGBA", (W, H), (34, 34, 40, 255))
    x = 20
    for p in pics:
        canvas.alpha_composite(p, (x, 20))
        x += p.width + 20
    return canvas


def button_states(img: Image.Image) -> dict:
    im = img.convert("RGBA")
    a = im.getchannel("A")

    def tone(e):
        rgb = e.convert("RGB")
        r = rgb.convert("RGBA"); r.putalpha(a)
        return r
    hover = tone(ImageEnhance.Brightness(im.convert("RGB")).enhance(1.12))
    pressed = tone(ImageEnhance.Brightness(im.convert("RGB")).enhance(0.82))
    dis = ImageEnhance.Color(im.convert("RGB")).enhance(0.25)
    dis = ImageEnhance.Brightness(dis).enhance(0.85).convert("RGBA")
    dis.putalpha(a.point(lambda v: int(v * 0.6)))
    return {"normal": im, "hover": hover, "pressed": pressed, "disabled": dis}
