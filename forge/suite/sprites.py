"""Sprite intake in the suite (BUILD 04 — spec §6 screen 5): drop a sheet → the numbered figures on the sheet itself →
click a figure, pick its facing → save → the game sheet, its preview GIFs and its edge report.

This is where a sheet's mapping file (`games/<game>/intake/<character>[__<variant>]/<sheet>.intake.json`) gets edited;
nobody should have to open it by hand. The work itself is the forge's own: `night4/intake.py` finds and cuts the
figures, and the `sprite_intake` job (run in this process by `night4/inline.run_now`, exactly as sprite_intake.bat
does) packs the sheet. Nothing here is a second implementation of either.

    candidates(cfg, game)                      pictures that could be sheets: the game folder's top level + uploads
    save_upload(cfg, game, ch, var, name, b)   a dropped picture, kept under the intake folder (never overwritten)
    open_sheet(cfg, game, ch, var, sheet)      detect the figures; the mapping as it stands (the forge's first guess
                                               is written the first time, unchecked)
    save_mapping(cfg, game, mapping, …, who)   facings from clicks → the mapping file (old version kept, journalled)
    make_sheet(cfg, game, mapping, who)        the sprite_intake job, now → sheet.png, GIFs, edges, warnings
    pockets(img, backdrop)                     backdrop showing through between an arm and the body (see below)

**See-through gaps.** On a JPEG sheet the white between an arm and the body is not perfectly flat. Since wiring day
(W10) intake.py knows it: its foreground clears such a gap by the proven rule when no person has decided, and exactly
the person's `holes` when they have. The screen still finds the gaps (detection keeps them), marks them, and lets the
person keep or clear each one; the mapping records the ones to clear as `holes` (one point inside each), and the
original sheet goes to the job as it is — never changed, no cut-out copy.
    tools(cfg, game) / add_tool(…)             the outside-tool register (G13): which program made the sheet

Writes only: its own intake folder, the tool register (models/licences.json, through handoff.add_tool), jobs/running →
jobs/done and out/<id>/ (through run_now), the game's journal. Safe beside a running worker.
"""
from __future__ import annotations
import hashlib, io, json, os, re
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image

from .. import config as cfgmod
from ..log import get
from . import journal, settings

log = get("suite")
IMG_EXTS = (".png", ".jpg", ".jpeg", ".webp")
MAX_UPLOAD = 80 * 1024 * 1024
WORDS = {"S": "faces you", "SW": "three-quarter front, turned to the left", "W": "faces left",
         "NW": "three-quarter back, turned to the left", "N": "back to you",
         "NE": "three-quarter back, turned to the right", "E": "faces right",
         "SE": "three-quarter front, turned to the right"}
REGISTER_ROOT: Path | None = None      # the tool register's root (None = the forge); tests point it elsewhere


class IntakeRefused(ValueError):
    pass


# ------------------------------------------------------------------ places
def intake_dir(cfg: dict, game: str) -> Path:
    return cfgmod.path_of(cfg, "games") / game / "intake"


def who_dir(character: str, variant: str | None) -> str:
    return str(character) + (f"__{variant}" if variant else "")


def mapping_path(cfg: dict, game: str, character: str, variant: str | None, sheet: Path) -> Path:
    """The same place night4/intake_job.mapping_path names (games/<game>/intake/<who>/<sheet>.intake.json)."""
    return intake_dir(cfg, game) / who_dir(character, variant) / f"{Path(sheet).stem}.intake.json"


def _game_root(cfg: dict, game: str) -> Path | None:
    from . import games
    try:
        r = games.game_root(cfg, game)
        return r if r and r.is_dir() else None
    except Exception:  # noqa: BLE001
        return None


def _inside(p: Path, root: Path | None) -> bool:
    if root is None:
        return False
    try:
        p.resolve().relative_to(Path(root).resolve())
        return True
    except (ValueError, OSError):
        return False


def allowed_picture(cfg: dict, game: str, p) -> Path:
    """A sheet the suite may read: inside the game's folder, its intake folder, or out/ — and a picture."""
    src = Path(str(p)).resolve()
    if src.suffix.lower() not in IMG_EXTS:
        raise IntakeRefused(f"{src.name} is not a picture the intake reads (png, jpg, webp)")
    if not (_inside(src, _game_root(cfg, game)) or _inside(src, intake_dir(cfg, game)) or
            _inside(src, cfgmod.path_of(cfg, "out"))):
        raise IntakeRefused(f"{src} is outside the game's folder, its intake folder and out/ — drop it here instead")
    if not src.is_file():
        raise IntakeRefused(f"not found: {src}")
    return src


def _mapping_ok(cfg: dict, game: str, p) -> Path:
    mp = Path(str(p)).resolve()
    if not mp.name.endswith(".intake.json") or not _inside(mp, intake_dir(cfg, game)):
        raise IntakeRefused(f"{mp.name} is not a mapping file in games/{game}/intake/")
    if not mp.is_file():
        raise IntakeRefused(f"no mapping file at {mp} — open the sheet first")
    return mp


def _hash(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()[:16]


def _write_atomic(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, p)


def _keep_old(mp: Path) -> Path | None:
    """The mapping as it was, kept in _history/ beside it before it changes (nothing is ever deleted)."""
    if not mp.exists():
        return None
    h = mp.parent / "_history"
    h.mkdir(exist_ok=True)
    dest = h / f"{mp.name[:-len('.intake.json')]}.{datetime.now():%Y%m%d-%H%M%S}.intake.json"
    k = 2
    while dest.exists():
        dest = h / f"{mp.name[:-len('.intake.json')]}.{datetime.now():%Y%m%d-%H%M%S}_{k}.intake.json"
        k += 1
    dest.write_bytes(mp.read_bytes())
    return dest


def _sign(cfg: dict, game: str, who: str | None, kind: str, obj: str, **kw) -> None:
    root = _game_root(cfg, game)
    if not who or root is None:
        return
    try:
        journal.append(root, who, kind, obj, **kw)
    except Exception as e:  # noqa: BLE001 — the work is done; a journal line that failed is a warning
        log.warning("intake: journal line not written (%s)", e)


# ------------------------------------------------------------------ what can be taken in
def mappings(cfg: dict, game: str) -> list[dict]:
    """Every mapping file this game has, newest first."""
    out = []
    d = intake_dir(cfg, game)
    if not d.is_dir():
        return out
    for mp in d.glob("*/*.intake.json"):
        try:
            m = json.loads(mp.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out.append({"mapping": str(mp), "sheet": m.get("sheet"), "character": m.get("character"),
                    "variant": m.get("variant"), "checked": bool(m.get("checked_by_person")),
                    "checked_by": m.get("checked_by"), "when": m.get("checked_at") or m.get("made"),
                    "mtime": mp.stat().st_mtime})
    out.sort(key=lambda r: -r["mtime"])
    return out


def candidates(cfg: dict, game: str) -> list[dict]:
    """Pictures that could be sheets: the top level of the game's folder (and any `sheet_folders` its
    forge.game.json lists, relative to it) plus every picture dropped into the intake before. Newest first."""
    seen, out = set(), []
    known: dict[str, list[dict]] = {}
    for m in mappings(cfg, game):
        if m["sheet"]:
            known.setdefault(str(Path(m["sheet"]).resolve()).lower(), []).append(m)
    places: list[tuple[Path, str, bool]] = []
    root = _game_root(cfg, game)
    if root is not None:
        places.append((root, "game folder", False))
        try:
            gcfg = cfgmod.game_config(cfg, game)
        except Exception:  # noqa: BLE001
            gcfg = {}
        for rel in gcfg.get("sheet_folders") or []:
            places.append((root / rel, f"game folder · {rel}", False))
    places.append((intake_dir(cfg, game), "dropped here", True))
    for base, where, deep in places:
        if not base.is_dir():
            continue
        files = base.glob("*/*") if deep else base.iterdir()
        for p in files:
            if not p.is_file() or p.suffix.lower() not in IMG_EXTS or "_history" in p.parts:
                continue
            key = str(p.resolve()).lower()
            if key in seen:
                continue
            seen.add(key)
            st = p.stat()
            out.append({"path": str(p.resolve()), "name": p.name, "where": where, "bytes": st.st_size,
                        "mtime": st.st_mtime, "mapped": [{"character": m["character"], "variant": m["variant"],
                                                          "checked": m["checked"]} for m in known.get(key, [])]})
    out.sort(key=lambda r: -r["mtime"])
    return out


def _safe_stem(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(str(s)).stem).strip("._")
    return s[:80] or "sheet"


def save_upload(cfg: dict, game: str, character: str, variant: str | None, filename: str, data: bytes) -> Path:
    """A picture dropped on the page → games/<game>/intake/<who>/<name>.<ext>. The same bytes again reuse the file;
    a different picture with the same name gets _2, _3 … — nothing is overwritten."""
    if not character:
        raise IntakeRefused("choose whose sheet it is first")
    if not data:
        raise IntakeRefused("the dropped file was empty")
    if len(data) > MAX_UPLOAD:
        raise IntakeRefused(f"that picture is {len(data) / 1e6:.0f} MB — the intake takes up to {MAX_UPLOAD // 1_000_000} MB")
    try:
        with Image.open(io.BytesIO(data)) as im:
            fmt = (im.format or "").upper()
            im.verify()
    except Exception as e:  # noqa: BLE001
        raise IntakeRefused(f"{filename} is not a picture the forge can read ({e})")
    ext = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}.get(fmt)
    if not ext:
        raise IntakeRefused(f"{filename} is a {fmt or 'unknown'} picture — save it as PNG, JPG or WEBP")
    d = intake_dir(cfg, game) / who_dir(character, variant)
    d.mkdir(parents=True, exist_ok=True)
    stem = _safe_stem(filename)
    dest, k = d / f"{stem}{ext}", 2
    while dest.exists():
        if dest.read_bytes() == data:
            return dest
        dest = d / f"{stem}_{k}{ext}"
        k += 1
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, dest)
    log.info("intake: kept a dropped sheet as %s (%d bytes)", dest, len(data))
    return dest


# ------------------------------------------------------------------ the registry, for the screen
def character_info(cfg: dict, game: str, character: str, variant: str | None) -> dict:
    from ..night4 import characters as chm
    try:
        ch = chm.load(cfg, game, character)
    except Exception as e:  # noqa: BLE001 — a sheet can be cut before its character has a registry file
        return {"known": False, "asymmetric": None, "why": None, "note": str(e)}
    v = (ch.get("variants") or {}).get(variant or "") or {}
    return {"known": True, "name": ch.get("name") or character, "asymmetric": chm.is_asymmetric(ch, variant),
            "why": v.get("_asymmetric_why") or ch.get("_asymmetric_why"),
            "field_sheet": (v.get("wanted") or {}).get("field_sheet")}


# ------------------------------------------------------------------ see-through gaps (holes)
POCKET_MIN_AREA = 120          # px; an eye white or a glint is smaller, or not this close to the backdrop colour
POCKET_MEDIAN = 8              # median distance to the backdrop colour (sum over r, g, b)
POCKET_SHARE = 0.75            # share of its pixels within 15 of the backdrop colour
POCKET_TALL = 0.08             # at least this share of a figure's height: an arm's gap is long, an eye is not


def pockets(img: Image.Image, bd: dict, fg: np.ndarray | None = None, h_ref: int | None = None) -> list[dict]:
    """Enclosed patches of (nearly) the backdrop colour that the intake would keep as figure: [{pt, bbox, area}].
    Flat backdrops only (a painted checkerboard's pockets the intake already recognises; alpha has none)."""
    from ..night4 import cc, intake as it
    if bd.get("kind") != "flat" or not bd.get("keys"):
        return []
    rgb = np.asarray(img.convert("RGB"))
    near = it._near(rgb, bd["keys"], int(bd.get("tolerance") or 30))
    lab, n = cc.label(near, 4)
    edge = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]])).tolist())
    if fg is None:
        fg = it.foreground(img, bd)[0]
    key = np.asarray(bd["keys"][0], dtype=np.int32)
    out = []
    for bx in cc.boxes(lab, n):
        if bx["id"] in edge or bx["area"] < POCKET_MIN_AREA:
            continue
        x0, y0, x1, y1 = bx["bbox"]
        if h_ref and (y1 - y0) < POCKET_TALL * h_ref:
            continue
        sel = lab[y0:y1, x0:x1] == bx["id"]
        if not fg[y0:y1, x0:x1][sel].any():
            continue                                    # the intake clears this one itself
        d = np.abs(rgb[y0:y1, x0:x1][sel].astype(np.int32) - key).sum(axis=1)
        if float(np.median(d)) <= POCKET_MEDIAN and float((d <= 15).mean()) >= POCKET_SHARE:
            ys, xs = np.nonzero(sel)
            mid = len(ys) // 2
            out.append({"pt": [int(x0 + xs[mid]), int(y0 + ys[mid])], "bbox": [int(v) for v in bx["bbox"]],
                        "area": int(bx["area"])})
    return out


def precut(src: Path, m: dict) -> Image.Image:
    """The sheet cut out as the intake cuts it (a preview): intake.py's own foreground with the person's holes
    (wiring day W10 — the intake does this itself now), then decontaminate."""
    from ..night4 import intake as it
    with Image.open(src) as im:
        img = im.convert("RGBA")
    bd = m.get("backdrop") or it.backdrop(img)
    fg, _a = it.foreground(img, bd, holes=m.get("holes") if "holes" in m else None)
    return it.decontaminate(img, fg, bd)


# ------------------------------------------------------------------ open / save / make
def _figures_view(m: dict) -> list[dict]:
    out = []
    for e in m.get("figures") or []:
        out.append({"n": e.get("n"), "bbox": e.get("bbox"), "facing": e.get("facing") if not e.get("skip") else None,
                    "frame": int(e.get("frame") or 0), "skip": bool(e.get("skip")), "flip": bool(e.get("flip"))})
    return out


def summary_line(m: dict) -> str:
    parts = []
    for e in m.get("figures") or []:
        if e.get("skip"):
            parts.append(f"{e['n']} left out")
        elif e.get("facing"):
            parts.append(f"{e['n']} {e['facing']}" + (f"·{e['frame']}" if e.get("frame") else "") + (" flipped" if e.get("flip") else ""))
        else:
            parts.append(f"{e['n']} ?")
    if m.get("mirror"):
        parts.append("fill " + ", ".join(m["mirror"]) + " by flipping")
    if m.get("holes"):
        parts.append(f"{len(m['holes'])} see-through gap(s) cleared")
    return "; ".join(parts)


def open_sheet(cfg: dict, game: str, character: str, variant: str | None, sheet, tool: str | None = None,
               fresh: bool = False, who: str | None = None) -> dict:
    """Find the figures on the sheet and return the mapping as it stands. The first time, the forge's guess is written
    (unchecked) so the clicks have a file to land in. `fresh` replaces a mapping whose sheet has changed with a new
    guess (the old one is kept in _history/)."""
    from ..night4 import intake as it
    if not character:
        raise IntakeRefused("choose whose sheet it is first")
    src = allowed_picture(cfg, game, sheet)
    with Image.open(src) as im:
        im.load()
        img = im.copy()
    try:
        det = it.detect(img)
    except it.IntakeError as e:
        raise IntakeRefused(str(e))
    found = pockets(img, det["backdrop"], det["_fg"], det.get("h_ref"))
    mp = mapping_path(cfg, game, character, variant, src)
    first, changed = not mp.exists(), False
    if first or fresh:
        old = _keep_old(mp) if fresh else None
        m = it.new_mapping(src, det, character, variant)
        m["made_by"] = "the forge's first guess (suite)"
        m["holes"] = [p["pt"] for p in found]
        if tool:
            m["tool"] = tool
        elif fresh and old is not None:
            try:
                m["tool"] = json.loads(old.read_text(encoding="utf-8")).get("tool")
            except (OSError, ValueError):
                pass
        _write_atomic(mp, json.dumps(m, indent=1, ensure_ascii=False))
        log.info("intake: %s for %s — %s", "fresh guess" if fresh else "first guess", src.name, m["guess"])
        if fresh:
            _sign(cfg, game, who, "art", f"sprite intake · {who_dir(character, variant)} · {src.name}",
                  note="the sheet had changed — started again from a fresh guess (the old mapping is in _history/)")
    else:
        m = json.loads(mp.read_text(encoding="utf-8"))
        changed = bool(m.get("sheet_sha1")) and m["sheet_sha1"] != it.sha1(src)
        if tool and m.get("tool") != tool:
            m["tool"] = tool
            _write_atomic(mp, json.dumps(m, indent=1, ensure_ascii=False))
    raw = mp.read_bytes()
    info = character_info(cfg, game, character, variant)
    holes = [list(map(int, h)) for h in m.get("holes") or []]
    for h in holes:                                    # a hole the person marked that is not a suggestion
        if not any(p["bbox"][0] <= h[0] < p["bbox"][2] and p["bbox"][1] <= h[1] < p["bbox"][3] for p in found):
            found.append({"pt": h, "bbox": [h[0] - 6, h[1] - 6, h[0] + 6, h[1] + 6], "area": 0, "marked": True})
    for p in found:
        p["hole"] = any(p["bbox"][0] <= h[0] < p["bbox"][2] and p["bbox"][1] <= h[1] < p["bbox"][3] for h in holes)
    return {"ok": True, "sheet": str(src), "sheet_name": src.name, "size": det["size"],
            "backdrop": det["backdrop"]["kind"], "figures": _figures_view(m),
            "labels": [d["bbox"] for d in det["dropped"] if d["what"] == "label"],
            "strays": [d["bbox"] for d in det["dropped"] if d["what"] == "stray blob"],
            "pockets": found, "holes": holes,
            "found": len(det["figures"]), "guess": m.get("guess"), "confidence": m.get("confidence"),
            "checked": bool(m.get("checked_by_person")), "checked_by": m.get("checked_by"), "checked_at": m.get("checked_at"),
            "mirror": list(m.get("mirror") or []), "mapping": str(mp),
            "mapping_rel": str(mp.relative_to(cfgmod.path_of(cfg, "games"))).replace("\\", "/"), "rev": _hash(raw),
            "character": character, "variant": variant, "tool": m.get("tool"), "first": first, "sheet_changed": changed,
            "char": info, "words": WORDS, "facings": list(it.FACINGS), "results": results(cfg, mp)}


def _auto_frames(figs: list[dict]) -> None:
    """Frames in figure-number order within each facing (two figures facing N → N·0 and N·1)."""
    count: dict[str, int] = {}
    for e in sorted(figs, key=lambda e: int(e.get("n") or 0)):
        if e.get("skip") or not e.get("facing"):
            continue
        e["frame"] = count.get(e["facing"], 0)
        count[e["facing"]] = e["frame"] + 1


def save_mapping(cfg: dict, game: str, mapping, rev: str | None, figures: list[dict], mirror: list[str] | None,
                 who: str | None, mirror_anyway: bool = False, holes: list | None = None) -> dict:
    """The clicks → the mapping file: facing / left out / flipped per figure (frames numbered in figure order within
    a facing), an optional wider box, the mirror list. Marks it checked by a person, keeps the old version in
    _history/, journals before → after. A file changed since it was opened (`rev`) is refused, not overwritten."""
    from ..night4 import intake as it
    if not who:
        raise IntakeRefused("set who you are first (top right) — a checked mapping is signed")
    mp = _mapping_ok(cfg, game, mapping)
    raw = mp.read_bytes()
    if rev and _hash(raw) != rev:
        return {"ok": False, "conflict": True, "message": "this mapping changed since you opened it (another window or "
                "a session) — reopen the sheet to see it, then click again"}
    m = json.loads(raw)
    before = summary_line(m)
    by_n = {int(e["n"]): e for e in m.get("figures") or []}
    W, H = None, None
    for f in figures or []:
        n = int(f.get("n"))
        e = by_n.get(n)
        if e is None:
            raise IntakeRefused(f"there is no figure {n} on this sheet")
        skip = bool(f.get("skip"))
        fc = f.get("facing")
        fc = str(fc).upper() if fc else None
        if fc and fc not in it.FACINGS:
            raise IntakeRefused(f"figure {n}: '{fc}' is not a facing — use one of {' '.join(it.FACINGS)}")
        e["facing"] = None if skip else fc
        e["frame"] = 0
        for k, on in (("skip", skip), ("flip", bool(f.get("flip")) and not skip)):
            if on:
                e[k] = True
            else:
                e.pop(k, None)
        if f.get("bbox"):
            if W is None:
                with Image.open(m["sheet"]) as im:
                    W, H = im.size
            if not isinstance(f["bbox"], (list, tuple)) or len(f["bbox"]) != 4:
                raise IntakeRefused(f"figure {n}: a box is four numbers (left, top, right, bottom)")
            b = [int(round(float(v))) for v in f["bbox"]]
            b = [max(0, b[0]), max(0, b[1]), min(W, b[2]), min(H, b[3])]
            if b[2] - b[0] < 4 or b[3] - b[1] < 4:
                raise IntakeRefused(f"figure {n}: that box is empty")
            e["bbox"] = b
    _auto_frames(list(by_n.values()))
    have = {e["facing"] for e in by_n.values() if e.get("facing") and not e.get("skip")}
    if not have:
        raise IntakeRefused("no figure has a facing yet — click a figure, then the way it faces")
    mir = []
    for spec in mirror or []:
        parts = re.split(r"\s*(?:→|->|>)\s*", str(spec).upper())
        if len(parts) != 2 or parts[0] not in it.FACINGS or it.OPPOSITE.get(parts[0]) != parts[1]:
            raise IntakeRefused(f"'{spec}' — a mirror fills a facing from its opposite, like W→E")
        if parts[1] in have:
            continue                                   # it has its own figure now; nothing to fill
        if parts[0] not in have:
            raise IntakeRefused(f"{parts[1]} can't be filled from {parts[0]}: no figure faces {parts[0]}")
        mir.append(f"{parts[0]}→{parts[1]}")
    info = character_info(cfg, game, m.get("character") or "", m.get("variant"))
    if mir and info.get("asymmetric") and not mirror_anyway:
        return {"ok": False, "asymmetric": True,
                "message": f"{info.get('name') or m.get('character')} is marked asymmetric in the registry"
                           + (f" ({info['why']})" if info.get("why") else "") + f" — flipping {', '.join(mir)} puts it on "
                           "the wrong side. Confirm to flip anyway, or leave those facings empty."}
    m["mirror"] = mir
    if holes is not None:
        if W is None:
            with Image.open(m["sheet"]) as im:
                W, H = im.size
        hs = []
        for h in holes:
            if not isinstance(h, (list, tuple)) or len(h) != 2:
                raise IntakeRefused("a see-through gap is one point: [x, y]")
            x, y = int(round(float(h[0]))), int(round(float(h[1])))
            if not (0 <= x < W and 0 <= y < H):
                raise IntakeRefused(f"the point {x}, {y} is outside the sheet")
            hs.append([x, y])
        m["holes"] = hs
    m["checked_by_person"] = True
    m["checked_by"] = who
    m["checked_at"] = settings.now().isoformat(timespec="seconds")
    after = summary_line(m)
    kept = _keep_old(mp)
    _write_atomic(mp, json.dumps(m, indent=1, ensure_ascii=False))
    log.info("intake: %s saved the facings of %s (%s)", who, mp.name, after)
    rel = str(mp.relative_to(cfgmod.path_of(cfg, "games"))).replace("\\", "/")
    _sign(cfg, game, who, "art", f"sprite intake · {who_dir(m.get('character'), m.get('variant'))} · {Path(m['sheet']).name}",
          before=before if before != after else None, after=after, link=f"games/{rel}",
          note="facings checked by hand" + (f" (the old mapping is in _history/{kept.name})" if kept else ""))
    return {"ok": True, "message": "Saved — the mapping is checked by you.", "rev": _hash(mp.read_bytes()),
            "summary": after, "mirror": mir}


def results(cfg: dict, mp: Path, limit: int = 6) -> list[dict]:
    """The intake jobs that used this mapping, newest first (jobs/done, names written by the intake)."""
    out = []
    d = cfgmod.path_of(cfg, "jobs") / "done"
    key = str(Path(mp).resolve()).lower()
    def newest(p: Path):
        try:
            return p.stat().st_mtime_ns
        except OSError:
            return 0
    for p in sorted(d.glob("*-intake_*.json"), key=lambda p: (newest(p), p.name), reverse=True):
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if j.get("type") != "sprite_intake" or key not in {str(Path(str(j.get(k) or "")).resolve()).lower()
                                                         for k in ("mapping", "intake_mapping")}:
            continue
        out.append(_result_view(cfg, j))
        if len(out) >= limit:
            break
    return out


def _result_view(cfg: dict, j: dict) -> dict:
    jid = j["id"]
    o = cfgmod.path_of(cfg, "out") / jid
    rep = {}
    try:
        rep = json.loads((o / "report.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    res = j.get("result") or {}
    url = lambda f: f"/out/{jid}/{f}"
    anims = {p.stem[len("anim_"):]: url(p.name) for p in sorted(o.glob("anim_*.gif"))}
    # where a figure's box meets the sheet's own edge — a limb really cut off. (Since wiring day W10, edges.md's
    # "cut off" column says the same: a sheet edge, or a box a person narrowed.)
    edges: dict[int, list[str]] = {}
    try:
        mm = json.loads(Path(str(j.get("intake_mapping") or j.get("mapping"))).read_text(encoding="utf-8"))
        with Image.open(str(j.get("cut_from") or j.get("input"))) as im:
            W, H = im.size
        for e in mm.get("figures") or []:
            x0, y0, x1, y1 = e["bbox"]
            edges[int(e["n"])] = [s for s, hit in (("left", x0 <= 0), ("top", y0 <= 0), ("right", x1 >= W), ("bottom", y1 >= H)) if hit]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    figs = []
    for f in rep.get("figures") or []:
        f = dict(f)
        f["sheet_edge"] = edges.get(int(f.get("n") or 0), [])
        figs.append(f)
    return {"job": jid, "when": j.get("finished_at") or j.get("started_at"), "sheet": url("sheet.png"),
            "anim": url("anim.png") if (o / "anim.png").exists() else None, "turntable": url("turntable.gif"),
            "numbers": url("numbers.png"), "edges": url("edges.md"), "anims": anims,
            "found": res.get("found", rep.get("found")), "missing": res.get("missing", rep.get("missing") or []),
            "warnings": res.get("warnings", rep.get("warnings") or []), "commercial_ok": res.get("commercial_ok"),
            "figures": figs, "scale": rep.get("scale"), "cell": rep.get("cell"), "holes": j.get("holes") or 0,
            "mirrored": rep.get("mirrored") or [], "out": str(o)}


def make_sheet(cfg: dict, game: str, mapping, who: str | None) -> dict:
    """The sprite_intake job with this mapping, run now in this process (run_now — the same handler the worker uses,
    the same as sprite_intake.bat). Refuses a mapping no person has checked."""
    from ..cli_night4 import _safe
    from ..night4.inline import run_now
    if not who:
        raise IntakeRefused("set who you are first (top right) — the sheet is signed")
    mp = _mapping_ok(cfg, game, mapping)
    m = json.loads(mp.read_text(encoding="utf-8"))
    if not m.get("checked_by_person"):
        raise IntakeRefused("the facings are still the forge's guess — click through the figures and save first")
    src = Path(str(m.get("sheet") or ""))
    if not src.is_file():
        raise IntakeRefused(f"the sheet is no longer at {src}")
    ch, var = str(m["character"]), m.get("variant")
    job = {"type": "sprite_intake", "input": str(src.resolve()), "character": ch, "game": game,
           "batch": f"intake/{who_dir(ch, var)}", "mapping": str(mp),
           "name": _safe(f"intake_{ch}_{var or ''}_{src.stem}".replace("__", "_"))}
    # Wiring day W10: the intake clears the person's see-through gaps itself (intake.foreground with the mapping's
    # `holes`), so the original sheet goes in as it is — no _cut/ copy any more.
    job["holes"] = len(m.get("holes") or [])
    if var:
        job["variant"] = var
    if m.get("tool"):
        job["tool"] = m["tool"]
    jid, res, err = run_now(cfg, job)
    obj = f"sprite intake · {who_dir(ch, var)} · {src.name}"
    if err:
        _sign(cfg, game, who, "art", obj, link=f"jobs/failed/{jid}.json", note=f"the game sheet failed: {err}")
        return {"ok": False, "job": jid, "message": f"The intake failed: {err} (jobs/failed/{jid}.json)"}
    done = cfgmod.path_of(cfg, "jobs") / "done" / f"{jid}.json"
    j = json.loads(done.read_text(encoding="utf-8")) if done.exists() else {**job, "id": jid, "result": res}
    view = _result_view(cfg, j)
    have = 8 - len(view["missing"])
    _sign(cfg, game, who, "art", obj, link=f"out/{jid}",
          note=f"made the game sheet — {have} of 8 facings" + (f", missing {', '.join(view['missing'])}" if view["missing"] else "")
               + (f"; {len(view['warnings'])} warning(s)" if view["warnings"] else ""))
    msg = f"The game sheet is made ({have} of 8 facings)." + (" Read the warnings below." if view["warnings"] else "")
    return {"ok": True, "message": msg, "result": view}


# ------------------------------------------------------------------ which program made the sheet (G13)
def _memo(cfg: dict, game: str) -> Path:
    return intake_dir(cfg, game) / "tool.json"


def tools(cfg: dict, game: str) -> dict:
    from .. import handoff as ho
    reg = ho.load_tools(REGISTER_ROOT)
    last = None
    try:
        last = json.loads(_memo(cfg, game).read_text(encoding="utf-8")).get("last")
    except (OSError, ValueError):
        pass
    return {"tools": [{"key": k, "commercial_ok": v.get("commercial_ok"), "license": v.get("license"),
                       "checked": v.get("checked")} for k, v in sorted(reg.items())], "last": last}


def remember_tool(cfg: dict, game: str, key: str | None) -> None:
    if key:
        _write_atomic(_memo(cfg, game), json.dumps({"last": key}, indent=1))


def add_tool(cfg: dict, game: str, name: str, version: str, commercial: str, condition: str, where: str,
             who: str | None) -> dict:
    """handoff.add_tool — the same register handoff_tool_add.bat writes. The licence answer is the person's; the
    forge never guesses one."""
    from .. import handoff as ho
    if not who:
        raise IntakeRefused("set who you are first (top right) — a licence line is signed")
    c = str(commercial or "").strip().lower()
    if c not in ("yes", "no"):
        raise IntakeRefused("answer yes or no: may its results be used commercially?")
    try:
        key = ho.add_tool(name, version, c == "yes", condition or "", where or "", root=REGISTER_ROOT)
    except ho.HandoffError as e:
        raise IntakeRefused(str(e))
    remember_tool(cfg, game, key)
    _sign(cfg, game, who, "setting", f"tool register · {key}",
          note=f"commercial use {'permitted' if c == 'yes' else 'NOT permitted'}" + (f" ({condition})" if condition else "")
               + (f" — checked at {where}" if where else ""))
    return {"ok": True, "message": f"Recorded {key} in the tool register.", "key": key}
