"""Contact sheets (for review) and sprite sheets (for the engine)."""
from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def _ascii(text: str) -> str:
    """Pillow's built-in font has few glyphs beyond Latin-1; keep labels readable."""
    return (text.replace("\u2014", "-").replace("\u2013", "-").replace("\u00b7", ".").replace("\u2192", "->")
            .encode("latin-1", "replace").decode("latin-1"))


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # old Pillow
        return ImageFont.load_default()


def contact_sheet(images: list[Image.Image], labels: list[str] | None = None, cols: int = 4,
                  cell: tuple[int, int] = (288, 162), title: str | None = None, pad: int = 8) -> Image.Image:
    """A labelled grid: each image fitted (not stretched) into a cell with its label under it.
    Pixel art is shown with nearest-neighbour scaling so the pixels stay crisp."""
    labels = labels or [""] * len(images)
    cw, ch = cell
    label_h = 18
    rows = max(1, (len(images) + cols - 1) // cols)
    title_h = 28 if title else 0
    W = pad + cols * (cw + pad)
    H = title_h + pad + rows * (ch + label_h + pad)
    sheet = Image.new("RGB", (W, H), (24, 24, 28))
    dr = ImageDraw.Draw(sheet)
    f = _font(12)
    if title:
        dr.text((pad, 6), _ascii(title), font=_font(16), fill=(235, 230, 215))
    for i, im in enumerate(images):
        r, c = divmod(i, cols)
        x = pad + c * (cw + pad)
        y = title_h + pad + r * (ch + label_h + pad)
        dr.rectangle([x - 1, y - 1, x + cw, y + ch], outline=(70, 70, 80))
        src = im.convert("RGBA")
        k = min(cw / src.width, ch / src.height)
        # small sources (pixel art) scale up with NEAREST; big ones scale down with LANCZOS
        resample = Image.NEAREST if k >= 1.0 else Image.LANCZOS
        if k >= 1.0:
            k = max(1, int(k))
        fitted = src.resize((max(1, int(src.width * k)), max(1, int(src.height * k))), resample)
        # checkerboard under transparent art so alpha is visible
        bg = Image.new("RGBA", (cw, ch), (40, 40, 46, 255))
        if fitted.getextrema()[3][0] < 255:
            bd = ImageDraw.Draw(bg)
            for yy in range(0, ch, 8):
                for xx in range(0, cw, 8):
                    if (xx // 8 + yy // 8) % 2 == 0:
                        bd.rectangle([xx, yy, xx + 7, yy + 7], fill=(52, 52, 60, 255))
        bg.paste(fitted, ((cw - fitted.width) // 2, (ch - fitted.height) // 2), fitted)
        sheet.paste(bg, (x, y))
        lab = labels[i] if i < len(labels) else ""
        if lab:
            dr.text((x + 2, y + ch + 2), _ascii(lab)[:60], font=f, fill=(220, 215, 200))
    return sheet


def pack_frames(frames: list[Image.Image], cols: int = 8, cell: tuple[int, int] | None = None,
                anchor: str = "bottom") -> tuple[Image.Image, dict]:
    """Row-major sprite sheet with uniform cells. Returns (sheet, meta)."""
    if not frames:
        raise ValueError("no frames")
    if cell is None:
        cell = (max(f.width for f in frames), max(f.height for f in frames))
    cw, ch = cell
    rows = (len(frames) + cols - 1) // cols
    sheet = Image.new("RGBA", (cols * cw, rows * ch), (0, 0, 0, 0))
    for i, f in enumerate(frames):
        r, c = divmod(i, cols)
        src = f.convert("RGBA")
        if anchor == "bottom":
            pos = (c * cw + (cw - src.width) // 2, r * ch + ch - src.height)
        else:
            pos = (c * cw + (cw - src.width) // 2, r * ch + (ch - src.height) // 2)
        sheet.paste(src, pos, src)
    meta = {"cell": [cw, ch], "cols": cols, "rows": rows, "count": len(frames), "anchor": anchor}
    return sheet, meta


def load_images(paths: list[str | Path]) -> list[Image.Image]:
    out = []
    for p in paths:
        im = Image.open(p)
        im.load()
        out.append(im)
    return out
