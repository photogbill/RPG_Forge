"""Grow a broadleaf tree by rule instead of guessing it from a picture.

    <Blender's Python> grow_tree.py <out_dir> [--seed N] [--bare] [--views 4] [--name linden] [--sheet species.json]
    blender --background --python grow_tree.py -- <the same arguments>

The wood is grown the way a real crown fills its space (space colonisation: twigs reach for free room inside the
crown's outline), thicknesses follow the pipe rule (a limb is as thick as what it carries), and the leaves are
small flat cards carrying a painted sprig, which is how real-time trees are built. One seed = one tree; another
seed = its sibling, never its copy. --bare leaves the leaves off (winter, or a dead tree).
Writes <name>_seed<N>.glb and <name>_seed<N>_<k>.png views into <out_dir>.

--sheet: a species sheet (JSON) whose numbers replace the broadleaf defaults below, one by one (the Trees tab's sliders
write it). Copied into the forge from the first game's stage proof (BUILD 36); the sheet, the "--" arguments and a
TREE line with the sheet used are new, the growing is unchanged.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

try:                                            # Blender's own Python has numpy but not scipy
    from scipy.spatial import cKDTree
except ImportError:
    cKDTree = None


def nearest(nodes: np.ndarray, pts: np.ndarray):
    """For every point: distance to, and index of, the nearest node."""
    if cKDTree is not None:
        return cKDTree(nodes).query(pts)
    dist = np.empty(len(pts)); idx = np.empty(len(pts), dtype=int)
    for a in range(0, len(pts), 512):                                          # plain numpy, in slices to keep memory small
        d = np.linalg.norm(pts[a:a + 512, None, :] - nodes[None, :, :], axis=2)
        idx[a:a + 512] = d.argmin(axis=1)
        dist[a:a + 512] = d[np.arange(len(d)), idx[a:a + 512]]
    return dist, idx

# ------------------------------------------------------------------------------------------------ the species sheet
LINDEN = {
    "height": 14.0,            # metres, roots to top of crown
    "trunk_radius": 0.95,      # at chest height: "a trunk as wide as a car"
    "fork_height": 3.0,        # where the heavy limbs leave the trunk
    "limbs": 6,                # heavy low limbs
    "limb_tilt": (48, 72),     # degrees from straight up
    "crown_centre_z": 7.9,
    "crown_radius": 7.9,       # sideways
    "crown_half_height": 6.9,
    "crown_floor": 5.9,        # no foliage below this
    "masses": 26,              # the crown is made of separate masses of leaf with air between them
    "mass_radius": (2.1, 3.2),
    "attractors": 7400,        # how finely the crown is filled
    "step": 0.40,              # length of one piece of twig
    "reach": 4.5,              # how far a twig "sees" free room
    "close": 0.62,             # room counts as taken within this distance
    "twig_radius": 0.022,
    "pipe": 2.35,              # pipe-rule exponent
    "leaf_card": (0.80, 1.25), # metres, smallest and largest sprig card
    "cards_per_twig": 4,
}


def grow(sp: dict, rng: np.random.Generator):
    """Return (positions, parent index) of every node of the wood."""
    D = sp["step"]
    pos: list[np.ndarray] = [np.zeros(3)]
    par: list[int] = [-1]
    # the trunk, with a slow lean and a slight wander
    lean = rng.normal(0, 0.035, 2)
    z = 0.0
    while z < sp["fork_height"]:
        z += D
        p = pos[-1] + np.array([lean[0] + rng.normal(0, 0.012), lean[1] + rng.normal(0, 0.012), 1.0]) * D
        pos.append(p); par.append(len(pos) - 2)
    fork = len(pos) - 1
    # the heavy limbs: they leave low, reach out, then turn upward
    n = sp["limbs"]
    az0 = rng.uniform(0, math.tau)
    for k in range(n):
        az = az0 + math.tau * k / n + rng.normal(0, 0.22)
        tilt = math.radians(rng.uniform(*sp["limb_tilt"]))
        start = max(fork - int(rng.integers(0, 3)), 2)
        d = np.array([math.cos(az) * math.sin(tilt), math.sin(az) * math.sin(tilt), math.cos(tilt)])
        cur = start
        for _ in range(int(rng.integers(6, 10))):
            d = d + np.array([0, 0, 0.07]) + rng.normal(0, 0.06, 3)          # bend upward as it goes
            d /= np.linalg.norm(d)
            pos.append(pos[cur] + d * D); par.append(cur); cur = len(pos) - 1
    # one leader carrying on upward
    cur, d = fork, np.array([0.0, 0.0, 1.0])
    for _ in range(7):
        d = d + rng.normal(0, 0.09, 3); d /= np.linalg.norm(d)
        pos.append(pos[cur] + d * D); par.append(cur); cur = len(pos) - 1

    # free room: points inside the crown's outline, more of them toward the outside (that is where leaves live)
    masses = leaf_masses(sp, rng)
    per = sp["attractors"] // len(masses)
    parts = []
    for (mc, mr) in masses:
        v = rng.normal(size=(per, 3)); v /= np.linalg.norm(v, axis=1)[:, None]
        r = rng.uniform(0, 1, per) ** (1 / 2.6)
        parts.append(mc + v * r[:, None] * np.array([mr, mr, mr * 0.72]))
    att = np.vstack(parts)
    att = att[att[:, 2] > sp["crown_floor"] - 0.8]

    nodes = np.array(pos)
    children = np.zeros(len(nodes), dtype=int)
    for i in par:
        if i >= 0: children[i] += 1
    for _ in range(400):
        if len(att) == 0:
            break
        dist, idx = nearest(nodes, att)
        keep = dist > sp["close"]
        att, dist, idx = att[keep], dist[keep], idx[keep]
        seen = dist < sp["reach"]
        if not seen.any():
            break
        dirs = att[seen] - nodes[idx[seen]]
        dirs /= np.linalg.norm(dirs, axis=1)[:, None]
        acc = np.zeros_like(nodes)
        np.add.at(acc, idx[seen], dirs)
        growing = np.unique(idx[seen])
        growing = growing[children[growing] < 3]
        if len(growing) == 0:
            break
        nd = acc[growing]
        nd /= np.maximum(np.linalg.norm(nd, axis=1)[:, None], 1e-9)
        nd += np.array([0, 0, 0.05]) + rng.normal(0, 0.10, nd.shape)          # a little upward pull, a little wander
        nd /= np.linalg.norm(nd, axis=1)[:, None]
        new = nodes[growing] + nd * D
        far = nearest(nodes, new)[0] > 0.55 * D                                # never grow back onto the wood
        if not far.any():
            break
        new, growing = new[far], growing[far]
        children[growing] += 1
        par.extend(int(g) for g in growing)
        nodes = np.vstack([nodes, new])
        children = np.concatenate([children, np.zeros(len(new), dtype=int)])
    return nodes, np.array(par), masses


def leaf_masses(sp: dict, rng: np.random.Generator):
    """Centres and sizes of the crown's masses of leaf: spread over a dome, kept apart so air shows between them."""
    c = np.array([0.0, 0.0, sp["crown_centre_z"]])
    rad = np.array([sp["crown_radius"], sp["crown_radius"], sp["crown_half_height"]])
    out: list[tuple[np.ndarray, float]] = [(c + np.array([rng.normal(0, 0.5), rng.normal(0, 0.5), rad[2] * 0.70]), sp["mass_radius"][1])]
    tries = 0
    while len(out) < sp["masses"] and tries < 4000:
        tries += 1
        v = rng.normal(size=3); v /= np.linalg.norm(v)
        p = c + v * rad * rng.uniform(0.58, 0.80)
        if p[2] < sp["crown_floor"] + 1.2:
            continue
        mr = rng.uniform(*sp["mass_radius"])
        if all(np.linalg.norm(p - q) > 0.78 * (mr + qr) for q, qr in out):
            out.append((p, mr))
    return out


def thickness(nodes, par, sp):
    """Pipe rule: every twig end has the twig radius; a parent carries the sum of its children."""
    e = sp["pipe"]
    order = np.argsort(-np.arange(len(nodes)))                                 # children always come after parents
    acc = np.zeros(len(nodes))
    kids = np.zeros(len(nodes), dtype=int)
    for i in par:
        if i >= 0: kids[i] += 1
    acc[kids == 0] = sp["twig_radius"] ** e
    for i in order:
        p = par[i]
        if p >= 0:
            acc[p] += acc[i]
    r = np.maximum(acc ** (1 / e), sp["twig_radius"])
    # stretch the range so that twig ends keep the twig radius and chest height gets the asked trunk radius
    chest = r[min(3, len(r) - 1)]
    g = math.log(sp["trunk_radius"] / sp["twig_radius"]) / max(math.log(chest / sp["twig_radius"]), 1e-6)
    r = sp["twig_radius"] * (r / sp["twig_radius"]) ** g
    return r, kids


def chains(par, r, kids):
    """Split the wood into runs: at each fork the thickest child carries on, the others start a new run."""
    n = len(par)
    childs: list[list[int]] = [[] for _ in range(n)]
    for i, p in enumerate(par):
        if p >= 0: childs[p].append(i)
    out, starts = [], [(0, -1)]
    while starts:
        s, parent = starts.pop()
        run = [parent] if parent >= 0 else []
        cur = s
        while True:
            run.append(cur)
            cs = childs[cur]
            if not cs:
                break
            cs = sorted(cs, key=lambda c: -r[c])
            for other in cs[1:]:
                starts.append((other, cur))
            cur = cs[0]
        out.append(run)
    return out


def wood_mesh(nodes, r, runs, rng):
    """Tubes along every run; sides by thickness; a flare with buttress roots at the foot. Returns verts, faces, uvs."""
    V, F, UV = [], [], []
    phase = rng.uniform(0, math.tau)
    for run in runs:
        pts = nodes[run]
        rad = r[run].copy()
        if len(run) < 2:
            continue
        rad[0] = min(rad[0], rad[1] * 1.15)                                   # a side branch starts at its own thickness
        sides = 16 if rad.max() > 0.3 else 10 if rad.max() > 0.1 else 6 if rad.max() > 0.04 else 4
        tang = np.gradient(pts, axis=0)
        tang /= np.linalg.norm(tang, axis=1)[:, None]
        ref = np.array([1.0, 0, 0]) if abs(tang[0][0]) < 0.9 else np.array([0, 1.0, 0])
        nrm = np.cross(tang[0], ref); nrm /= np.linalg.norm(nrm)
        base = len(V)
        along = 0.0
        for k in range(len(pts)):
            if k:
                along += float(np.linalg.norm(pts[k] - pts[k - 1]))
                nrm = nrm - tang[k] * np.dot(nrm, tang[k])                     # carry the frame along without twisting
                nrm /= np.linalg.norm(nrm)
            bn = np.cross(tang[k], nrm)
            for s in range(sides):
                a = math.tau * s / sides
                rr = rad[k]
                z = pts[k][2]
                if run[0] == 0:                                               # the trunk: flare and buttress roots
                    rr *= 1 + 0.85 * math.exp(-max(z, 0) / 0.55) + 0.30 * math.exp(-max(z, 0) / 0.9) * math.sin(5 * a + phase)
                    rr *= 1 + 0.035 * math.sin(9 * a + z * 1.7)                # old bark is never round
                V.append(pts[k] + (nrm * math.cos(a) + bn * math.sin(a)) * rr)
                UV.append((s / sides, along))
        for k in range(len(pts) - 1):
            for s in range(sides):
                a0 = base + k * sides + s
                a1 = base + k * sides + (s + 1) % sides
                F.append((a0, a1, a1 + sides, a0 + sides))
    return np.array(V), F, UV


def leaf_cards(nodes, par, r, kids, sp, rng, masses):
    """Sprig cards on the thin wood. Each card belongs to the nearest mass of leaf and is shaded as part of it."""
    thin = np.where(r < sp["twig_radius"] * 3.0)[0]
    centres = np.array([m[0] for m in masses]); sizes = np.array([m[1] for m in masses])
    V, F, UV, COL, NRM = [], [], [], [], []
    sun = np.array([-0.35, -0.45, 0.82]); sun /= np.linalg.norm(sun)
    for i in thin:
        d = np.linalg.norm(centres - nodes[i], axis=1) / sizes
        m = int(np.argmin(d))
        if d[m] > 1.35 or nodes[i][2] < sp["crown_floor"] - 0.6:
            continue                                                           # bare wood between the masses and below the crown
        n_cards = sp["cards_per_twig"] + (2 if kids[i] == 0 else 0)
        for _ in range(n_cards):
            p = nodes[i] + rng.normal(0, 0.22, 3)
            out = p - centres[m]; out /= max(np.linalg.norm(out), 1e-6)
            n = out * 0.7 + np.array([0, 0, 0.6]) + rng.normal(0, 0.5, 3)
            n /= np.linalg.norm(n)
            t = np.cross(n, rng.normal(size=3)); t /= np.linalg.norm(t)
            b = np.cross(n, t)
            s = rng.uniform(*sp["leaf_card"]) * 0.5
            base = len(V)
            for (u, v) in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                V.append(p + t * u * s + b * v * s)
                UV.append(((u + 1) / 2, (v + 1) / 2))
            F.append((base, base + 1, base + 2, base + 3))
            # painted light: the sunny shoulder of each mass is yellow-green, its underside deep green
            lit = float(np.dot(out, sun))
            light = 0.92 + 0.52 * lit + 0.14 * (p[2] / sp["height"]) + rng.normal(0, 0.08)
            light = min(max(light, 0.36), 1.65)
            warm = max(lit, 0.0) * 0.30 + rng.normal(0, 0.05)
            COL += [(min(light + warm, 2.0), light, max(light - 1.3 * abs(warm), 0.2), 1.0)] * 4
            soft = out * 0.85 + n * 0.15; soft /= np.linalg.norm(soft)             # each mass shades as one soft body
            NRM += [soft] * 4
    return np.array(V), F, UV, COL, np.array(NRM)


# ------------------------------------------------------------------------------------------------------- pictures
def sprig_texture(path: Path, rng: np.random.Generator, size: int = 768):
    """Paint one sprig of small heart-shaped linden leaves on nothing (transparent), for the leaf cards."""
    from PIL import Image, ImageDraw
    S = size * 2
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    def leaf(cx, cy, scale, angle, shade):
        """A heart with a drawn-out tip; `angle` is where the tip points (0 = up the picture)."""
        pts = []
        for k in range(40):
            t = math.tau * k / 40
            x = 16 * math.sin(t) ** 3
            y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)   # cleft at +y, point at -y
            if y < -9: y -= 5.0
            x, y = x * scale, (y - 6) * scale                                   # the stalk joins at the cleft
            ca, sa = math.cos(angle), math.sin(angle)
            pts.append((cx + x * ca + y * sa, cy - (-x * sa + y * ca) * -1))
        g = shade
        col = (int(70 * g), int(140 * g), int(46 * g), 255)
        edge = (int(34 * g), int(84 * g), int(30 * g), 255)
        vein = (int(126 * g), int(176 * g), int(78 * g), 255)
        d.polygon(pts, fill=col)
        d.line(pts + [pts[0]], fill=edge, width=max(int(S * 0.003), 2))
        tip = pts[20]
        d.line([(cx, cy), tip], fill=vein, width=max(int(S * 0.0028), 2))
        for f in (0.35, 0.6):
            mx, my = cx + (tip[0] - cx) * f, cy + (tip[1] - cy) * f
            for side in (-1, 1):
                d.line([(mx, my), (mx + (tip[1] - cy) * 0.22 * side + (tip[0] - cx) * 0.16, my - (tip[0] - cx) * 0.22 * side + (tip[1] - cy) * 0.16)],
                       fill=vein, width=max(int(S * 0.002), 1))

    c = S * 0.5
    twigs = [(-0.50, 0.56), (0.0, 0.64), (0.55, 0.54), (-1.05, 0.40), (1.10, 0.42)]
    for (ta, tl) in twigs:
        ex, ey = c + math.sin(ta) * tl * S, c * 1.55 - math.cos(ta) * tl * S * 1.25
        d.line([(c, c * 1.9), (ex, ey)], fill=(70, 54, 38, 255), width=int(S * 0.006))
    order = []
    for (ta, tl) in twigs:
        for j in range(6):
            f = 0.22 + 0.78 * (j + rng.uniform(0, 0.6)) / 6
            bx = c + math.sin(ta) * tl * S * f
            by = c * 1.9 - (c * 1.9 - (c * 1.55 - math.cos(ta) * tl * S * 1.25)) * f
            side = -1 if j % 2 else 1
            order.append((by, bx, ta + side * rng.uniform(0.7, 1.25), rng.uniform(0.80, 1.30), rng.uniform(0.0040, 0.0054)))
    for (by, bx, ang, shade, sc) in sorted(order, key=lambda o: -o[0]):       # far leaves first, near ones over them
        leaf(bx, by, S * sc, ang, shade)
    im = im.resize((size, size), Image.LANCZOS)
    im.save(path)
    return path


def build(sp: dict, seed: int, out_dir: Path, name: str, bare: bool = False):
    rng = np.random.default_rng(seed)
    nodes, par, masses = grow(sp, rng)
    r, kids = thickness(nodes, par, sp)
    runs = chains(par, r, kids)
    bpy.ops.wm.read_factory_settings(use_empty=True)

    V, F, UV = wood_mesh(nodes, r, runs, rng)
    wood = bpy.data.meshes.new("wood")
    wood.from_pydata(V.tolist(), [], F)
    uv = wood.uv_layers.new(name="UVMap")
    flat = [UV[v] for poly in wood.polygons for v in poly.vertices]
    uv.data.foreach_set("uv", [c for pair in flat for c in pair])
    for p in wood.polygons: p.use_smooth = True
    wood_ob = bpy.data.objects.new("M_bark", wood)
    bpy.context.scene.collection.objects.link(wood_ob)
    wood.materials.append(bark_material())

    stats = {"nodes": len(nodes), "wood_tris": len(F) * 2, "leaf_tris": 0, "cards": 0}
    if not bare:
        tex = out_dir / f"{name}_sprig.png"
        try:
            sprig_texture(tex, np.random.default_rng(7))
        except ImportError:                       # a Blender Python without PIL: the same sprig, painted once and kept
            import shutil
            shutil.copyfile(Path(__file__).with_name("sprig_broadleaf.png"), tex)
        LV, LF, LUV, LCOL, LNRM = leaf_cards(nodes, par, r, kids, sp, rng, masses)
        leaf = bpy.data.meshes.new("leaves")
        leaf.from_pydata(LV.tolist(), [], LF)
        uv = leaf.uv_layers.new(name="UVMap")
        uv.data.foreach_set("uv", [c for pair in LUV for c in pair])              # 4 loops per quad, same order as verts
        col = leaf.color_attributes.new(name="Col", type="FLOAT_COLOR", domain="POINT")
        col.data.foreach_set("color", [c for rgba in LCOL for c in rgba])
        leaf.normals_split_custom_set_from_vertices(LNRM.tolist())
        leaf_ob = bpy.data.objects.new("N_leaves", leaf)
        bpy.context.scene.collection.objects.link(leaf_ob)
        leaf.materials.append(leaf_material(tex))
        stats["leaf_tris"] = len(LF) * 2
        stats["cards"] = len(LF)
    return stats


def bark_material():
    m = bpy.data.materials.new("bark"); m.use_nodes = True
    nt = m.node_tree; b = nt.nodes["Principled BSDF"]
    uv = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping"); mp.inputs["Scale"].default_value = (9.0, 0.55, 1.0)   # furrows run along the limb
    n1 = nt.nodes.new("ShaderNodeTexNoise"); n1.inputs["Scale"].default_value = 2.2; n1.inputs["Detail"].default_value = 9
    n1.inputs["Roughness"].default_value = 0.62
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.36; ramp.color_ramp.elements[0].color = (0.035, 0.030, 0.026, 1)
    ramp.color_ramp.elements[1].position = 0.66; ramp.color_ramp.elements[1].color = (0.44, 0.40, 0.33, 1)
    bump = nt.nodes.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = 0.9; bump.inputs["Distance"].default_value = 0.06
    nt.links.new(uv.outputs["UV"], mp.inputs["Vector"]); nt.links.new(mp.outputs["Vector"], n1.inputs["Vector"])
    nt.links.new(n1.outputs["Fac"], ramp.inputs["Fac"]); nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    nt.links.new(n1.outputs["Fac"], bump.inputs["Height"]); nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    b.inputs["Roughness"].default_value = 0.92
    return m


def leaf_material(tex: Path):
    m = bpy.data.materials.new("leaves"); m.use_nodes = True
    nt = m.node_tree; b = nt.nodes["Principled BSDF"]
    img = nt.nodes.new("ShaderNodeTexImage"); img.image = bpy.data.images.load(str(tex))
    col = nt.nodes.new("ShaderNodeVertexColor"); col.layer_name = "Col"
    mul = nt.nodes.new("ShaderNodeMixRGB"); mul.blend_type = "MULTIPLY"; mul.inputs["Fac"].default_value = 1.0
    nt.links.new(img.outputs["Color"], mul.inputs["Color1"]); nt.links.new(col.outputs["Color"], mul.inputs["Color2"])
    nt.links.new(mul.outputs["Color"], b.inputs["Base Color"])
    nt.links.new(img.outputs["Alpha"], b.inputs["Alpha"])
    b.inputs["Roughness"].default_value = 0.6
    for key in ("Subsurface Weight", "Transmission Weight"):
        if key in b.inputs: b.inputs[key].default_value = 0.0
    m.use_backface_culling = False
    return m


def render(out_dir: Path, name: str, views=(35, 125, 215, 305), size: int = 560, samples: int = 40):
    scene = bpy.context.scene
    meshes = [o for o in scene.objects if o.type == "MESH"]
    lo = Vector((1e9,) * 3); hi = Vector((-1e9,) * 3)
    for o in meshes:
        for cnr in o.bound_box:
            w = o.matrix_world @ Vector(cnr)
            lo = Vector(map(min, lo, w)); hi = Vector(map(max, hi, w))
    mid = (lo + hi) * 0.5; rr = max(hi - lo) * 0.5
    scene.render.engine = "CYCLES"; scene.cycles.device = "CPU"; scene.cycles.samples = samples
    scene.cycles.use_denoising = False; scene.cycles.transparent_max_bounces = 16
    scene.render.resolution_x = scene.render.resolution_y = size
    world = bpy.data.worlds.new("w"); world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.5, 0.52, 0.56, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.9
    scene.world = world
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); sun.data.energy = 2.6
    sun.rotation_euler = Vector((-0.4, -0.5, -0.75)).to_track_quat("-Z", "Y").to_euler()
    scene.collection.objects.link(sun)
    g = bpy.data.meshes.new("g")
    g.from_pydata([(-80, -80, 0), (80, -80, 0), (80, 80, 0), (-80, 80, 0)], [], [(0, 1, 2, 3)])
    gm = bpy.data.materials.new("ground"); gm.diffuse_color = (0.42, 0.42, 0.44, 1); g.materials.append(gm)
    scene.collection.objects.link(bpy.data.objects.new("g", g))
    cd = bpy.data.cameras.new("c"); cd.lens = 70
    cam = bpy.data.objects.new("c", cd); scene.collection.objects.link(cam); scene.camera = cam
    files = []
    for k, yaw in enumerate(views):
        a = math.radians(yaw)
        cam.location = mid + Vector((math.sin(a), -math.cos(a), 0.55)).normalized() * rr * 5.2
        cam.rotation_euler = (mid - cam.location).to_track_quat("-Z", "Y").to_euler()
        scene.render.filepath = str(out_dir / f"{name}_{k}.png")
        bpy.ops.render.render(write_still=True)
        files.append(scene.render.filepath)
    return files


def species(path=None) -> dict:
    """The broadleaf defaults with a sheet's numbers on top (pairs given as two-item lists)."""
    sp = dict(LINDEN)
    if path:
        import json
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        for k, v in (data.get("numbers") or data).items():
            if k in sp:
                sp[k] = tuple(v) if isinstance(sp[k], tuple) else type(sp[k])(v)
    return sp


def main(argv):
    out_dir = Path(argv[0]); out_dir.mkdir(parents=True, exist_ok=True)
    def opt(flag, default):
        return argv[argv.index(flag) + 1] if flag in argv else default
    seed = int(opt("--seed", 11)); name = opt("--name", "linden")
    bare = "--bare" in argv
    tag = f"{name}_seed{seed}" + ("_bare" if bare else "")
    sp = species(opt("--sheet", None))
    stats = build(sp, seed, out_dir, name, bare)
    print("TREE", tag, stats, flush=True)
    for o in bpy.context.scene.objects:
        o.select_set(o.type == "MESH")
    bpy.ops.export_scene.gltf(filepath=str(out_dir / f"{tag}.glb"), export_format="GLB", use_selection=True, export_yup=True)
    n = int(opt("--views", 4))
    render(out_dir, tag, views=(35, 125, 215, 305)[:n], size=int(opt("--size", 560)), samples=int(opt("--samples", 40)))
    print("DONE", tag, flush=True)


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
