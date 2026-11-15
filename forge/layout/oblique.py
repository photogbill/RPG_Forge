"""The map camera, as a block-out: a scene plan → everything a painted, walkable map needs before it is painted.

One fixed camera for every walkable map (a game's art bible states it once): looking north, from high above, with no
vanishing points. The ground is drawn to scale — a square tile stays square — and height stands straight up the
picture:

    screen_x = x * tile            screen_y = (y - z * height_scale) * tile        (x east, y south, z up; tiles)

So a wall that faces the camera (it runs east–west, on the north side of a room) shows its whole face above the
floor's north edge; walls on the south and the sides are cut down to stubs so the room can be seen into; furniture
shows its top and its front. Because the floor is plan-true, a point on the floor is the same pixel in the plan and
in the painting — the walk area, the doors and the spawns come straight from the plan and need no tracing.

    plan (JSON)  →  guide.png   flat colour per surface: the picture a model paints over (img2img `init`)
                    depth.png   nearness to the camera, white = near (a ControlNet `depth` image, preprocessed)
                    lines.png   the edges of every surface, white on black (a ControlNet `lineart` image, preprocessed)
                    over.png    white where something stands ABOVE the actors (a tree's canopy, a beam): cut the
                                painting with it to make the map's overlay layer
                    normal.png  which way every surface faces (OpenGL normals: floors and tops toward the viewer,
                                fronts tilted down the picture) — exact, because the plan knows; a 2D light uses it
                    glow.png    the surfaces that give light (materials named glow_*, and "screen"), on black
                    textures    render(plan, textures={material: tiling picture}) fills the guide's surfaces with real
                                materials at a true scale — a place built from the plan and a texture library alone
                    lit(...)    the guide with a light plan painted on it (lamps, a night outdoors, shade at the foot
                                of things): what an img2img starts from when the light is part of the design
                    walk rings  the floor an actor can stand on, as nested polygons in pixels
                    anchors     named floor points in pixels (spawns, doors, where a person stands to use a thing)

The plan (tile units, floats allowed):

    {"id": "farmhouse", "tile": 96, "size": [30, 20], "height_scale": 1.0, "background": "night",
     "materials": {"quilt": [120, 60, 70]},                      # optional: extra or overridden colours
     "ground": [ {"mat": "plank", "rect": [x, y, w, d],           # drawn in order; "walk": false makes it scenery
                  "pattern": {"kind": "boards", "run": "x", "every": 0.33}},   # or "checker" (+ "alt": a second material)
                 {"mat": "rug", "ellipse": [cx, cy, rx, ry]},
                 {"mat": "grass", "poly": [[x, y], ...]} ],
     "solids": [ {"id": "north_wall", "mat": "plaster", "rect": [x, y, w, d], "h": 3.0,
                  "face": [ {"mat": "window_night", "x": 4.0, "w": 1.6, "z": 1.0, "h": 1.4} ]},   # things ON its front
                 {"id": "table", "mat": "wood", "rect": [x, y, w, d], "h": 0.8, "z": 0.0},
                 {"id": "trunk", "mat": "bark", "cyl": [cx, cy, r], "h": 3.2},
                 {"id": "canopy", "mat": "leaves", "cyl": [cx, cy, r], "z": 3.0, "h": 1.6, "over": true, "block": false} ],
     "blocks": [[x, y, w, d]],                                    # extra floor nobody may stand on
     "anchors": {"start": [x, y]} }

Nothing here knows a game: materials are colour names, the plan is the game's.
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
from PIL import Image

# camera pitch used for the depth image only (the picture itself is the oblique rule above): nearness grows to the
# south (toward the camera) and with height
NEAR_Y, NEAR_Z = 0.57, 0.82

# flat guide colours — only to tell surfaces apart and to start an img2img in the right hue
MATERIALS: dict[str, tuple[int, int, int]] = {
    "void": (8, 8, 12), "night": (14, 18, 30), "cut": (38, 34, 32),
    "plank": (128, 88, 56), "plank_dark": (92, 62, 42), "porch": (118, 112, 104), "deck": (124, 98, 72),
    "carpet": (96, 110, 92), "rug": (150, 64, 52), "rug_blue": (62, 84, 124), "linoleum": (196, 188, 160),
    "checker": (170, 172, 160), "tile": (200, 204, 204), "flagstone": (118, 116, 110), "concrete": (140, 140, 136),
    "grass": (74, 112, 58), "grass_dark": (48, 78, 44), "dirt": (112, 86, 60), "gravel": (150, 146, 136),
    "asphalt": (56, 58, 62), "path": (156, 142, 118), "garden": (70, 58, 40), "water": (50, 88, 120),
    "plaster": (198, 186, 160), "wallpaper": (150, 164, 140), "wallpaper_warm": (186, 150, 110),
    "stone": (126, 120, 110), "brick": (140, 76, 60), "siding": (206, 204, 196), "shingle": (60, 56, 58),
    "wood": (120, 78, 46), "wood_light": (176, 138, 92), "cabinet": (210, 200, 176), "counter": (90, 96, 100),
    "metal": (150, 156, 162), "appliance": (214, 216, 218), "sofa": (86, 104, 84), "chair": (140, 96, 64),
    "quilt": (150, 70, 78), "bed": (214, 206, 190), "books": (110, 60, 50), "screen": (40, 70, 90),
    "rack": (26, 30, 36), "glow_cyan": (60, 220, 230), "glow_warm": (255, 196, 110), "firebox": (22, 18, 16),
    "window_night": (36, 52, 92), "window_day": (170, 206, 230), "door": (104, 70, 46), "picture": (176, 150, 96),
    "bark": (82, 60, 44), "leaves": (52, 96, 52), "fence": (150, 132, 104), "car": (70, 84, 110),
}

WALKABLE = {"plank", "plank_dark", "porch", "deck", "carpet", "rug", "rug_blue", "linoleum", "checker", "tile",
            "flagstone", "concrete", "grass", "dirt", "gravel", "asphalt", "path"}


class PlanError(ValueError):
    pass


def load(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _colour(plan: dict, mat: str) -> tuple[int, int, int]:
    own = plan.get("materials") or {}
    if mat in own:
        return tuple(int(v) for v in own[mat])
    if mat in MATERIALS:
        return MATERIALS[mat]
    raise PlanError(f"material '{mat}' has no colour — add it to the plan's \"materials\"")


def _footprint(s: dict) -> tuple[float, float, float, float]:
    """(x0, y0, x1, y1) of a solid on the floor."""
    if "rect" in s:
        x, y, w, d = [float(v) for v in s["rect"]]
        return x, y, x + w, y + d
    if "cyl" in s:
        cx, cy, r = [float(v) for v in s["cyl"]]
        return cx - r, cy - r, cx + r, cy + r
    raise PlanError(f"solid '{s.get('id', '?')}' has neither \"rect\" nor \"cyl\"")


def check(plan: dict) -> list[str]:
    """Problems a person should fix before anything is painted (an empty list = the plan is sound)."""
    out = []
    try:
        w, h = [float(v) for v in plan["size"]]
    except Exception:
        return ["the plan has no \"size\": [tiles wide, tiles deep]"]
    seen = set()
    for s in plan.get("solids") or []:
        sid = s.get("id")
        if sid:
            if sid in seen:
                out.append(f"two solids are called '{sid}'")
            seen.add(sid)
        try:
            x0, y0, x1, y1 = _footprint(s)
        except PlanError as e:
            out.append(str(e)); continue
        if x1 <= x0 or y1 <= y0:
            out.append(f"solid '{sid or '?'}' has no size")
        if (x0 < -0.01 or y0 < -0.01 or x1 > w + 0.01 or y1 > h + 0.01) and not s.get("over"):
            out.append(f"solid '{sid or '?'}' stands outside the picture")     # a canopy may hang past the edge
        for f in s.get("face") or []:
            if "rect" not in s:
                out.append(f"solid '{sid or '?'}': only a box has a front to put things on"); break
            fx, fw = float(f["x"]), float(f["w"])
            if fx < x0 - 0.01 or fx + fw > x1 + 0.01 or float(f.get("z", 0)) + float(f["h"]) > float(s.get("h", 0)) + float(s.get("z", 0)) + 0.01:
                out.append(f"solid '{sid or '?'}': a face item ({f.get('mat')}) hangs off its front")
    for name, mat in [(s.get("id", "?"), s.get("mat")) for s in plan.get("solids") or []] + \
                     [("ground", g.get("mat")) for g in plan.get("ground") or []]:
        try:
            _colour(plan, str(mat))
        except PlanError as e:
            out.append(f"{name}: {e}")
    for k, p in (plan.get("anchors") or {}).items():
        if not (0 <= float(p[0]) <= w and 0 <= float(p[1]) <= h):
            out.append(f"anchor '{k}' is outside the picture")
    return out


class Blockout:
    """What render() returns. Images are PIL; the arrays stay for whoever wants to measure."""
    def __init__(self, plan, px, guide, depth, lines, over, face_id, normal=None, glow=None, world_y=None, height=None):
        self.plan, self.px = plan, px
        self.guide, self.depth, self.lines, self.over, self.face_id = guide, depth, lines, over, face_id
        self.normal, self.glow = normal, glow
        self.world_y, self.height = world_y, height      # per pixel: how far south, and how high, the thing shown there is (tiles)

    def save(self, out_dir: str | Path, stem: str | None = None) -> dict[str, Path]:
        d = Path(out_dir); d.mkdir(parents=True, exist_ok=True)
        stem = stem or str(self.plan.get("id") or "plan")
        paths = {}
        for name in ("guide", "depth", "lines", "over", "normal", "glow"):
            p = d / f"{stem}_{name}.png"
            getattr(self, name).save(p)
            paths[name] = p
        return paths


def _textures(spec: dict | None, px: int, root: Path | None) -> dict[str, np.ndarray]:
    """material → the texture as pixels, already at this drawing's scale (one repeat = "tiles" tiles)."""
    out = {}
    for mat, t in (spec or {}).items():
        if str(mat).startswith("_"):
            continue
        t = {"image": t} if isinstance(t, (str, Path, Image.Image)) else dict(t)
        im = t["image"]
        if not isinstance(im, Image.Image):
            path = Path(im)
            if not path.is_absolute() and root is not None:
                path = Path(root) / path
            if not path.exists():
                raise PlanError(f"texture for '{mat}' not found: {im}")
            im = Image.open(path)
        im = im.convert("RGB")
        if int(t.get("turn") or 0) % 180 == 90:
            im = im.transpose(Image.ROTATE_90)
        side = max(8, int(round(float(t.get("tiles", 4.0)) * px)))
        im = im.resize((side, max(8, int(round(side * im.size[1] / im.size[0])))), Image.LANCZOS)
        a = np.asarray(im, np.float32)
        if t.get("tint") is not None:
            a = a * _rgb01(t["tint"])[None, None, :]
        if t.get("gain") is not None:
            a = a * float(t["gain"])
        out[str(mat)] = np.clip(a, 0, 255)
    return out


def render(plan: dict, px: int | None = None, line_px: float | None = None, textures: dict | None = None,
           root: str | Path | None = None) -> Blockout:
    """Draw the plan at `px` pixels a tile (default: the plan's own "tile").

    `textures` (or the plan's own "textures") fills surfaces with a tiling picture instead of a flat colour:
        {"plank": {"image": "path.png", "tiles": 3.0, "turn": 90, "tint": [1, 0.9, 0.8], "gain": 1.1}, "grass": "grass.png"}
    One repeat of the picture covers "tiles" tiles (default 4), so a board or a brick has a true size; a floor is
    mapped by where it lies, a front by its width and height. Everything else — depth, lines, normals, the walk rings —
    is the same with or without textures. Relative paths are taken from `root`.
    """
    probs = check(plan)
    if probs:
        raise PlanError("; ".join(probs))
    px = int(px or plan.get("tile") or 96)
    tex = _textures(textures if textures is not None else plan.get("textures"), px, Path(root) if root else None)
    K = float(plan.get("height_scale", 1.0))
    W, H = int(round(float(plan["size"][0]) * px)), int(round(float(plan["size"][1]) * px))
    rgb = np.zeros((H, W, 3), np.uint8)
    rgb[:] = _colour(plan, str(plan.get("background") or "void"))
    yw = np.tile((np.arange(H, dtype=np.float32) + 0.5)[:, None] / px, (1, W))      # world y of what each pixel shows
    zz = np.zeros((H, W), np.float32)
    fid = np.zeros((H, W), np.int32)
    over = np.zeros((H, W), bool)
    nrm = np.zeros((H, W, 3), np.float32)
    nrm[..., 2] = 1.0                                                                  # everything starts as floor: facing the viewer
    glow = np.zeros((H, W, 3), np.uint8)
    lit = set(plan.get("emissive") or []) | {"screen"}
    counter = [0]
    xs = (np.arange(W, dtype=np.float32) + 0.5) / px
    sy = (np.arange(H, dtype=np.float32) + 0.5) / px                                  # screen y in tiles

    def put(mask, colour, yworld, zworld, is_over=False, shade=1.0, normal=(0.0, 0.0, 1.0), mat="", v=None):
        if not mask.any():
            return
        counter[0] += 1
        t = tex.get(mat)
        if t is not None:                                  # u runs east; v is how far south (floors, tops) or how high (fronts)
            th, tw = t.shape[:2]
            vv = np.broadcast_to(sy[:, None] if v is None else v, (H, W))[mask]
            uu = np.broadcast_to(xs[None, :], (H, W))[mask]
            rgb[mask] = np.clip(t[np.floor(vv * px).astype(np.int64) % th, np.floor(uu * px).astype(np.int64) % tw] * shade,
                                0, 255).astype(np.uint8)
        else:
            rgb[mask] = np.clip(np.array(colour, np.float32) * shade, 0, 255).astype(np.uint8)
        if isinstance(normal, np.ndarray):
            nrm[mask] = normal[mask]
        else:
            nrm[mask] = normal
        glow[mask] = np.array(colour, np.uint8) if (mat.startswith("glow_") or mat in lit) else 0
        yw[mask] = np.broadcast_to(yworld, mask.shape)[mask]
        zz[mask] = np.broadcast_to(zworld, mask.shape)[mask]
        fid[mask] = counter[0]
        over[mask] = is_over

    def rect_mask(x0, y0, x1, y1):
        m = np.zeros((H, W), bool)
        a, b = max(0, int(round(y0 * px))), min(H, int(round(y1 * px)))
        c, d = max(0, int(round(x0 * px))), min(W, int(round(x1 * px)))
        if b > a and d > c:
            m[a:b, c:d] = True
        return m

    # ---- the ground, in the order given (z = 0, so world y = screen y)
    for g in plan.get("ground") or []:
        col = _colour(plan, g["mat"])
        if "rect" in g:
            x, y, w, d = [float(v) for v in g["rect"]]
            m = rect_mask(x, y, x + w, y + d)
        elif "ellipse" in g:
            cx, cy, rx, ry = [float(v) for v in g["ellipse"]]
            m = ((xs[None, :] - cx) / rx) ** 2 + ((sy[:, None] - cy) / ry) ** 2 <= 1.0
        elif "poly" in g:
            from PIL import ImageDraw
            im = Image.new("1", (W, H), 0)
            ImageDraw.Draw(im).polygon([(float(a) * px, float(b) * px) for a, b in g["poly"]], fill=1)
            m = np.array(im, bool)
        else:
            raise PlanError("a ground item needs \"rect\", \"ellipse\" or \"poly\"")
        pat = g.get("pattern")
        if not pat:
            put(m, col, sy[:, None], 0.0, mat=str(g["mat"]))
            continue
        # a pattern is drawn as its own surfaces, so the boards or squares are in the guide AND in the line work
        every = max(0.05, float(pat.get("every", 0.5)))
        kind = str(pat.get("kind", "boards"))
        col2 = _colour(plan, pat["alt"]) if pat.get("alt") else tuple(int(c * 0.9) for c in col)
        ix = np.floor(xs[None, :] / every).astype(np.int64)
        iy = np.floor(sy[:, None] / every).astype(np.int64)
        if kind == "boards":                                 # "run": "x" = boards running east-west (stripes stacked north-south)
            idx = np.broadcast_to(iy if str(pat.get("run", "x")) == "x" else ix, (H, W))
            cell = idx
        elif kind == "checker":
            idx = np.broadcast_to(ix + iy, (H, W))
            cell = np.broadcast_to(ix * 100003 + iy, (H, W))
        else:
            raise PlanError(f"pattern kind '{kind}' is not one of boards, checker")
        for k in np.unique(cell[m]).tolist():
            part = m & (cell == k)
            odd = bool(int(idx[part][0]) % 2)
            put(part, col2 if odd else col, sy[:, None], 0.0, mat=str(g["mat"]))

    # ---- the solids, north to south (what stands nearer the camera is drawn later and covers what is behind)
    FRONT = (0.0, -0.7071, 0.7071)                 # a front faces down the picture and toward the viewer (OpenGL: y up)
    def south_edge(s):
        x0, y0, x1, y1 = _footprint(s)
        return (y1, float(s.get("z", 0.0)))

    for s in sorted(plan.get("solids") or [], key=south_edge):
        col = _colour(plan, s["mat"])
        z0, h = float(s.get("z", 0.0)), float(s.get("h", 0.0))
        top_z = z0 + h
        is_over = bool(s.get("over"))
        if "rect" in s:
            x0, y0, x1, y1 = _footprint(s)
            # the front (south face): world y = y1, z runs from top_z (at its top edge on screen) down to z0
            fm = rect_mask(x0, y1 - top_z * K, x1, y1 - z0 * K)
            put(fm, col, y1, (y1 - sy[:, None]) / K, is_over, shade=float(s.get("front_shade", 0.72)), normal=FRONT, mat=str(s["mat"]),
                v=(y1 - sy[:, None]) / K)
            for f in s.get("face") or []:
                fz, fh = float(f.get("z", 0.0)), float(f["h"])
                im = rect_mask(float(f["x"]), y1 - (z0 + fz + fh) * K, float(f["x"]) + float(f["w"]), y1 - (z0 + fz) * K)
                put(im, _colour(plan, f["mat"]), y1 - float(f.get("recess", 0.08)), (y1 - sy[:, None]) / K, is_over,
                    normal=FRONT, mat=str(f["mat"]), v=(y1 - sy[:, None]) / K)
            # the top: z = top_z, world y = screen y + top_z * K
            tm = rect_mask(x0, y0 - top_z * K, x1, y1 - top_z * K)
            put(tm, _colour(plan, s.get("top", s["mat"])), sy[:, None] + top_z * K, top_z, is_over, mat=str(s.get("top", s["mat"])),
                v=sy[:, None] + top_z * K)
        else:
            cx, cy, r = [float(v) for v in s["cyl"]]
            dx = xs[None, :] - cx
            inside = np.abs(dx) <= r
            half = np.sqrt(np.clip(r * r - dx * dx, 0, None))          # how far the circle reaches north/south at this x
            # the side we see: between the southern arc of the top circle and the southern arc of the base circle
            top_arc, base_arc = cy + half - top_z * K, cy + half - z0 * K
            fm = inside & (sy[:, None] >= cy - top_z * K) & (sy[:, None] >= top_arc - 2 * half) & (sy[:, None] <= base_arc) \
                 & (sy[:, None] >= top_arc)
            nx = np.clip(dx / max(r, 1e-6), -1.0, 1.0)                 # a round side turns away to the left and right
            side = np.sqrt(np.clip(1.0 - nx * nx, 0.0, 1.0)) * 0.7071
            round_n = np.broadcast_to(np.stack([nx, -side, side], axis=-1), (H, W, 3))
            put(fm, col, cy + half, (cy + half - sy[:, None]) / K, is_over, shade=float(s.get("front_shade", 0.72)),
                normal=round_n, mat=str(s["mat"]), v=(cy + half - sy[:, None]) / K)
            tm = (dx ** 2 + (sy[:, None] - (cy - top_z * K)) ** 2) <= r * r
            put(tm, _colour(plan, s.get("top", s["mat"])), sy[:, None] + top_z * K, top_z, is_over, mat=str(s.get("top", s["mat"])),
                v=sy[:, None] + top_z * K)

    # ---- the three companions
    near = NEAR_Y * yw + NEAR_Z * zz
    lo, hi = float(near.min()), float(near.max())
    depth = ((near - lo) / max(1e-6, hi - lo) * 255.0).astype(np.uint8)
    edge = np.zeros((H, W), bool)
    edge[:, 1:] |= fid[:, 1:] != fid[:, :-1]
    edge[1:, :] |= fid[1:, :] != fid[:-1, :]
    lines = Image.fromarray((edge * 255).astype(np.uint8), "L")
    lw = float(line_px if line_px is not None else max(1.0, px / 32.0))
    if lw > 1.0:
        from PIL import ImageFilter
        k = int(round(lw)) | 1
        lines = lines.filter(ImageFilter.MaxFilter(k))
    normal = Image.fromarray(np.clip((nrm * 0.5 + 0.5) * 255.0, 0, 255).astype(np.uint8), "RGB")
    return Blockout(plan, px, Image.fromarray(rgb, "RGB"), Image.fromarray(depth, "L"), lines,
                    Image.fromarray((over * 255).astype(np.uint8), "L"), fid, normal, Image.fromarray(glow, "RGB"),
                    world_y=yw, height=zz)


# ------------------------------------------------------------------------------------------------- the light
def _rgb01(c) -> np.ndarray:
    """A colour as three 0..1 floats: [r, g, b] in 0..1, or "ffc27a"."""
    if isinstance(c, str):
        h = c.strip().lstrip("#")
        return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], np.float32)
    if isinstance(c, (int, float)):
        return np.array([float(c)] * 3, np.float32)
    return np.array([float(v) for v in c], np.float32)


def _blur(a: np.ndarray, radius_px: float) -> np.ndarray:
    from PIL import ImageFilter
    im = Image.fromarray(np.clip(a * 255.0, 0, 255).astype(np.uint8), "L")
    return np.asarray(im.filter(ImageFilter.GaussianBlur(max(0.5, float(radius_px)))), np.float32) / 255.0


def lit(b: Blockout, lighting: dict | None = None, seed: int = 0) -> Image.Image:
    """The guide with a light plan painted on it — the picture an img2img starts from when the light is designed.

    A flat guide tells a model where things are and nothing about the light, so the model invents one. This paints
    the plan's light on the guide first: every surface is lit by the lamps it faces, areas can have their own
    ambient (indoors warm, outdoors a blue night), the floor darkens at the foot of whatever stands on it and under
    whatever hangs over it, and glowing surfaces spill a little. No rays are traced: a lamp can be told which area
    it lights ("within"), which is what a wall does.

        {"ambient": [0.5, 0.5, 0.5],                                   # everywhere not in a zone
         "zones":  [{"rect": [x, y, w, d], "ambient": [r, g, b]}],     # by where a thing STANDS (so a room's walls count)
         "lights": [{"at": [x, y], "z": 1.6, "colour": "ffc27a", "power": 1.0, "radius": 4.5, "within": [x, y, w, d]}],
         "contact": 0.4, "bloom": 0.5, "grain": 0.02}

    `lighting` defaults to the plan's own "lighting"; with neither, the guide comes back as it is.
    """
    L = lighting if lighting is not None else b.plan.get("lighting")
    if not L:
        return b.guide.copy()
    if b.world_y is None or b.height is None:
        raise PlanError("this block-out was not made by render(): it does not know where its pixels are")
    px = float(b.px)
    base = np.asarray(b.guide, np.float32) / 255.0
    H, W = base.shape[:2]
    X = np.broadcast_to(((np.arange(W, dtype=np.float32) + 0.5) / px)[None, :], (H, W))
    Y, Z = b.world_y, b.height
    n = np.asarray(b.normal, np.float32) / 255.0 * 2.0 - 1.0
    up = n[..., 2] > 0.9                                              # floors and tops; everything else faces south (or round)
    nx = np.where(up, 0.0, n[..., 0])
    ny = np.where(up, 0.0, np.sqrt(np.clip(1.0 - nx * nx, 0.0, 1.0)))
    nz = np.where(up, 1.0, 0.0)

    def inside(rect):
        x, y, w, d = [float(v) for v in rect]
        return (X >= x) & (X < x + w) & (Y >= y) & (Y < y + d)

    light = np.empty((H, W, 3), np.float32)
    light[:] = _rgb01(L.get("ambient", 0.5))
    for zn in L.get("zones") or []:
        light[inside(zn["rect"])] = _rgb01(zn.get("ambient", 0.5))
    for lamp in L.get("lights") or []:
        lx, ly = [float(v) for v in lamp["at"]]
        lz = float(lamp.get("z", 1.6))
        R = max(0.1, float(lamp.get("radius", 4.0)))
        dx, dy, dz = lx - X, ly - Y, lz - Z
        dist = np.sqrt(dx * dx + dy * dy + dz * dz) + 1e-6
        facing = (nx * dx + ny * dy + nz * dz) / dist
        wrap = np.clip((facing + 0.3) / 1.3, 0.0, 1.0)               # a surface turned a little away still catches some
        fall = np.clip(1.0 - (dist / R) ** 2, 0.0, 1.0) ** 2
        amount = wrap * fall * float(lamp.get("power", 1.0))
        if lamp.get("within"):
            amount = amount * inside(lamp["within"])
        light += amount[..., None] * _rgb01(lamp.get("colour", lamp.get("color", "ffffff")))

    over = np.asarray(b.over, np.uint8) > 127
    contact = float(L.get("contact", 0.4))
    if contact > 0:
        floor = (Z < 0.03) & up
        fronts = (~up) & (Z > 0.03) & ~over                          # the faces that meet the floor on screen
        foot = _blur(fronts.astype(np.float32), 0.22 * px)
        under = np.zeros((H, W), np.float32)                         # the ground under what hangs overhead
        rows = np.clip((Y * px).astype(np.int64), 0, H - 1)
        cols = np.broadcast_to(np.arange(W)[None, :], (H, W))
        under[rows[over], cols[over]] = 1.0
        under = _blur(under, 0.45 * px)
        shade = 1.0 - (contact * np.clip(1.6 * foot, 0.0, 1.0) + 0.8 * contact * under) * floor
        light *= np.clip(shade, 0.0, 1.0)[..., None]

    out = base * light
    bloom = float(L.get("bloom", 0.5))
    if bloom > 0:
        g = np.asarray(b.glow, np.float32) / 255.0
        if g.any():
            spill = np.stack([_blur(g[..., k], 0.7 * px) for k in range(3)], axis=-1)
            out = 1.0 - (1.0 - np.clip(out, 0, 1)) * (1.0 - np.clip(bloom * 1.6 * spill, 0, 1))      # screen
            out = np.maximum(out, g)                                  # the lamp itself stays as bright as it was
    grain = float(L.get("grain", 0.02))
    if grain > 0:
        rng = np.random.default_rng(int(seed))
        fine = rng.normal(0.0, grain, (H, W)).astype(np.float32)
        coarse = _blur(rng.random((H, W)).astype(np.float32), 0.35 * px) - 0.5
        out = out * (1.0 + 2.5 * grain * coarse[..., None] * 4.0) + fine[..., None]
    return Image.fromarray(np.clip(out * 255.0 + 0.5, 0, 255).astype(np.uint8), "RGB")


# ------------------------------------------------------------------------------------------------- the floor
def walk_grid(plan: dict, cell: float = 0.25, margin: float = 0.15, behind: float = 1.0) -> np.ndarray:
    """True where an actor's feet may be, on a grid of `cell` tiles. A floor is ground of a walkable material; a solid
    takes its footprint plus `margin`, plus the strip just north of it that its own height hides from the camera
    (`behind` × its height, at most one tile) — so nobody stands where the painting would have to cover them. A solid
    marked "over" is cut into the overlay layer instead, which is drawn above the actors: the floor behind it stays."""
    w, h = float(plan["size"][0]), float(plan["size"][1])
    nx, ny = int(round(w / cell)), int(round(h / cell))
    cx = (np.arange(nx) + 0.5) * cell
    cy = (np.arange(ny) + 0.5) * cell
    X, Y = np.meshgrid(cx, cy)
    ok = np.zeros((ny, nx), bool)
    for g in plan.get("ground") or []:
        walk = g.get("walk", g["mat"] in WALKABLE)
        if "rect" in g:
            x, y, gw, gd = [float(v) for v in g["rect"]]
            m = (X >= x) & (X < x + gw) & (Y >= y) & (Y < y + gd)
        elif "ellipse" in g:
            ex, ey, rx, ry = [float(v) for v in g["ellipse"]]
            m = ((X - ex) / rx) ** 2 + ((Y - ey) / ry) ** 2 <= 1.0
        else:
            from PIL import ImageDraw
            im = Image.new("1", (nx, ny), 0)
            ImageDraw.Draw(im).polygon([(float(a) / cell, float(b) / cell) for a, b in g["poly"]], fill=1)
            m = np.array(im, bool)
        ok[m] = bool(walk)
    for s in plan.get("solids") or []:
        if s.get("block") is False:
            continue
        x0, y0, x1, y1 = _footprint(s)
        low = float(s.get("z", 0.0)) < 0.5 and 0.4 < float(s.get("h", 0.0)) <= 2.0     # a cut-down wall stub hides nothing
        hide = min(1.0, behind * float(s.get("h", 0.0))) if low and not s.get("over") else 0.0
        if "cyl" in s:
            ccx, ccy, r = [float(v) for v in s["cyl"]]
            ok[((X - ccx) ** 2 + (Y - ccy) ** 2) <= (r + margin) ** 2] = False
            ok[(np.abs(X - ccx) <= r) & (Y >= ccy - r - hide) & (Y <= ccy)] = False
        else:
            ok[(X >= x0 - margin) & (X < x1 + margin) & (Y >= y0 - margin - hide) & (Y < y1 + margin)] = False
    for b in plan.get("blocks") or []:
        x, y, bw, bd = [float(v) for v in b]
        ok[(X >= x) & (X < x + bw) & (Y >= y) & (Y < y + bd)] = False
    # two floors that meet only corner to corner would make rings that touch: open the corner's worse half
    changed = True
    while changed:
        changed = False
        a, b_, c, d = ok[:-1, :-1], ok[:-1, 1:], ok[1:, :-1], ok[1:, 1:]
        diag1 = a & d & ~b_ & ~c
        diag2 = b_ & c & ~a & ~d
        if diag1.any():
            ii, jj = np.nonzero(diag1)
            ok[ii + 1, jj + 1] = False; changed = True
        if diag2.any():
            ii, jj = np.nonzero(diag2)
            ok[ii + 1, jj] = False; changed = True
    return ok


def keep_reachable(ok: np.ndarray, start: tuple[int, int]) -> np.ndarray:
    """Only the floor that can be walked to from `start` (grid row, col)."""
    out = np.zeros_like(ok)
    if not ok[start]:
        return out
    stack = [start]
    out[start] = True
    ny, nx = ok.shape
    while stack:
        i, j = stack.pop()
        for a, b in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
            if 0 <= a < ny and 0 <= b < nx and ok[a, b] and not out[a, b]:
                out[a, b] = True
                stack.append((a, b))
    return out


def rings(ok: np.ndarray, scale: float) -> list[list[list[int]]]:
    """The outlines of a grid of floor as closed polygons (corners only), in pixels: grid units × `scale`. Outer
    boundaries and holes both come out; they nest or stay apart, which is what a painted map's walk rings must do."""
    ny, nx = ok.shape
    pad = np.zeros((ny + 2, nx + 2), bool)
    pad[1:-1, 1:-1] = ok
    nxt: dict[tuple[int, int], list[tuple[int, int]]] = {}

    def edge(a, b):
        nxt.setdefault(a, []).append(b)

    ii, jj = np.nonzero(pad)
    for i, j in zip(ii.tolist(), jj.tolist()):
        y, x = i - 1, j - 1
        if not pad[i - 1, j]:
            edge((x, y), (x + 1, y))                 # top edge, floor on the right hand → clockwise outer rings
        if not pad[i, j + 1]:
            edge((x + 1, y), (x + 1, y + 1))
        if not pad[i + 1, j]:
            edge((x + 1, y + 1), (x, y + 1))
        if not pad[i, j - 1]:
            edge((x, y + 1), (x, y))
    out = []
    while nxt:
        start = next(iter(nxt))
        ring = [start]
        cur = start
        while True:
            ends = nxt[cur]
            b = ends.pop()
            if not ends:
                del nxt[cur]
            if b == start:
                break
            ring.append(b)
            cur = b
        pts = []
        n = len(ring)
        for k in range(n):                             # drop the points in the middle of a straight run
            p, q, r = ring[k - 1], ring[k], ring[(k + 1) % n]
            if (q[0] - p[0]) * (r[1] - q[1]) != (q[1] - p[1]) * (r[0] - q[0]):
                pts.append([int(round(q[0] * scale)), int(round(q[1] * scale))])
        if len(pts) >= 4:
            out.append(pts)
    out.sort(key=lambda r: -abs(_area(r)))
    return out


def _area(ring) -> float:
    return 0.5 * sum(ring[k][0] * ring[(k + 1) % len(ring)][1] - ring[(k + 1) % len(ring)][0] * ring[k][1] for k in range(len(ring)))


def walk_rings(plan: dict, cell: float = 0.25, start: str | None = None, **kw) -> list:
    """The plan's floor as a painted map's walk rings (pixels at the plan's tile size). With `start` (an anchor's
    name) only the floor that anchor can reach is kept, so a sealed-off patch never becomes a place to stand."""
    ok = walk_grid(plan, cell, **kw)
    if start:
        ax, ay = plan["anchors"][start]
        ok = keep_reachable(ok, (int(float(ay) / cell), int(float(ax) / cell)))
    return rings(ok, cell * float(plan.get("tile") or 96))


def anchors_px(plan: dict) -> dict[str, list[int]]:
    t = float(plan.get("tile") or 96)
    return {k: [int(round(float(v[0]) * t)), int(round(float(v[1]) * t))] for k, v in (plan.get("anchors") or {}).items()}


def reaches(plan: dict, a: str, b: str, cell: float = 0.25, **kw) -> bool:
    """Can an actor walk from anchor a to anchor b?"""
    ok = walk_grid(plan, cell, **kw)
    ax, ay = plan["anchors"][a]
    bx, by = plan["anchors"][b]
    r = keep_reachable(ok, (int(float(ay) / cell), int(float(ax) / cell)))
    return bool(r[int(float(by) / cell), int(float(bx) / cell)])


def agreement(painting: Image.Image, blockout: Blockout, tolerance_px: int | None = None, detail: bool = False):
    """Does the painting hold the plan? 0 = no better than chance, 1 = every line of the plan is an edge in the painting.

    The painting's strongest edges (three times as many pixels as the plan has line) are compared with the plan's
    line work, with a few pixels of tolerance: `hold` is the share of the plan's lines that have a painted edge on
    them, corrected for how much of the picture those edges would cover by luck — a busy painting does not score for
    being busy. With detail=True also returns `clean`: the share of the painting's strong edges that lie on the plan
    (low when the painter added walls and furniture of its own)."""
    from PIL import ImageFilter
    w, h = blockout.lines.size
    tol = int(tolerance_px if tolerance_px is not None else max(3, round(w / 360)))
    im = painting.convert("RGB").resize((w, h), Image.LANCZOS).filter(ImageFilter.GaussianBlur(1.2))
    g = np.asarray(im, np.float32)                                    # an edge in any channel counts: two surfaces of
    gx = np.abs(np.diff(g, axis=1, prepend=g[:, :1])).max(axis=2)    # the same brightness can still differ in hue
    gy = np.abs(np.diff(g, axis=0, prepend=g[:1, :])).max(axis=2)
    mag = np.maximum(gx, gy)
    plan_lines = np.asarray(blockout.lines) > 0
    n = int(plan_lines.sum())
    if n == 0:
        return (0.0, 0.0) if detail else 0.0
    keep = min(mag.size - 1, 3 * n)
    cut = np.partition(mag.ravel(), mag.size - keep)[mag.size - keep]
    strong = mag >= max(float(cut), 4.0)
    k = tol * 2 + 1
    grow = lambda m: np.asarray(Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(k))) > 0
    near_strong, near_plan = grow(strong), grow(plan_lines)

    def above_chance(hit: float, luck: float) -> float:
        return max(0.0, (hit - luck) / max(1e-6, 1.0 - luck))

    hold = above_chance(float((plan_lines & near_strong).sum()) / n, float(near_strong.mean()))
    clean = above_chance(float((strong & near_plan).sum()) / max(1, int(strong.sum())), float(near_plan.mean()))
    return (round(hold, 3), round(clean, 3)) if detail else round(hold, 3)
