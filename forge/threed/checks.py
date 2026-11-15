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
NAMES = {"level": "Sits level", "loose": "Loose pieces", "glass": "Blank glass", "thin": "Thin parts", "colour": "Colours hold"}
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


def check_loose(m: dict, s: dict) -> dict:
    P, F = m["P"], m["F"]
    if not len(F):
        return {"check": "loose", "ok": True, "pieces": 0, "loose": [], "line": f"{NAMES['loose']}: no surface to check."}
    pt = _parts(m, s)
    lab, ids, carea, pieces, assembly, res = pt["lab"], pt["ids"], pt["carea"], pt["pieces"], pt["assembly"], pt["res"]
    tot = float(pt["area"].sum()) or 1.0
    h = max(float(np.ptp(P[:, 1])), 1e-9)
    # the floor is the floor of the main body and what is joined to it (a free-floating slab must not become the floor)
    g = ground_plane(assembly)
    tol = max(0.02 * h, res)
    loose = []
    for p in pieces:
        if p["joined"] or p["size"] < float(s["loose_min_size"]):
            continue
        low = p["pts"][np.argmin(p["pts"][:, 1])]
        dist = float(low[1] - (g["coef"][0] * low[0] + g["coef"][1] * low[2] + g["coef"][2]))
        if abs(dist) <= tol:
            continue                                       # it stands on the ground by itself (a post, a bollard)
        loose.append({"size": round(p["size"], 3), "surface": round(float(carea[p["n"]]) / tot, 4),
                      "faces": int((lab == p["label"]).sum()), "where": "below the floor" if dist < 0 else "in the air"})
    loose.sort(key=lambda r: -r["size"])
    ok = not loose
    if ok:
        line = f"{NAMES['loose']}: none — every part is joined to the rest or stands on the ground."
    else:
        big = loose[0]
        line = (f"{NAMES['loose']}: {len(loose)} piece{'s' if len(loose) > 1 else ''} not joined to the rest "
                f"(the largest, {big['where']}, is {big['size'] * 100:.0f}% of the model's size and {big['surface'] * 100:.1f}% "
                "of its surface) — held back.")
    return {"check": "loose", "ok": ok, "pieces": int(len(ids)), "loose": loose, "line": line}


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


def front_view(m: dict, g: Glb, picture, size: int = 384, body: bool = False):
    """The model's colours as stored (no light), seen from the view its picture was taken from, with the picture's figure
    at the same size. Returns (model pixels (n,3), picture pixels (k,3), model head pixels, picture head pixels, view,
    model render (size,size,3) on grey, picture (size,size,3))."""
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

    def head(msk):
        rows = np.nonzero(msk.any(1))[0]
        if not len(rows):
            return msk
        top, bot = int(rows.min()), int(rows.max())
        h = msk.copy()
        h[top + max(1, int((bot - top) / 7)):, :] = False
        return h
    render = np.where(mask[..., None], col, 232.0)
    return (col[mask], P[pm], col[head(mask)], P[head(pm)], (float(az), float(el), float(match)), render, P)


def _stats(px: np.ndarray) -> dict:
    y = _luma(px) if len(px) else np.zeros(1)
    p10, p50, p90 = np.percentile(y, [10, 50, 90])
    return {"p10": round(float(p10), 1), "p50": round(float(p50), 1), "p90": round(float(p90), 1), "mean": round(float(y.mean()), 1)}


def check_colour(m: dict, g: Glb, picture, s: dict, kind: str = "prop") -> dict:
    if picture is None:
        return {"check": "colour", "ok": True, "skipped": True, "line": f"{NAMES['colour']}: no picture to compare with — not checked."}
    mp, pp, mh, ph, view, render, P = front_view(m, g, picture, body=kind in BODY_KINDS)
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
    head_r = None
    if body and len(mh) > 50 and len(ph) > 50:
        head_r = _stats(mh)["mean"] / max(_stats(ph)["mean"], 1.0)
        hlo, hhi = s["colour_head_band"]
        if not hlo <= head_r <= hhi:
            probs.append(f"the head {head_r * 100:.0f}% as bright as the picture's")
    ok = not probs
    line = (f"{NAMES['colour']}: {mean_r * 100:.0f}% of its picture's brightness, {spread_r * 100:.0f}% of its contrast"
            + (f", the head {head_r * 100:.0f}%" if head_r is not None else "") + " — passes." if ok else
            f"{NAMES['colour']}: " + "; ".join(probs) + " (the colour texture as stored, against the picture it was made from) — "
            + ("held back. Put right by matching it to the picture; nothing is remade." if body else
               "held back. The matched colours are shown beside it: a person chooses them or lets it through (a prop's "
               "picture carries studio light the texture rightly doesn't, so the match isn't trusted blind)."))
    return {"check": "colour", "ok": ok, "body": body, "auto_fix": body, "mean_ratio": round(mean_r, 3), "spread_ratio": round(spread_r, 3),
            "head_ratio": None if head_r is None else round(head_r, 3), "model": sm, "picture": sp, "view": list(view[:2]),
            "pairs": (mp, pp), "render": render, "picture_px": P, "line": line}


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


def fix_colour(src: Path, dst: Path, picture, cfg: dict | None = None, kind: str = "prop") -> dict:
    """Match a model's colour texture to its picture: fit the curves on the front view, apply them to every colour texture,
    write `dst` (the model as made is left as it is). Returns {"ok", "before", "after" (the check on dst), "lut"}."""
    from PIL import Image
    s = settings(cfg)
    g = Glb.load(src)
    m = g.mesh()
    before = check_colour(m, g, picture, s, kind)
    if before.get("skipped"):
        return {"ok": False, "before": before, "why": before["line"]}
    lut = tone_curves(*before["pairs"], max_slope=float(s.get("colour_max_slope") or 3.0))
    done = set()
    for ti, mat in _base_textures(g, m):
        if ti in done:
            continue
        img = g.texture_image(mat, "baseColorTexture")
        mode = img.mode
        a = np.asarray(img.convert("RGBA" if "A" in mode else "RGB")).copy()
        for c in range(3):
            a[..., c] = lut[c][a[..., c]]
        g.replace_image(ti, Image.fromarray(a, "RGBA" if "A" in mode else "RGB"))
        done.add(ti)
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    g.save(dst)
    g2 = Glb.load(dst)
    after = check_colour(g2.mesh(), g2, picture, s, kind)
    return {"ok": after["ok"], "before": before, "after": after, "lut": lut, "textures": len(done)}


def apply_lut(src: Path, dst: Path, lut) -> int:
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


def colour_picture(before: dict, after: dict | None, out: Path, size: int = 300) -> Path:
    """Before · after · the picture, side by side, with the numbers — so a person sees what the fix did."""
    from PIL import Image, ImageDraw
    tiles = [(before["render"], f"as made: {before['mean_ratio'] * 100:.0f}% bright, {before['spread_ratio'] * 100:.0f}% contrast")]
    if after is not None and after.get("render") is not None:
        tiles.append((after["render"], f"matched: {after['mean_ratio'] * 100:.0f}% bright, {after['spread_ratio'] * 100:.0f}% contrast"))
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


# ------------------------------------------------------------------------------------------------ all of them
def run(model: Path, picture: Path | None = None, kind: str = "prop", tier: str | None = None, cfg: dict | None = None,
        out_picture: Path | None = None, only: tuple | None = None) -> dict:
    """Every check that applies to this kind of thing. Returns {"ok", "lines", "results", "picture"} and, when
    `out_picture` is given, draws what each check saw there (a person looks at it before deciding)."""
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
                    results.append(check_loose(m, s))
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
    plain = [{k: v for k, v in r.items() if k not in ("faces", "outline", "pairs", "render", "picture_px")} for r in results]
    for r in plain:
        if "straighten" in r:
            r["straighten"] = [round(float(x), 6) for x in r["straighten"]]
    return {"ok": ok, "lines": lines, "results": plain, "picture": drawn, "checked": list(todo)}


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
