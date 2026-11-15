"""Wrecked versions from the intact model, and a glow layer the game can brighten (BUILD 39, part 8) — numpy only.

The launch-site run made each wrecked version from its own picture and it came out soft. The other way: keep the
intact model and damage it — dents pushed in, a hole punched through, scorch and soot on the colours around each hit —
so the wreck is the same object, as sharp as the intact one. Both ways are tried side by side before one is chosen.

    wreck(src, dst, seed=1, hits=3, strength=0.5)      -> report
    glow(src, dst, colours=("amber",), strength=1.0)   -> report

The glow layer: the parts of the model's colours that are the glow colour (an eye, a lamp) become an emissive texture,
with KHR_materials_emissive_strength, so the game can turn the glow up and down at run time (Godot: emission energy).
"""
from __future__ import annotations

import colorsys
from pathlib import Path

import numpy as np

from .meshio import Glb

GLOW_COLOURS = {"red": (235, 30, 25), "amber": (255, 165, 30), "blue": (60, 140, 255), "green": (60, 230, 90),
                "white": (250, 250, 250), "orange": (250, 110, 20), "yellow": (255, 215, 60)}


# ------------------------------------------------------------------------------------------------ helpers
def _prim(g: Glb):
    """The first triangle primitive with positions (image-to-3D writes exactly one)."""
    for mi, mesh in enumerate(g.j.get("meshes", [])):
        for pi, prim in enumerate(mesh.get("primitives", [])):
            if prim.get("mode", 4) == 4 and "POSITION" in prim.get("attributes", {}):
                return mi, pi, prim
    raise ValueError("the model has no triangles")


def vertex_normals(P: np.ndarray, F: np.ndarray) -> np.ndarray:
    n = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
    vn = np.zeros_like(P)
    for k in range(3):
        np.add.at(vn, F[:, k], n)
    return vn / np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-12)


def _smooth_noise(rng, P: np.ndarray, scale: float) -> np.ndarray:
    """Cheap smooth noise over 3D points: a sum of a few random waves (no grid, no library)."""
    out = np.zeros(len(P))
    for _ in range(6):
        k = rng.normal(size=3)
        k = k / np.linalg.norm(k) / scale * rng.uniform(0.6, 1.8)
        out += np.sin(P @ k + rng.uniform(0, 2 * np.pi))
    return out / 6


# ------------------------------------------------------------------------------------------------ wrecked versions
def wreck(src, dst, seed: int = 1, hits: int = 4, strength: float = 0.8, hole: bool = True) -> dict:
    """Damage the intact model: `hits` impacts on its upper, outer surface, each a dent with scorch around it; the largest
    punched through when `hole`. `strength` 0..1 scales the dents and the burn."""
    from PIL import Image, ImageDraw, ImageFilter
    rng = np.random.default_rng(seed)
    g = Glb.load(src)
    mi, pi, prim = _prim(g)
    P = g.accessor(prim["attributes"]["POSITION"]).astype(np.float64)
    F = g.accessor(prim["indices"]).reshape(-1, 3).astype(np.int64) if "indices" in prim else np.arange(len(P)).reshape(-1, 3)
    UV = g.accessor(prim["attributes"]["TEXCOORD_0"]).astype(np.float64) if "TEXCOORD_0" in prim["attributes"] else None
    diag = float(np.linalg.norm(P.max(0) - P.min(0))) or 1.0
    n_f = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
    area = np.linalg.norm(n_f, axis=1) / 2
    cen = P[F].mean(1)
    # impacts land on the upper two thirds and on faces that look outward (away from the middle)
    mid = (P.max(0) + P.min(0)) / 2
    outward = np.einsum("ij,ij->i", n_f / np.maximum(2 * area, 1e-18)[:, None], cen - mid) > 0
    upper = cen[:, 1] > P[:, 1].min() + 0.33 * np.ptp(P[:, 1])
    w = area * outward * upper
    if w.sum() <= 0:
        w = area
    picks = rng.choice(len(F), size=max(1, int(hits)), replace=False, p=w / w.sum())
    centres = cen[picks]
    radii = diag * rng.uniform(0.08, 0.16, size=len(picks)) * (0.6 + 0.8 * strength)
    vn = vertex_normals(P, F)
    noise = _smooth_noise(rng, P, diag * 0.03)
    moved = np.zeros(len(P), bool)
    for c, r in zip(centres, radii):
        d = np.linalg.norm(P - c, axis=1)
        inside = d < r
        fall = (1 - (d[inside] / r) ** 2) ** 2
        depth = r * (0.25 + 0.45 * strength) * fall * (0.6 + 0.8 * (noise[inside] + 1) / 2)
        P[inside] -= vn[inside] * depth[:, None]
        moved |= inside
    removed = 0
    if hole and len(picks):
        # the largest hit is punched through; with strength above one half, the second largest too
        order = np.argsort(-radii)[: (2 if strength > 0.5 and len(picks) > 1 else 1)]
        gone = np.zeros(len(F), bool)
        for k in order:
            d = np.linalg.norm(cen - centres[k], axis=1)
            ragged = 1 + 0.35 * _smooth_noise(rng, cen, diag * 0.02)
            gone |= d < radii[k] * (0.3 + 0.25 * strength) * ragged
        removed = int(gone.sum())
        F = F[~gone]
    # scorch and soot on the colours: the faces around each hit, darkened in the texture (with ragged edges)
    scorched = 0
    mat_i = prim.get("material")
    mats = g.j.get("materials") or []
    if UV is not None and mat_i is not None and mat_i < len(mats):
        base_ref = (mats[mat_i].get("pbrMetallicRoughness") or {}).get("baseColorTexture")
        if base_ref is not None:
            img = g.texture_image(mats[mat_i], "baseColorTexture").convert("RGBA")
            W, H = img.size
            burn = Image.new("L", (W, H), 0)
            dr = ImageDraw.Draw(burn)
            cen2 = P[F].mean(1)
            for c, r in zip(centres, radii):
                d = np.linalg.norm(cen2 - c, axis=1)
                for fi in np.nonzero(d < r * 1.6)[0]:
                    s = 1 - min(1.0, d[fi] / (r * 1.6))
                    tri = [(float(UV[v, 0] * W), float(UV[v, 1] * H)) for v in F[fi]]
                    dr.polygon(tri, fill=int(255 * min(1.0, 0.25 + s * 1.1)))
                    scorched += 1
            burn = burn.filter(ImageFilter.GaussianBlur(radius=max(1, W // 400)))
            b = np.asarray(burn, dtype=np.float64) / 255 * (0.7 + 0.3 * strength)
            grain = rng.random((H // 8 + 1, W // 8 + 1))
            grain = np.kron(grain, np.ones((8, 8)))[:H, :W]
            b = np.clip(b * (0.8 + 0.5 * grain), 0, 1)
            a = np.asarray(img, dtype=np.float64)
            soot = np.array([22.0, 19.0, 17.0])
            a[..., :3] *= 1 - 0.22 * strength                   # grime over everything: a wreck is never clean
            a[..., :3] = a[..., :3] * (1 - 0.93 * b[..., None]) + soot * (0.93 * b[..., None])
            g.replace_image(base_ref["index"], Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGBA").convert("RGB"))
    # write the new surface back: positions, normals, faces (tangents would be stale: they are left out)
    attrs = prim["attributes"]
    attrs["POSITION"] = g.add_accessor(P.astype(np.float32), "VEC3", 34962, minmax=True)
    if "NORMAL" in attrs:
        attrs["NORMAL"] = g.add_accessor(vertex_normals(P, F).astype(np.float32), "VEC3", 34962)
    attrs.pop("TANGENT", None)
    prim["indices"] = g.add_accessor(F.astype(np.uint32).reshape(-1, 1), "SCALAR", 34963)
    g.save(dst)
    return {"hits": len(picks), "moved_vertices": int(moved.sum()), "faces_removed": removed, "faces_scorched": scorched,
            "seed": seed, "strength": strength, "file": str(dst)}


# ------------------------------------------------------------------------------------------------ the glow layer
def _rgb(c) -> tuple[int, int, int]:
    if isinstance(c, str):
        if c in GLOW_COLOURS:
            return GLOW_COLOURS[c]
        parts = [int(x) for x in c.replace(" ", "").replace(":", ",").split(",")]
        return parts[0], parts[1], parts[2]
    return tuple(int(x) for x in c)[:3]


def glow_mask(img, colour, hue_tol: float = 0.06, min_sat: float = 0.45, min_val: float = 0.55) -> np.ndarray:
    """Texels that are the glow colour: close in hue, saturated and bright (for white: simply very bright)."""
    a = np.asarray(img.convert("RGB"), dtype=np.float64) / 255
    r, gch, b = a[..., 0], a[..., 1], a[..., 2]
    mx, mn = a.max(2), a.min(2)
    val = mx
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-9), 0)
    tr, tg, tb = (x / 255 for x in _rgb(colour))
    th, ts, tv = colorsys.rgb_to_hsv(tr, tg, tb)
    if ts < 0.15:                                           # a white glow: the brightest, least coloured texels
        return (val > 0.94) & (sat < 0.12)
    hue = np.zeros_like(val)
    d = np.maximum(mx - mn, 1e-9)
    hr = ((gch - b) / d) % 6
    hg = (b - r) / d + 2
    hb = (r - gch) / d + 4
    hue = np.where(mx == r, hr, np.where(mx == gch, hg, hb)) / 6
    dh = np.minimum(np.abs(hue - th), 1 - np.abs(hue - th))
    return (dh < hue_tol) & (sat > min_sat) & (val > min_val)


def glow(src, dst, colours=("amber",), strength: float = 1.0, name: str = "glow") -> dict:
    """An emissive layer from the glow colours already in the model's colours. Returns {"share", "found", ...}."""
    from PIL import Image, ImageFilter
    g = Glb.load(src)
    found, shares = [], []
    for mat in g.j.get("materials") or []:
        base = g.texture_image(mat, "baseColorTexture")
        if base is None:
            continue
        rgb = base.convert("RGB")
        mask = np.zeros(rgb.size[::-1], bool)
        for c in colours:
            m = glow_mask(rgb, c)
            if m.any():
                found.append(c if isinstance(c, str) else ",".join(map(str, _rgb(c))))
            mask |= m
        if not mask.any():
            continue
        mimg = Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3))
        m = np.asarray(mimg, dtype=np.float64)[..., None] / 255
        em = (np.asarray(rgb, dtype=np.float64) * m).astype(np.uint8)
        ti = g.add_image(Image.fromarray(em, "RGB"))
        mat["emissiveTexture"] = {"index": ti}
        mat["emissiveFactor"] = [1.0, 1.0, 1.0]
        mat.setdefault("extensions", {})["KHR_materials_emissive_strength"] = {"emissiveStrength": float(strength)}
        mat.setdefault("extras", {})["forge_glow"] = {"layer": name, "colours": [str(c) for c in colours]}
        g.use_extension("KHR_materials_emissive_strength")
        shares.append(float(mask.mean()))
    g.save(dst)
    share = max(shares) if shares else 0.0
    line = (f"Glow layer '{name}': {share * 100:.2f}% of the colours glow ({', '.join(sorted(set(found)))}); the game sets "
            "its strength at run time." if share else
            f"Glow layer '{name}': none of {', '.join(map(str, colours))} is in the model's colours — the glow was lost in "
            "image-to-3D (dark characters lose it most): paint it on, or make it from the picture again.")
    return {"share": round(share, 5), "found": sorted(set(found)), "line": line, "file": str(dst)}


# ------------------------------------------------------------------------------------------------ flames (BUILD 40)
FLAME_COLOURS = ("amber", "orange", "yellow")


def _flame_texture(texture=None, size: int = 128):
    """The flame card's picture as RGBA: a flame on black (a palette render) with its brightness as its alpha; without one,
    a plain teardrop flame made here (a stand-in until a palette flame is picked)."""
    from PIL import Image
    if texture:
        img = Image.open(texture).convert("RGB")
        a = np.asarray(img, dtype=np.float64)
    else:
        yy, xx = np.mgrid[0:size, 0:size] / (size - 1.0)
        w = 0.20 * np.sqrt(np.clip(1 - yy, 0, 1)) * np.clip(yy * 3, 0, 1) + 1e-6       # wide at the foot, a point at the top
        d = np.abs(xx - 0.5) / w
        inside = np.clip(1 - d, 0, 1) * (yy > 0.12) * (yy < 0.95)
        heat = inside ** 0.6
        a = np.stack([255 * heat, 200 * heat ** 1.4, 90 * heat ** 3], -1)
    lum = a.max(2) / 255.0
    alpha = np.clip((lum - 0.06) * 1.6, 0, 1)
    rgba = np.dstack([a, alpha * 255]).clip(0, 255).astype(np.uint8)
    # where the flame sits in its picture: its width and its foot, so the card can be sized and set on the fire
    ys, xs = np.nonzero(alpha > 0.25)
    H, W = alpha.shape
    if len(xs):
        span = ((xs.max() - xs.min() + 1) / W, (ys.max() - ys.min() + 1) / H)
        foot = (H - 1 - ys.max()) / H
    else:
        span, foot = (1.0, 1.0), 0.0
    return Image.fromarray(rgba, "RGBA"), span, foot


def flame_sites(g: Glb, colours=FLAME_COLOURS, join: float = 0.05, min_faces: int = 2, min_val: float = 0.82) -> list[dict]:
    """Where the model's own colours burn: faces whose colour is a flame colour, gathered into sites (one per fire,
    one per candle). Returns [{"x", "z", "base", "top", "width", "faces"}] in the model's units."""
    m = g.mesh()
    if not len(m["F"]):
        return []
    mats = m["materials"] or []
    P, F, UV, FM = m["P"], m["F"], m["UV"], m["face_material"]
    hot = np.zeros(len(F), bool)
    for mi, mat in enumerate(mats):
        img = g.texture_image(mat, "baseColorTexture")
        if img is None:
            continue
        rgb = img.convert("RGB")
        mask = np.zeros(rgb.size[::-1], bool)
        for c in colours:
            mask |= glow_mask(rgb, c, min_val=min_val)       # a flame is bright: bread and brass are not on fire
        if not mask.any():
            continue
        sel = FM == mi
        uvc = UV[F[sel]].mean(1)
        h, w = mask.shape
        px = np.clip((uvc[:, 0] % 1.0) * w, 0, w - 1).astype(int)
        py = np.clip((uvc[:, 1] % 1.0) * h, 0, h - 1).astype(int)
        hot[np.nonzero(sel)[0][mask[py, px]]] = True
    if not hot.any():
        return []
    C = P[F[hot]].mean(1)
    lo, hi = P.min(0), P.max(0)
    cell = max(float(np.linalg.norm(hi - lo)) * join, 1e-6)
    keys = np.floor((C - lo) / cell).astype(int)
    cells: dict[tuple, list[int]] = {}
    for i, k in enumerate(map(tuple, keys)):
        cells.setdefault(k, []).append(i)
    seen, sites = set(), []
    for k in cells:
        if k in seen:
            continue
        stack, comp = [k], []
        seen.add(k)
        while stack:
            c = stack.pop()
            comp += cells[c]
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        n = (c[0] + dx, c[1] + dy, c[2] + dz)
                        if n in cells and n not in seen:
                            seen.add(n)
                            stack.append(n)
        if len(comp) < min_faces:
            continue
        pts = C[comp]
        ext = pts.max(0) - pts.min(0)
        sites.append({"x": float(np.median(pts[:, 0])), "z": float(np.median(pts[:, 2])), "base": float(np.percentile(pts[:, 1], 20)),
                      "top": float(pts[:, 1].max()), "width": float(max(ext[0], ext[2], cell * 0.5)), "faces": len(comp)})
    sites.sort(key=lambda s: -s["faces"])
    return sites


def flame(src, dst, texture=None, colours=FLAME_COLOURS, strength: float = 3.0, max_sites: int = 6, scale: float = 1.0,
          source: str = "", min_val: float = 0.82, width_share=None) -> dict:
    """Flame cards on a model: at every site where its colours burn, two crossed cards carrying a flame picture (its
    brightness as its alpha, glowing, lit by nothing), sized to the site and stood on it. The game can flicker them."""
    g = Glb.load(src)
    sites = flame_sites(g, colours, min_val=min_val)[:max_sites]
    if width_share and sites:
        lo, hi = g.bounds()
        span_xz = float(max(hi[0] - lo[0], hi[2] - lo[2]))
        for s in sites:
            s["width"] = float(width_share) * span_xz       # the fire is this share of the thing's width (a ring of stones)
    if not sites:
        g.save(dst)
        return {"sites": 0, "line": "Flame: none of " + ", ".join(map(str, colours)) + " is in the model's colours — no "
                "flame was added (paint the burning part, or place the flame by hand).", "file": str(dst)}
    img, span, foot = _flame_texture(texture)
    ti = g.add_image(img)
    mat = {"name": "forge_flame", "alphaMode": "BLEND", "doubleSided": True,
           "pbrMetallicRoughness": {"baseColorTexture": {"index": ti}, "metallicFactor": 0.0, "roughnessFactor": 1.0},
           "emissiveTexture": {"index": ti}, "emissiveFactor": [1.0, 1.0, 1.0],
           "extensions": {"KHR_materials_emissive_strength": {"emissiveStrength": float(strength)}, "KHR_materials_unlit": {}},
           "extras": {"forge_flame": {"source": source or ("a flame made here (stand-in)" if not texture else str(texture)),
                                      "sites": len(sites)}}}
    g.use_extension("KHR_materials_emissive_strength")
    g.use_extension("KHR_materials_unlit")
    P, F, UV = [], [], []
    for s in sites:
        w = s["width"] * scale / max(span[0], 0.05)            # the card is wider than the flame drawn on it
        h = w                                                   # the flame pictures are square
        y0 = s["base"] - foot * h                               # the flame's foot on the fire
        for ang in (0.0, np.pi / 2):
            dx, dz = np.cos(ang) * w / 2, np.sin(ang) * w / 2
            b = len(P)
            P += [(s["x"] - dx, y0, s["z"] - dz), (s["x"] + dx, y0, s["z"] + dz),
                  (s["x"] + dx, y0 + h, s["z"] + dz), (s["x"] - dx, y0 + h, s["z"] - dz)]
            UV += [(0, 1), (1, 1), (1, 0), (0, 0)]
            F += [(b, b + 1, b + 2), (b, b + 2, b + 3)]
    g.add_mesh_node(np.array(P), np.array(F), np.array(UV), mat, "forge_flame")
    g.save(dst)
    return {"sites": len(sites), "where": [{k: round(v, 3) if isinstance(v, float) else v for k, v in s.items()} for s in sites],
            "line": f"Flame: {len(sites)} flame card{'s' if len(sites) != 1 else ''} set where the model's colours burn "
                    f"({'from ' + source if source else 'a stand-in flame made here'}); glowing, unlit, the game can flicker "
                    "them.", "file": str(dst)}
