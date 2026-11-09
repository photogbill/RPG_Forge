"""Palettes and perceptual snapping.

The palette law (one master palette for the whole game) is enforced here: every generated image is
snapped to the nearest palette colour in **OKLab**, a perceptual space where "nearest" matches what
eyes see (RGB distance does not — it over-weights dark blues and under-weights yellows).

Palette files: `palettes/<name>.hex` (one `rrggbb` per line, Lospec's format), `.gpl` (GIMP) or
`.json` (a list of "#rrggbb"). `pull_lospec(slug)` downloads one from lospec.com (needs network —
run it on the machine that has it).
"""
from __future__ import annotations
import json, re
from pathlib import Path
import numpy as np
from PIL import Image

HEX = re.compile(r"#?([0-9a-fA-F]{6})\b")


# ---------------------------------------------------------------- loading
def load_palette(path: Path) -> np.ndarray:
    """→ (N, 3) uint8 array of sRGB colours."""
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
        cols = data if isinstance(data, list) else data.get("colors") or data.get("palette")
        rgb = [tuple(int(HEX.search(c).group(1)[i:i + 2], 16) for i in (0, 2, 4)) for c in cols]
    elif path.suffix.lower() == ".gpl":
        rgb = []
        for line in text.splitlines():
            parts = line.split()
            if len(parts) >= 3 and all(p.isdigit() for p in parts[:3]):
                rgb.append(tuple(int(p) for p in parts[:3]))
    else:
        rgb = [tuple(int(m[i:i + 2], 16) for i in (0, 2, 4)) for m in HEX.findall(text)]
    if not rgb:
        raise ValueError(f"no colours found in {path}")
    # dedupe, keep order
    seen, out = set(), []
    for c in rgb:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return np.array(out, dtype=np.uint8)


def find_palette(name_or_path: str, palettes_dir: Path) -> Path:
    p = Path(name_or_path)
    if p.exists():
        return p
    for ext in (".hex", ".gpl", ".json"):
        q = Path(palettes_dir) / (name_or_path + ext)
        if q.exists():
            return q
    raise FileNotFoundError(f"palette '{name_or_path}' not found in {palettes_dir} (try: python -m forge palette pull {name_or_path})")


def pull_lospec(slug: str, palettes_dir: Path) -> Path:
    """Download https://lospec.com/palette-list/<slug>.hex into palettes/. Network required."""
    import urllib.request
    url = f"https://lospec.com/palette-list/{slug}.hex"
    req = urllib.request.Request(url, headers={"User-Agent": "RPG_Forge/0.1 (palette fetch)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        text = r.read().decode("utf-8", errors="replace")
    if not HEX.search(text):
        raise ValueError(f"{url} returned no colours")
    out = Path(palettes_dir) / f"{slug}.hex"
    out.write_text(text.strip() + "\n", encoding="utf-8")
    return out


# ---------------------------------------------------------------- colour science
def srgb_to_linear(c: np.ndarray) -> np.ndarray:
    c = c.astype(np.float64) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(c: np.ndarray) -> np.ndarray:
    c = np.clip(c, 0.0, 1.0)
    s = np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)
    return np.clip(np.round(s * 255.0), 0, 255).astype(np.uint8)


_M1 = np.array([[0.4122214708, 0.5363325363, 0.0514459929],
                [0.2119034982, 0.6806995451, 0.1073969566],
                [0.0883024619, 0.2817188376, 0.6299787005]])
_M2 = np.array([[0.2104542553, 0.7936177850, -0.0040720468],
                [1.9779984951, -2.4285922050, 0.4505937099],
                [0.0259040371, 0.7827717662, -0.8086757660]])


def srgb_to_oklab(rgb: np.ndarray) -> np.ndarray:
    """(…, 3) uint8 sRGB → (…, 3) float OKLab (Björn Ottosson's formulation)."""
    lin = srgb_to_linear(rgb.reshape(-1, 3))
    lms = lin @ _M1.T
    lms_ = np.cbrt(lms)
    lab = lms_ @ _M2.T
    return lab.reshape(rgb.shape[:-1] + (3,))


# ---------------------------------------------------------------- snapping
class Snapper:
    """Snap pixels to a palette; built once per palette, reused across images/frames."""

    def __init__(self, palette_rgb: np.ndarray):
        self.rgb = np.asarray(palette_rgb, dtype=np.uint8)
        self.lab = srgb_to_oklab(self.rgb)

    def nearest(self, pixels_rgb: np.ndarray) -> np.ndarray:
        """(N, 3) uint8 → (N,) palette indices."""
        lab = srgb_to_oklab(pixels_rgb)
        # chunk to keep memory flat on big images
        out = np.empty(lab.shape[0], dtype=np.int64)
        step = 65536
        for i in range(0, lab.shape[0], step):
            d = lab[i:i + step, None, :] - self.lab[None, :, :]
            out[i:i + step] = np.argmin(np.einsum("ijk,ijk->ij", d, d), axis=1)
        return out

    def snap(self, img: Image.Image, dither: str | None = None, prev_idx: np.ndarray | None = None,
             hysteresis: float = 0.0) -> tuple[Image.Image, np.ndarray]:
        """Return (snapped RGBA image, palette index map). Fully transparent pixels stay transparent.

        dither="ordered" applies a 4×4 Bayer threshold in OKLab lightness before snapping (rarely
        wanted for pixel art, but right for painted cards). `prev_idx` + `hysteresis` (ΔE in OKLab,
        ~0.02 is subtle) keep a pixel on its previous palette entry when the new nearest is barely
        closer — stops animation frames flickering between two near-equal colours.
        """
        rgba = np.asarray(img.convert("RGBA"))
        h, w = rgba.shape[:2]
        rgb = rgba[..., :3].reshape(-1, 3)
        alpha = rgba[..., 3].reshape(-1)
        if dither == "ordered":
            bayer = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], dtype=np.float64) / 16.0 - 0.5
            yy, xx = np.mgrid[0:h, 0:w]
            noise = bayer[yy % 4, xx % 4].reshape(-1, 1) * 12.0  # ± 6 levels of 255
            rgb = np.clip(rgb.astype(np.float64) + noise, 0, 255).astype(np.uint8)
        idx = self.nearest(rgb)
        if prev_idx is not None and hysteresis > 0.0 and prev_idx.shape == idx.shape:
            lab = srgb_to_oklab(rgb)
            d_new = np.sum((lab - self.lab[idx]) ** 2, axis=1)
            d_old = np.sum((lab - self.lab[prev_idx]) ** 2, axis=1)
            keep = (d_old - d_new) < hysteresis ** 2
            idx = np.where(keep, prev_idx, idx)
        out = np.zeros((h * w, 4), dtype=np.uint8)
        out[:, :3] = self.rgb[idx]
        out[:, 3] = np.where(alpha > 0, 255, 0) if img.mode in ("RGBA", "LA", "P") else 255
        return Image.fromarray(out.reshape(h, w, 4), "RGBA"), idx.reshape(h, w)


def report(img: Image.Image, palette_rgb: np.ndarray | None = None) -> dict:
    """How many distinct colours; how many pixels are off-palette (if a palette is given)."""
    rgba = np.asarray(img.convert("RGBA"))
    opaque = rgba[rgba[..., 3] > 0][:, :3]
    uniq = np.unique(opaque, axis=0)
    out = {"colors": int(uniq.shape[0]), "opaque_pixels": int(opaque.shape[0])}
    if palette_rgb is not None:
        pal = {tuple(c) for c in np.asarray(palette_rgb).tolist()}
        off = sum(1 for c in uniq.tolist() if tuple(c) not in pal)
        out["off_palette_colors"] = int(off)
    return out
