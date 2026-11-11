"""The character registry as pages (BUILD 04 — spec §6 screen 6): variants, the locked seed, the look blocks, the
reference pictures, `asymmetric`, the wanted outputs; the face-consistency sheet; *make the set*.

Reads `games/<game>/characters/<id>.json` through night4/characters.py and the prompt library through prompts.py;
the face sheet is reviews.character_sheet (the same as `review --character`); the set is the same batch file
`characters.bat set` writes, submitted through the same submit shim `submit.bat` runs, its printout shown as is.

Edits from the page are few and plain — the locked seed, `asymmetric`, reference pictures — format-preserving
(jsondoc), the old file kept in characters/_history/, journalled. **Look blocks are not edited here**: their words
belong to whoever owns the art direction, and they live in the prompt library (the Prompt library screen, BUILD 14).
"""
from __future__ import annotations
import contextlib, io, json, os
from datetime import datetime
from pathlib import Path

from .. import config as cfgmod
from ..log import get
from . import journal, settings
from .jsondoc import JsonDoc

log = get("suite")
EDITABLE = ("seed", "asymmetric", "references")
_done_cache: dict[str, dict[str, dict | None]] = {}


class CastRefused(ValueError):
    pass


def _chm():
    from ..night4 import characters
    return characters


def _game_root(cfg: dict, game: str) -> Path | None:
    from . import games
    try:
        r = games.game_root(cfg, game)
        return r if r and r.is_dir() else None
    except Exception:  # noqa: BLE001
        return None


def _sign(cfg: dict, game: str, who: str | None, kind: str, obj: str, **kw) -> None:
    root = _game_root(cfg, game)
    if not who or root is None:
        return
    try:
        journal.append(root, who, kind, obj, **kw)
    except Exception as e:  # noqa: BLE001
        log.warning("characters: journal line not written (%s)", e)


def _library(cfg: dict, game: str) -> dict:
    from .. import prompts as pl
    try:
        return pl.load(cfg, game)
    except Exception as e:  # noqa: BLE001 — a broken library file is shown, not fatal
        return {"blocks": {}, "files": {}, "version": None, "error": str(e)}


def block_states(text, lib: dict) -> list[dict]:
    """Each {{block}} in a prompt: written (green), placeholder (red — not written yet) or missing (grey)."""
    from .. import prompts as pl
    out = []
    for ref in pl.refs(text):
        t = lib["blocks"].get(ref)
        if t is None:
            out.append({"ref": ref, "state": "missing", "text": None, "file": None})
        elif str(t).strip().upper().startswith("TODO"):
            out.append({"ref": ref, "state": "placeholder", "text": str(t), "file": lib["files"].get(ref)})
        else:
            out.append({"ref": ref, "state": "written", "text": str(t), "file": lib["files"].get(ref)})
    return out


def done_jobs(cfg: dict) -> list[dict]:
    """The finished jobs that name a character, newest first. jobs/done can hold thousands of bake-off jobs, so each
    file is read once and remembered by name (a done file is never rewritten in place)."""
    d = cfgmod.path_of(cfg, "jobs") / "done"
    seen = _done_cache.setdefault(str(d), {})
    try:
        names = [e.name for e in os.scandir(d) if e.name.endswith(".json")]
    except OSError:
        return []
    for name in names:
        if name in seen:
            continue
        try:
            j = json.loads((d / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue                                  # half-written: read again next time
        seen[name] = ({k: j.get(k) for k in ("id", "type", "character", "variant", "name", "finished_at", "input", "batch")}
                      if j.get("character") and not j.get("tombstone") else None)
    keep = set(names)
    out = [v for k, v in seen.items() if v and k in keep]
    out.sort(key=lambda j: str(j.get("finished_at") or ""), reverse=True)
    return out


def listing(cfg: dict, game: str) -> list[dict]:
    chm = _chm()
    lib = _library(cfg, game)
    rows = []
    for cid in chm.all_ids(cfg, game):
        try:
            ch = chm.load(cfg, game, cid)
        except chm.CharacterError as e:
            rows.append({"id": cid, "name": cid, "error": str(e)}); continue
        vs = ch.get("variants") or {}
        red = sum(1 for v in vs.values() for f in ("prompt", "negative") for b in block_states(v.get(f), lib)
                  if b["state"] != "written")
        rows.append({"id": cid, "name": ch.get("name") or cid, "stub": bool(ch.get("_stub")),
                     "asymmetric": ch.get("asymmetric"), "variants": list(vs), "placeholders": red,
                     "seeds": sorted({v.get("seed") for v in vs.values() if v.get("seed") not in (None, -1)})})
    rows.sort(key=lambda r: (r.get("stub", True), str(r.get("name")).lower()))
    return rows


def page(cfg: dict, game: str, cid: str) -> dict:
    chm = _chm()
    try:
        ch = chm.load(cfg, game, cid)
    except chm.CharacterError as e:
        raise CastRefused(str(e))
    lib = _library(cfg, game)
    raw = Path(ch["_file"]).read_bytes()
    variants = []
    for vn, v in (ch.get("variants") or {}).items():
        refs = []
        for i, r in enumerate(v.get("references") or []):
            refs.append({"i": i, "path": str(r), "exists": Path(str(r)).is_file(), "name": Path(str(r)).name})
        variants.append({
            "name": vn, "describe": v.get("describe"), "default": vn == (ch.get("default_variant") or next(iter(ch["variants"]))),
            "prompt": v.get("prompt"), "negative": v.get("negative"),
            "blocks": block_states(v.get("prompt"), lib), "neg_blocks": block_states(v.get("negative"), lib),
            "recipe": {k: v.get(k) for k in ("checkpoint", "sampler", "scheduler", "steps", "cfg", "size") if v.get(k) is not None},
            "seed": v.get("seed"), "asymmetric": chm.is_asymmetric(ch, vn), "asym_own": "asymmetric" in v,
            "why": v.get("_asymmetric_why") or ch.get("_asymmetric_why"), "references": refs,
            "wanted": {k: val for k, val in (v.get("wanted") or {}).items() if not k.startswith("_")},
            "wanted_notes": [val for k, val in (v.get("wanted") or {}).items() if k.startswith("_")],
            "sheet_loras": v.get("sheet_loras") or [], "alternatives": v.get("alternatives") or {},
            "loras": v.get("loras") or []})
    try:
        problems = chm.check(cfg, game, cid)
    except Exception as e:  # noqa: BLE001
        problems = [f"the check itself failed: {e}"]
    pics = []
    for j in done_jobs(cfg):
        if j.get("character") != cid:
            continue
        o = cfgmod.path_of(cfg, "out") / str(j["id"])
        for f in ("sheet.png", "contact.png", "render.png"):
            if (o / f).exists():
                pics.append({"job": j["id"], "type": j.get("type"), "variant": j.get("variant"), "when": j.get("finished_at"),
                             "file": f, "url": f"/out/{j['id']}/{f}", "thumb": f"/thumb?p={j['id']}/{f}"})
                break
        if len(pics) >= 24:
            break
    return {"id": cid, "name": ch.get("name") or cid, "stub": ch.get("_stub"), "comment": ch.get("_comment"),
            "facts": ch.get("facts"), "asymmetric": ch.get("asymmetric"), "why": ch.get("_asymmetric_why"),
            "default_variant": ch.get("default_variant"), "variants": variants, "problems": problems,
            "pictures": pics, "face_sheets": face_sheets(cfg, cid), "file": ch["_file"],
            "file_rel": f"games/{game}/characters/{cid}.json", "rev": ch["_hash"], "library_error": lib.get("error"),
            "library_version": lib.get("version")}


# ------------------------------------------------------------------ the face-consistency sheet
def face_sheets(cfg: dict, cid: str) -> list[dict]:
    d = cfgmod.path_of(cfg, "out") / "review" / f"character_{cid}"
    return [{"url": f"/out/review/character_{cid}/{p.name}", "when": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")}
            for p in sorted(d.glob("sheet_*.jpg"))] if d.is_dir() else []


def make_face_sheet(cfg: dict, game: str, cid: str, who: str | None) -> dict:
    """reviews.character_sheet — every variant and mood of one face on one compact sheet (review --character)."""
    from ..night4 import reviews
    try:
        paths, n = reviews.character_sheet(cfg, cid)
    except ValueError as e:
        return {"ok": False, "message": f"Nothing to put on it yet: {e}."}
    _sign(cfg, game, who, "art", f"character · {cid}", link=f"out/review/character_{cid}",
          note=f"made the face-consistency sheet ({n} picture(s), {len(paths)} page(s))")
    return {"ok": True, "message": f"The face sheet is made — {n} picture(s) on {len(paths)} page(s).",
            "sheets": face_sheets(cfg, cid)}


# ------------------------------------------------------------------ make the set
def _set_job(game: str, cid: str, variant: str | None, parts: list[str] | None) -> dict:
    job = {"type": "character_set", "character": cid, "game": game}
    if variant:
        job["variant"] = variant
    if parts:
        job["parts"] = list(parts)
    return job


def plan_set(cfg: dict, game: str, cid: str, variant: str | None, parts: list[str] | None = None) -> dict:
    """What `characters set` would queue, without queueing: the renders it would make, or why it can't yet (a
    placeholder look block, no locked seed, a never-list word) — in the words submit itself uses."""
    from ..night4 import charset
    chm = _chm()
    job = _set_job(game, cid, variant, parts)
    try:
        full = charset.expand_set(cfg, job, game)
    except (charset.CharsetError, chm.CharacterError) as e:
        lib = _library(cfg, game)
        try:
            _vn, v = chm.variant(chm.load(cfg, game, cid), variant)
            red = [b for f in ("prompt", "negative") for b in block_states(v.get(f), lib) if b["state"] != "written"]
        except chm.CharacterError:
            red = []
        return {"ok": False, "can_queue": False, "message": f"Can't queue the set yet — {e}",
                "blocks": red}
    rows = [{"part": r["part"], "seed": r["seed"], "size": r["size"], "checkpoint": r.get("checkpoint"),
             "loras": [l.get("name") for l in r.get("loras") or [] if isinstance(l, dict)]} for r in full["renders"]]
    return {"ok": True, "can_queue": True, "variant": full["variant"], "renders": rows,
            "message": f"{len(rows)} render(s) on seed {rows[0]['seed'] if rows else '?'} — the same face — then the "
                       "turnaround cut into the game's sheet contract.", "blocks_used": full.get("prompt_blocks") or []}


def queue_set(cfg: dict, game: str, cid: str, variant: str | None, who: str | None, parts: list[str] | None = None) -> dict:
    """The batch file `characters.bat set` writes, then the submit shim `submit.bat` runs — its printout returned."""
    from .. import cli
    if not who:
        raise CastRefused("set who you are first (top right) — a queued set is signed")
    plan = plan_set(cfg, game, cid, variant, parts)
    if not plan["can_queue"]:
        return plan
    vn = plan["variant"]
    job = _set_job(game, cid, vn, parts)
    p = cfgmod.path_of(cfg, "games") / game / "batches" / f"charset_{cid}_{vn}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps({"batch": p.stem, "jobs": [job]}, indent=1), encoding="utf-8", newline="\n")
    os.replace(tmp, p)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cli.cmd_submit(cfg, [str(p)])
    printed = buf.getvalue().strip()
    ok = rc == 0
    _sign(cfg, game, who, "queue", f"character · {cid}/{vn}", link=f"games/{game}/batches/{p.name}",
          note=("queued the character set — " if ok else "the character set did not submit — ") + (printed.splitlines() or [""])[-1][:300])
    return {"ok": ok, "message": "Queued — the worker makes it after what's already waiting." if ok
            else "It did not submit — the printout says why.", "printed": printed, "batch": str(p)}


# ------------------------------------------------------------------ the few edits the page makes
def edit(cfg: dict, game: str, cid: str, variant: str, field: str, value, rev: str | None, who: str | None) -> dict:
    """The locked seed (a whole number, or empty for none), `asymmetric` (true / false), or the reference pictures
    (add one path / remove one). Format-preserving; the old file kept in characters/_history/; journalled."""
    chm = _chm()
    if not who:
        raise CastRefused("set who you are first (top right) — registry edits are signed")
    if field not in EDITABLE:
        raise CastRefused(f"'{field}' isn't edited here — the look words live in the prompt library, written by whoever "
                          "owns the art direction")
    ch = chm.load(cfg, game, cid)
    if variant not in (ch.get("variants") or {}):
        raise CastRefused(f"{cid} has no variant '{variant}'")
    p = Path(ch["_file"])
    raw = p.read_bytes()
    if rev and ch["_hash"] != rev:
        return {"ok": False, "conflict": True, "message": f"{p.name} changed since you opened it — reload the page"}
    doc = JsonDoc.from_bytes(raw)
    ptr = f"/variants/{variant.replace('~', '~0').replace('/', '~1')}"
    before = doc.get(f"{ptr}/{field}") if doc.has(f"{ptr}/{field}") else None
    if field == "seed":
        s = str(value).strip() if value is not None else ""
        if s in ("", "none", "null"):
            new = None
        else:
            try:
                new = int(s)
            except ValueError:
                raise CastRefused(f"a seed is a whole number — '{s}' isn't")
            if new < 0 or new > 2**63 - 1:
                raise CastRefused("a seed is a whole number from 0 up")
    elif field == "asymmetric":
        if not isinstance(value, bool):
            raise CastRefused("asymmetric is yes or no")
        new = value
    else:
        refs = list(before or [])
        op = (value or {}).get("op") if isinstance(value, dict) else None
        path = str((value or {}).get("path") or "").strip().strip('"') if isinstance(value, dict) else ""
        if op == "add":
            if not path:
                raise CastRefused("give the picture's full path")
            if Path(path).suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".tif", ".tiff", ".bmp"):
                raise CastRefused(f"{Path(path).name} doesn't look like a picture")
            if path in refs:
                return {"ok": True, "message": "Already a reference.", "changed": False}
            refs.append(path)
        elif op == "remove":
            if path not in refs:
                raise CastRefused("that picture isn't one of the references")
            refs.remove(path)
        else:
            raise CastRefused("references: add or remove one path")
        new = refs
    if before == new:
        return {"ok": True, "message": "Already so — nothing changed.", "changed": False}
    if doc.has(f"{ptr}/{field}"):
        doc.set(f"{ptr}/{field}", new)
    else:
        doc.add(ptr, field, new)
    out = doc.to_bytes()
    json.loads(out.decode("utf-8-sig"))                    # never write a file that does not parse
    hist = p.parent / "_history"
    hist.mkdir(exist_ok=True)
    (hist / f"{cid}.{datetime.now():%Y%m%d-%H%M%S}.json").write_bytes(raw)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_bytes(out)
    os.replace(tmp, p)
    log.info("characters: %s set %s/%s.%s %r → %r", who, cid, variant, field, before, new)
    _sign(cfg, game, who, "edit", f"character · {cid}/{variant} · {field}", before=before, after=new,
          link=f"games/{game}/characters/{cid}.json")
    return {"ok": True, "changed": True, "message": f"Saved {field} for {cid} · {variant}.", "rev": chm.load(cfg, game, cid)["_hash"]}
