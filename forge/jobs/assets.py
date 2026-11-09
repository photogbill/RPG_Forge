"""Breadth jobs for the game's content: icon (F6) and sleeve (F7).

icon   — a prop on a square canvas: key-colour render → background removed → trimmed → centred with padding.
sleeve — square art by the model + typography by PIL. A model asked to spell gets it wrong; PIL never does.
"""
from __future__ import annotations
import io, random, textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from ..ops import alpha as al, sheet as sh
from .common import Context, write_prov, save_png, licence_chain
from .gpu import _client, build_graph, _color_word
from .paint import _pick_models


def _seed(job: dict) -> int:
    s = int(job.get("seed", -1) if job.get("seed") is not None else -1)
    return random.randint(0, 2**31 - 1) if s < 0 else s


def _render(ctx: Context, job: dict, w: int, h: int, seed: int) -> tuple[Image.Image, dict]:
    client = _client(ctx)
    g, prov = build_graph(ctx, job, w, h, seed, count=1)
    img = Image.open(io.BytesIO(client.run(g)[0])).convert("RGB")
    return img, prov


def _parts(prov: dict) -> dict:
    parts = {"checkpoint": prov["checkpoint"]}
    for i, lo in enumerate(prov.get("loras") or []):
        parts[f"lora{i + 1}"] = lo["name"]
    return parts


def fit_on_canvas(cut: Image.Image, canvas: int, padding: float) -> Image.Image:
    """Scale an RGBA cut-out to fit a square canvas inside `padding` (fraction per side) and centre it."""
    inner = max(1, int(round(canvas * (1.0 - 2.0 * padding))))
    w, h = cut.size
    k = inner / float(max(w, h, 1))
    small = cut.resize((max(1, int(round(w * k))), max(1, int(round(h * k)))), Image.LANCZOS)
    out = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    out.paste(small, ((canvas - small.width) // 2, (canvas - small.height) // 2), small)
    return out


def icon(job: dict, ctx: Context, out: Path) -> dict:
    j = _pick_models(ctx, job)
    key = str(j.get("key_color") or "#ff00ff")
    j["prompt"] = f"{job['prompt']}, single object, isolated on a flat solid {_color_word(key)} background, centered, full object visible"
    w, h = j.get("size") or [1024, 1024]
    canvas = int(j.get("canvas") or 256)
    pad = float(j["padding"]) if j.get("padding") is not None else 0.08
    n, seed = int(j.get("variants") or 1), _seed(j)
    snapper = ctx.snapper(j) if j.get("snap") else None
    outputs, seeds, prov = [], [], {}
    for i in range(n):
        sfx = "" if n == 1 else f"_{i + 1}"
        img, prov = _render(ctx, j, int(w), int(h), seed + i)
        save_png(img, out / f"raw{sfx}.png")
        cut = al.trim(al.remove_flat_background(img.convert("RGBA"), al.hex_to_rgb(key), tolerance=int(j.get("tolerance", 40))))
        ic = fit_on_canvas(cut, canvas, pad)
        if snapper is not None:
            ic, _ = snapper.snap(ic)
        save_png(ic, out / f"icon{sfx}.png")
        outputs.append(f"icon{sfx}.png")
        seeds.append(seed + i)
    if n > 1:
        save_png(sh.contact_sheet([Image.open(out / o) for o in outputs], [f"seed {s}" for s in seeds], cols=min(n, 4),
                                  cell=(canvas, canvas), title=j.get("name")), out / "contact.png")
    licences, ok = licence_chain(ctx, _parts(prov))
    prov.pop("seed", None)
    prov.update(licences=licences, commercial_ok=ok)
    write_prov(out, j, **prov, seeds=seeds, canvas=canvas, padding=pad, key_color=key,
               post=["remove_flat_background", "trim", "fit_on_canvas", "palette_snap" if snapper else None], outputs=outputs)
    return {"outputs": outputs, "seed": seed, "commercial_ok": ok}


# ------------------------------------------------------------------ sleeves
def find_font(ctx: Context, job: dict, bold: bool) -> str | None:
    p = job.get("font_bold" if bold else "font")
    if p and ctx.resolve(p).exists():
        return str(ctx.resolve(p))
    g = ctx.game(job)
    dirs = [ctx.resolve(d) for d in (g.get("fonts_dirs") or [])]
    if g.get("game_root"):
        dirs.append(Path(g["game_root"]) / "project" / "assets" / "fonts")
    dirs.append(ctx.root / "assets" / "fonts")
    for d in dirs:
        if d.exists():
            fonts = sorted(list(d.glob("*.ttf")) + list(d.glob("*.otf")))
            pick = [f for f in fonts if ("bold" in f.name.lower()) == bold] or fonts
            if pick:
                return str(pick[0])
    return None


def _load(path: str | None, size: int):
    if path:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return sh._font(size)


def _fit_font(draw: ImageDraw.ImageDraw, text: str, path: str | None, max_w: int, start: int, min_size: int = 10):
    size = start
    while size > min_size:
        f = _load(path, size)
        if draw.textlength(text, font=f) <= max_w:
            return f
        size = int(size * 0.92)
    return _load(path, min_size)


def _wrap(draw, text: str, path: str | None, max_w: int, start: int, lines: int = 2):
    """One line if it fits at a decent size, else wrap to `lines` lines and fit the widest."""
    f = _fit_font(draw, text, path, max_w, start)
    if getattr(f, "size", start) >= start * 0.6 or len(text) < 14:
        return [text], f
    width = max(8, len(text) // lines + 2)
    parts = textwrap.wrap(text, width=width)[:lines]
    widest = max(parts, key=lambda s: draw.textlength(s, font=_load(path, start)))
    return parts, _fit_font(draw, widest, path, max_w, start)


def _record_mark(draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int, alpha: int = 200):
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 255, 255, alpha), width=max(1, r // 8))
    rr = max(2, r // 3)
    draw.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=(255, 255, 255, alpha))
    d = max(1, r // 10)
    draw.ellipse([cx - d, cy - d, cx + d, cy + d], fill=(0, 0, 0, alpha))


def compose_sleeve(art: Image.Image, title: str, artist: str = "", label: str = "", layout: str = "band",
                   size: int = 1024, font: str | None = None, font_bold: str | None = None) -> Image.Image:
    """Lay the type over the art. Pure PIL — tested without a GPU."""
    base = art.convert("RGBA").resize((size, size), Image.LANCZOS)
    over = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    m = size // 20
    if layout == "corner":
        lines, tf = _wrap(d, title, font_bold, int(size * 0.62), size // 11)
        y = m
        shadow = Image.new("RGBA", base.size, (0, 0, 0, 0))
        sd = ImageDraw.Draw(shadow)
        for ln in lines:
            sd.text((m + 2, y + 2), ln, font=tf, fill=(0, 0, 0, 200))
            d.text((m, y), ln, font=tf, fill=(255, 255, 255, 255))
            y += int(getattr(tf, "size", size // 11) * 1.12)
        if artist:
            af = _fit_font(d, artist, font, int(size * 0.62), size // 26)
            sd.text((m + 2, y + 6), artist, font=af, fill=(0, 0, 0, 200))
            d.text((m, y + 4), artist, font=af, fill=(235, 235, 235, 255))
        base = Image.alpha_composite(base, shadow.filter(ImageFilter.GaussianBlur(3)))
        _record_mark(d, size - m - size // 22, size - m - size // 22, size // 22)
        if label:
            lf = _load(font, size // 48)
            d.text((m, size - m - size // 48), label, font=lf, fill=(255, 255, 255, 190))
    else:
        band_h = int(size * 0.2)
        d.rectangle([0, size - band_h, size, size], fill=(8, 8, 12, 178))
        lines, tf = _wrap(d, title, font_bold, int(size * 0.78), size // 13)
        th = int(getattr(tf, "size", size // 13) * 1.1) * len(lines)
        af = _fit_font(d, artist, font, int(size * 0.78), size // 30) if artist else None
        ah = int(getattr(af, "size", 0) * 1.3) if af else 0
        y = size - band_h + (band_h - th - ah) // 2
        for ln in lines:
            d.text((m, y), ln, font=tf, fill=(255, 255, 255, 255))
            y += int(getattr(tf, "size", size // 13) * 1.1)
        if af:
            d.text((m, y + 2), artist, font=af, fill=(225, 225, 225, 255))
        _record_mark(d, size - m - size // 26, size - band_h // 2, size // 26)
        if label:
            lf = _load(font, size // 50)
            d.text((size - m - d.textlength(label, font=lf) - size // 13, size - band_h + m // 3), label, font=lf, fill=(255, 255, 255, 170))
    return Image.alpha_composite(base, over).convert("RGB")


def sleeve(job: dict, ctx: Context, out: Path) -> dict:
    j = _pick_models(ctx, job)
    w, h = j.get("size") or [1024, 1024]
    seed = _seed(j)
    art, prov = _render(ctx, j, int(w), int(h), seed)
    save_png(art, out / "art.png")
    fb, fr = find_font(ctx, j, True), find_font(ctx, j, False)
    img = compose_sleeve(art, str(j["title"]), str(j.get("artist") or ""), str(j.get("label") or ""),
                         str(j.get("layout") or "band"), int(j.get("out_size", 1024)), fr, fb or fr)
    save_png(img, out / "sleeve.png")
    licences, ok = licence_chain(ctx, _parts(prov))
    prov.update(licences=licences, commercial_ok=ok)
    write_prov(out, j, **prov, title=j["title"], artist=j.get("artist"), layout=j.get("layout"), fonts=[fb, fr],
               post=["compose_sleeve (PIL typography)"], outputs=["sleeve.png"])
    return {"outputs": ["sleeve.png"], "seed": seed, "commercial_ok": ok, "fonts": [fb, fr]}
