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

BUILD 84 part 5 — trees by species. A sheet may now also say how the tree LOOKS and what FORM it has; a sheet that says
none of it grows exactly the tree it grew before (the same seed gives the same tree, to the vertex):
  leaf       the sprig painted on the leaf cards: heart (a linden's) | oval (a live oak's small leathery leaf) | delta (a
             cottonwood's triangle) | lance (a pecan's long leaflets, in pairs) | feather (a mesquite's or a bald
             cypress's fine leaflets) | scale (a juniper's dense sprays)
  leaf_tint  three numbers that multiply the sprig's own green (a live oak darker, a mesquite greyer)
  bark       the bark's light colour;  flare, flare_height: how the trunk widens at the foot (a bald cypress's buttress)
  form       broadleaf (the grower above) — or one of three plants no crown-filling rule can grow, each built by its own
             rule from the sheet's numbers and the seed:
               column   a saguaro: a ribbed column with a domed top and arms that leave level and turn upward
               canes    an ocotillo: a spray of long thin canes from one foot, red flower spikes at the tips
               rosette  a yucca: a trunk, a skirt of dead blades, one or more heads of sword leaves, a flower stalk
             These carry their colours on the mesh itself (no leaf cards, no bark picture).
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
    # BUILD 84 part 5 — the look and the form (a sheet that gives none of these grows exactly as before)
    "form": "broadleaf",       # broadleaf | column | canes | rosette
    "leaf": "heart",           # the sprig on the leaf cards: heart | oval | delta | lance | feather | scale
    "leaf_tint": (1.0, 1.0, 1.0),          # multiplies the sprig's own green
    "bark": (0.44, 0.40, 0.33),            # the bark's light colour (linear, 0-1)
    "flare": 0.85,             # how much the trunk widens at the foot
    "flare_height": 0.55,      # over how many metres the flare dies away
    # column (a saguaro)
    "ribs": 20,                # pleats round the column
    "rib_depth": 0.16,         # how deep a pleat is, as a share of the radius
    "arms": 3,                 # arms (0 = a young spear)
    "arm_from": (0.32, 0.55),  # where the arms leave the column, as shares of its height
    "arm_reach": (0.7, 1.3),   # metres an arm goes out level before it turns up
    "arm_top": (0.55, 0.92),   # how high an arm's top comes, as shares of the height
    # canes (an ocotillo)
    "canes": 18,               # canes from the one foot
    "cane_radius": 0.022,      # at the foot (metres); a cane thins to a third of it
    "cane_lean": (6, 32),      # degrees from straight up
    "bloom": 1.0,              # share of the canes that end in a red flower spike (0 = none)
    # rosette (a yucca)
    "heads": 1,                # heads of sword leaves (a soaptree yucca branches into two or three when old)
    "blades": 90,              # living blades a head
    "blade": (0.45, 0.75),     # metres, shortest and longest blade
    "blade_width": 0.028,      # metres
    "skirt": 0.55,             # how far down the trunk the dead blades hang, as a share of the trunk
    "stalk": 2.2,              # metres of flower stalk above a head (0 = none)
}
SPRIG_GREEN = {"heart": (70, 140, 46), "oval": (44, 92, 40), "delta": (80, 150, 50), "lance": (60, 126, 44),
               "feather": (98, 134, 72), "scale": (42, 84, 52)}


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


def wood_mesh(nodes, r, runs, rng, flare: float = 0.85, flare_height: float = 0.55):
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
                    rr *= 1 + flare * math.exp(-max(z, 0) / flare_height) + 0.30 * math.exp(-max(z, 0) / 0.9) * math.sin(5 * a + phase)
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
            tint = sp.get("leaf_tint", (1.0, 1.0, 1.0))
            COL += [(min(light + warm, 2.0) * tint[0], light * tint[1], max(light - 1.3 * abs(warm), 0.2) * tint[2], 1.0)] * 4
            soft = out * 0.85 + n * 0.15; soft /= np.linalg.norm(soft)             # each mass shades as one soft body
            NRM += [soft] * 4
    return np.array(V), F, UV, COL, np.array(NRM)


# ------------------------------------------------------------------------------------------------------- pictures
# an outline a leaf, stalk at (0, 0), tip at (0, 1): half-widths at eleven stations from stalk to tip
LEAF_SHAPES = {
    "oval": (0.0, 0.20, 0.30, 0.36, 0.38, 0.37, 0.33, 0.27, 0.19, 0.10, 0.0),       # a live oak's small leathery leaf
    "delta": (0.0, 0.34, 0.50, 0.48, 0.42, 0.35, 0.28, 0.21, 0.14, 0.07, 0.0),      # a cottonwood's triangle
    "lance": (0.0, 0.07, 0.11, 0.135, 0.145, 0.14, 0.125, 0.10, 0.07, 0.035, 0.0),  # a pecan's leaflet
    "feather": (0.0, 0.035, 0.05, 0.055, 0.055, 0.05, 0.045, 0.04, 0.03, 0.015, 0.0),   # a mesquite's, a bald cypress's
    "scale": (0.0, 0.10, 0.15, 0.17, 0.17, 0.16, 0.15, 0.13, 0.10, 0.06, 0.0),      # a juniper's stubby spray
}
# leaves a twig, their length as a share of the picture (smallest, largest), in pairs?, how far they stand off the twig
SPRIG_LAYOUT = {"oval": (9, (0.085, 0.115), True, (0.75, 1.15)), "delta": (5, (0.15, 0.20), False, (0.6, 1.1)),
                "lance": (7, (0.17, 0.23), True, (0.75, 1.05)), "feather": (15, (0.10, 0.14), True, (0.9, 1.2)),
                "scale": (12, (0.07, 0.11), True, (0.5, 0.95))}


def sprig_shapes(path: Path, rng: np.random.Generator, leaf: str, size: int = 768):
    """BUILD 84 part 5: a sprig of another kind of leaf (see LEAF_SHAPES), painted the way the linden's is — twigs from the
    card's foot, far leaves first, each leaf a filled outline with a midrib, its own shade of the kind's green."""
    from PIL import Image, ImageDraw
    S = size * 2
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    half = LEAF_SHAPES[leaf]
    per, lengths, pairs, off = SPRIG_LAYOUT[leaf]
    base = SPRIG_GREEN[leaf]
    c = S * 0.5
    twigs = [(-0.50, 0.56), (0.0, 0.64), (0.55, 0.54), (-1.05, 0.40), (1.10, 0.42)]
    if leaf in ("feather", "scale"):
        twigs += [(-0.25, 0.60), (0.28, 0.60)]                                 # finer leaves: more of the card filled
    foot = (c, c * 1.9)
    ends = [(c + math.sin(ta) * tl * S, c * 1.55 - math.cos(ta) * tl * S * 1.25) for ta, tl in twigs]
    for e in ends:
        d.line([foot, e], fill=(70, 54, 38, 255), width=int(S * (0.004 if leaf in ("feather", "scale") else 0.006)))
    todo = []
    for (ta, _), e in zip(twigs, ends):
        along = math.atan2(e[0] - foot[0], foot[1] - e[1])                    # the twig's own direction (0 = up the picture)
        for j in range(per):
            f = 0.16 + 0.84 * (j + rng.uniform(0, 0.6)) / per
            bx, by = foot[0] + (e[0] - foot[0]) * f, foot[1] + (e[1] - foot[1]) * f
            sides = (-1, 1) if pairs else ((-1,) if j % 2 else (1,))
            for side in sides:
                todo.append((by, bx, along + side * rng.uniform(*off), rng.uniform(0.80, 1.30), rng.uniform(*lengths) * S))
        todo.append((e[1], e[0], along + rng.uniform(-0.15, 0.15), rng.uniform(0.9, 1.3), lengths[1] * S))   # one at the tip
    for (by, bx, ang, shade, length) in sorted(todo, key=lambda o: -o[0]):   # far leaves first, near ones over them
        ca, sa = math.cos(ang), math.sin(ang)
        right, left = [], []
        for k, w in enumerate(half):
            y = k / (len(half) - 1) * length
            for x, into in ((w * length, right), (-w * length, left)):
                into.append((bx + x * ca + y * sa, by + x * sa - y * ca))
        pts = right + left[::-1]
        g = shade
        col = tuple(min(int(v * g), 255) for v in base) + (255,)
        edge = tuple(int(v * g * 0.55) for v in base) + (255,)
        vein = tuple(min(int(v * g * 1.35 + 18), 255) for v in base) + (255,)
        d.polygon(pts, fill=col)
        d.line(pts + [pts[0]], fill=edge, width=max(int(S * 0.0016), 1))
        if leaf not in ("feather",):
            d.line([(bx, by), (bx + length * sa, by - length * ca)], fill=vein, width=max(int(S * 0.0016), 1))
    im = im.resize((size, size), Image.LANCZOS)
    im.save(path)
    return path


def sprig_texture(path: Path, rng: np.random.Generator, size: int = 768, leaf: str = "heart"):
    """Paint one sprig of small heart-shaped linden leaves on nothing (transparent), for the leaf cards."""
    if leaf != "heart" and leaf in LEAF_SHAPES:
        return sprig_shapes(path, rng, leaf, size)
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
    if sp.get("form", "broadleaf") != "broadleaf":
        return build_plant(sp, rng, bare)
    nodes, par, masses = grow(sp, rng)
    r, kids = thickness(nodes, par, sp)
    runs = chains(par, r, kids)
    bpy.ops.wm.read_factory_settings(use_empty=True)

    V, F, UV = wood_mesh(nodes, r, runs, rng, float(sp.get("flare", 0.85)), float(sp.get("flare_height", 0.55)))
    wood = bpy.data.meshes.new("wood")
    wood.from_pydata(V.tolist(), [], F)
    uv = wood.uv_layers.new(name="UVMap")
    flat = [UV[v] for poly in wood.polygons for v in poly.vertices]
    uv.data.foreach_set("uv", [c for pair in flat for c in pair])
    for p in wood.polygons: p.use_smooth = True
    wood_ob = bpy.data.objects.new("M_bark", wood)
    bpy.context.scene.collection.objects.link(wood_ob)
    wood.materials.append(bark_material(sp.get("bark", (0.44, 0.40, 0.33))))

    stats = {"nodes": len(nodes), "wood_tris": len(F) * 2, "leaf_tris": 0, "cards": 0}
    if not bare:
        tex = out_dir / f"{name}_sprig.png"
        leaf_kind = str(sp.get("leaf") or "heart")
        try:
            sprig_texture(tex, np.random.default_rng(7), leaf=leaf_kind)
        except ImportError:                       # a Blender Python without PIL: the same sprig, painted once and kept
            import shutil
            kept = Path(__file__).with_name(f"sprig_{leaf_kind}.png")
            shutil.copyfile(kept if leaf_kind != "heart" and kept.exists() else Path(__file__).with_name("sprig_broadleaf.png"), tex)
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


AFTER_EXPORT: list = []      # what is wired into a material only once the .glb is written (for the pictures)


def bark_material(light=(0.44, 0.40, 0.33)):
    m = bpy.data.materials.new("bark"); m.use_nodes = True
    nt = m.node_tree; b = nt.nodes["Principled BSDF"]
    uv = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping"); mp.inputs["Scale"].default_value = (9.0, 0.55, 1.0)   # furrows run along the limb
    n1 = nt.nodes.new("ShaderNodeTexNoise"); n1.inputs["Scale"].default_value = 2.2; n1.inputs["Detail"].default_value = 9
    n1.inputs["Roughness"].default_value = 0.62
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.36; ramp.color_ramp.elements[0].color = (0.035, 0.030, 0.026, 1)
    ramp.color_ramp.elements[1].position = 0.66; ramp.color_ramp.elements[1].color = (float(light[0]), float(light[1]), float(light[2]), 1)
    # BUILD 84 part 5: a .glb cannot carry Blender's own furrows, and with them wired in it carried no colour at all — the
    # wood reached a game white. So the .glb is written with the bark's one colour (below), and the furrows are wired in
    # afterwards, for the pictures (AFTER_EXPORT, run by main once the .glb is written).
    b.inputs["Base Color"].default_value = (float(light[0]) * 0.6, float(light[1]) * 0.6, float(light[2]) * 0.6, 1)
    bump = nt.nodes.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = 0.9; bump.inputs["Distance"].default_value = 0.06
    nt.links.new(uv.outputs["UV"], mp.inputs["Vector"]); nt.links.new(mp.outputs["Vector"], n1.inputs["Vector"])
    nt.links.new(n1.outputs["Fac"], ramp.inputs["Fac"])
    AFTER_EXPORT.append(lambda: nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"]))
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


# ------------------------------------------------------------------------------------------------ BUILD 84 part 5: three plants
def _frames(pts: np.ndarray):
    """A frame carried along a path without twisting: (tangent, normal, binormal) a point."""
    tang = np.gradient(pts, axis=0)
    tang /= np.maximum(np.linalg.norm(tang, axis=1)[:, None], 1e-9)
    ref = np.array([1.0, 0, 0]) if abs(tang[0][0]) < 0.9 else np.array([0, 1.0, 0])
    nrm = np.cross(tang[0], ref); nrm /= np.linalg.norm(nrm)
    out = []
    for k in range(len(pts)):
        if k:
            nrm = nrm - tang[k] * np.dot(nrm, tang[k])
            nrm /= max(np.linalg.norm(nrm), 1e-9)
        out.append((tang[k], nrm.copy(), np.cross(tang[k], nrm)))
    return out


def _tube(V, F, COL, pts, rad, sides, colour, ribs: int = 0, rib_depth: float = 0.0, cap: bool = True):
    """A tube along a path into (V, F, COL). `colour(k, s, crest)` gives a vertex its colour; with `ribs` the tube is
    pleated (two vertices a pleat: its crest and its valley). The far end is closed to a point."""
    pts = np.asarray(pts, dtype=float)
    n = ribs * 2 if ribs else sides
    base = len(V)
    for k, (t, nr, bn) in enumerate(_frames(pts)):
        for s in range(n):
            a = math.tau * s / n
            crest = (s % 2 == 0) if ribs else True
            rr = rad[k] * (1.0 if crest else 1.0 - rib_depth)
            V.append(pts[k] + (nr * math.cos(a) + bn * math.sin(a)) * rr)
            COL.append(colour(k, s, crest))
    for k in range(len(pts) - 1):
        for s in range(n):
            a0 = base + k * n + s
            a1 = base + k * n + (s + 1) % n
            F.append((a0, a1, a1 + n, a0 + n))
    if cap:
        tip = len(V)
        V.append(pts[-1] + _frames(pts)[-1][0] * rad[-1] * 0.6)
        COL.append(colour(len(pts) - 1, 0, True))
        last = base + (len(pts) - 1) * n
        for s in range(n):
            F.append((last + s, last + (s + 1) % n, tip))


def _dome(pts, rad, steps: int = 6):
    """Round the far end of a column: the last stretch of the path, its radius falling as a quarter circle."""
    pts, rad = list(pts), list(rad)
    end, r = np.asarray(pts[-1], dtype=float), rad[-1]
    d = np.asarray(pts[-1], dtype=float) - np.asarray(pts[-2], dtype=float)
    d /= max(np.linalg.norm(d), 1e-9)
    for i in range(1, steps + 1):
        a = (math.pi / 2) * i / (steps + 0.6)
        pts.append(end + d * r * math.sin(a))
        rad.append(r * math.cos(a))
    return np.array(pts), np.array(rad)


def column_plant(sp: dict, rng: np.random.Generator):
    """A saguaro: one ribbed column, a little narrower at the foot, a domed top; arms that leave it level, turn upward
    through an elbow and stand; green on the crests of the pleats and deep green in their valleys, woody at the foot."""
    H, R = float(sp["height"]), float(sp["trunk_radius"])
    ribs, depth = int(sp["ribs"]), float(sp["rib_depth"])
    V, F, COL = [], [], []
    lean = rng.normal(0, 0.012, 2)

    def skin(height_of):
        def colour(k, s, crest):
            z = height_of(k)
            g = (0.30, 0.42, 0.20) if crest else (0.11, 0.19, 0.10)
            wood = max(0.0, 1.0 - z / (0.09 * H))                              # the foot of an old saguaro is bark
            j = 1.0 + 0.08 * math.sin(s * 2.3 + k * 0.7)
            return (g[0] * j * (1 - wood) + 0.30 * wood, g[1] * j * (1 - wood) + 0.24 * wood, g[2] * j * (1 - wood) + 0.17 * wood, 1.0)
        return colour
    zs = np.linspace(0.0, H - R, 26)
    pts = np.array([[lean[0] * z, lean[1] * z, z] for z in zs])
    rad = np.array([R * (0.80 + 0.20 * min(z / (0.35 * H), 1.0)) * (1.0 - 0.10 * max(0.0, (z - 0.6 * H) / (0.4 * H))) for z in zs])
    pts, rad = _dome(pts, rad)
    _tube(V, F, COL, pts, rad, 0, skin(lambda k: pts[k][2]), ribs, depth)
    az0 = rng.uniform(0, math.tau)
    n_arms = int(sp["arms"])
    for i in range(n_arms):
        az = az0 + math.tau * i / max(n_arms, 1) + rng.normal(0, 0.35)
        z0 = H * rng.uniform(*sp["arm_from"])
        reach = rng.uniform(*sp["arm_reach"])
        top = max(H * rng.uniform(*sp["arm_top"]), z0 + 0.8)
        ar = R * rng.uniform(0.62, 0.80)
        out = np.array([math.cos(az), math.sin(az), 0.0])
        elbow = min(0.55, reach * 0.6)
        path = [np.array([lean[0] * z0, lean[1] * z0, z0]) + out * (R * 0.5)]
        path.append(path[0] + out * max(reach - elbow, 0.15))
        for j in range(1, 7):                                                  # the elbow: a quarter turn upward
            a = (math.pi / 2) * j / 6
            path.append(path[1] + out * elbow * math.sin(a) + np.array([0, 0, elbow * (1 - math.cos(a))]))
        rise = max(top - path[-1][2] - ar, 0.3)
        for j in range(1, 9):
            path.append(path[7] + np.array([rng.normal(0, 0.01), rng.normal(0, 0.01), rise * j / 8]))
        ap = np.array(path)
        arad = np.full(len(ap), ar)
        arad[0] = ar * 0.85                                                    # the neck where it leaves the column
        ap, arad = _dome(ap, arad)
        _tube(V, F, COL, ap, arad, 0, skin(lambda k: H), max(int(ribs * 0.7), 8), depth)
    return np.array(V), F, np.array(COL), {"arms": n_arms}


def canes_plant(sp: dict, rng: np.random.Generator, bare: bool = False):
    """An ocotillo: long thin canes from one foot, each leaning its own way and curving a little outward, grey with green
    in it; in bloom a red spike at the tip. Bare (the dry months, most of the year): no red, greyer canes."""
    H = float(sp["height"])
    V, F, COL = [], [], []
    n = int(sp["canes"])
    az0 = rng.uniform(0, math.tau)
    spikes = 0
    for i in range(n):
        az = az0 + math.tau * i / n + rng.normal(0, 0.25)
        lean = math.radians(rng.uniform(*sp["cane_lean"]))
        length = H / max(math.cos(lean), 0.5) * rng.uniform(0.72, 1.0)
        out = np.array([math.cos(az), math.sin(az), 0.0])
        steps = 14
        p = np.array([out[0], out[1], 0.0]) * rng.uniform(0.02, 0.10)
        d = out * math.sin(lean * 0.55) + np.array([0, 0, math.cos(lean * 0.55)])
        path = [p.copy()]
        for j in range(steps):
            d = d + out * (math.sin(lean) * 0.07) + rng.normal(0, 0.018, 3)   # a cane bows outward as it climbs
            d /= np.linalg.norm(d)
            p = p + d * (length / steps)
            path.append(p.copy())
        path = np.array(path)
        r0 = float(sp["cane_radius"]) * rng.uniform(0.8, 1.2)
        rad = np.array([r0 * (1.0 - 0.66 * j / steps) for j in range(steps + 1)])
        grey = rng.uniform(0.85, 1.1)

        def colour(k, s, crest, grey=grey):
            f = k / steps
            dry = (0.40, 0.37, 0.31) if bare else (0.33, 0.37, 0.24)
            stripe = 0.82 if s % 2 else 1.0                                    # the cane's own ridges
            return (dry[0] * grey * stripe, dry[1] * grey * stripe * (1 + 0.1 * f), dry[2] * grey * stripe, 1.0)
        _tube(V, F, COL, path, rad, 6, colour)
        if not bare and rng.uniform() < float(sp["bloom"]):
            spikes += 1
            tip = path[-1]
            sd = path[-1] - path[-2]; sd /= np.linalg.norm(sd)
            sp_len = rng.uniform(0.16, 0.30)
            sp_pts = np.array([tip + sd * sp_len * f for f in (0.0, 0.25, 0.6, 1.0)])
            sp_rad = np.array([rad[-1] * 1.3, rad[-1] * 3.6, rad[-1] * 2.8, rad[-1] * 0.6])
            _tube(V, F, COL, sp_pts, sp_rad, 6, lambda k, s, crest: (0.78 + 0.1 * (s % 2), 0.10 + 0.05 * k / 3, 0.05, 1.0))
    return np.array(V), F, np.array(COL), {"canes": n, "spikes": spikes}


def rosette_plant(sp: dict, rng: np.random.Generator, bare: bool = False):
    """A yucca: a trunk (none when the height is a blade's length), each head a ball of sword leaves — the living ones
    blue-green and stiff, last years' hanging tan down the trunk as a skirt — and a flower stalk with a cream plume."""
    H, R = float(sp["height"]), float(sp["trunk_radius"])
    V, F, COL = [], [], []
    blade_lo, blade_hi = sp["blade"]
    width = float(sp["blade_width"])
    heads = max(int(sp["heads"]), 1)
    trunk_top = max(H - blade_hi * 0.8, 0.0)
    fork = trunk_top * (0.62 if heads > 1 else 1.0)
    lean = rng.normal(0, 0.03, 2)
    centres = []
    if trunk_top > 0.05:
        zs = np.linspace(0.0, fork, 8)
        pts = np.array([[lean[0] * z, lean[1] * z, z] for z in zs])
        bark = lambda k, s, crest: (0.25 + 0.05 * (s % 2), 0.21 + 0.04 * (s % 2), 0.16, 1.0)   # noqa: E731
        _tube(V, F, COL, pts, np.full(len(pts), R), 8, bark, cap=heads > 1)
        if heads == 1:
            centres.append(pts[-1])
        else:
            az0 = rng.uniform(0, math.tau)
            for i in range(heads):
                az = az0 + math.tau * i / heads + rng.normal(0, 0.3)
                out = np.array([math.cos(az), math.sin(az), 0.0])
                top = pts[-1] + out * rng.uniform(0.25, 0.5) + np.array([0, 0, (trunk_top - fork) * rng.uniform(0.7, 1.0)])
                bp = np.array([pts[-1] + (top - pts[-1]) * f + out * 0.12 * math.sin(math.pi * f) for f in np.linspace(0, 1, 6)])
                _tube(V, F, COL, bp, np.full(len(bp), R * 0.72), 8, bark, cap=False)
                centres.append(bp[-1])
    else:
        centres.append(np.zeros(3))

    def blade(root, direction, length, colour_root, colour_tip, droop=0.0, width=width):
        direction = direction / max(np.linalg.norm(direction), 1e-9)
        side = np.cross(direction, np.array([0, 0, 1.0]))
        if np.linalg.norm(side) < 1e-6:
            side = np.array([1.0, 0, 0])
        side /= np.linalg.norm(side)
        base = len(V)
        for f, w in ((0.0, 1.0), (0.5, 0.8), (1.0, 0.06)):
            mid = root + direction * length * f + np.array([0, 0, -droop * length * f * f])
            for sgn in (-1, 1):
                V.append(mid + side * sgn * width * w * 0.5)
                COL.append(tuple(colour_root[i] * (1 - f) + colour_tip[i] * f for i in range(3)) + (1.0,))
        F.append((base, base + 1, base + 3, base + 2))
        F.append((base + 2, base + 3, base + 5, base + 4))

    n_blades = int(sp["blades"])
    for c in centres:
        for _ in range(n_blades):
            v = rng.normal(size=3)
            v[2] = abs(v[2]) * 0.9 - 0.25                                      # a ball of blades, fuller above than below
            v /= np.linalg.norm(v)
            g = rng.uniform(0.85, 1.15)
            blade(c + v * R * 0.5, v, rng.uniform(blade_lo, blade_hi), (0.20 * g, 0.31 * g, 0.22 * g), (0.42 * g, 0.50 * g, 0.34 * g),
                  droop=0.10 if v[2] < 0.2 else 0.0)
        skirt = float(sp["skirt"]) * max(trunk_top, 0.0)
        for _ in range(int(n_blades * 0.9) if skirt > 0.05 else 0):            # last years' blades, hanging
            az = rng.uniform(0, math.tau)
            drop = rng.uniform(0.0, skirt)
            root = c + np.array([math.cos(az), math.sin(az), 0.0]) * R * 0.9 + np.array([0, 0, -drop * 0.8])
            v = np.array([math.cos(az) * 0.35, math.sin(az) * 0.35, -1.0])
            g = rng.uniform(0.8, 1.15)
            blade(root, v, rng.uniform(blade_lo, blade_hi) * 0.9, (0.46 * g, 0.38 * g, 0.24 * g), (0.60 * g, 0.52 * g, 0.36 * g))
        stalk = float(sp["stalk"])
        if stalk > 0.05 and not bare:
            top = c + np.array([rng.normal(0, 0.05), rng.normal(0, 0.05), stalk])
            sp_pts = np.array([c + (top - c) * f for f in np.linspace(0, 1, 7)])
            _tube(V, F, COL, sp_pts, np.linspace(0.022, 0.010, 7), 5, lambda k, s, crest: (0.45, 0.42, 0.28, 1.0))
            for _ in range(46):                                                # the plume: small cream bells round the top third
                f = rng.uniform(0.62, 1.0)
                at = c + (top - c) * f
                v = rng.normal(size=3); v[2] = -abs(v[2]) * 0.6
                g = rng.uniform(0.9, 1.1)
                root = at + np.array([v[0], v[1], 0.0]) * 0.10 * (1.2 - f)
                blade(root, v, rng.uniform(0.07, 0.12), (0.86 * g, 0.84 * g, 0.70 * g), (0.95 * g, 0.93 * g, 0.80 * g), width=0.06)
    return np.array(V), F, np.array(COL), {"heads": len(centres), "blades": n_blades * len(centres)}


def plant_material(rough: float = 0.72):
    """The colours a plant carries on its own mesh (a colour a vertex), both faces of a blade shown."""
    m = bpy.data.materials.new("plant"); m.use_nodes = True
    nt = m.node_tree; b = nt.nodes["Principled BSDF"]
    col = nt.nodes.new("ShaderNodeVertexColor"); col.layer_name = "Col"
    nt.links.new(col.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = rough
    m.use_backface_culling = False
    return m


def build_plant(sp: dict, rng: np.random.Generator, bare: bool = False):
    form = sp["form"]
    if form == "column":
        V, F, COL, stats = column_plant(sp, rng)
    elif form == "canes":
        V, F, COL, stats = canes_plant(sp, rng, bare)
    elif form == "rosette":
        V, F, COL, stats = rosette_plant(sp, rng, bare)
    else:
        raise SystemExit(f"a species sheet's form is broadleaf, column, canes or rosette (not {form!r})")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    me = bpy.data.meshes.new("plant")
    me.from_pydata(V.tolist(), [], F)
    col = me.color_attributes.new(name="Col", type="FLOAT_COLOR", domain="POINT")
    col.data.foreach_set("color", [c for rgba in COL.tolist() for c in rgba])
    for p in me.polygons:
        p.use_smooth = form != "rosette"
    ob = bpy.data.objects.new("M_plant", me)
    bpy.context.scene.collection.objects.link(ob)
    me.materials.append(plant_material(0.55 if form == "column" else 0.78))
    tris = sum(len(f) - 2 for f in F)
    return {"form": form, "nodes": 0, "wood_tris": tris, "leaf_tris": 0, "cards": 0, **stats}


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
    for wire in AFTER_EXPORT:
        wire()
    AFTER_EXPORT.clear()
    n = int(opt("--views", 4))
    render(out_dir, tag, views=(35, 125, 215, 305)[:n], size=int(opt("--size", 560)), samples=int(opt("--samples", 40)))
    print("DONE", tag, flush=True)


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
