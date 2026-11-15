"""See-through things as flat panels with a cut-out texture, never image-to-3D (BUILD 39).

Image-to-3D loses chain-link mesh, netting, grilles and wire: the launch-site run's fence and gate kept their posts and
rails and lost the mesh. A game draws such things the way games always have — a flat panel whose texture is see-through
where the wire isn't (glTF alphaMode MASK, both sides drawn). The posts and rails that did come through are kept: a
panel can stand inside a 3D model, along its long side.

An entry of kind "panel":

    {"id": "fence_chainlink", "kind": "panel", "real_size_m": {"width": 3.0, "height": 2.1},
     "panel": {"texture": "<a picture: a Filter Forge render, a photo>" | "standin:chainlink",
               "tile_m": 0.5,                    # metres one repeat of the texture covers
               "from_model": "<a .glb whose posts and wire to keep>", "model_size_m": {"height": 2.6},
               "bottom_m": 0.05, "top_m": 2.1,    # where the panel starts and stops (default: from the model)
               "segments": [{"from": [-1.5, 0], "to": [1.5, 0]}],   # metres, in the placed model (default: its long side)
               "texture_licence": "filter_forge"}}

A picture without transparency is keyed: its background (the colour round its edge) becomes see-through.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

log = logging.getLogger("forge.threed.panels")
STANDIN = "standin:chainlink"


def chainlink_texture(px: int = 512, diamonds: int = 6, wire: float = 0.07, seed: int = 7):
    """A stand-in chain-link texture (RGBA, tiles seamlessly): two sets of diagonal wires in a diamond weave, galvanised
    grey with a little rust, see-through between the wires. Made here so a panel can be built and seen before a real
    texture (Filter Forge's 'Rusty Chainlink') is rendered."""
    from PIL import Image
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:px, 0:px].astype(np.float64) / px
    u = (x + y) * diamonds                       # one wire set
    v = (x - y) * diamonds                       # the other
    # the woven zigzag: each wire wanders a little as it passes over and under the other
    du = 0.06 * np.sin(np.pi * 2 * v)
    dv = 0.06 * np.sin(np.pi * 2 * u)
    fu = np.abs(((u + du) % 1.0) - 0.5)
    fv = np.abs(((v + dv) % 1.0) - 0.5)
    w = wire * 0.5 * diamonds / 6
    a_u = np.clip((0.5 - fu - (0.5 - w)) / (w * 0.6), 0, 1)
    a_v = np.clip((0.5 - fv - (0.5 - w)) / (w * 0.6), 0, 1)
    alpha = np.maximum(a_u, a_v)
    shade = 0.75 + 0.25 * np.maximum(a_u * np.cos(np.pi * 2 * v), a_v * np.cos(np.pi * 2 * u))
    base = np.array([158.0, 162.0, 165.0])
    rust = np.array([128.0, 82.0, 52.0])
    noise = rng.random((px // 16 + 1, px // 16 + 1))
    noise = np.kron(noise, np.ones((16, 16)))[:px, :px]
    t = np.clip((noise - 0.72) * 3, 0, 1)[..., None]
    rgb = (base * (1 - t) + rust * t) * shade[..., None]
    img = np.dstack([np.clip(rgb, 0, 255), alpha * 255]).astype(np.uint8)
    return Image.fromarray(img, "RGBA")


def cutout(img, threshold: float = 34.0):
    """RGBA with see-through: the picture's own transparency when it has some, else its background colour keyed out."""
    from PIL import Image
    im = img.convert("RGBA")
    a = np.asarray(im)
    if a[..., 3].min() < 250:
        return im
    rgb = a[..., :3].astype(np.float64)
    edge = np.concatenate([rgb[:3].reshape(-1, 3), rgb[-3:].reshape(-1, 3), rgb[:, :3].reshape(-1, 3), rgb[:, -3:].reshape(-1, 3)])
    bg = np.median(edge, axis=0)
    d = np.linalg.norm(rgb - bg, axis=2)
    alpha = np.clip((d - threshold * 0.5) / (threshold * 0.5), 0, 1) * 255
    return Image.fromarray(np.dstack([a[..., :3], alpha.astype(np.uint8)]), "RGBA")


def _texture(cfg, gid, spec: dict):
    from PIL import Image
    t = spec.get("texture") or STANDIN
    if t == STANDIN:
        return chainlink_texture(), True, "stand-in chain-link (made by the forge; replace with the real texture)"
    from .world import _resolve
    p = _resolve(cfg, gid, t)
    if not p or not p.exists():
        log.warning("the panel's texture %s is not there — using the stand-in until it is", t)
        return chainlink_texture(), True, f"stand-in chain-link ({t} is not there yet)"
    img = Image.open(p)
    img.load()
    return cutout(img), False, str(t)


def material(tex_index: int, name: str = "cutout_panel") -> dict:
    return {"name": name, "pbrMetallicRoughness": {"baseColorTexture": {"index": tex_index}, "metallicFactor": 0.8,
                                                   "roughnessFactor": 0.55},
            "alphaMode": "MASK", "alphaCutoff": 0.5, "doubleSided": True}


def quad(p0, p1, bottom: float, top: float, tile_m: float):
    """One upright panel from p0 = (x, z) to p1 at heights bottom..top: positions, faces, UVs (repeats by tile_m), normals."""
    (x0, z0), (x1, z1) = p0, p1
    length = float(np.hypot(x1 - x0, z1 - z0))
    P = np.array([[x0, bottom, z0], [x1, bottom, z1], [x1, top, z1], [x0, top, z0]], dtype=np.float64)
    F = np.array([[0, 1, 2], [0, 2, 3]])
    U, V = length / tile_m, (top - bottom) / tile_m
    UV = np.array([[0, V], [U, V], [U, 0], [0, 0]], dtype=np.float64)
    n = np.array([-(z1 - z0), 0.0, x1 - x0])
    n /= max(np.linalg.norm(n), 1e-12)
    return P, F, UV, np.tile(n, (4, 1)), length


def fence_line(P: np.ndarray) -> dict:
    """Where a fence-like model's panel goes: along its long horizontal side, at the line where most of its rails are."""
    lo, hi = P.min(0), P.max(0)
    long_axis = 0 if (hi[0] - lo[0]) >= (hi[2] - lo[2]) else 2
    thin_axis = 2 - long_axis
    hist, edges = np.histogram(P[:, thin_axis], bins=64)
    k = int(np.argmax(hist))
    at = float((edges[k] + edges[k + 1]) / 2)
    a, b = float(lo[long_axis]), float(hi[long_axis])
    if long_axis == 0:
        return {"from": [a, at], "to": [b, at], "length": b - a}
    return {"from": [at, a], "to": [at, b], "length": b - a}


def make(cfg, gid: str, e: dict, out: Path) -> dict:
    """The panel (and the model it stands in, when there is one) as <out>/<id>.glb at its real size. Returns a report."""
    from . import meshio
    spec = dict(e.get("panel") or {})
    tile = float(spec.get("tile_m") or 0.5)
    img, stand_in, tex_note = _texture(cfg, gid, spec)
    lines = []
    final = Path(out) / f"{e['id']}.glb"
    size = e.get("real_size_m") or {}
    if spec.get("from_model"):
        from .world import _resolve, item_dir, read_state
        src = _resolve(cfg, gid, spec["from_model"])
        if (not src or not src.exists()) and read_state(cfg, gid, spec["from_model"]).get("model_raw"):
            src = _resolve(cfg, gid, read_state(cfg, gid, spec["from_model"])["model_raw"])
        if not src or not src.exists():
            raise FileNotFoundError(f"the model to keep the posts from is not there: {spec['from_model']}")
        placed = Path(out) / f"{e['id']}__posts.glb"
        rep = meshio.place(src, placed, size=spec.get("model_size_m") or size or None)
        g = meshio.Glb.load(placed)
        P = g.mesh()["P"]
        top_default = float(P[:, 1].max()) * 0.82
        segs = spec.get("segments") or [fence_line(P)]
        lines.append(f"Kept the posts and rails of {Path(src).name} at {rep['size_m']} m; "
                     f"{len(segs)} panel{'s' if len(segs) > 1 else ''} along {'the given lines' if spec.get('segments') else 'its long side'}.")
    else:
        g = meshio.Glb.new()
        w = float(size.get("width") or 2.0)
        top_default = float(size.get("height") or 2.0)
        segs = [{"from": [-w / 2, 0.0], "to": [w / 2, 0.0]}]
        lines.append(f"A free-standing panel {w:g} m wide.")
    bottom = float(spec.get("bottom_m", 0.05 if spec.get("from_model") else 0.0))
    top = float(spec.get("top_m") or top_default)
    t = g.add_image(img)
    mat = material(t)
    total = 0.0
    for k, sgm in enumerate(segs):
        Pq, Fq, UVq, Nq, length = quad(sgm["from"], sgm["to"], bottom, top, tile)
        g.add_mesh_node(Pq, Fq, UVq, dict(mat), f"panel_{k}", normals=Nq)
        total += length
    g.save(final)
    lo, hi = meshio.Glb.load(final).bounds()
    lines.append(f"Panel: {total:.2f} m long, from {bottom:g} m to {top:.2f} m up, the texture repeating every {tile:g} m "
                 f"({tex_note}).")
    if stand_in:
        lines.append("The texture is the forge's stand-in; the real one replaces it by pointing the entry's panel.texture at it "
                     "and choosing Make again.")
    return {"glb": str(final), "size_m": {"width": round(float(hi[0] - lo[0]), 3), "height": round(float(hi[1] - lo[1]), 3),
                                          "depth": round(float(hi[2] - lo[2]), 3)},
            "lines": lines, "texture": tex_note, "stand_in": stand_in}
