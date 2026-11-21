"""Writing Material Maker graphs from Python (BUILD 87, Part 2): a small builder, and the forge's first six graphs.

    python -m forge.materials graphs          writes forge/materials/graphs/<name>.ptex and <name>.json again

A graph here is built only from node types whose parameters were read from the installed node library (Material Maker
1.8's nodes/*.mmg) and that the program's own shipped examples use the same way: voronoi, perlin, fbm, colorize,
blend, warp, bricks, weave, scratches, transform, invert, uniform, uniform_greyscale, normal_map, occlusion, material.
`forge.materials.mm.lint` checks every graph against the library before Material Maker is started.

Each of the six is one surface in two states — "broken" (cracked, ashed, marked) and "mended" (filled, swept, washed)
— moved by named parameters from 0 to 1 that the side file maps onto node parameters (almost always how much one
layer is blended in). A game decides which of its eras wears which state; nothing here knows.

How the surfaces are built, so the next graph is written the same way:
  * height first (white = high): the body of the surface, then cracks cut into it;
  * colour from the same noises as the height, so a dark crack sits in a low crack;
  * roughness as its own picture (glass is smooth where it is clean and rough where ash sits on it);
  * the normal map from the finished height (normal_map), occlusion from it too (occlusion), and the Material node's
    depth input gets the height turned over — Material Maker wants depth there (white = deep), and its Godot export
    turns it back, so <name>_heightmap.png comes out white = high.
These six were written without seeing them rendered (see docs/MATERIALS.md); expect to tune numbers after the first
export — open the .ptex in Material Maker, move things, save, and it is still the forge's graph.
"""
from __future__ import annotations

import json
from pathlib import Path

GRAPHS = Path(__file__).resolve().parent / "graphs"
MULTIPLY, NORMAL, SCREEN, OVERLAY, LIGHTEN, DARKEN = 2, 0, 3, 4, 9, 10


def colour(r: float, g: float, b: float, a: float = 1.0) -> dict:
    return {"a": a, "b": b, "g": g, "r": r, "type": "Color"}


def gradient(stops: list) -> dict:
    """[(pos, grey) | (pos, (r, g, b))] → Material Maker's gradient."""
    pts = []
    for pos, v in stops:
        r, g, b = (v, v, v) if isinstance(v, (int, float)) else v
        pts.append({"a": 1, "b": b, "g": g, "pos": pos, "r": r})
    return {"interpolation": 1, "points": pts, "type": "Gradient"}


class Graph:
    """Nodes and connections, written down as a .ptex. Every node gets its own fixed seed and a place on the canvas."""

    def __init__(self, name: str, label: str):
        self.name, self.label = name, label
        self.nodes: list[dict] = []
        self.links: list[dict] = []
        self.side: dict = {"parameters": {}, "settings": {}}

    def node(self, type_: str, name: str | None = None, **params) -> str:
        i = len(self.nodes)
        name = name or f"{type_}_{i}"
        if any(n["name"] == name for n in self.nodes):
            raise ValueError(f"node name used twice: {name}")
        self.nodes.append({"name": name, "node_position": {"x": 220 * (i % 7) - 660, "y": 170 * (i // 7) - 340},
                           "parameters": params, "seed": round((0.1031 + 0.2749 * i) % 1.0, 4), "type": type_})
        return name

    def link(self, src: str, dst: str, to_port: int = 0, from_port: int = 0) -> None:
        self.links.append({"from": src, "from_port": from_port, "to": dst, "to_port": to_port})

    # --- the handful of moves every surface uses
    def perlin(self, sx, sy=None, it=6, pers=0.6, name=None) -> str:
        return self.node("perlin", name, scale_x=sx, scale_y=sx if sy is None else sy, iterations=it, persistence=pers)

    def fbm(self, noise, scale, it=5, pers=0.6, name=None) -> str:
        return self.node("fbm", name, noise=noise, scale_x=scale, scale_y=scale, folds=0, iterations=it, persistence=pers)

    def voronoi(self, scale, intensity=0.6, name=None) -> str:
        return self.node("voronoi", name, scale_x=scale, scale_y=scale, stretch_x=1, stretch_y=1, intensity=intensity, randomness=1)

    def ramp(self, src: str, stops: list, name=None, from_port: int = 0) -> str:
        n = self.node("colorize", name, gradient=gradient(stops))
        self.link(src, n, 0, from_port)
        return n

    def blend(self, top: str, base: str, amount: float, mode: int = NORMAL, mask: str | None = None, name=None) -> str:
        n = self.node("blend", name, blend_type=mode, amount=amount)
        self.link(top, n, 0)
        self.link(base, n, 1)
        if mask:
            self.link(mask, n, 2)
        return n

    def warp(self, src: str, by: str, amount: float, name=None, from_port: int = 0) -> str:
        n = self.node("warp", name, amount=amount, eps=0.045, mode=0)
        self.link(src, n, 0, from_port)
        self.link(by, n, 1)
        return n

    def flat(self, r, g=None, b=None, name=None) -> str:
        if g is None:
            return self.node("uniform_greyscale", name, color=r)
        return self.node("uniform", name, color=colour(r, g, b))

    def invert(self, src: str, name=None) -> str:
        n = self.node("invert", name)
        self.link(src, n, 0)
        return n

    def crack_lines(self, scale: float, thin: float, wide: float, bend: float = 0.22) -> tuple[str, str]:
        """A cracked-plate pattern, bent so no line is straight: (thin dark lines on white, wide WHITE lines on black).
        The first is multiplied into height and colour; the second is the mask a filler is laid through."""
        v = self.voronoi(scale)
        w = self.warp(v, self.perlin(4, it=3, pers=0.5), bend, from_port=1)          # voronoi's second output: its borders
        return self.ramp(w, [(0.0, 0.0), (thin, 1.0)]), self.ramp(w, [(0.0, 1.0), (wide, 0.0)])

    def ash_mask(self, scale: float = 5, lo: float = 0.46, hi: float = 0.72) -> str:
        """Where ash, soot or dust settles: broad soft patches (white = covered)."""
        return self.ramp(self.perlin(scale, it=6, pers=0.62), [(lo, 0.0), (hi, 1.0)])

    def finish(self, albedo: str, height: str, rough: str, relief: float = 1.0, metal: float = 0.0, depth_scale: float = 0.3) -> None:
        nm = self.node("normal_map", "normal", param0=11, param1=relief, param2=0, param4=1)
        self.link(height, nm, 0)
        ao = self.node("occlusion", "occlusion", param0=10, param2=2.0)
        self.link(height, ao, 0)
        depth = self.invert(height, "depth")
        m = self.node("material", "Material", albedo_color=colour(1, 1, 1), metallic=metal, roughness=1, emission_energy=1,
                      normal=1, ao=1, depth_scale=depth_scale, flags_transparent=False, sss=0, size=11)
        self.link(albedo, m, 0)
        self.link(rough, m, 2)
        self.link(nm, m, 4)
        self.link(ao, m, 5)
        self.link(depth, m, 6)

    def named(self, name: str, doc: str, default: float, *sets: dict) -> None:
        self.side["parameters"][name] = {"doc": doc, "default": default, "sets": list(sets)}

    def to_json(self) -> dict:
        return {"connections": self.links, "label": self.label, "longdesc": "", "name": self.name,
                "node_position": {"x": 0, "y": 0}, "nodes": self.nodes, "parameters": {}, "seed": 0.0, "shortdesc": "",
                "type": "graph"}


def amount(node: str, lo: float, hi: float) -> dict:
    return {"node": node, "param": "amount", "to": [lo, hi]}


# ------------------------------------------------------------------ the six
def caliche() -> Graph:
    """Caliche: the pale, hard lime crust of dry country — cream and tan, knobbly, cracked into plates."""
    g = Graph("caliche", "Caliche (lime hardpan)")
    swell = g.perlin(3, it=8, pers=0.75)
    knobs = g.fbm(2, 12, it=4, pers=0.6)
    body = g.blend(knobs, swell, 0.45)
    thin, wide = g.crack_lines(5, 0.07, 0.17)
    height = g.blend(thin, body, 0.6, MULTIPLY, name="crack_height")
    base = g.ramp(g.perlin(6, it=10, pers=0.85), [(0.2, (0.62, 0.55, 0.44)), (0.6, (0.82, 0.78, 0.69)), (0.9, (0.90, 0.88, 0.82))])
    c1 = g.blend(thin, base, 0.5, MULTIPLY, name="crack_colour")
    c2 = g.blend(g.flat(0.93, 0.91, 0.86), c1, 0.0, mask=wide, name="mend_colour")
    ash = g.ash_mask()
    c3 = g.blend(g.flat(0.33, 0.32, 0.31), c2, 0.0, mask=ash, name="ash_colour")
    r0 = g.ramp(knobs, [(0.0, 0.82), (1.0, 0.97)])
    rough = g.blend(g.flat(1.0), r0, 0.0, mask=ash, name="ash_rough")
    g.finish(c3, height, rough, relief=1.0)
    g.named("cracks", "how deep and dark the plate cracks are", 0.5, amount("crack_height", 0.05, 0.9), amount("crack_colour", 0.0, 0.75))
    g.named("ash", "ash and soot lying in patches", 0.0, amount("ash_colour", 0.0, 0.8), amount("ash_rough", 0.0, 0.9))
    g.named("mend", "the cracks filled with pale new lime", 0.0, amount("mend_colour", 0.0, 0.85))
    g.side.update(label=g.label, what=caliche.__doc__, settings={"broken": {"cracks": 0.9, "ash": 0.55, "mend": 0.0},
                                                                 "mended": {"cracks": 0.25, "ash": 0.0, "mend": 0.7}})
    return g


def ash_crust() -> Graph:
    """Ash crust: fire ash that rain has set into a thin grey crust, curled at the edges of its plates, flecked with charcoal."""
    g = Graph("ash_crust", "Ash crust")
    und = g.fbm(1, 6, it=6, pers=0.6)
    v = g.voronoi(9, intensity=0.5)
    w = g.warp(v, g.perlin(4, it=3, pers=0.5), 0.2, from_port=1)
    thin = g.ramp(w, [(0.0, 0.0), (0.05, 1.0)])
    curl = g.ramp(w, [(0.0, 0.85), (0.3, 0.5)])                       # plates lift toward their edges
    body = g.blend(curl, und, 0.5, OVERLAY)
    height = g.blend(thin, body, 0.6, MULTIPLY, name="crack_height")
    base = g.ramp(g.fbm(0, 8, it=8, pers=0.7), [(0.15, (0.20, 0.19, 0.18)), (0.5, (0.47, 0.46, 0.44)), (0.85, (0.72, 0.71, 0.68))])
    flecks = g.ramp(g.fbm(2, 24, it=3, pers=0.5), [(0.08, 0.0), (0.16, 1.0)])
    c1 = g.blend(flecks, base, 0.5, MULTIPLY, name="fleck_colour")
    c2 = g.blend(thin, c1, 0.5, MULTIPLY, name="crack_colour")
    c3 = g.blend(g.flat(0.80, 0.79, 0.76), c2, 0.0, name="pale_colour")
    rough = g.ramp(und, [(0.0, 0.9), (1.0, 1.0)])
    g.finish(c3, height, rough, relief=0.9)
    g.named("cracks", "how sharply the crust has cracked into plates", 0.5, amount("crack_height", 0.15, 0.95), amount("crack_colour", 0.1, 0.8))
    g.named("ash", "how fresh the fire is: charcoal flecks in the ash", 0.5, amount("fleck_colour", 0.15, 0.9))
    g.named("mend", "rained in and walked on: paler, bound, quieter", 0.0, amount("pale_colour", 0.0, 0.45))
    g.side.update(label=g.label, what=ash_crust.__doc__, settings={"broken": {"cracks": 0.9, "ash": 0.9, "mend": 0.0},
                                                                   "mended": {"cracks": 0.35, "ash": 0.2, "mend": 0.8}})
    return g


def canvas() -> Graph:
    """Canvas: heavy olive-drab tent cloth — a plain weave you can count, slubbed threads, soft sag."""
    g = Graph("canvas", "Canvas (tent cloth)")
    wv = g.node("weave", "weave", columns=32, rows=32, width=0.9)
    tiled = g.node("transform", "weave_tiled", translate_x=0, translate_y=0, rotate=0, scale_x=0.25, scale_y=0.25, repeat=True)
    g.link(wv, tiled, 0)                                               # 32 threads, four times over: 128 across the tile
    slub = g.perlin(2, 24, it=4, pers=0.6)
    h0 = g.blend(slub, tiled, 0.25, MULTIPLY)
    h1 = g.blend(g.perlin(2, 3, it=3, pers=0.4), h0, 0.35, OVERLAY)
    fray = g.node("scratches", "fray", length=0.35, width=0.25, layers=3, waviness=0.4, angle=0, randomness=1)
    tears = g.invert(fray)                                             # dark tears on white
    height = g.blend(tears, h1, 0.0, MULTIPLY, name="crack_height")
    base = g.ramp(g.perlin(5, it=8, pers=0.7), [(0.2, (0.36, 0.35, 0.24)), (0.8, (0.49, 0.47, 0.33))])
    c1 = g.blend(tiled, base, 0.35, MULTIPLY)
    stain = g.ramp(g.perlin(3, it=7, pers=0.75), [(0.5, 0.0), (0.72, 1.0)])
    c2 = g.blend(g.flat(0.19, 0.17, 0.13), c1, 0.0, mask=stain, name="stain_colour")
    ash = g.ash_mask(4)
    c3 = g.blend(g.flat(0.12, 0.12, 0.12), c2, 0.0, mask=ash, name="ash_colour")
    c4 = g.blend(tears, c3, 0.0, MULTIPLY, name="crack_colour")
    c5 = g.blend(g.flat(0.62, 0.60, 0.47), c4, 0.0, name="mend_colour")
    rough = g.ramp(tiled, [(0.0, 0.98), (1.0, 0.86)])
    g.finish(c5, height, rough, relief=0.8, depth_scale=0.15)
    g.named("cracks", "frayed threads and small tears", 0.2, amount("crack_height", 0.0, 0.8), amount("crack_colour", 0.0, 0.6))
    g.named("stains", "water stains and mildew", 0.3, amount("stain_colour", 0.0, 0.8))
    g.named("ash", "soot from cook fires and worse", 0.0, amount("ash_colour", 0.0, 0.75))
    g.named("mend", "washed and sun-bleached", 0.0, amount("mend_colour", 0.0, 0.35))
    g.side.update(label=g.label, what=canvas.__doc__, settings={"broken": {"cracks": 0.8, "stains": 0.75, "ash": 0.6, "mend": 0.0},
                                                                "mended": {"cracks": 0.15, "stains": 0.2, "ash": 0.0, "mend": 0.8}})
    return g


def fused_glass() -> Graph:
    """Fused glass: sand the heat turned to glass — bottle-green to black pools, bubbles, hairline crazing."""
    g = Graph("fused_glass", "Fused glass")
    flow = g.perlin(2, it=4, pers=0.45)
    ripple = g.perlin(6, it=5, pers=0.5)
    h0 = g.blend(ripple, flow, 0.25)
    bub = g.ramp(g.voronoi(14, intensity=0.7), [(0.0, 0.0), (0.1, 1.0)])           # pits at the cell centres
    h1 = g.blend(bub, h0, 0.35, MULTIPLY)
    thin, _wide = g.crack_lines(6, 0.035, 0.1, bend=0.15)
    height = g.blend(thin, h1, 0.3, MULTIPLY, name="crack_height")
    base = g.ramp(flow, [(0.15, (0.03, 0.06, 0.05)), (0.55, (0.10, 0.22, 0.16)), (0.9, (0.30, 0.42, 0.30))])
    white_lines = g.invert(thin)
    c1 = g.blend(white_lines, base, 0.2, SCREEN, name="crack_colour")              # a fracture in glass is bright, not dark
    dust = g.ash_mask(4, 0.5, 0.75)
    c2 = g.blend(g.flat(0.42, 0.40, 0.36), c1, 0.0, mask=dust, name="ash_colour")
    r0 = g.ramp(ripple, [(0.0, 0.05), (1.0, 0.16)])
    r1 = g.blend(g.flat(0.95), r0, 0.0, mask=dust, name="ash_rough")
    r2 = g.blend(white_lines, r1, 0.3, LIGHTEN, name="crack_rough")
    rough = g.blend(g.flat(0.04), r2, 0.0, name="mend_rough")
    g.finish(c2, height, rough, relief=0.6, depth_scale=0.2)
    g.named("cracks", "crazing: how many fractures show", 0.4, amount("crack_height", 0.05, 0.85), amount("crack_colour", 0.0, 0.6), amount("crack_rough", 0.0, 0.7))
    g.named("ash", "dust and ash lying on the glass, dulling it", 0.0, amount("ash_colour", 0.0, 0.85), amount("ash_rough", 0.0, 0.9))
    g.named("mend", "swept and worn smooth underfoot", 0.0, amount("mend_rough", 0.0, 0.5))
    g.side.update(label=g.label, what=fused_glass.__doc__, settings={"broken": {"cracks": 0.85, "ash": 0.6, "mend": 0.0},
                                                                     "mended": {"cracks": 0.3, "ash": 0.05, "mend": 0.8}})
    return g


def whitewash_brick() -> Graph:
    """Whitewash over brick: limewash on a red brick wall — whole where it is kept up, flaking back to brick where it is not."""
    g = Graph("whitewash_brick", "Whitewash over brick")
    br = g.node("bricks", "bricks", pattern=0, repeat=1, rows=12, columns=6, row_offset=0.5, mortar=0.06, bevel=0.08, round=0.02, corner=0)
    grain = g.fbm(1, 16, it=6, pers=0.65)
    h_br = g.blend(grain, br, 0.22, MULTIPLY)
    brick_c = g.ramp(br, [(0.0, (0.42, 0.17, 0.12)), (0.5, (0.55, 0.24, 0.16)), (1.0, (0.63, 0.33, 0.22))], from_port=1)
    wall_c = g.blend(brick_c, g.flat(0.62, 0.60, 0.56), 1.0, mask=br)
    paint = g.ramp(g.perlin(4, it=8, pers=0.8), [(0.30, 0.0), (0.40, 1.0)], name="paint_mask")     # white = paint still on
    paint_c = g.ramp(g.perlin(8, it=5, pers=0.5), [(0.0, (0.86, 0.85, 0.80)), (1.0, (0.95, 0.94, 0.90))])
    c1 = g.blend(paint_c, wall_c, 1.0, mask=paint, name="paint_colour")
    h1 = g.blend(g.flat(0.78), h_br, 0.55, mask=paint)                 # paint half fills the joints
    thin, _wide = g.crack_lines(7, 0.06, 0.15, bend=0.2)
    height = g.blend(thin, h1, 0.3, MULTIPLY, name="crack_height")
    c2 = g.blend(thin, c1, 0.2, MULTIPLY, name="crack_colour")
    soot = g.ash_mask(3, 0.48, 0.74)
    c3 = g.blend(g.flat(0.14, 0.13, 0.12), c2, 0.0, mask=soot, name="ash_colour")
    rough = g.blend(g.flat(0.72), g.flat(0.93), 1.0, mask=paint)
    g.finish(c3, height, rough, relief=1.0)
    g.named("coverage", "how much of the wall the whitewash still covers", 0.75,
            {"node": "paint_mask", "param": "gradient", "point": 0, "key": "pos", "to": [0.62, 0.02]},
            {"node": "paint_mask", "param": "gradient", "point": 1, "key": "pos", "to": [0.72, 0.12]})
    g.named("cracks", "cracks through paint and mortar", 0.3, amount("crack_height", 0.0, 0.8), amount("crack_colour", 0.0, 0.6))
    g.named("ash", "soot climbing the wall", 0.0, amount("ash_colour", 0.0, 0.7))
    g.side.update(label=g.label, what=whitewash_brick.__doc__,
                  settings={"broken": {"coverage": 0.45, "cracks": 0.8, "ash": 0.55}, "mended": {"coverage": 0.97, "cracks": 0.05, "ash": 0.0}})
    return g


def chalked_wall() -> Graph:
    """A chalked wall: grey lime plaster that people have written on — strokes, tallies and the smears of wiping them off."""
    g = Graph("chalked_wall", "Chalked wall")
    plaster = g.fbm(0, 5, it=8, pers=0.7)
    trowel = g.perlin(2, 10, it=4, pers=0.5)
    h0 = g.blend(trowel, plaster, 0.35)
    thin, wide = g.crack_lines(4, 0.05, 0.14)
    height = g.blend(thin, h0, 0.3, MULTIPLY, name="crack_height")
    base = g.ramp(plaster, [(0.2, (0.47, 0.45, 0.41)), (0.8, (0.63, 0.61, 0.56))])
    marks = g.node("scratches", "marks", length=0.55, width=0.35, layers=5, waviness=0.15, angle=80, randomness=0.6)
    smear = g.ramp(g.perlin(3, it=6, pers=0.7), [(0.45, 0.0), (0.8, 1.0)])
    chalk = g.blend(smear, marks, 0.6, LIGHTEN)
    c1 = g.blend(g.flat(0.93, 0.93, 0.90), base, 0.5, mask=chalk, name="chalk_colour")
    c2 = g.blend(thin, c1, 0.3, MULTIPLY, name="crack_colour")
    c3 = g.blend(g.flat(0.70, 0.69, 0.65), c2, 0.0, mask=wide, name="mend_colour")
    soot = g.ash_mask(3, 0.5, 0.76)
    c4 = g.blend(g.flat(0.13, 0.12, 0.12), c3, 0.0, mask=soot, name="ash_colour")
    r0 = g.ramp(plaster, [(0.0, 0.86), (1.0, 0.95)])
    rough = g.blend(g.flat(1.0), r0, 0.5, mask=chalk, name="chalk_rough")
    g.finish(c4, height, rough, relief=0.8, depth_scale=0.15)
    g.named("chalk", "how much chalk is on the wall: fresh marks, or their ghosts", 0.5, amount("chalk_colour", 0.05, 0.95), amount("chalk_rough", 0.0, 0.8))
    g.named("cracks", "cracks in the plaster", 0.3, amount("crack_height", 0.0, 0.85), amount("crack_colour", 0.0, 0.7))
    g.named("ash", "soot", 0.0, amount("ash_colour", 0.0, 0.65))
    g.named("mend", "the cracks filled with new plaster", 0.0, amount("mend_colour", 0.0, 0.9))
    g.side.update(label=g.label, what=chalked_wall.__doc__,
                  settings={"broken": {"chalk": 0.9, "cracks": 0.8, "ash": 0.5, "mend": 0.0}, "mended": {"chalk": 0.18, "cracks": 0.2, "ash": 0.0, "mend": 0.8}})
    return g


RECIPES = (canvas, fused_glass, whitewash_brick, chalked_wall, ash_crust, caliche)


def build_all(dest: Path | None = None) -> list[Path]:
    """Write every recipe's .ptex and side file. Returns the .ptex paths."""
    dest = Path(dest or GRAPHS)
    dest.mkdir(parents=True, exist_ok=True)
    out = []
    for fn in RECIPES:
        g = fn()
        p = dest / f"{g.name}.ptex"
        p.write_text(json.dumps(g.to_json(), indent="\t") + "\n", encoding="utf-8", newline="\n")
        side = {"name": g.name, "label": g.side.get("label"), "what": " ".join(str(g.side.get("what") or "").split()),
                "made_by": "forge/materials/mmgraph.py - written from the node library, tuned after the first export",
                "licence": "the graph is part of the forge (its licence); Material Maker itself is MIT",
                "needs": ["albedo", "roughness", "normal", "ao", "depth"],
                "parameters": g.side["parameters"], "settings": g.side["settings"]}
        p.with_suffix(".json").write_text(json.dumps(side, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        out.append(p)
    return out
