"""The checks after every model (BUILD 39): each writes one plain line, and a failing one holds the thing back.

Measured on the launch-site run of 2026-11-13/14 (35 props and buildings), where a person had found these faults by eye:

  sits level     two measures that must agree: the plane the thing would rest on (the way up whose contact patch is
                 widest — a level thing stands on its whole base or all its feet) and the way up its own walls, roofs
                 and posts say. Both more than 2 degrees off, agreeing on the direction: it leans as a whole — a fail.
                 Caught every Pixal3D model of the run (2-14°; the hut nobody had noticed was 8° off), a building that
                 leans (11°) and a slab on its corner (40°). A thing that is upright by its own structure but rests on a
                 slope or on parts that hang lower — a stair, a wall-mounted box with padlocks — passes, with a note.
  loose pieces   parts of the mesh that touch neither the rest of it nor the ground — a slab floating under a closure, an
                 aerial's arm hanging in the air. A post that stands on the ground by itself is not loose.
  blank glass    surface whose colour is a flat near-white and whose material is a perfect mirror (metal 1, roughness 0):
                 image-to-3D's way of making windows, lamps and glass jugs; in a plain room it renders blank white.
  thin parts     see-through parts lost: holes in the model's outline (with small gaps closed) where the picture's
                 outline is filled — a fence or a gate that kept its frame and lost its mesh shows its empty panels. Seen
                 from the view the picture was taken from (searched). More than a fifth of the outline open where the
                 picture is filled is a fail. Measured on 76 models: the fence 64%, the gate 42%, everything else 10% or less.

  colours hold   (BUILD 40) the model seen from the picture's view, its colour texture as stored (no light), against the
                 picture's figure: brightness at the 10th, 50th and 90th percentile, and for a body the head band on its own.
                 Measured on the two launch-site runs: every body came out about half as bright as its picture (0.5-0.6
                 of its brightness; dark faces lost their features), the props and buildings near their pictures but flatter.
                 A miss is put right, not remade: `fix_colour` fits one monotonic tone curve per channel from the model's
                 front-view colours to the picture's and applies it to the whole colour texture (`fix_glass` gives a white
                 mirror a dark glass colour and its own roughness). The model as made is always kept beside the fixed one.

BUILD 84 (2f), after three good models were held for "1 piece not joined to the rest (below the floor)" — which turned out,
looked at, to be three different things, so there are three answers (`fix_loose`; the model as made is always kept):
  (1) a sheet of ground the image-to-3D step left floating under a concrete closure: a piece that lies WHOLLY under the
      floor is taken off;
  (2) an office chair the step had stood behind a building, its feet a hand's width through the floor: a piece that stands
      by itself but a LITTLE through the floor is stood on the floor (lifted by what it was sunk), so the building is no
      longer stood on the chair's feet with a gap under its own walls;
  (3) a chandelier's own centre crystal: a thing that HANGS has no floor, so its pieces are judged by how near they hang
      to the rest (`hangs=True` — said by the entry, or read from its words by the world queue).
A piece in the air, or deep through the floor, is held as before.

Which checks apply depends on the kind of thing (a pistol lies on its side; a person isn't a building): `CHECKS_FOR`.
Every number is a setting (forge.json -> threed.checks). `run()` returns {"ok", "lines", "results", "picture"}.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from . import raster
from .meshio import Glb, quat_between

DEFAULTS = {
    "level_max_deg": 2.0,          # the build's rule: more than 2 degrees off level is a fail
    "loose_min_size": 0.04,        # a floating piece at least this share of the model's size (tidy takes off smaller crumbs)
    "loose_gap": 0.012,            # how close (share of the size) a piece must come to the rest, or to the ground, to count as touching
    "glass_max_share": 0.003,      # more than 0.3 % of the surface as a white mirror
    "thin_max_lost": 0.2,          # more than a fifth of the model's outline open where the picture's is filled
    "straighten_up_to_deg": 15.0,  # the world queue turns a thing that leans as a whole level by itself up to this (0 = hold every lean)
    # BUILD 84 (2f) — a loose piece nobody would miss is put right by the queue, not held (a prop or a building; never a body)
    "loose_fix": True,             # take off a piece that lies wholly under the floor; stand a piece that is a little through it on it
    "loose_fix_max_share": 0.10,   # ... taking off only while it is under this share of the surface (more: a person looks)
    "loose_sink_max": 0.06,        # "a little through the floor": no deeper than this share of the model's height ...
    "loose_sink_own": 0.34,        # ... and no more than this share of the piece's own height
    "loose_hang_gap": 0.04,        # a thing that hangs (a chandelier): a piece this close to the rest (share of the size) hangs by it
    # BUILD 84 part 6 — proportions: an entry's second measure against the made thing (scaled by its first)
    "size_check": True,
    "size_max_off": 0.3334,        # held when a second measure comes out more than a third from what was asked
    # BUILD 40 — colours hold (the model's front view against its picture; brightness as stored, 0-255, Rec. 709 luma)
    "colour_mean_band": [0.8, 1.25],   # the model's mean brightness over the picture's
    "colour_spread_min": 0.6,          # the model's contrast (90th - 10th percentile) over the picture's
    "colour_head_band": [0.75, 1.33],  # a body's head band (the top seventh of the figure), model over picture
    "colour_prop_band": [0.6, 1.6],    # a prop or building: its picture carries studio light and highlights its colour texture
                                       # rightly doesn't, so only a clear miss is held, and a person chooses the matched colours
    "colour_fix": True,                # the world queue puts a body's colour miss right by itself (the model as made kept beside it)
    "colour_max_slope": 3.0,           # the tone curve never steepens a colour range more than this (keeps texture noise down)
    "glass_fix": True,                 # ... and gives a white mirror a dark glass colour
    "glass_colour": [34, 42, 48],      # sRGB of fixed glass
    "glass_roughness": 0.18,           # its roughness (metal 0)
    # BUILD 73 — the head band from the level front view, the face (skin) and the hair measured apart
    "head_shadow_share": 0.3333,       # the picture's face more than this much darker than its own neck and hands = a hat's
                                       # (or a hood's) shadow in the picture: said so, never held on the head alone
    "face_chroma_tol": 0.035,          # how near a pixel's chromaticity must be to the face's own to count as skin
    "face_luma_band": [0.55, 1.8],     # ... and its brightness, against the face's own middle (dark hair of a skin hue is out)
    "head_fix": False,                 # BUILD 84: off — no curve on a body, the head's included (BUILD 73 had it on: a body
                                       # whose only miss was its face got a tone curve on its head alone, feathered)
    "head_feather": 0.2,               # the feather below the head line, as a share of the head band's height (0.5 reached
                                       # the collar: a white shirt went pink on the first try)
    # BUILD 73 — a prop's picture carries studio light; its stored colour does not
    "neutral_drift_max": 0.06,         # (scaled: 0.06 = a mean rise in saturation of 0.06 over the neutrals, or 15% of them rising
                                       # by more than 0.12) a match may not turn the model's whites and greys into a colour (white shoes went pink,
                                       # a white coat mint, a white shirt beige under BUILD 40's per-colour curves): above
                                       # this mean rise in saturation, the brightness-only curve is tried instead
    "loudness_max": 1.35,              # a matched model's colours at most this much louder (max - min) than its picture's
    "skin_shift_max": 0.012,           # a match may not move the face's colour (chromaticity) further from the picture's than this
    "prop_highlight_pct": 90,          # the picture's brightest tail above this percentile is not counted
    "prop_dark_floor": 70.0,           # a picture whose own middle is below this is of a dark thing (a black chair, a pistol):
    "prop_detail_min": 0.3333,
    "prop_shadow_min": 0.2,            # the model's 10th percentile at least this share of the (highlight-free) picture's         # ... it is held only if the model kept less than this share of the picture's contrast
    # BUILD 84 — a body's colours by brightness only: one gain for the whole colour picture, never a curve, never a hue
    "body_gain_margin": 0.02,          # the gain aims this far inside each band it has to meet (the mean, the face, the contrast)
    "body_gain_max": 2.5,              # never more than this, nor less than its inverse
    "body_gain_clip_share": 0.005,     # at most this share of the lit texels pushed past white by the gain
    "hue_moved_deg": 10.0,             # a texel whose hue turned more than this ...
    "hue_moved_max": 0.02,             # ... on more than this share of the coloured texels: the hue moved — a body is held, never released so
    "face_redo_below": 0.5,            # after the gain, a face still under half its picture's brightness did not come through:
                                       # the body is made again once (BUILD 73's face_redo); a smaller miss is released at the gain, said so
    # BUILD 84 — metal out of the colour check (a look review of 2026-11-18: dark iron is meant to be darker than its lit picture)
    "metal_from": 0.8,                 # a texel whose metalness (the metallicRoughness texture's blue x metallicFactor) is at least
                                       # this is marked as metal. The image-to-3D step leaves what it can't tell at about 0.5 (a
                                       # body's cloth, a brazier's iron at 0.3-0.4); the sousaphone's brass and the bench's iron
                                       # ends are 0.9-1.0 (measured 2026-11-19 on six models of the queue)
    "metal_skip_share": 0.85,          # a thing more metal than this, seen from its picture's view, is not colour-checked at all
}
# kind/tier -> the checks that make sense for it
CHECKS_FOR = {
    "building": ("level", "loose", "glass", "thin", "colour"),
    "large_prop": ("level", "loose", "glass", "thin", "colour"),
    "small_prop": ("level", "loose", "glass", "thin", "colour"),
    "hand_prop": ("loose", "glass", "thin", "colour"),           # a hand prop lies however it likes
    "prop": ("level", "loose", "glass", "thin", "colour"),
    "body": ("loose", "glass", "thin", "colour"),                # a body is stood up by its skeleton, not by its floor
    "principal": ("loose", "glass", "thin", "colour"),
    "named": ("loose", "glass", "thin", "colour"),
    "crowd": ("loose", "glass", "thin", "colour"),
}
NAMES = {"level": "Sits level", "loose": "Loose pieces", "glass": "Blank glass", "thin": "Thin parts", "colour": "Colours hold",
         "size": "Proportions"}
BODY_KINDS = ("body", "principal", "named", "crowd")


def settings(cfg: dict | None) -> dict:
    s = dict(DEFAULTS)
    s.update(((cfg or {}).get("threed") or {}).get("checks") or {})
    return s


def which(kind: str, tier: str | None = None) -> tuple:
    return CHECKS_FOR.get(tier or "", None) or CHECKS_FOR.get(kind, ("loose", "glass", "thin", "colour"))


# ------------------------------------------------------------------------------------------------ geometry helpers
def face_normals(P: np.ndarray, F: np.ndarray):
    n = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
    area = np.linalg.norm(n, axis=1) / 2
    return n / np.maximum(2 * area, 1e-18)[:, None], area


def ground_plane(P: np.ndarray, cells: int = 16, band: float = 0.02, iters: int = 10) -> dict:
    """The plane the thing stands on: per footprint cell its lowest point, then a least-squares plane through the lower
    envelope (cells more than `band` x height above the plane are dropped and the fit repeated).
    Returns {"tilt_deg", "normal", "coef" (y = a x + b z + c), "cells_used", "cells"}."""
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    h = max(float(np.ptp(y)), 1e-9)
    ix = np.clip(((x - x.min()) / max(float(np.ptp(x)), 1e-9) * cells).astype(np.int64), 0, cells - 1)
    iz = np.clip(((z - z.min()) / max(float(np.ptp(z)), 1e-9) * cells).astype(np.int64), 0, cells - 1)
    key = ix * cells + iz
    order = np.lexsort((y, key))
    ks = key[order]
    sel = order[np.r_[True, ks[1:] != ks[:-1]]]
    pts = P[sel]
    keep = np.ones(len(pts), bool)
    coef = np.array([0.0, 0.0, float(y.min())])

    def fit(q):
        """y = a x + b z + c through q; along a line-like footprint (a fence, a rail) only the slope along it is known,
        so across it the plane is taken as level rather than guessed."""
        xz = q[:, [0, 2]] - q[:, [0, 2]].mean(0)
        w, V = np.linalg.eigh(xz.T @ xz / max(len(q), 1))
        if len(q) < 3 or w[0] < (0.2 ** 2) * max(w[1], 1e-18):
            ax = V[:, 1]
            t = xz @ ax
            if np.ptp(t) < 1e-12:
                return np.array([0.0, 0.0, float(q[:, 1].mean())])
            a1, c1 = np.polyfit(t, q[:, 1], 1)
            mx, mz = q[:, 0].mean(), q[:, 2].mean()
            return np.array([a1 * ax[0], a1 * ax[1], c1 - a1 * (ax[0] * mx + ax[1] * mz)])
        A = np.c_[q[:, 0], q[:, 2], np.ones(len(q))]
        return np.linalg.lstsq(A, q[:, 1], rcond=None)[0]
    if len(pts) >= 2:
        for _ in range(iters):
            coef = fit(pts[keep])
            resid = pts[:, 1] - (coef[0] * pts[:, 0] + coef[1] * pts[:, 2] + coef[2])
            new = resid <= band * h
            if new.sum() < 2 or (new == keep).all():
                break
            keep = new
    n = np.array([-coef[0], 1.0, -coef[1]])
    n /= np.linalg.norm(n)
    return {"tilt_deg": float(np.degrees(np.arccos(np.clip(n[1], -1, 1)))), "normal": n, "coef": coef,
            "cells_used": int(keep.sum()), "cells": int(len(pts))}


def components(P: np.ndarray, F: np.ndarray, tol_rel: float = 1e-5) -> np.ndarray:
    """A label per face: faces sharing a vertex (positions welded within tol_rel x size) have the same label."""
    if not len(F):
        return np.zeros(0, dtype=np.int64)
    diag = float(np.linalg.norm(P.max(0) - P.min(0))) or 1.0
    q = np.round(P / max(diag * tol_rel, 1e-12)).astype(np.int64)
    _, vid = np.unique(q, axis=0, return_inverse=True)
    vid = vid.ravel()
    FV = vid[F]
    a = np.r_[FV[:, 0], FV[:, 1], FV[:, 2]]
    b = np.r_[FV[:, 1], FV[:, 2], FV[:, 0]]
    lab = np.arange(int(vid.max()) + 1)
    for _ in range(500):
        m = np.minimum(lab[a], lab[b])
        new = lab.copy()
        np.minimum.at(new, a, m)
        np.minimum.at(new, b, m)
        new = new[new]
        new = new[new]
        if np.array_equal(new, lab):
            break
        lab = new
    return lab[FV[:, 0]]


# ------------------------------------------------------------------------------------------------ the four checks
def support_tilt(P: np.ndarray, eps: float = 0.012, keep: float = 0.85, sample: int = 6000) -> dict:
    """The plane a thing would rest on: of every way up (to 50 degrees off vertical), the one whose contact patch — the
    points within eps of the lowest along it — is widest; among near-widest (keep), the one closest to vertical."""
    rng = np.random.default_rng(0)
    Q = P if len(P) <= sample else P[rng.choice(len(P), sample, replace=False)]
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    cells = 32                                             # the lowest point under each part of the footprint: feet are small
    ix = np.clip(((x - x.min()) / max(float(np.ptp(x)), 1e-9) * cells).astype(np.int64), 0, cells - 1)
    iz = np.clip(((z - z.min()) / max(float(np.ptp(z)), 1e-9) * cells).astype(np.int64), 0, cells - 1)
    key = ix * cells + iz
    order = np.lexsort((y, key))
    ks = key[order]
    Q = np.vstack([Q, P[order[np.r_[True, ks[1:] != ks[:-1]]]]])
    def patch(t: float, phi: float):
        tr, pr = np.radians(t), np.radians(phi)
        u = np.array([np.sin(tr) * np.cos(pr), np.cos(tr), np.sin(tr) * np.sin(pr)])
        h = Q @ u
        c = Q[h <= h.min() + eps * max(float(np.ptp(h)), 1e-12)]
        if len(c) < 3:
            return 0.0, u
        e1 = np.cross(u, [0.0, 0.0, 1.0])
        e1 /= np.linalg.norm(e1)
        e2 = np.cross(u, e1)
        w = np.clip(np.linalg.eigvalsh(np.cov(np.vstack([c @ e1, c @ e2]))), 0, None)
        return 12 * float(np.sqrt(w[0] * w[1])), u               # a uniform rectangle's area from its two spreads

    cands = []
    for t in list(np.arange(0, 4.01, 0.5)) + list(np.arange(5, 50.1, 1.5)):
        for phi in ([0.0] if t == 0 else np.arange(0, 360, 12)):
            a, u = patch(float(t), float(phi))
            cands.append((a, float(t), float(phi), u))
    top = max(c[0] for c in cands) or 1e-12
    area, t, phi, u = min((c for c in cands if c[0] >= keep * top), key=lambda c: c[1])
    if t > 0:                                                    # a lean: find it to a quarter of a degree
        near = [(*patch(tt, pp), tt, pp) for tt in np.arange(max(0.0, t - 1.5), t + 1.51, 0.25)
                for pp in np.arange(phi - 12, phi + 12.1, 3)]
        a2, u2, t2, _ = max(near, key=lambda c: c[0])
        if a2 >= area:
            t, u = float(t2), u2
    return {"tilt_deg": float(t), "up": u}


def structure_tilt(P: np.ndarray, F: np.ndarray, cone: float = 30.0, iters: int = 8) -> dict:
    """The way up a thing's own surfaces say: floors and roofs face up, walls face sideways (area weighted, refined)."""
    n, a = face_normals(P, F)
    u = np.array([0.0, 1.0, 0.0])
    cv, sh = np.cos(np.radians(cone)), np.sin(np.radians(cone))
    for _ in range(iters):
        d = n @ u
        flat, wall = np.abs(d) > cv, np.abs(d) < sh
        parts = []
        if a[flat].sum() > 0:
            v = (n[flat] * np.sign(d[flat])[:, None] * a[flat][:, None]).sum(0)
            parts.append((v / np.linalg.norm(v), float(a[flat].sum())))
        if a[wall].sum() > 0:
            M = (n[wall, :, None] * n[wall, None, :] * a[wall][:, None, None]).sum(0)
            w, V = np.linalg.eigh(M)
            v = V[:, 0] * (np.sign(V[:, 0] @ u) or 1.0)
            parts.append((v, float(a[wall].sum())))
        if not parts:
            break
        u2 = sum(v * w for v, w in parts)
        u2 = u2 / np.linalg.norm(u2)
        if np.allclose(u2, u, atol=1e-7):
            break
        u = u2
    return {"tilt_deg": float(np.degrees(np.arccos(min(1.0, abs(float(u[1])))))), "up": u}


def check_level(m: dict, s: dict) -> dict:
    lim = float(s["level_max_deg"])
    sup = support_tilt(_parts(m, s)["assembly"])          # the floor of the thing itself, never of a piece floating under it
    st = structure_tilt(m["P"], m["F"])
    tilt, own = round(sup["tilt_deg"], 1), round(st["tilt_deg"], 1)
    between = float(np.degrees(np.arccos(min(1.0, abs(float(sup["up"] @ st["up"]))))))
    fix = quat_between(sup["up"], [0.0, 1.0, 0.0])
    base = {"check": "level", "tilt_deg": tilt, "structure_deg": own, "between_deg": round(between, 1), "straighten": fix}
    if tilt <= lim:
        return {**base, "ok": True, "line": f"{NAMES['level']}: {tilt}° off level — passes (the limit is {lim:g}°)."}
    if own <= max(2 * lim, 4.0) and (between > 8.0 or own <= lim):
        return {**base, "ok": True, "rests_on_slope": True,
                "line": f"{NAMES['level']}: upright by its own walls and posts ({own}° off); it rests {tilt}° off level on a slope "
                        "or on parts that hang lower (a stair, a wall-mounted box) — passes, not straightened."}
    if between <= 8.0:
        return {**base, "ok": False, "leans_as_whole": True,
                "line": f"{NAMES['level']}: {tilt}° off level, and its own walls lean the same way (the limit is {lim:g}°) — held back. "
                        "It leans as a whole, so Straighten fixes it without remaking it."}
    return {**base, "ok": False,
            "line": f"{NAMES['level']}: which way is up isn't clear — it rests {tilt}° off level, its own walls say {own}° — held back. "
                    "Look at it: Straighten turns it onto the plane it rests on."}


def _parts(m: dict, s: dict) -> dict:
    """The mesh's pieces: the main body, which pieces are joined to it, and the points of that assembly (cached in m)."""
    if "_parts" in m:
        return m["_parts"]
    P, F = m["P"], m["F"]
    lab = components(P, F)
    ids = np.unique(lab)
    area = face_normals(P, F)[1]
    carea = np.bincount(np.searchsorted(ids, lab), weights=area, minlength=len(ids))
    main = ids[int(np.argmax(carea))]
    diag = float(np.linalg.norm(P.max(0) - P.min(0))) or 1.0
    res = diag * float(s["loose_gap"])
    lo = P.min(0)
    main_v = P[np.unique(F[lab == main].ravel())]
    occ = set(map(tuple, np.unique(np.floor((main_v - lo) / res).astype(np.int64), axis=0)))
    offs = [(i, j, k) for i in (-1, 0, 1) for j in (-1, 0, 1) for k in (-1, 0, 1)]
    # which pieces are joined to the main body: a real share of their surface lies against it, not one grazing corner
    pieces = []
    for n_, k in enumerate(ids):
        if k == main:
            continue
        pts = P[np.unique(F[lab == k].ravel())]
        size = float(np.linalg.norm(pts.max(0) - pts.min(0))) / diag
        vox = np.unique(np.floor((pts - lo) / res).astype(np.int64), axis=0)
        near = sum(1 for v in vox if any((v[0] + o[0], v[1] + o[1], v[2] + o[2]) in occ for o in offs))
        pieces.append({"n": n_, "label": k, "pts": pts, "size": size, "joined": near >= max(3, 0.02 * len(vox))})
    assembly = np.vstack([main_v] + [p["pts"] for p in pieces if p["joined"]])
    m["_parts"] = {"lab": lab, "ids": ids, "area": area, "carea": carea, "main": main, "pieces": pieces,
                   "assembly": assembly, "res": res}
    return m["_parts"]


TIDY_SCRAPS = 0.02        # tidy (Blender) takes off every loose piece with fewer than this share of the largest piece's points
HANG_SCRAPS = 0.002       # ... but a thing that hangs keeps its drops: only dust goes (world.place_final)


def _gap(pts: np.ndarray, others: np.ndarray, sample: int = 500) -> float:
    """The nearest distance between a piece's points and the rest's (plain numpy; the piece is sampled)."""
    if not len(pts) or not len(others):
        return float("inf")
    a = pts[np.linspace(0, len(pts) - 1, min(sample, len(pts))).astype(np.int64)].astype(np.float32)
    b = others.astype(np.float32)
    best = np.inf
    for i in range(0, len(a), 24):
        d = a[i: i + 24, None, :] - b[None, :, :]
        best = min(best, float(np.einsum("ijk,ijk->ij", d, d).min()))
    return float(np.sqrt(best))


def _loose_rows(m: dict, s: dict, hangs: bool = False) -> tuple[list[dict], dict]:
    """Every loose piece with the faces it is made of (`sel`) and, where the queue may put it right by itself, how
    (`fix`: "off" — it lies wholly under the floor; "lift" — it stands a little through the floor, with `lift`, how far
    up it must go, in the model's own units). Also what a hanging thing's separate pieces measured (`hung`)."""
    P, F = m["P"], m["F"]
    pt = _parts(m, s)
    lab, carea, pieces, assembly, res = pt["lab"], pt["carea"], pt["pieces"], pt["assembly"], pt["res"]
    tot = float(pt["area"].sum()) or 1.0
    h = max(float(np.ptp(P[:, 1])), 1e-9)
    diag = float(np.linalg.norm(P.max(0) - P.min(0))) or 1.0
    # the floor is the floor of the main body and what is joined to it (a free-floating slab must not become the floor)
    g = None if hangs else ground_plane(assembly)
    tol = max(0.02 * h, res)
    main_faces = max(int((lab == pt["main"]).sum()), 1)
    rows, hung = [], []
    for p in pieces:
        if p["joined"] or p["size"] < float(s["loose_min_size"]):
            continue
        pts = p["pts"]
        row = {}
        if hangs:
            # a thing that hangs has no floor to stand on: a crystal drop on a wire too thin to model hangs BY the frame,
            # a finger's width from it — it is loose only when it is far from everything else
            gap = _gap(pts, assembly) / diag
            if gap <= float(s["loose_hang_gap"]):
                hung.append(gap)
                continue
            where = "in the air"
        else:
            low = pts[np.argmin(pts[:, 1])]
            dist = float(low[1] - (g["coef"][0] * low[0] + g["coef"][1] * low[2] + g["coef"][2]))
            if abs(dist) <= tol:
                continue                                       # it stands on the ground by itself (a post, a bollard)
            d = pts[:, 1] - (g["coef"][0] * pts[:, 0] + g["coef"][1] * pts[:, 2] + g["coef"][2])
            top, sunk, own = float(d.max()), float(-d.min()), max(float(np.ptp(pts[:, 1])), 1e-9)
            where = "below the floor" if dist < 0 else "in the air"
            if top <= tol:
                row.update(fix="off", why="under the floor")   # nothing of it reaches up to the floor
            elif dist < 0 and top > tol and sunk <= float(s["loose_sink_max"]) * h and sunk <= float(s["loose_sink_own"]) * own:
                row.update(fix="lift", why="a little through the floor", lift=round(sunk, 6),
                           sunk=round(sunk / h, 4))            # it stands by itself, a little through the floor
        sel = lab == p["label"]
        rows.append({"size": round(p["size"], 3), "surface": round(float(carea[p["n"]]) / tot, 4), "faces": int(sel.sum()),
                     "of_main": round(float(sel.sum()) / main_faces, 4), "where": where, **row, "sel": sel})
    rows.sort(key=lambda r: -r["size"])
    return rows, {"pieces": int(len(pt["ids"])), "hung": hung}


def _can_fix(rows: list[dict], s: dict) -> tuple[bool, float]:
    """Whether the queue may put right what it can (and the share of the surface it would take off)."""
    off = float(sum(r["surface"] for r in rows if r.get("fix") == "off"))
    some = any(r.get("fix") for r in rows)
    return bool(some and s.get("loose_fix") and off < float(s["loose_fix_max_share"])), off


def check_loose(m: dict, s: dict, hangs: bool = False) -> dict:
    P, F = m["P"], m["F"]
    if not len(F):
        return {"check": "loose", "ok": True, "pieces": 0, "loose": [], "line": f"{NAMES['loose']}: no surface to check."}
    rows, info = _loose_rows(m, s, hangs)
    faces = np.zeros(len(F), dtype=bool)
    for r in rows:
        faces |= r["sel"]
    loose = [{k: v for k, v in r.items() if k != "sel"} for r in rows]
    can, share = _can_fix(rows, s)
    ok = not loose
    if ok and hangs and info["hung"]:
        n = len(info["hung"])
        line = (f"{NAMES['loose']}: none — it hangs, so it has no floor to stand on: its {n} separate piece{'s' if n > 1 else ''} "
                f"hang{'s' if n == 1 else ''} close by the rest (the furthest {max(info['hung']) * 100:.1f}% of its size away).")
    elif ok:
        line = f"{NAMES['loose']}: none — every part is joined to the rest or stands on the ground."
    else:
        big = loose[0]
        line = (f"{NAMES['loose']}: {len(loose)} piece{'s' if len(loose) > 1 else ''} not joined to the rest "
                f"(the largest, {big['where']}, is {big['size'] * 100:.0f}% of the model's size and {big['surface'] * 100:.1f}% "
                "of its surface) — held back.")
        if any(r.get("fix") == "off" for r in loose) and not can and s.get("loose_fix"):
            line += f" (What lies under the floor is {share * 100:.0f}% of the surface: too much to take off unasked.)"
    out = {"check": "loose", "ok": ok, "pieces": info["pieces"], "loose": loose, "line": line, "faces": faces}
    if any(r.get("fix") for r in loose):
        out.update(can_fix=can, fix_share=round(share, 4))
    if hangs:
        out.update(hangs=True, hung=[round(x, 4) for x in info["hung"]])
    return out


def fix_loose(src: Path, dst: Path, cfg: dict | None = None, hangs: bool = False) -> dict:
    """BUILD 84 (2f) — the loose pieces nobody would miss, put right: one that lies wholly under the floor (a sheet of
    ground the image-to-3D step left there) is taken off, its triangles and their vertices out of the file
    (`Glb.drop_faces`), while what is taken off is under `loose_fix_max_share` of the surface; one that stands by itself
    a little through the floor is stood on the floor (`Glb.move_faces`, up by what it was sunk). Either way the thing is
    stood on its own floor afterwards, not on what was under it. Writes `dst` only when something changed; `src` is
    never changed. Returns {"ok" (nothing loose is left), "changed", "removed", "lifted", "share", "left"}."""
    s = settings(cfg)
    g = Glb.load(src)
    m = g.mesh()
    if not len(m["F"]):
        return {"ok": True, "changed": False, "left": 0}
    rows, _ = _loose_rows(m, s, hangs)
    can, share = _can_fix(rows, s)
    if not can:
        return {"ok": not rows, "changed": False, "left": len(rows), "share": round(share, 4)}
    plain = lambda r: {k: v for k, v in r.items() if k != "sel"}   # noqa: E731
    lifted = [r for r in rows if r.get("fix") == "lift"]
    for r in lifted:                                         # first: positions only, the triangles keep their order
        g.move_faces(r["sel"], (0.0, float(r["lift"]), 0.0))
    off = [r for r in rows if r.get("fix") == "off"]
    if off:
        drop = np.zeros(len(m["F"]), dtype=bool)
        for r in off:
            drop |= r["sel"]
        g.drop_faces(drop)
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    g.save(dst)
    after = check_loose(Glb.load(dst).mesh(), s, hangs)
    return {"ok": after["ok"], "changed": True, "share": round(share, 4), "left": len(after["loose"]),
            "removed": [plain(r) for r in off], "lifted": [plain(r) for r in lifted]}


def loose_words(fr: dict) -> list[str]:
    """What `fix_loose` did, in sentences for the thing's report."""
    out = []
    off, up = fr.get("removed") or [], fr.get("lifted") or []
    if off:
        n = len(off)
        out.append(f"Loose pieces: {n} piece{'s' if n > 1 else ''} taken off by the queue — {'it' if n == 1 else 'they'} lay "
                   f"wholly under the floor ({'a piece' if n == 1 else 'pieces'} of ground the image-to-3D step left there): "
                   f"{sum(r['surface'] for r in off) * 100:.1f}% of the surface, {sum(r['faces'] for r in off):,} triangles. "
                   "Nothing above the floor has changed; the model as made is kept beside it.")
    if up:
        n = len(up)
        small = all(r.get("of_main", 1.0) < TIDY_SCRAPS for r in up)
        out.append(f"Loose pieces: {n} piece{'s' if n > 1 else ''} that stood by {'itself' if n == 1 else 'themselves'} a little "
                   f"through the floor ({max(r['sunk'] for r in up) * 100:.1f}% of the model's height at most) stood on the "
                   f"floor by the queue — so the thing stands on its own floor, not on {'its' if n == 1 else 'their'} feet. "
                   + (f"({'It is' if n == 1 else 'They are'} small enough — under {TIDY_SCRAPS * 100:.0f}% of the main piece — "
                      f"that tidying takes {'it' if n == 1 else 'them'} off altogether where Blender is there to tidy; "
                      "the model as made is kept beside it.)" if small else
                      "Look at it in Review: the image-to-3D step put it there, not the picture (the model as made is kept "
                      "beside it)."))
    return out


def _face_colours(F: np.ndarray, UV: np.ndarray, img, samples=((1 / 3, 1 / 3), (0.6, 0.2), (0.2, 0.6), (0.2, 0.2))) -> np.ndarray:
    T = np.asarray(img.convert("RGB"), dtype=np.float32)
    th, tw = T.shape[:2]
    out = []
    for w0, w1 in samples:
        w2 = 1 - w0 - w1
        u = w0 * UV[F[:, 0], 0] + w1 * UV[F[:, 1], 0] + w2 * UV[F[:, 2], 0]
        v = w0 * UV[F[:, 0], 1] + w1 * UV[F[:, 1], 1] + w2 * UV[F[:, 2], 1]
        out.append(T[np.clip((v * th).astype(np.int64), 0, th - 1), np.clip((u * tw).astype(np.int64), 0, tw - 1)])
    return np.stack(out, 1)


def check_glass(m: dict, g: Glb, s: dict) -> dict:
    P, F, UV = m["P"], m["F"], m["UV"]
    area = face_normals(P, F)[1]
    tot = float(area.sum()) or 1.0
    white_mirror = np.zeros(len(F), bool)
    flat_white = np.zeros(len(F), bool)
    for mi, mat in enumerate(m["materials"] or []):
        sel = m["face_material"] == mi
        if not sel.any():
            continue
        pbr = mat.get("pbrMetallicRoughness") or {}
        base = g.texture_image(mat, "baseColorTexture")
        bf = np.array((pbr.get("baseColorFactor") or [1, 1, 1, 1])[:3], dtype=np.float32) * 255
        if base is not None:
            C = _face_colours(F[sel], UV, base) * (bf / 255.0)
        else:
            C = np.broadcast_to(bf, (int(sel.sum()), 4, 3))
        mean = C.mean(1)
        spread = C.max(axis=(1, 2)) - C.min(axis=(1, 2))
        bright = (mean.min(1) > 200) & (spread < 18)
        mr = g.texture_image(mat, "metallicRoughnessTexture")
        metal_f, rough_f = float(pbr.get("metallicFactor", 1.0)), float(pbr.get("roughnessFactor", 1.0))
        if mr is not None:
            M = _face_colours(F[sel], UV, mr).mean(1)
            metal, rough = M[:, 2] / 255 * metal_f, M[:, 1] / 255 * rough_f
        else:
            metal, rough = np.full(int(sel.sum()), metal_f), np.full(int(sel.sum()), rough_f)
        mirror = (metal > 0.9) & (rough < 0.1)
        idx = np.nonzero(sel)[0]
        white_mirror[idx] = bright & mirror
        flat_white[idx] = bright & (mean.min(1) > 245) & (spread < 4)
    share = float(area[white_mirror].sum()) / tot
    ok = share <= float(s["glass_max_share"])
    line = (f"{NAMES['glass']}: none." if share == 0 else
            f"{NAMES['glass']}: {share * 100:.2f}% of the surface is a white mirror — passes (the limit is {float(s['glass_max_share']) * 100:.1f}%)."
            if ok else
            f"{NAMES['glass']}: {share * 100:.1f}% of the surface is a white mirror (windows, lamps, glass, polished metal) — "
            "in a plain room it renders blank white. Held back.")
    return {"check": "glass", "ok": ok, "share": round(share, 4), "faces": white_mirror, "line": line}


def picture_mask(img, size: int = 384, thresh: float = 28.0) -> np.ndarray:
    """The thing in its picture: everything that differs from the plain background (taken from the picture's border),
    except a soft grey cast shadow."""
    from PIL import Image
    im = np.asarray(img.convert("RGB").resize((size, size), Image.LANCZOS), dtype=np.float32)
    border = np.concatenate([im[:4].reshape(-1, 3), im[-4:].reshape(-1, 3), im[:, :4].reshape(-1, 3), im[:, -4:].reshape(-1, 3)])
    bg = np.median(border, axis=0)
    d = np.linalg.norm(im - bg, axis=2)
    chroma = im.max(2) - im.min(2)
    drop = bg.mean() - im.mean(2)
    shadow = (chroma < 12) & (drop > 0) & (drop < 40) & (d < 45)
    return (d > thresh) & ~shadow


def _align(P: np.ndarray, target_small: np.ndarray, size: int = 128) -> tuple[float, float, float]:
    target = raster.dilate(raster.closing(target_small, 2), 2)
    box = raster.robust_box(target)

    def score(az, el):
        s_ = raster.fit_into(raster.dilate(raster.splat(P, az, el, size), 1), box, size)
        s_ = raster.dilate(raster.closing(s_, 2), 2)
        return float((s_ & target).sum()) / max(int((s_ | target).sum()), 1)
    best = max((score(az, el), az, el) for el in (0, 15, 30, 45) for az in range(0, 360, 15))
    _, az0, el0 = best
    best = max([best] + [(score(az0 + da, el0 + de), az0 + da, el0 + de) for de in (-8, -4, 0, 4, 8) for da in (-8, -4, 0, 4, 8)])
    return best


def _outside(bg: np.ndarray) -> np.ndarray:
    """Background pixels reachable from the picture's edge (a flood fill, numpy only)."""
    reach = np.zeros_like(bg)
    reach[0, :], reach[-1, :], reach[:, 0], reach[:, -1] = bg[0, :], bg[-1, :], bg[:, 0], bg[:, -1]
    while True:
        grown = raster.dilate(reach, 1) & bg
        if (grown == reach).all():
            return reach
        reach = grown


def hole_share(mask: np.ndarray, r: int) -> tuple[float, np.ndarray, np.ndarray]:
    """How much of an outline (small gaps closed by r) is enclosed see-through: (share, the holes, the filled outline)."""
    m = raster.closing(mask, r)
    holes = ~m & ~_outside(~m)
    filled = m | holes
    return float(holes.sum()) / max(int(filled.sum()), 1), holes, filled


def check_thin(m: dict, picture, s: dict, size: int = 320) -> dict:
    from PIL import Image
    if picture is None:
        return {"check": "thin", "ok": True, "skipped": True, "line": f"{NAMES['thin']}: no picture to compare with — not checked."}
    pm = picture_mask(picture, size)
    if pm.sum() < 50:
        return {"check": "thin", "ok": True, "skipped": True,
                "line": f"{NAMES['thin']}: the thing couldn't be told from its picture's background — not checked."}
    small = np.asarray(Image.fromarray(pm.astype(np.uint8) * 255).resize((128, 128), Image.BILINEAR)) > 60
    match, az, el = _align(m["P"], small)
    R = raster.view_matrix(az, el)
    scr, _ = raster.project(m["P"], R, size)
    sil = raster.rasterize(scr, m["F"], size)[0]
    box = raster.robust_box(pm)
    r = max(2, int(round(max(box[2] - box[0], box[3] - box[1]) * 0.02)))
    hp, _, _ = hole_share(pm, r)
    hm, holes, filled = hole_share(sil, r)
    lost = max(0.0, hm - hp)
    lim = float(s["thin_max_lost"])
    ok = lost <= lim
    line = (f"{NAMES['thin']}: {lost * 100:.0f}% of the outline is open where the picture is filled — passes (the limit is "
            f"{lim * 100:.0f}%)." if ok else
            f"{NAMES['thin']}: {lost * 100:.0f}% of the model's outline is open where the picture is filled (the limit is "
            f"{lim * 100:.0f}%) — see-through parts (mesh, netting, grilles) did not come through. Held back: make it as a "
            "cut-out panel instead.")
    return {"check": "thin", "ok": ok, "lost": round(lost, 3), "model_holes": round(hm, 3), "picture_holes": round(hp, 3),
            "view": [float(az), float(el)], "match": round(match, 3), "outline": (filled & ~holes, holes), "line": line}


# ------------------------------------------------------------------------------------------------ colours hold (BUILD 40)
def _luma(a: np.ndarray) -> np.ndarray:
    return a[..., 0] * 0.2126 + a[..., 1] * 0.7152 + a[..., 2] * 0.0722


def _base_textures(g: Glb, m: dict) -> list[tuple[int, dict]]:
    """(texture index, material) for every material that has a colour texture."""
    out = []
    for mat in m["materials"] or []:
        ref = (mat.get("pbrMetallicRoughness") or {}).get("baseColorTexture")
        if ref and "textures" in g.j and (ref["index"], mat) not in out:
            out.append((int(ref["index"]), mat))
    return out


def metal_texture(g: Glb, mat: dict):
    """BUILD 84: the material's metalness as a picture the renderer can sample (the metallicRoughness texture's blue channel
    times metallicFactor, in all three channels, 0-255), or None when the material says nothing of metal."""
    from PIL import Image
    pbr = mat.get("pbrMetallicRoughness") or {}
    f = float(pbr.get("metallicFactor", 1.0))
    mr = g.texture_image(mat, "metallicRoughnessTexture")
    if mr is None:
        return None if f < 0.5 else Image.new("RGB", (4, 4), (255, 255, 255))   # no texture: the factor is the metal
    b = np.asarray(mr.convert("RGB"), dtype=np.float64)[..., 2] * f
    b = np.clip(np.round(b), 0, 255).astype(np.uint8)
    return Image.fromarray(np.stack([b, b, b], -1), "RGB")


def front_view(m: dict, g: Glb, picture, size: int = 384, body: bool = False, info: dict | None = None):
    """The model's colours as stored (no light), seen from the view its picture was taken from, with the picture's figure
    at the same size. Returns (model pixels (n,3), picture pixels (k,3), model head pixels, picture head pixels, view,
    model render (size,size,3) on grey, picture (size,size,3)).

    BUILD 84: parts the model marks as metal are left out of both sides (a metal's own colour is darker than its lit
    picture, because in the game its brightness comes from what it reflects); `info`, if given, gets "metal_share" — the
    share of the model's visible pixels that are metal."""
    from PIL import Image
    pm = picture_mask(picture, size)
    small = np.asarray(Image.fromarray(pm.astype(np.uint8) * 255).resize((128, 128), Image.BILINEAR)) > 60
    match, az, el = _align(m["P"], small)
    mats = m["materials"] or []
    tex = g.texture_image(mats[0], "baseColorTexture") if mats else None
    if tex is None:
        raise ValueError("the model has no colour texture")
    P = np.asarray(picture.convert("RGB").resize((size, size), Image.LANCZOS), dtype=np.float64)
    if body and 90 < az % 360 < 270:
        # an outline is the same from the front and from behind. A body's picture is always taken from the front, and
        # every body the image-to-3D step made (40 of 40 in the two launch-site runs) faces the front at azimuth 0, so a
        # body is seen from the front half. (A prop keeps the view its outline matches best: a three-quarter picture
        # rarely matches its own back.)
        az = (az + 180) % 360
    R = raster.view_matrix(az, el)
    scr, _ = raster.project(m["P"], R, size)
    mask, _, col, _ = raster.rasterize(scr, m["F"], size, m["UV"], tex, want_color=True)
    metal = np.zeros(mask.shape, bool)
    mtex = metal_texture(g, mats[0]) if mats else None
    if mtex is not None:
        _, _, mcol, _ = raster.rasterize(scr, m["F"], size, m["UV"], mtex, want_color=True)
        metal = mask & (mcol[..., 0] >= float(DEFAULTS["metal_from"]) * 255)
    if info is not None:
        info["metal_share"] = round(float(metal.sum()) / max(int(mask.sum()), 1), 3)
    if metal.any():
        # the picture's figure stands where the model's does (the view was chosen to match their outlines): the metal's
        # place, grown by two pixels for the seam, is taken out of the picture too
        pm = pm & ~raster.dilate(metal, 2)
        mask_c = mask & ~metal
    else:
        mask_c = mask

    def head(msk):
        rows = np.nonzero(msk.any(1))[0]
        if not len(rows):
            return msk
        top, bot = int(rows.min()), int(rows.max())
        h = msk.copy()
        h[top + max(1, int((bot - top) / 7)):, :] = False
        return h
    render = np.where(mask[..., None], col, 232.0)
    return (col[mask_c], P[pm], col[head(mask_c)], P[head(pm)], (float(az), float(el), float(match)), render, P)


def _stats(px: np.ndarray) -> dict:
    y = _luma(px) if len(px) else np.zeros(1)
    p10, p50, p90 = np.percentile(y, [10, 50, 90])
    return {"p10": round(float(p10), 1), "p50": round(float(p50), 1), "p90": round(float(p90), 1), "mean": round(float(y.mean()), 1)}


def check_colour(m: dict, g: Glb, picture, s: dict, kind: str = "prop") -> dict:
    if picture is None:
        return {"check": "colour", "ok": True, "skipped": True, "line": f"{NAMES['colour']}: no picture to compare with — not checked."}
    vinfo: dict = {}
    mp, pp, mh, ph, view, render, P = front_view(m, g, picture, body=kind in BODY_KINDS, info=vinfo)
    metal_share = float(vinfo.get("metal_share") or 0.0)
    if metal_share >= float(s.get("metal_skip_share", DEFAULTS["metal_skip_share"])):
        return {"check": "colour", "ok": True, "skipped": True, "metal_share": round(metal_share, 3),
                "line": f"{NAMES['colour']}: {metal_share * 100:.0f}% of what its picture shows is marked as metal — a metal's "
                        "brightness comes from what it reflects, not from its own colour, so it is not checked."}
    if len(pp) < 200 or len(mp) < 200:
        return {"check": "colour", "ok": True, "skipped": True,
                "line": f"{NAMES['colour']}: the thing couldn't be told from its picture's background — not checked."}
    sm, sp = _stats(mp), _stats(pp)
    mean_r = sm["mean"] / max(sp["mean"], 1.0)
    spread_r = (sm["p90"] - sm["p10"]) / max(sp["p90"] - sp["p10"], 1.0)
    body = kind in BODY_KINDS
    lo, hi = s["colour_mean_band"] if body else s["colour_prop_band"]
    probs = []
    if not lo <= mean_r <= hi:
        probs.append(f"{mean_r * 100:.0f}% as bright as its picture")
    if body and spread_r < float(s["colour_spread_min"]):
        probs.append(f"{spread_r * 100:.0f}% of its picture's contrast")
    head_r, head = None, None
    if body:
        # BUILD 73: the head band from the level front view in both (from above, a head is mostly hair), the face (skin
        # only) and the hair measured apart. The old band (the top seventh of the aligned view) is kept as head_band_ratio.
        try:
            head = head_check(m, g, picture, s)
        except Exception as ex:  # noqa: BLE001 — a figure the split can't read falls back to the old band, said so
            head = {"ok": None, "why": f"the face couldn't be told apart ({ex})"}
        if head.get("ok") is None and len(mh) > 50 and len(ph) > 50:
            head_r = _stats(mh)["mean"] / max(_stats(ph)["mean"], 1.0)
            hlo, hhi = s["colour_head_band"]
            if not hlo <= head_r <= hhi:
                probs.append(f"the head {head_r * 100:.0f}% as bright as the picture's")
        elif head.get("ok") is not None:
            head_r = head["face_ratio"]
            if not head["ok"]:
                probs.append(f"the face {head['face_ratio'] * 100:.0f}% as bright as the picture's")
    prop = None
    if not body:
        prop = prop_check(sm, sp, mp, pp, s)
        probs = [] if prop["ok"] else [prop["why"]]
        mean_r = prop["mid_ratio"]
    ok = not probs
    head_said = ""
    if head and head.get("ok") is not None:
        head_said = (f", the face {head['face_ratio'] * 100:.0f}%" + (f" and the hair {head['hair_ratio'] * 100:.0f}%" if head.get("hair_ratio") is not None else "")
                     + (" (the picture's face is in shadow — a hat or a hood — so the face alone doesn't hold it)" if head.get("shadowed") else ""))
    elif head_r is not None:
        head_said = f", the head {head_r * 100:.0f}%"
    if prop is not None:
        head_said = prop["said"]
    line = (f"{NAMES['colour']}: {mean_r * 100:.0f}% of its picture's brightness, {spread_r * 100:.0f}% of its contrast"
            + head_said + " — passes." if ok else
            f"{NAMES['colour']}: " + "; ".join(probs) + " (the colour texture as stored, against the picture it was made from) — "
            + ("held back. Put right by matching it to the picture; nothing is remade." if body else
               "held back. The matched colours are shown beside it: a person chooses them or lets it through (a prop's "
               "picture carries studio light the texture rightly doesn't, so the match isn't trusted blind)."))
    if metal_share >= 0.02:
        line = line.replace(" — passes.", f" — passes (the {metal_share * 100:.0f}% marked as metal left out).") if ok else \
            line.replace(" (the colour texture as stored,", f" (the {metal_share * 100:.0f}% marked as metal left out; the colour texture as stored,")
    out = {"check": "colour", "ok": ok, "body": body, "auto_fix": body, "mean_ratio": round(mean_r, 3), "spread_ratio": round(spread_r, 3),
           "head_ratio": None if head_r is None else round(head_r, 3), "model": sm, "picture": sp, "view": list(view[:2]),
           "pairs": (mp, pp), "render": render, "picture_px": P, "line": line, "metal_share": round(metal_share, 3)}
    if head and head.get("ok") is not None:
        sp_ = head.get("split") or ({}, {})
        out.update(face_chroma=[sp_[0].get("ref_chroma"), sp_[1].get("ref_chroma")])
        out.update(face_ratio=head["face_ratio"], hair_ratio=head.get("hair_ratio"), head_shadowed=bool(head.get("shadowed")),
                   head_view=[0.0, 0.0], face_only=bool(probs) and all(pr.startswith("the face") for pr in probs),
                   head_pairs=head.get("pairs"))
    if prop is not None:
        out.update(prop=prop)
    return out


# ------------------------------------------------------------------------------------------------ BUILD 73: the face, not the hair
def _chroma(px: np.ndarray) -> np.ndarray:
    t = px.sum(-1, keepdims=True) + 1e-6
    return px[..., :2] / t


def face_split(img: np.ndarray, mask: np.ndarray, s: dict | None = None) -> dict:
    """A figure seen level from the front (img (H,W,3) 0-255, mask (H,W) bool): its head band (the top seventh), the face
    in it (skin only — the pixels nearest the face's own colour, not hair, a hat or glasses) and the rest of the band (the
    hair), and the skin below the head (neck and hands). The face's own colour is taken from the band's lower middle, where
    a face is, by chromaticity; a pixel counts as skin when its chromaticity is near that and its brightness is within a
    band of the face's middle — so dark hair of the same hue is not skin. Numpy only."""
    s = {**DEFAULTS, **(s or {})}
    img = np.asarray(img, dtype=np.float64)
    rows = np.nonzero(mask.any(1))[0]
    if len(rows) < 14:
        return {"found": False}
    top, bot = int(rows.min()), int(rows.max())
    hb = max(2, int(round((bot - top) / 7)))
    yy = np.arange(mask.shape[0])[:, None]
    xx = np.arange(mask.shape[1])[None, :]
    band = mask & (yy >= top) & (yy < top + hb)
    ys, xs = np.nonzero(band)
    if len(xs) < 20:
        return {"found": False}
    # the head's own middle column, from the band's lower half (shoulders and hats are wider than a face)
    low = band & (yy >= top + hb * 0.45)
    lx = np.nonzero(low)[1] if low.any() else xs
    cx, w = (np.percentile(lx, 10) + np.percentile(lx, 90)) / 2, max(4.0, np.percentile(lx, 90) - np.percentile(lx, 10))
    seed = low & (np.abs(xx - cx) <= 0.22 * w + 1)
    if seed.sum() < 8:
        seed = low if low.sum() >= 8 else band
    Y = _luma(img)
    sy = Y[seed]
    keep = (sy >= np.percentile(sy, 25)) & (sy <= np.percentile(sy, 97))       # not the eyes, brows and nostrils
    ref_c = np.median(_chroma(img[seed][keep]), axis=0)
    ref_y = float(np.median(sy[keep])) if keep.any() else float(np.median(sy))
    C = _chroma(img)
    near = np.linalg.norm(C - ref_c, axis=-1) <= float(s["face_chroma_tol"])
    lo, hi = s["face_luma_band"]
    lit = (Y >= lo * ref_y) & (Y <= hi * ref_y)
    skin = band & near & lit
    hair = band & ~skin
    # the neck: just under the head band, within the face's own width — found by its colour alone, since a face in a
    # hat's shadow and the lit neck under it are the same skin at two brightnesses (a beige shirt below stays out)
    below = mask & (yy >= top + hb) & (yy < top + int(hb * 1.7)) & (np.abs(xx - cx) <= 0.5 * w + 1)
    skin_below = below & near & (Y > 25)
    return {"found": True, "top": top, "band_h": hb, "band": band, "face": skin, "hair": hair, "skin_below": skin_below,
            "face_luma": float(Y[skin].mean()) if skin.sum() >= 12 else None,
            "hair_luma": float(Y[hair].mean()) if hair.sum() >= 12 else None,
            "below_luma": float(Y[skin_below].mean()) if skin_below.sum() >= 12 else None,
            "ref_chroma": [round(float(c), 4) for c in ref_c], "ref_luma": round(ref_y, 1)}


def face_verdict(model: dict, picture: dict, s: dict | None = None) -> dict:
    """The face of the model against the face of the picture (both from face_split): two numbers, face and hair, and a
    verdict on the face alone. Where the picture's own face is more than a third darker than its neck and hands (a hat's
    shadow), it is said so and the head alone does not hold the thing."""
    s = {**DEFAULTS, **(s or {})}
    if not (model.get("found") and picture.get("found")) or model.get("face_luma") is None or picture.get("face_luma") is None:
        return {"ok": None, "why": "no face was found to compare"}
    fr = model["face_luma"] / max(picture["face_luma"], 1.0)
    hr = (model["hair_luma"] / max(picture["hair_luma"], 1.0)
          if model.get("hair_luma") is not None and picture.get("hair_luma") is not None else None)
    shadowed = (picture.get("below_luma") is not None
                and picture["face_luma"] < (1.0 - float(s["head_shadow_share"])) * picture["below_luma"])
    lo, hi = s["colour_head_band"]
    inside = lo <= fr <= hi
    return {"ok": bool(inside or shadowed), "face_ratio": round(fr, 3), "hair_ratio": None if hr is None else round(hr, 3),
            "shadowed": bool(shadowed), "inside": bool(inside),
            "picture_face": round(picture["face_luma"], 1), "picture_neck_hands": None if picture.get("below_luma") is None else round(picture["below_luma"], 1),
            "model_face": round(model["face_luma"], 1)}


def level_front(m: dict, g: Glb, picture, size: int = 384):
    """The model's stored colours seen level from the front (azimuth 0, elevation 0 — every body faces +Z, 40 of 40), and
    its picture at the same size: (render (size,size,3), model mask, picture (size,size,3), picture mask)."""
    from PIL import Image
    mats = m["materials"] or []
    tex = g.texture_image(mats[0], "baseColorTexture") if mats else None
    if tex is None:
        raise ValueError("the model has no colour texture")
    R = raster.view_matrix(0.0, 0.0)
    scr, _ = raster.project(m["P"], R, size)
    mask, _, col, _ = raster.rasterize(scr, m["F"], size, m["UV"], tex, want_color=True)
    pm = picture_mask(picture, size)
    P = np.asarray(picture.convert("RGB").resize((size, size), Image.LANCZOS), dtype=np.float64)
    return np.where(mask[..., None], col, 232.0), mask, P, pm


def head_check(m: dict, g: Glb, picture, s: dict) -> dict:
    """BUILD 73 part 1 on a model: the face and the hair from the level front, against the picture's."""
    render, mm, P, pm = level_front(m, g, picture)
    a, b = face_split(render, mm, s), face_split(P, pm, s)
    v = face_verdict(a, b, s)
    if v.get("ok") is not None:
        v["pairs"] = (render[a["band"]], P[b["band"]])        # what a head-only curve is fitted on (part 2)
        v["split"] = (a, b)
        v["frames"] = (render, P)
    return v


def prop_check(sm: dict, sp: dict, mp: np.ndarray, pp: np.ndarray, s: dict) -> dict:
    """BUILD 73 part 4: a prop against its picture with the picture's highlights taken out (its brightest tail above the
    90th percentile is not counted; the 10th and the 50th percentiles are compared). A picture whose own middle is below a
    floor is of a dark thing — it may be dark: it is held only if the model has lost its detail (contrast below a third
    of the picture's), not for being dark."""
    yp = _luma(pp) if len(pp) else np.zeros(1)
    ym = _luma(mp) if len(mp) else np.zeros(1)
    cut = np.percentile(yp, float(s["prop_highlight_pct"]))
    yt = yp[yp <= cut] if (yp <= cut).sum() > 20 else yp
    p10, p50 = np.percentile(yt, [10, 50])
    m10, m50 = np.percentile(ym, [10, 50])
    r50 = float(m50 / max(p50, 1.0))
    r10 = float(m10 / max(p10, 8.0))
    mid = r50                     # the middle decides; the shadows only say whether they were crushed
    det_p = float(np.percentile(yt, 90) - p10)
    det_m = float(np.percentile(ym, 90) - m10)
    detail = det_m / max(det_p, 1.0)
    dark = float(p50) < float(s["prop_dark_floor"])
    lo, hi = s["colour_prop_band"]
    if dark:
        ok = detail >= float(s["prop_detail_min"])
        why = (f"a dark thing that has lost its detail — {detail * 100:.0f}% of its picture's contrast" if not ok else "")
        said = f" (a dark thing: its picture's middle is {p50:.0f} of 255; it kept {detail * 100:.0f}% of the detail)"
    else:
        crushed = r10 < float(s["prop_shadow_min"])
        ok = lo <= mid <= hi and not crushed
        why = ("" if ok else f"{mid * 100:.0f}% as bright as its picture in the middle (highlights out)" if not lo <= mid <= hi
               else f"its shadows crushed — {r10 * 100:.0f}% of the picture's")
        said = f" (against the picture with its highlights out: the middle {r50 * 100:.0f}%, the shadows {r10 * 100:.0f}%)"
    return {"ok": bool(ok), "dark": bool(dark), "mid_ratio": round(mid, 3), "r50": round(r50, 3), "r10": round(r10, 3),
            "detail": round(detail, 3), "picture_mid": round(float(p50), 1), "why": why, "said": said}


def _max3(W: np.ndarray) -> np.ndarray:
    """A 3 x 3 maximum filter (numpy only)."""
    P = np.pad(W, 1, mode="edge")
    return np.max([P[1 + dy:P.shape[0] - 1 + dy, 1 + dx:P.shape[1] - 1 + dx] for dy in (-1, 0, 1) for dx in (-1, 0, 1)], axis=0)


def head_weights(m: dict, tex_size: tuple[int, int], head_line: float, feather: float) -> np.ndarray:
    """A weight in texture space (th, tw), 1 on the head's texels, 0 below the neck, feathered between: every face is
    weighted by its centre's height (y up) against the head line, and its texels are painted with that weight."""
    tw, th = tex_size
    P, F, UV = m["P"], m["F"], m["UV"]
    yc = P[F, 1].mean(1)
    wf = np.clip((yc - (head_line - feather)) / max(feather, 1e-9), 0.0, 1.0)
    size = max(tw, th)
    scr = np.c_[UV[:, 0] * size, UV[:, 1] * size, np.zeros(len(UV))]
    _, _, _, face_at = raster.rasterize(scr, F, size)
    W = np.where(face_at >= 0, wf[np.clip(face_at, 0, None)], 0.0)
    # small triangles miss every pixel centre and leave holes the renderer still samples (they showed as dark specks on
    # the first try): grow the weight into its own gaps, then soften it by a texel
    W = _max3(_max3(W))
    Pd = np.pad(W, 1, mode="edge")                       # (not np.roll: that wraps the head's rows onto the feet's)
    W = (W + Pd[:-2, 1:-1] + Pd[2:, 1:-1] + Pd[1:-1, :-2] + Pd[1:-1, 2:]) / 5.0
    W = np.maximum(W, np.where(face_at >= 0, wf[np.clip(face_at, 0, None)], 0.0))
    if (tw, th) != (size, size):
        from PIL import Image
        W = np.asarray(Image.fromarray((W * 255).astype(np.uint8)).resize((tw, th), Image.BILINEAR), dtype=np.float64) / 255.0
    return W


def fix_head(src: Path, dst: Path, picture, cfg: dict | None = None) -> dict:
    """BUILD 73 part 2: a whole-body match cannot mend a face, so the tone curve is fitted for the head alone (the level
    front's head band, model against picture) and applied to the head's texels only, feathered at the neck. `dst` is
    written; the model as made is left as it is. Returns {"ok", "before", "after", "lut"}.

    BUILD 84: not used on a body any more — no curve goes on a body, the head's included (one gain for the whole colour
    picture, `fix_colour_body`). Kept for a person's own use from the command line; `head_fix` is off by default."""
    from PIL import Image
    s = settings(cfg)
    g = Glb.load(src)
    m = g.mesh()
    before = head_check(m, g, picture, s)
    if before.get("ok") is None:
        return {"ok": False, "before": before, "why": before.get("why")}
    mp, pp = before["pairs"]
    ly = luma_curve(mp, pp, max_slope=float(s.get("colour_max_slope") or 3.0))     # brightness only: no colour cast on skin
    lut = np.stack([ly, ly, ly])
    y = m["P"][:, 1]
    top, bot = float(y.max()), float(y.min())
    band = (top - bot) / 7.0
    head_line = top - band
    mats = m["materials"] or []
    refs = _base_textures(g, m)
    if not refs:
        return {"ok": False, "before": before, "why": "no colour texture"}
    ti, mat = refs[0]
    img = g.texture_image(mat, "baseColorTexture")
    mode = img.mode
    a = np.asarray(img.convert("RGBA" if "A" in mode else "RGB")).astype(np.float64)
    W = head_weights(m, (a.shape[1], a.shape[0]), head_line, band * float(s["head_feather"]))
    out = a.copy()
    mapped = apply_luma(a, ly)
    for c in range(3):
        out[..., c] = a[..., c] * (1 - W) + mapped[..., c] * W
    g.replace_image(ti, Image.fromarray(np.clip(np.round(out), 0, 255).astype(np.uint8), "RGBA" if "A" in mode else "RGB"))
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    g.save(dst)
    g2 = Glb.load(dst)
    after = head_check(g2.mesh(), g2, picture, s)
    return {"ok": bool(after.get("ok")) and bool(after.get("inside") or after.get("shadowed")), "before": before, "after": after,
            "lut": lut, "head_texels": int((W > 0.5).sum())}


def head_picture(before: dict, after: dict | None, out: Path, size: int = 240) -> Path:
    """BUILD 73: before / after / picture for the head, at twice the size the check picture shows it."""
    from PIL import Image, ImageDraw
    font, plain = _font(14)

    def crop(frame, split):
        rows = np.nonzero(split["band"].any(1))[0]
        cols = np.nonzero(split["band"].any(0))[0]
        if not len(rows) or not len(cols):
            return Image.new("RGB", (size, size), (40, 40, 40))
        t, b = rows.min(), rows.max() + int(split["band_h"] * 0.3)
        cx = (cols.min() + cols.max()) // 2
        half = max(b - t, cols.max() - cols.min()) // 2 + 4
        box = (max(0, cx - half), max(0, t - 4), min(frame.shape[1], cx + half), min(frame.shape[0], t - 4 + 2 * half))
        return Image.fromarray(np.clip(frame, 0, 255).astype(np.uint8)).crop(box).resize((size, size), Image.LANCZOS)
    tiles = [("as made", crop(before["frames"][0], before["split"][0])),
             ("head matched", crop(after["frames"][0], after["split"][0]) if after and after.get("frames") else None),
             ("the picture", crop(before["frames"][1], before["split"][1]))]
    W = Image.new("RGB", (size * 3, size + 44), (24, 24, 30))
    d = ImageDraw.Draw(W)
    for i, (name, im) in enumerate(tiles):
        if im is not None:
            W.paste(im, (i * size, 0))
        d.text((i * size + 6, size + 3), plain(name), fill=(220, 220, 220), font=font)
    d.text((6, size + 22), plain(f"face {before['face_ratio'] * 100:.0f}% -> "
                                 + (f"{after['face_ratio'] * 100:.0f}%" if after and after.get('face_ratio') is not None else "?")
                                 + " of the picture's"), fill=(255, 200, 150), font=font)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    W.save(out)
    return out


def tone_curves(model_px: np.ndarray, picture_px: np.ndarray, knots: int = 33, max_slope: float = 3.0) -> np.ndarray:
    """One monotonic curve per channel (a 256-entry table, uint8) taking the model's colours to the picture's: the two
    distributions matched quantile by quantile, smoothed, never decreasing. Not a fixed gamma."""
    q = np.linspace(0, 100, knots)
    lut = np.zeros((3, 256), np.float64)
    x = np.arange(256, dtype=np.float64)
    for c in range(3):
        src = np.percentile(model_px[:, c], q)
        dst = np.percentile(picture_px[:, c], q)
        src = np.maximum.accumulate(src + np.arange(knots) * 1e-3)      # strictly increasing
        dst = np.maximum.accumulate(dst)
        # beyond the model's own range the curve continues with its end slopes, gently
        y = np.interp(x, src, dst)
        lo_s = (dst[1] - dst[0]) / max(src[1] - src[0], 1e-3)
        hi_s = (dst[-1] - dst[-2]) / max(src[-1] - src[-2], 1e-3)
        y = np.where(x < src[0], dst[0] - (src[0] - x) * min(lo_s, 3.0), y)
        y = np.where(x > src[-1], dst[-1] + (x - src[-1]) * min(hi_s, 3.0), y)
        k = np.ones(9) / 9
        y = np.convolve(np.pad(y, 4, mode="edge"), k, mode="valid")
        # no range steeper than max_slope (a narrow band of dark texels stretched five times over shows its noise):
        # integrate the clipped slope, then put the model's median back where the picture's median is
        dy = np.clip(np.diff(y), 0, max_slope)
        y2 = np.r_[0.0, np.cumsum(dy)]
        med = int(np.clip(round(float(np.median(model_px[:, c]))), 0, 255))
        y2 += y[med] - y2[med]
        lut[c] = np.maximum.accumulate(np.clip(y2, 0, 255))
    return np.round(lut).astype(np.uint8)


def _sat(px: np.ndarray) -> np.ndarray:
    mx, mn = px.max(-1), px.min(-1)
    return (mx - mn) / np.maximum(mx, 1.0)


def neutral_drift(before_px: np.ndarray, after_px: np.ndarray) -> float:
    """How far a match turned the model's near-neutral pixels (whites, greys: saturation under 0.12, not black) toward a
    colour: the mean rise in saturation over them, 0 when there are fewer than 50."""
    b, a = np.asarray(before_px, dtype=np.float64), np.asarray(after_px, dtype=np.float64)
    n = min(len(b), len(a))
    b, a = b[:n], a[:n]
    keep = (_sat(b) < 0.12) & (_luma(b) > 60)
    if keep.sum() < 50:
        return 0.0
    rise = _sat(a[keep]) - _sat(b[keep])
    # two ways to turn whites into a colour: all of them a little (a white coat gone mint: the mean), or some of them a lot
    # (white shoes gone pink: the share that rose more than 0.12). Both are scaled so that 1.0 is the limit.
    return float(max(rise.mean() / 0.06, (rise > 0.12).mean() / 0.15)) * 0.06


def luma_curve(model_px: np.ndarray, picture_px: np.ndarray, max_slope: float = 3.0) -> np.ndarray:
    """One brightness curve (256 entries) taking the model's brightness to the picture's — the same quantile match as
    tone_curves, on brightness alone, so it changes no colour's hue."""
    ym = _luma(np.asarray(model_px, dtype=np.float64))
    yp = _luma(np.asarray(picture_px, dtype=np.float64))
    return tone_curves(np.c_[ym, ym, ym], np.c_[yp, yp, yp], max_slope=max_slope)[0]


def apply_gain(a: np.ndarray, lut_y: np.ndarray) -> np.ndarray:
    """Every pixel's brightness through the curve, its colour's proportions kept: rgb * new/old (capped), added near black.
    Keeps hue exactly, but inflates a dark saturated colour (a navy jacket went royal blue) — tried third."""
    rgb = a[..., :3].astype(np.float64)
    y = _luma(rgb)
    yn = np.asarray(lut_y, dtype=np.float64)[np.clip(np.round(y), 0, 255).astype(np.int64)]
    gain = np.clip(yn / np.maximum(y, 1.0), 0.0, 4.0)
    out = np.where((y < 6)[..., None], rgb + (yn - y)[..., None], rgb * gain[..., None])
    return np.clip(np.round(out), 0, 255)


def apply_luma(a: np.ndarray, lut_y: np.ndarray) -> np.ndarray:
    """The one curve (fitted on brightness) through each of the three channels alike. The bake's fault (no colour-space
    step, BUILD 40) is one curve on all three channels, so this undoes it without turning any colour toward another: the
    channels keep their order, a grey stays grey. (A gain on brightness — rgb * new/old — was tried first and turned a navy
    jacket royal blue; one curve a colour turned white shoes pink and dark hair green.)"""
    lut = np.asarray(lut_y, dtype=np.float64)
    rgb = np.clip(np.round(a[..., :3].astype(np.float64)), 0, 255).astype(np.int64)
    return lut[rgb]


def fix_colour(src: Path, dst: Path, picture, cfg: dict | None = None, kind: str = "prop", mode: str = "auto") -> dict:
    """Match a model's colour texture to its picture: fit the curves on the front view, apply them to every colour texture,
    write `dst` (the model as made is left as it is). Returns {"ok", "before", "after" (the check on dst), "lut", "mode",
    "drift"}. `mode`: "rgb" (BUILD 40: one curve a colour), "luma" (BUILD 73: one brightness curve, every hue kept), or
    "auto" — rgb first, and luma when rgb turns the model's whites and greys into a colour (`neutral_drift_max`). A match
    that still drifts is not ok, whatever its numbers."""
    s = settings(cfg)
    dst = Path(dst)
    if kind in BODY_KINDS:
        # BUILD 84: a body is never put through a curve — not one a colour, not one on brightness through the channels, not
        # one shaped like a gain. One gain for the whole colour picture, or nothing (a black suit went navy under the curve).
        return fix_colour_body(src, dst, picture, cfg, kind)
    if mode == "auto":
        # BUILD 73: three ways in turn — one shared curve (the bake's own fault undone), one curve a colour, a brightness
        # gain — and the first whose numbers pass, whose whites stay white and whose skin stays the picture's colour is
        # kept. None: the first is offered, for a person to judge.
        tried = []
        for md in ("luma", "rgb", "gain"):
            tmp = dst if md == "luma" else dst.with_name(dst.stem + f"__{md}.glb")
            r = fix_colour(src, tmp, picture, cfg, kind, md)
            tried.append((md, tmp, r))
            if r.get("after") is None:
                return r
            if r.get("ok"):
                if tmp != dst:
                    import shutil
                    shutil.move(str(tmp), str(dst))
                r["tried"] = [t[0] for t in tried]
                return r
        first = tried[0][2]
        first["tried"] = [t[0] for t in tried]
        first["why_not"] = {t[0]: t[2].get("refused") for t in tried}
        return first
    from PIL import Image
    g = Glb.load(src)
    m = g.mesh()
    before = check_colour(m, g, picture, s, kind)
    if before.get("skipped"):
        return {"ok": False, "before": before, "why": before["line"]}
    slope = float(s.get("colour_max_slope") or 3.0)
    if mode in ("luma", "gain"):
        ly = luma_curve(*before["pairs"], max_slope=slope)
        lut = np.stack([ly, ly, ly])
    else:
        lut = tone_curves(*before["pairs"], max_slope=slope)
    done = set()
    for ti, mat in _base_textures(g, m):
        if ti in done:
            continue
        img = g.texture_image(mat, "baseColorTexture")
        im_mode = img.mode
        a = np.asarray(img.convert("RGBA" if "A" in im_mode else "RGB")).copy()
        if mode == "luma":
            a[..., :3] = apply_luma(a, ly).astype(np.uint8)
        elif mode == "gain":
            a[..., :3] = apply_gain(a, ly).astype(np.uint8)
        else:
            for c in range(3):
                a[..., c] = lut[c][a[..., c]]
        g.replace_image(ti, Image.fromarray(a, "RGBA" if "A" in im_mode else "RGB"))
        done.add(ti)
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    g.save(dst)
    g2 = Glb.load(dst)
    after = check_colour(g2.mesh(), g2, picture, s, kind)
    drift = neutral_drift(before["pairs"][0], after["pairs"][0])
    skin = skin_shift(before, after)
    loud = loudness(after["pairs"][0]) / max(loudness(after["pairs"][1]), 1.0)
    refused = ("its numbers" if not after["ok"] else "its whites turned a colour" if drift > float(s["neutral_drift_max"])
               else "its skin moved away from the picture's colour" if skin > float(s["skin_shift_max"])
               else "its colours came out louder than the picture's" if loud > float(s["loudness_max"]) else None)
    return {"ok": refused is None, "before": before, "after": after, "lut": lut, "textures": len(done), "mode": mode,
            "drift": round(drift, 3), "skin_shift": round(skin, 4), "loudness": round(loud, 3), "refused": refused}


# ------------------------------------------------------------------------------------------------ BUILD 84: one gain for a body
def colour_arrays(g: Glb, m: dict) -> list[tuple[int, dict, np.ndarray, str]]:
    """Every colour texture of a model once: (texture index, material, its pixels as float (h, w, 3|4), its PIL mode)."""
    out, done = [], set()
    for ti, mat in _base_textures(g, m):
        if ti in done:
            continue
        img = g.texture_image(mat, "baseColorTexture")
        mode = img.mode
        out.append((ti, mat, np.asarray(img.convert("RGBA" if "A" in mode else "RGB")).astype(np.float64), mode))
        done.add(ti)
    return out


def texels_used(m: dict, mat_index: int | None, shape: tuple[int, int]) -> np.ndarray:
    """(h, w) bool: the texels the model's unwrap actually covers (for the faces of material `mat_index`, or all faces).
    A baked colour picture fills the rest with whatever it likes, which must not count."""
    th, tw = shape
    F = m["F"]
    if mat_index is not None and m.get("face_material") is not None and len(m["face_material"]) == len(F):
        F = F[m["face_material"] == mat_index]
    if not len(F) or m.get("UV") is None:
        return np.ones((th, tw), bool)
    size = max(tw, th)
    UV = m["UV"]
    scr = np.c_[UV[:, 0] * size, UV[:, 1] * size, np.zeros(len(UV))]
    _, _, _, face_at = raster.rasterize(scr, F, size)
    used = face_at >= 0
    if (tw, th) != (size, size):
        from PIL import Image
        used = np.asarray(Image.fromarray(used.astype(np.uint8) * 255).resize((tw, th), Image.NEAREST)) > 0
    return used


def clip_gain(arrays: list[np.ndarray], share: float, used: list[np.ndarray] | None = None) -> float:
    """The largest gain that pushes no more than `share` of the lit texels (brighter than 8 in some channel; only those the
    unwrap uses, when `used` is given) past white. On the first body it was tried on, the texels that would clip first were its skin
    (215, 171, 150): past this gain a face goes pale and yellow, not brighter."""
    parts = []
    for i, a in enumerate(arrays):
        mx = a[..., :3].max(-1)
        if used is not None and i < len(used) and used[i] is not None and used[i].shape == mx.shape:
            mx = mx[used[i]]
        parts.append(mx.reshape(-1))
    mx = np.concatenate(parts) if parts else np.zeros(1)
    lit = mx[mx > 8]
    if len(lit) < 100:
        return float("inf")
    top = float(np.percentile(lit, 100.0 * (1.0 - share)))
    return 255.0 / max(top, 1.0)


def one_gain(a: np.ndarray, gain: float) -> np.ndarray:
    """Every texel's three channels times one number (alpha kept). A hue cannot move under it, nor a colour's saturation;
    only a channel pushed past white is clipped."""
    out = a.copy()
    out[..., :3] = np.clip(np.round(a[..., :3] * float(gain)), 0, 255)
    return out


def _window(lo: float, hi: float, ratio: float | None) -> tuple[float, float] | None:
    """The gains that bring `ratio` inside [lo, hi] (ratio times gain), or None when it can't be read."""
    if ratio is None or ratio <= 1e-6:
        return None
    return (lo / ratio, hi / ratio)


def _meet(*ws):
    lo = max(w[0] for w in ws)
    hi = min(w[1] for w in ws)
    return (lo, hi) if lo <= hi else None


def _nearest(w: tuple[float, float], target) -> float:
    """The point of window `w` nearest to `target` (a number, or another window)."""
    if isinstance(target, tuple):
        if target[1] < w[0]:
            return w[0]
        if target[0] > w[1]:
            return w[1]
        return float(min(max(1.0, max(w[0], target[0])), min(w[1], target[1])))
    return float(min(max(target, w[0]), w[1]))


def choose_gain(before: dict, s: dict, top: float = float("inf")) -> dict:
    """The one gain for a body (BUILD 84), from the colour check on the body as made. Each measure the check holds a body by
    gives a window of gains that brings it inside its band (aimed `body_gain_margin` inside): the mean brightness, the face
    (when one was found) and the contrast; the gain is also kept under `top` (whites not pushed past white) and within
    `body_gain_max`. Where the windows meet, the gain nearest 1 is taken — the least change from the body as made, so a
    black stays as black as the check allows. Where they don't, the face comes before the mean and the mean before the
    contrast: skin is what a wrong match spoils first (the look review of 2026-11-18). Returns {"gain", "inside" (what the windows
    promise), "gave_way" (the measures it could not meet), "windows"}."""
    mg = float(s.get("body_gain_margin", DEFAULTS["body_gain_margin"]))
    gmax = float(s.get("body_gain_max", DEFAULTS["body_gain_max"]))
    lo, hi = s["colour_mean_band"] if before.get("body", True) else s["colour_prop_band"]     # an animal is checked as a thing
    hlo, hhi = s["colour_head_band"]
    hard = (1.0 / gmax, min(gmax, max(top, 1.0)))
    face = before.get("head_ratio") if not before.get("head_shadowed") else None      # the face, or the head band when no face was found
    wins = {"mean": _window(lo + mg, hi - mg, before.get("mean_ratio")),
            "face": _window(hlo + mg, hhi - mg, face),
            "contrast": (_window(float(s["colour_spread_min"]) + mg, float("inf"), before.get("spread_ratio"))
                         if before.get("body", True) else None)}
    order = [k for k in ("face", "mean", "contrast") if wins[k] is not None]
    gave = []
    cur = hard
    for k in order:                                    # each measure in turn, as long as it can still be met
        nxt = _meet(cur, wins[k])
        if nxt is None:
            gave.append(k)
        else:
            cur = nxt
    if gave:
        # what gave way is still come as near as the others allow: the mean first, then the contrast
        want = wins.get(gave[0])
        gain = _nearest(cur, want) if want else _nearest(cur, 1.0)
    else:
        gain = _nearest(cur, 1.0)
    stopped = None                                     # what held the gain where it is, when something gave way
    if gave:
        edges = [("whites", min(top, gmax) if top != float("inf") else None), ("limit", gmax), ("limit", 1.0 / gmax)]
        edges += [(k, wins[k][0]) for k in ("face", "contrast") if wins[k] is not None and k not in gave]
        edges += [(k, wins[k][1]) for k in ("face", "contrast") if wins[k] is not None and k not in gave]
        near = [(abs(gain - v), k) for k, v in edges if v is not None and v != float("inf")]
        stopped = min(near)[1] if near and min(near)[0] < 1e-6 else None
    return {"gain": round(float(gain), 4), "inside": not gave, "gave_way": gave, "stopped_by": stopped,
            "top": None if top == float("inf") else round(top, 3),
            "windows": {k: (None if w is None else [round(w[0], 3), round(min(w[1], 99.0), 3)]) for k, w in wins.items()}}


def _hue_deg(a: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Hue in degrees and chroma (max - min) of (n, 3) colours 0-255."""
    r, g, b = a[:, 0], a[:, 1], a[:, 2]
    mx, mn = a.max(1), a.min(1)
    c = mx - mn
    cs = np.where(c > 0, c, 1.0)
    h = np.where(mx == r, ((g - b) / cs) % 6, np.where(mx == g, (b - r) / cs + 2, (r - g) / cs + 4)) * 60.0
    return h, c


def hue_moved(before: list[np.ndarray], after: list[np.ndarray], s: dict | None = None, sample: int = 400_000) -> dict:
    """BUILD 84: how far a release turned the colours of a body, texel by texel against the body as made (the same unwrap):
    of the texels with a colour in both (max - min at least 20, and not near black), the share whose hue turned more than
    `hue_moved_deg`. One gain moves nothing (only a clipped highlight); a curve a colour moves a great deal. Returns
    {"ok", "share", "median_deg", "texels"}."""
    s = {**DEFAULTS, **(s or {})}
    hb, ha = [], []
    for a, b in zip(before, after):
        if a.shape[:2] != b.shape[:2]:
            return {"ok": False, "share": 1.0, "median_deg": None, "texels": 0, "why": "the colour pictures are not the same size"}
        hb.append(a[..., :3].reshape(-1, 3))
        ha.append(b[..., :3].reshape(-1, 3))
    if not hb:
        return {"ok": True, "share": 0.0, "median_deg": 0.0, "texels": 0}
    A, B = np.concatenate(hb).astype(np.float64), np.concatenate(ha).astype(np.float64)
    if len(A) > sample:
        idx = np.random.default_rng(84).choice(len(A), sample, replace=False)
        A, B = A[idx], B[idx]
    h1, c1 = _hue_deg(A)
    h2, c2 = _hue_deg(B)
    keep = (c1 >= 20) & (c2 >= 20) & (A.max(1) >= 30) & (B.max(1) >= 30)
    if keep.sum() < 50:
        return {"ok": True, "share": 0.0, "median_deg": 0.0, "texels": int(keep.sum())}
    d = np.abs(h1[keep] - h2[keep]) % 360
    d = np.minimum(d, 360 - d)
    share = float((d > float(s["hue_moved_deg"])).mean())
    return {"ok": share <= float(s["hue_moved_max"]), "share": round(share, 4), "median_deg": round(float(np.median(d)), 2),
            "texels": int(keep.sum())}


def fix_colour_body(src: Path, dst: Path, picture, cfg: dict | None = None, kind: str = "body") -> dict:
    """BUILD 84 part 1 — a body's colours by brightness only: the colour check on the body as made (`src`), one gain chosen
    for it (choose_gain), every colour texture times that one number, written to `dst`; the check again on `dst`, and the
    hue against the body as made. The body as made is left as it is. Returns the shape fix_colour returns —
    {"ok" (inside the check, hue unmoved), "before", "after", "lut" (the gain as three equal rows, so apply_lut puts the
    same on a moving copy), "mode": "one_gain", "gain", "inside", "gave_way", "hue", "refused", "said"}."""
    from PIL import Image
    s = settings(cfg)
    dst = Path(dst)
    g = Glb.load(src)
    m = g.mesh()
    before = check_colour(m, g, picture, s, kind)
    if before.get("skipped"):
        return {"ok": False, "before": before, "why": before["line"], "mode": "one_gain"}
    arrs = colour_arrays(g, m)
    if not arrs:
        return {"ok": False, "before": before, "why": "the body has no colour texture", "mode": "one_gain"}
    mats = m.get("materials") or []
    used = []
    for _, mat, a, _ in arrs:
        try:
            used.append(texels_used(m, next((i for i, x in enumerate(mats) if x is mat), None), a.shape[:2]))
        except Exception:  # noqa: BLE001 — without the unwrap's cover every lit texel counts (a little stricter)
            used.append(None)
    top = clip_gain([a for _, _, a, _ in arrs], float(s.get("body_gain_clip_share", DEFAULTS["body_gain_clip_share"])), used)
    pick = choose_gain(before, s, top)
    gain = pick["gain"]
    new = []
    for ti, mat, a, im_mode in arrs:
        b = one_gain(a, gain)
        new.append(b)
        g.replace_image(ti, Image.fromarray(b.astype(np.uint8), "RGBA" if "A" in im_mode else "RGB"))
    dst.parent.mkdir(parents=True, exist_ok=True)
    g.save(dst)
    g2 = Glb.load(dst)
    after = check_colour(g2.mesh(), g2, picture, s, kind)
    hue = hue_moved([a for _, _, a, _ in arrs], new, s)
    lut1 = np.clip(np.round(np.arange(256) * gain), 0, 255).astype(np.uint8)
    inside = bool(after.get("ok"))
    if not hue["ok"]:
        refused = f"its hue moved ({hue['share'] * 100:.1f}% of its coloured texels turned more than {s['hue_moved_deg']:.0f}°)"
    elif not inside:
        refused = "one gain cannot bring it inside the check"
    else:
        refused = None
    said = (f"one gain ×{gain:.2f} for the whole colour picture ({after.get('mean_ratio', 0) * 100:.0f}% of its picture's "
            f"brightness" + (f", the face {after['face_ratio'] * 100:.0f}%" if after.get("face_ratio") is not None else "") + ")")
    if not inside:
        stop = {"whites": f"past ×{gain:.2f} its brightest colours would be pushed past white (on a body that is the skin first: "
                          "it goes pale and yellow, not brighter)",
                "face": "past it the face would be brighter than its picture's allows",
                "contrast": "past it the contrast would fall out of its band",
                "limit": f"×{gain:.2f} is as far as one gain is allowed to go"}.get(pick.get("stopped_by") or "")
        said += " — not inside the check" + (f": {stop}" if stop else "") + ". Released at that gain, nothing else changed"
    return {"ok": refused is None, "before": before, "after": after, "lut": np.stack([lut1, lut1, lut1]), "mode": "one_gain",
            "gain": gain, "inside": inside, "gave_way": pick["gave_way"], "stopped_by": pick.get("stopped_by"),
            "windows": pick["windows"], "clip_top": pick["top"],
            "hue": hue, "hue_ok": bool(hue["ok"]), "refused": refused, "said": said, "textures": len(arrs),
            "drift": 0.0, "skin_shift": 0.0, "loudness": None}


def loudness(px: np.ndarray) -> float:
    """How loud the colours are: the mean of (max - min) over the pixels, in 0-255 — a navy jacket brightened by a gain
    turns royal blue and doubles this; a grey stays at 0."""
    a = np.asarray(px, dtype=np.float64)
    return float((a.max(-1) - a.min(-1)).mean()) if len(a) else 0.0


def skin_shift(before: dict, after: dict) -> float:
    """How much further the face's colour (chromaticity, not brightness) is from the picture's after a match than before
    it — 0 when it came nearer or there is no face. A match that turns dark skin red is refused by this."""
    try:
        (mb, pb), (ma, pa) = before.get("face_chroma"), after.get("face_chroma")
        if not (mb and pb and ma and pa):
            return 0.0
        return max(0.0, float(np.linalg.norm(np.subtract(ma, pa)) - np.linalg.norm(np.subtract(mb, pb))))
    except (TypeError, ValueError):
        return 0.0


def apply_lut(src: Path, dst: Path, lut, mode: str = "rgb") -> int:
    """The same tone curves on another file of the same body (its rigged, moving copy): every colour texture. Returns how
    many textures changed."""
    from PIL import Image
    lut = np.asarray(lut, dtype=np.uint8)
    g = Glb.load(src)
    m = g.mesh()
    done = set()
    for ti, mat in _base_textures(g, m):
        if ti in done:
            continue
        img = g.texture_image(mat, "baseColorTexture")
        a = np.asarray(img.convert("RGBA" if "A" in img.mode else "RGB")).copy()
        if mode == "luma":                       # BUILD 73: the brightness-only curve, every hue kept
            a[..., :3] = apply_luma(a, lut[0]).astype(np.uint8)
        else:
            for c in range(3):
                a[..., c] = lut[c][a[..., c]]
        g.replace_image(ti, Image.fromarray(a, "RGBA" if a.shape[2] == 4 else "RGB"))
        done.add(ti)
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    g.save(dst)
    return len(done)


def _grow_glass(m: dict, g: Glb, seed: np.ndarray, rings: int = 40) -> np.ndarray:
    """The glass check finds the flat faces of a pane; a highlight or an edge makes some faces of the same pane fail its
    tight test and stay white. Grow from the faces found into touching faces that are near-white and near-mirror."""
    P, F, UV = m["P"], m["F"], m["UV"]
    cand = np.zeros(len(F), bool)
    for mi, mat in enumerate(m["materials"] or []):
        sel = m["face_material"] == mi
        if not sel.any():
            continue
        pbr = mat.get("pbrMetallicRoughness") or {}
        base = g.texture_image(mat, "baseColorTexture")
        if base is None:
            continue
        C = _face_colours(F[sel], UV, base)
        bright = C.mean(1).min(1) > 175
        mr = g.texture_image(mat, "metallicRoughnessTexture")
        if mr is not None:
            M = _face_colours(F[sel], UV, mr).mean(1)
            mirrorish = (M[:, 2] / 255 * float(pbr.get("metallicFactor", 1.0)) > 0.6) & \
                        (M[:, 1] / 255 * float(pbr.get("roughnessFactor", 1.0)) < 0.3)
        else:
            mirrorish = np.ones(int(sel.sum()), bool)
        cand[np.nonzero(sel)[0]] = bright & mirrorish
    # touching = sharing a corner, by position (the mesh is split along its texture seams)
    _, vid = np.unique(np.round(P / max(float(np.ptp(P, axis=0).max()), 1e-9) * 1e5).astype(np.int64), axis=0, return_inverse=True)
    vid = vid.reshape(-1)
    FV = vid[F]
    cur = seed.copy()
    for _ in range(rings):
        on = np.zeros(int(vid.max()) + 1, bool)
        on[FV[cur].reshape(-1)] = True
        nxt = cur | (cand & on[FV].any(1))
        if (nxt == cur).all():
            break
        cur = nxt
    return cur


def fix_glass(src: Path, dst: Path, cfg: dict | None = None) -> dict:
    """Blank glass put right: the faces the glass check finds (a flat near-white perfect mirror) get a dark glass colour
    in the colour texture and their own roughness (metal 0) in the metal/roughness texture. Writes `dst`."""
    from PIL import Image
    s = settings(cfg)
    g = Glb.load(src)
    m = g.mesh()
    r = check_glass(m, g, s)
    faces = r.get("faces")
    if faces is None or not faces.any():
        return {"ok": True, "changed": False, "share": r["share"]}
    faces = _grow_glass(m, g, faces)
    painted = 0
    for mi, mat in enumerate(m["materials"] or []):
        sel = faces & (m["face_material"] == mi)
        if not sel.any():
            continue
        pbr = mat.get("pbrMetallicRoughness") or {}
        for slot, fill in (("baseColorTexture", None), ("metallicRoughnessTexture", None)):
            ref = pbr.get(slot)
            if not ref:
                continue
            img = g.texture_image(mat, slot)
            a = np.asarray(img.convert("RGBA" if "A" in img.mode else "RGB")).copy()
            th, tw = a.shape[:2]
            size = max(th, tw)
            uvpx = np.c_[m["UV"][:, 0] * tw, m["UV"][:, 1] * th, np.zeros(len(m["UV"]))]
            hit = raster.rasterize(uvpx, m["F"][sel], size)[0][:th, :tw]
            hit = raster.dilate(hit, 2)                 # the seams around a window too
            if slot == "baseColorTexture":
                a[hit, 0], a[hit, 1], a[hit, 2] = s["glass_colour"]
            else:                                       # glTF: G = roughness, B = metalness
                a[hit, 1] = int(round(float(s["glass_roughness"]) * 255))
                a[hit, 2] = 0
            g.replace_image(int(ref["index"]), Image.fromarray(a, "RGBA" if a.shape[2] == 4 else "RGB"))
            painted += int(hit.sum())
        if not pbr.get("metallicRoughnessTexture"):
            # no texture to carry it: the material as a whole is told it isn't a perfect mirror (metal 0)
            pbr["metallicFactor"] = 0.0
            pbr["roughnessFactor"] = max(float(pbr.get("roughnessFactor", 1.0)), float(s["glass_roughness"]))
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    g.save(dst)
    g2 = Glb.load(dst)
    after = check_glass(g2.mesh(), g2, s)
    return {"ok": after["ok"], "changed": True, "share": r["share"], "after_share": after["share"], "texels": painted}


def colour_picture(before: dict, after: dict | None, out: Path, size: int = 300, label: str | None = None) -> Path:
    """Before · after · the picture, side by side, with the numbers — so a person sees what the fix did. `before` is the
    model as first made (BUILD 84: every caller passes that, never an already-matched one); `label` names what the middle
    one is ("one gain ×1.14"; "matched" when not given)."""
    from PIL import Image, ImageDraw
    tiles = [(before["render"], f"as made: {before['mean_ratio'] * 100:.0f}% bright, {before['spread_ratio'] * 100:.0f}% contrast")]
    if after is not None and after.get("render") is not None:
        tiles.append((after["render"], f"{label or 'matched'}: {after['mean_ratio'] * 100:.0f}% bright, {after['spread_ratio'] * 100:.0f}% contrast"))
    tiles.append((before["picture_px"], "the picture"))
    font, plain = _font(13)
    W = Image.new("RGB", (size * len(tiles), size + 24), (24, 24, 30))
    d = ImageDraw.Draw(W)
    for i, (a, lab) in enumerate(tiles):
        W.paste(Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).resize((size, size)), (i * size, 0))
        d.text((i * size + 6, size + 4), plain(lab), fill=(210, 210, 210), font=font)
    out.parent.mkdir(parents=True, exist_ok=True)
    W.save(out, quality=88) if out.suffix.lower() in (".jpg", ".jpeg") else W.save(out)
    return out


# ------------------------------------------------------------------------------------------------ BUILD 84 part 6: proportions
SIZE_WORDS = {"height": "tall", "length": "long", "width": "wide", "depth": "deep"}


def size_check(lo, hi, asked: dict | None, s: dict) -> dict | None:
    """Do the made thing's proportions answer what was asked? `asked` is the entry's real size. With one measure there is
    nothing to compare (None: not checked, and nothing is said). With two or more, the thing is taken at the size its
    first measure gives it (height, then length, then a named side — `meshio.SIZE_ORDER`, the one it is really scaled by)
    and each other measure is compared with what the model then has: more than `size_max_off` (a third) away is held,
    with the numbers. "length" is the longer side on the ground. A named side ("width", "depth") is compared with
    whichever ground side is nearer to it — a model may come out turned a quarter, and that is not a fault — unless
    both are named: then the longer asked is compared with the longer made, the shorter with the shorter."""
    from .meshio import SIZE_ORDER
    if not s.get("size_check") or not asked:
        return None
    lo, hi = np.asarray(lo, dtype=np.float64), np.asarray(hi, dtype=np.float64)
    ext = {"width": float(hi[0] - lo[0]), "height": float(hi[1] - lo[1]), "depth": float(hi[2] - lo[2])}
    ext["length"] = max(ext["width"], ext["depth"])
    given = [(k, float(asked[k])) for k in SIZE_ORDER if asked.get(k) not in (None, "", 0)]
    if len(given) < 2 or ext[given[0][0]] <= 1e-9:
        return None
    k0, v0 = given[0]
    scale = v0 / ext[k0]
    ground = sorted((ext["width"] * scale, ext["depth"] * scale))            # the made thing's ground sides: short, long
    both = asked.get("width") not in (None, "", 0) and asked.get("depth") not in (None, "", 0)
    limit = float(s["size_max_off"])
    rows = []
    for k, v in given[1:]:
        if k == "length":
            got = ground[1]
        elif k == "height":
            got = ext["height"] * scale
        elif both:
            other = float(asked["depth" if k == "width" else "width"])
            got = ground[1] if v >= other else ground[0]
        else:
            got = min(ground, key=lambda x: abs(np.log(max(x, 1e-9) / v)))
        ratio = got / v
        rows.append({"measure": k, "asked_m": round(v, 3), "made_m": round(got, 3), "ratio": round(ratio, 3),
                     "ok": bool(max(ratio, 1.0 / max(ratio, 1e-9)) - 1.0 <= limit)})
    ok = all(r["ok"] for r in rows)
    said = "; ".join(f"asked {r['asked_m']:g} m {SIZE_WORDS[r['measure']]}, it is {r['made_m']:.1f} m ({r['ratio'] * 100:.0f}%)"
                     for r in rows)
    line = (f"{NAMES['size']}: at {v0:g} m {SIZE_WORDS[k0]} — {said} — "
            + ("passes (within a third)." if ok else
               "more than a third from what was asked — held back. Its picture and its size disagree: change the words "
               "or the size, or let it through."))
    return {"check": "size", "ok": ok, "by": k0, "scale": round(scale, 6), "measures": rows, "line": line}


# ------------------------------------------------------------------------------------------------ all of them
def run(model: Path, picture: Path | None = None, kind: str = "prop", tier: str | None = None, cfg: dict | None = None,
        out_picture: Path | None = None, only: tuple | None = None, hangs: bool = False) -> dict:
    """Every check that applies to this kind of thing. Returns {"ok", "lines", "results", "picture"} and, when
    `out_picture` is given, draws what each check saw there (a person looks at it before deciding). `hangs`: the thing
    hangs from above (BUILD 84, 2f) — its loose pieces are judged by how near they hang, not against a floor."""
    s = settings(cfg)
    g = Glb.load(model)
    m = g.mesh()
    pic = None
    if picture and Path(picture).exists():
        from PIL import Image
        pic = Image.open(picture)
        pic.load()
    todo = only or which(kind, tier)
    results = []
    if not len(m["F"]):
        results.append({"check": "surface", "ok": False, "line": "The model has no triangles — held back."})
    else:
        for c in todo:
            try:
                if c == "level":
                    results.append(check_level(m, s))
                elif c == "loose":
                    results.append(check_loose(m, s, hangs))
                elif c == "glass":
                    results.append(check_glass(m, g, s))
                elif c == "thin":
                    results.append(check_thin(m, pic, s))
                elif c == "colour":
                    results.append(check_colour(m, g, pic, s, tier if tier in BODY_KINDS else kind))
            except Exception as e:  # noqa: BLE001 — a check that breaks says so; it never stops the queue
                results.append({"check": c, "ok": True, "error": str(e),
                                "line": f"{NAMES.get(c, c)}: the check itself failed ({type(e).__name__}: {e}) — not checked."})
    ok = all(r["ok"] for r in results)
    drawn = None
    if out_picture is not None and len(m["F"]):
        try:
            drawn = str(draw(m, g, results, pic, Path(out_picture)))
        except Exception as e:  # noqa: BLE001
            drawn = None
            results.append({"check": "picture", "ok": True, "line": f"(the check picture could not be drawn: {e})"})
    lines = [r["line"] for r in results]
    # what a check measured with (pixels, faces, pictures) stays here; only its numbers and words go on to be written down
    plain = [{k: v for k, v in r.items() if k not in ("faces", "outline", "pairs", "head_pairs", "render", "picture_px")}
             for r in results]
    for r in plain:
        if "straighten" in r:
            r["straighten"] = [round(float(x), 6) for x in r["straighten"]]
    return {"ok": ok, "lines": lines, "results": [jsonable(r) for r in plain], "picture": drawn, "checked": list(todo)}


def jsonable(v, _depth: int = 0):
    """BUILD 78 (after the queue failed every released body, 2026-11-18 00:24: "Object of type ndarray is not JSON
    serializable" — BUILD 73's head_pairs had been left in the colour check's result): a check's result made safe to write.
    numpy numbers become plain numbers; a small array becomes a list; an array of more than 64 values (pixels) is left
    out — it was never meant to be written. Tuples become lists."""
    if _depth > 12:
        return None
    if isinstance(v, dict):
        out = {}
        for k, x in v.items():
            if isinstance(x, np.ndarray) and x.size > 64:
                continue
            out[str(k)] = jsonable(x, _depth + 1)
        return out
    if isinstance(v, (list, tuple)):
        return [jsonable(x, _depth + 1) for x in v if not (isinstance(x, np.ndarray) and x.size > 64)]
    if isinstance(v, np.ndarray):
        return jsonable(v.tolist(), _depth + 1)
    if isinstance(v, np.bool_):
        return bool(v)
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating):
        return float(v)
    return v


def draw(m: dict, g: Glb, results: list[dict], pic, out: Path, size: int = 300) -> Path:
    """One picture of what the checks saw: the model from the front and the side with the floor line in red, the
    picture's outline against the model's (magenta = in the picture, missing from the model), white mirrors in cyan."""
    from PIL import Image, ImageDraw
    mat0 = (m["materials"] or [None])[0]
    tex = g.texture_image(mat0, "baseColorTexture") if mat0 else None
    by = {r["check"]: r for r in results}
    tiles, labels = [], []
    lo = m["P"].min(0)
    for az, el, label in ((0, 0, "front"), (90, 0, "side"), (35, 25, "three-quarter")):
        img = raster.render(m["P"], m["F"], az, el, size, m["UV"], tex)
        if "glass" in by and not by["glass"]["ok"] and by["glass"].get("faces") is not None:
            R = raster.view_matrix(az, el)
            scr, _ = raster.project(m["P"], R, size)
            fa = raster.rasterize(scr, m["F"], size)[3]
            hit = (fa >= 0) & by["glass"]["faces"][np.clip(fa, 0, None)]
            img[hit] = [0, 230, 255]
        if "loose" in by and not by["loose"]["ok"] and isinstance(by["loose"].get("faces"), np.ndarray) and by["loose"]["faces"].any():
            # BUILD 84 (2f): the loose piece itself, in orange. "1 piece below the floor" was a slab, a chair and a crystal
            # on three models: whoever decides should see which it is
            R = raster.view_matrix(az, el)
            scr, _ = raster.project(m["P"], R, size)
            fa = raster.rasterize(scr, m["F"], size)[3]
            hit = (fa >= 0) & by["loose"]["faces"][np.clip(fa, 0, None)]
            img[hit] = [255, 120, 0]
        if el == 0:
            rows = np.nonzero((img != 232).any(2).any(1))[0]
            if len(rows):
                img[min(size - 1, int(rows.max())), :, :] = [235, 40, 40]
        tiles.append(Image.fromarray(img))
        labels.append(label)
    if "thin" in by and by["thin"].get("outline") is not None:
        solid, holes = by["thin"]["outline"]
        vis = np.full(solid.shape + (3,), 238, np.uint8)
        vis[solid] = [125, 125, 125]
        vis[holes] = [255, 0, 220]
        tiles.append(Image.fromarray(vis).resize((size, size)))
        labels.append("outline: magenta = open")
    if pic is not None:
        tiles.append(pic.convert("RGB").resize((size, size)))
        labels.append("the picture")
    font, plain = _font(13)
    W = Image.new("RGB", (size * len(tiles), size + 26 + 17 * len(results) + 8), (24, 24, 30))
    d = ImageDraw.Draw(W)
    for i, (t, lab) in enumerate(zip(tiles, labels)):
        W.paste(t, (i * size, 0))
        d.text((i * size + 6, size + 5), plain(lab), fill=(200, 200, 200), font=font)
    y = size + 26
    for r in results:
        col = (130, 220, 150) if r["ok"] else (255, 120, 110)
        d.text((6, y), plain(("PASS   " if r["ok"] else "HELD   ") + r["line"][:240]), fill=col, font=font)
        y += 17
    out.parent.mkdir(parents=True, exist_ok=True)
    W.save(out, quality=88) if out.suffix.lower() in (".jpg", ".jpeg") else W.save(out)
    return out


def _font(px: int):
    """A real font where the computer has one (dashes and degree signs then draw properly), else Pillow's own with the
    text kept to plain characters."""
    from PIL import ImageFont
    for name in ("DejaVuSans.ttf", "segoeui.ttf", "arial.ttf", "Arial.ttf", "Helvetica.ttc", "/System/Library/Fonts/Helvetica.ttc",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, px), (lambda t: t)
        except OSError:
            continue
    table = str.maketrans({"\u2014": "-", "\u2013": "-", "\u00b0": " deg", "\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"'})
    return ImageFont.load_default(), (lambda t: t.translate(table).encode("ascii", "replace").decode("ascii"))


def main(args: list[str]) -> int:
    """python -m forge 3d checks <model.glb> [--picture p.png] [--kind prop|building|body] [--tier ...] [--draw out.png]"""
    if not args:
        print(main.__doc__)
        return 2

    def opt(flag, d=None):
        return args[args.index(flag) + 1] if flag in args and args.index(flag) + 1 < len(args) else d
    r = run(Path(args[0]), Path(opt("--picture")) if opt("--picture") else None, opt("--kind", "prop"), opt("--tier"),
            out_picture=Path(opt("--draw")) if opt("--draw") else None)
    for ln in r["lines"]:
        print(ln)
    if "--json" in args:
        print(json.dumps(r["results"], indent=1))
    return 0 if r["ok"] else 1
