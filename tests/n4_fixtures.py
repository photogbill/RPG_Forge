"""Synthetic sprite sheets for the Night 4 intake tests (no real art in the repo)."""
from __future__ import annotations
import numpy as np
from PIL import Image, ImageDraw, ImageFont

COLOURS = [(200, 40, 40), (40, 160, 60), (40, 70, 200), (190, 150, 30), (150, 40, 170), (30, 160, 170),
           (220, 110, 30), (110, 110, 110)]


def figure(h: int, colour, holster: bool = True, pocket: bool = False, eye: bool = True) -> Image.Image:
    """A little person on transparent: head, body, legs; a holster on its right hip (asymmetric); optionally an arm
    bent back to the hip leaving an enclosed pocket of backdrop; a white eye inside the head."""
    w = int(h * 0.55)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = tuple(colour) + (255,)
    dark = tuple(max(0, v - 60) for v in colour) + (255,)
    hr = int(h * 0.11)
    cx = w // 2
    d.ellipse([cx - hr, 0, cx + hr, 2 * hr], fill=c)
    if eye:
        d.ellipse([cx - hr // 3, hr // 2, cx + hr // 3, hr // 2 + hr // 2], fill=(255, 255, 255, 255))
    bt, bb = 2 * hr + 2, int(h * 0.62)
    bw = int(w * 0.36)
    d.rectangle([cx - bw // 2, bt, cx + bw // 2, bb], fill=c)
    d.rectangle([cx - bw // 2, bb, cx - 2, h - 1], fill=dark)
    d.rectangle([cx + 2, bb, cx + bw // 2, h - 1], fill=dark)
    if pocket:
        # arm leaving the shoulder, out, down and back to the hip: an enclosed hole between arm and body
        ax = cx - bw // 2
        d.rectangle([ax - int(w * 0.22), bt + 4, ax, bt + 4 + max(3, h // 40)], fill=c)
        d.rectangle([ax - int(w * 0.22), bt + 4, ax - int(w * 0.22) + max(3, h // 40), bb - 6], fill=c)
        d.rectangle([ax - int(w * 0.22), bb - 6 - max(3, h // 40), ax, bb - 6], fill=c)
    if holster:
        d.rectangle([cx + bw // 2, int(h * 0.52), cx + bw // 2 + max(3, w // 10), int(h * 0.66)], fill=(30, 20, 10, 255))
    return im


def paste_all(bg: Image.Image, figs, spots) -> Image.Image:
    out = bg.convert("RGBA").copy()
    for f, (x, y) in zip(figs, spots):
        out.alpha_composite(f, (x, y))
    return out


def checker(size, sq=16, a=(255, 255, 255), b=(204, 204, 204), noise=4, seed=0) -> Image.Image:
    w, h = size
    yy, xx = np.mgrid[0:h, 0:w]
    m = ((xx // sq + yy // sq) % 2).astype(bool)
    arr = np.where(m[..., None], np.array(b), np.array(a)).astype(np.int32)
    arr += np.random.default_rng(seed).integers(-noise, noise + 1, arr.shape)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")


def clean_grid() -> Image.Image:
    figs = [figure(180, COLOURS[i]) for i in range(8)]
    bg = Image.new("RGB", (8 * 160, 220), (255, 0, 255))
    return paste_all(bg, figs, [(i * 160 + 30, 20) for i in range(8)]).convert("RGB")


def ragged_grid() -> Image.Image:
    rng = np.random.default_rng(3)
    bg = Image.new("RGB", (760, 1100), (70, 74, 80))
    figs, spots = [], []
    for r in range(4):
        for c in range(3):
            h = 200 + int(rng.integers(-6, 7))
            figs.append(figure(h, COLOURS[r]))
            spots.append((40 + c * 230 + int(rng.integers(-20, 25)), 40 + r * 260 + int(rng.integers(-15, 15))))
    return paste_all(bg, figs, spots).convert("RGB")


def labelled() -> Image.Image:
    bg = Image.new("RGB", (900, 360), (240, 236, 228))
    figs = [figure(220, COLOURS[i]) for i in range(4)]
    im = paste_all(bg, figs, [(40 + i * 220, 20) for i in range(4)])
    d = ImageDraw.Draw(im)
    try:
        f = ImageFont.load_default(size=28)
    except TypeError:
        f = ImageFont.load_default()
    for i, word in enumerate(["FRONT", "SIDE", "BACK", "SIDE"]):
        d.text((50 + i * 220, 290), word, fill=(20, 20, 20), font=f)
    d.text((300, 320), "SARAH TURNAROUND", fill=(20, 20, 20), font=f)
    return im.convert("RGB")


def white_backdrop() -> Image.Image:
    bg = Image.new("RGB", (700, 300), (255, 255, 255))
    figs = [figure(240, COLOURS[i], pocket=True) for i in range(3)]
    return paste_all(bg, figs, [(60 + i * 220, 30) for i in range(3)]).convert("RGB")


def painted_checker() -> Image.Image:
    bg = checker((1000, 320))
    figs = [figure(260, COLOURS[i], pocket=True) for i in range(5)]
    return paste_all(bg, figs, [(40 + i * 190, 30) for i in range(5)]).convert("RGB")
