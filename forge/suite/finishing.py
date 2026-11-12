"""Art feedback and finishing in the suite (BUILD 14 — spec §6 screens 7–10, F5–F8, §8 B6).

    called_out(cfg) / callout(cfg, game, action, draft, who)   the redo drafts (playtest notes, review notes, mark-ups):
                                                               queue one, dismiss it, or hand it out to the person
    take_in(cfg, game, who)                                    the game's F9 notes → drafts (feedback_in.bat)
    markup(cfg, game, jid, file, shapes, note, fix, who)       circles and strokes on a picture → an inpaint mask → a
                                                               scene_state fix draft (and a full redo) — never queued
    library(cfg, game) / edit_block(…) / where_used / ab_draft  the prompt library as shelves (prompts.py)
    bakeoffs(cfg, game) / bakeoff_act(…)                       the game's bake-off suites: counts, hours, queue, report
    handoffs(cfg) / hand_in(…)                                 outside tools: folders out and back (handoff.py)
    models(cfg, game, scan)                                    the model shelf report (models_shelf.build) — deletes nothing

Every one calls the forge's own functions, the same as the .bat files; every write is signed in the game's journal.
"""
from __future__ import annotations
import contextlib, io, json, os, re
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

from .. import config as cfgmod
from ..log import get
from . import journal
from .jsondoc import JsonDoc

log = get("suite")


class FinishRefused(ValueError):
    pass


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
        log.warning("finishing: journal line not written (%s)", e)


def _need(who: str | None, what: str) -> None:
    if not who:
        raise FinishRefused(f"set who you are first (top right) — {what} is signed")


def _printed(fn, *a) -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = fn(*a)
    return rc, buf.getvalue().strip()


# ------------------------------------------------------------------ Called out
def called_out(cfg: dict) -> list[dict]:
    from ..night4 import feedback
    out = []
    for d in feedback.list_drafts(cfg):
        p = feedback.drafts_dir(cfg) / d["draft"]
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            j = {}
        mk = j.get("_markup") or {}
        out.append({**d, "mask": j.get("mask"), "prompt": j.get("prompt"), "base": j.get("base"),
                    "marked": mk.get("marked"), "by": (j.get("_called_out") or {}).get("tester"),
                    "source": (j.get("_called_out") or {}).get("from") or ("playtest" if j.get("_called_out") else None)})
    return out


def callout(cfg: dict, game: str, action: str, draft: str, who: str | None) -> dict:
    from ..night4 import feedback
    _need(who, "a decision on a draft")
    if action not in ("draft_submit", "draft_dismiss", "draft_himself"):
        raise FinishRefused(f"unknown action {action}")
    r = feedback.draft_action(cfg, action, draft)
    if r.get("ok"):
        word = {"draft_submit": "queued the draft", "draft_dismiss": "dismissed the draft",
                "draft_himself": "handed the picture out to fix by hand"}[action]
        _sign(cfg, game, who, "queue" if action == "draft_submit" else "draft", f"called out · {draft}", note=f"{word} — {r.get('message')}")
    return r


def take_in(cfg: dict, game: str, who: str | None) -> dict:
    from ..night4 import feedback
    _need(who, "taking in the notes")
    from . import playtest
    try:
        r = feedback.take_in(cfg, playtest.art_file(cfg, game), game)   # BUILD 17: where the game's adapter says F9 writes
    except FileNotFoundError as e:
        return {"ok": False, "message": str(e)}
    msg = (f"{len(r['filed'])} note(s) matched a delivered picture → redo drafts under Called out; {len(r['bumped'])} matched a "
           f"stand-in → priority bumps; {r['skipped']} already read.")
    _sign(cfg, game, who, "draft", "playtest notes", note=msg)
    return {"ok": True, "message": msg, "result": r}


# ------------------------------------------------------------------ mark up a picture (B6)
def _mask(size: tuple[int, int], shapes: list[dict]) -> Image.Image:
    """White where the person drew (ellipses filled, strokes thickened), black elsewhere — the inpaint mask."""
    m = Image.new("L", size, 0)
    d = ImageDraw.Draw(m)
    W, H = size
    for s in shapes or []:
        kind = s.get("kind")
        if kind == "ellipse":
            x0, y0, x1, y1 = (float(v) for v in s["box"])
            box = [max(0, min(x0, x1)), max(0, min(y0, y1)), min(W, max(x0, x1)), min(H, max(y0, y1))]
            if box[2] - box[0] >= 2 and box[3] - box[1] >= 2:
                d.ellipse(box, fill=255)
        elif kind == "stroke":
            pts = [(float(x), float(y)) for x, y in s.get("points") or []]
            w = max(4, int(float(s.get("width") or max(W, H) * 0.02)))
            if len(pts) >= 2:
                d.line(pts, fill=255, width=w, joint="curve")
            for x, y in pts:
                d.ellipse([x - w / 2, y - w / 2, x + w / 2, y + w / 2], fill=255)
    return m


def markup(cfg: dict, game: str, jid: str, file: str, shapes: list[dict], note: str, fix_prompt: str, who: str | None,
           state) -> dict:
    """The person circles what's wrong and says what: the circles become the inpaint mask of a scene_state fix draft on
    this picture (and feedback.draft_redo writes the full redo beside it). Drafts only — queued from Called out."""
    from ..night4 import feedback
    _need(who, "a mark-up")
    note = str(note or "").strip()
    if not note:
        raise FinishRefused("say what's wrong — the note goes with the draft")
    if not shapes:
        raise FinishRefused("circle or draw over what's wrong first")
    j = state.job(jid)
    if j is None:
        raise FinishRefused(f"no job {jid}")
    out = cfgmod.path_of(cfg, "out") / jid
    src = (out / Path(str(file)).name)
    if not src.is_file():
        raise FinishRefused(f"{file} is not in out/{jid}/")
    with Image.open(src) as im:
        size = im.size
        base = im.convert("RGB")
    m = _mask(size, shapes)
    if not m.getbbox():
        raise FinishRefused("the marks are empty — draw a circle round what's wrong")
    import numpy as np
    share = float(np.count_nonzero(np.asarray(m))) / float(size[0] * size[1])
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    mdir = cfgmod.path_of(cfg, "out") / "markup" / jid
    mdir.mkdir(parents=True, exist_ok=True)
    mask_p = mdir / f"{stamp}_mask.png"
    m.save(mask_p)
    over = base.copy()
    red = Image.new("RGB", size, (230, 40, 40))
    over.paste(Image.blend(base, red, 0.45), (0, 0), m)
    marked_p = mdir / f"{stamp}_marked.jpg"
    over.save(marked_p, "JPEG", quality=88)
    wanted = ((j.get("meta") or {}).get("wanted") or j.get("_wanted") or j.get("name") or jid)
    if isinstance(wanted, list):
        wanted = wanted[0] if wanted else jid
    entry = {"note": note, "tester": who, "from": "mark-up in the suite", "time": datetime.now().isoformat(timespec="seconds")}
    paths = feedback.draft_redo(cfg, j, note, str(wanted), entry)
    fix = next((p for p in paths if "-fix-" in p.name), None)
    rel_base = f"out/{jid}" if (j.get("result") or {}).get("slots") else f"out/{jid}/{src.name}"
    mk = {"mask": str(mask_p), "marked": f"/out/markup/{jid}/{marked_p.name}", "share": round(share, 4), "file": src.name}
    if fix is None:                                 # a portrait, an icon …: draft_redo wrote the full redo only
        fix = feedback.drafts_dir(cfg) / f"{stamp}-fix-{Path(str(wanted)).name}.json"
        base_job = {"type": "scene_state", "name": f"{j.get('name') or Path(str(wanted)).name}_fix", "_draft": True,
                    "redo_of": jid, "comment": note, "_wanted": str(wanted), "_called_out": entry, "seed": j.get("seed") if isinstance(j.get("seed"), int) else -1,
                    "meta": {**(j.get("meta") or {}), "wanted": str(wanted), "redo_of": jid}}
        fix.write_text(json.dumps(base_job, indent=1, ensure_ascii=False), encoding="utf-8")
        paths.append(fix)
    d = json.loads(fix.read_text(encoding="utf-8"))
    d.update({"base": rel_base, "mask": str(mask_p), "prompt": str(fix_prompt or "").strip(), "_markup": mk,
              "_why": "a mark-up: repaint only what was circled" + ("" if fix_prompt else " — write what it should be (the prompt) before queueing")})
    if share > 0.35:
        d["_why"] += f" (the circles cover {share:.0%} of the picture — a state repaint refuses over 35 %; use the full redo)"
    tmp = fix.with_name(fix.name + ".tmp")
    tmp.write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, fix)
    _sign(cfg, game, who, "draft", str(wanted), link=f"out/markup/{jid}/{marked_p.name}",
          note=f"marked up {jid} ({share:.0%} of the picture): {note}")
    return {"ok": True, "message": "Two drafts are under Called out: a repaint of what you circled"
                                   + ("" if fix_prompt else " (it needs a line saying what it should be before it can be queued)")
                                   + " and a full redo with a new seed. Nothing is queued.",
            "drafts": [p.name for p in paths], "marked": mk["marked"], "share": mk["share"]}


# ------------------------------------------------------------------ the prompt library (screen 7)
def library(cfg: dict, game: str) -> dict:
    from .. import prompts as pl
    try:
        lib = pl.load(cfg, game)
    except pl.PromptError as e:
        return {"error": str(e), "shelves": [], "never": [], "problems": []}
    shelves: dict[str, list] = {}
    for name, text in sorted(lib["blocks"].items()):
        state = "placeholder" if str(text).strip().upper().startswith("TODO") else "written"
        refs = pl.refs(text)
        missing = [r for r in refs if r not in lib["blocks"]]
        shelves.setdefault(name.split(".")[0], []).append({"name": name, "text": text, "state": state, "file": lib["files"].get(name),
                                                           "refs": refs, "missing": missing})
    order = list(pl.SHELVES)
    out = [{"shelf": s, "known": s in order, "blocks": b, "placeholders": sum(1 for x in b if x["state"] == "placeholder")}
           for s, b in sorted(shelves.items(), key=lambda kv: (order.index(kv[0]) if kv[0] in order else 999, kv[0]))]
    batches = sorted(p.stem for p in (cfgmod.path_of(cfg, "games") / game / "batches").glob("*.json"))
    return {"shelves": out, "never": lib["never"], "triggers": lib["triggers"], "version": lib["version"],
            "problems": pl.check_library(lib), "batches": batches, "count": len(lib["blocks"])}


def edit_block(cfg: dict, game: str, name: str, text: str, who: str | None) -> dict:
    """A block's words, in the file that defines it — format-preserving, the old file kept in prompts/_history/,
    journalled. A new block goes into prompts/night4.json (the shelf file produce plan writes)."""
    from .. import prompts as pl
    _need(who, "a block's words")
    name = str(name or "").strip()
    if not re.match(r"^[A-Za-z0-9_.\-]+$", name) or "." not in name:
        raise FinishRefused("a block is named shelf.name — letters, digits, . _ -")
    lib = pl.load(cfg, game)
    folder = pl.folder(cfg, game)
    p = folder / (lib["files"].get(name) or "night4.json")
    if p.name == "never.json":
        raise FinishRefused("never.json holds the never-list, not blocks")
    raw = p.read_bytes() if p.exists() else b'{\n "blocks": {}\n}\n'
    doc = JsonDoc.from_bytes(raw)
    if not doc.has("/blocks"):
        doc.add("", "blocks", {})
    ptr = "/blocks/" + name.replace("~", "~0").replace("/", "~1")
    before = doc.get(ptr) if doc.has(ptr) else None
    text = str(text)
    if before == text:
        return {"ok": True, "changed": False, "message": "Already so — nothing changed."}
    test = dict(lib["blocks"])
    test[name] = text
    try:
        pl.expand_text("{{%s}}" % name, test) if not text.strip().upper().startswith("TODO") else None
    except pl.PromptError as e:
        if "placeholder" not in str(e):
            raise FinishRefused(f"those words don't expand: {e}")
    bad = pl.never_hits({"prompt": text}, pl.never_words(lib))
    if bad:
        raise FinishRefused(f"the words contain {', '.join(bad)} — on the never-list")
    if before is None:
        doc.add("/blocks", name, text)
    else:
        doc.set(ptr, text)
    new = doc.to_bytes()
    json.loads(new.decode("utf-8-sig"))
    if p.exists():
        h = folder / "_history"
        h.mkdir(exist_ok=True)
        (h / f"{p.stem}.{datetime.now():%Y%m%d-%H%M%S}.json").write_bytes(raw)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_bytes(new)
    os.replace(tmp, p)
    _sign(cfg, game, who, "edit", f"prompt block · {name}", before=before, after=text, link=f"games/{game}/prompts/{p.name}")
    return {"ok": True, "changed": True, "message": f"Saved {{{{{name}}}}}" + (" — still a placeholder." if text.strip().upper().startswith("TODO") else ".")}


def where_used(cfg: dict, block: str) -> list[dict]:
    from .. import prompts as pl
    return pl.where_used(cfg, block)[:60]


def ab_draft(cfg: dict, game: str, block: str, batch: str, who: str | None) -> dict:
    from .. import prompts as pl
    _need(who, "an A/B draft")
    try:
        p = pl.ab_drafts(cfg, block, batch, 4, game)
    except pl.PromptError as e:
        return {"ok": False, "message": str(e)}
    _sign(cfg, game, who, "draft", f"A/B · {block}", link=str(p), note=f"same-seed pairs with and without {{{{{block}}}}} on {batch}")
    return {"ok": True, "message": f"An A/B draft is at {p.name}: the same pictures with and without {{{{{block}}}}}, same seed. "
                                   "Check it, delete its _draft line, then submit.bat it.", "file": str(p)}


# ------------------------------------------------------------------ bake-offs (screen 8)
def bakeoffs(cfg: dict, game: str) -> dict:
    from .. import bakeoff
    d = cfgmod.path_of(cfg, "games") / game / "bakeoff"
    try:
        inv = bakeoff.inventory(cfg) or []
    except Exception as e:  # noqa: BLE001
        inv, err = [], str(e)
    else:
        err = None
    out_root = cfgmod.path_of(cfg, "out") / "bakeoff"
    rows = []
    for p in sorted(d.glob("*.json")) if d.is_dir() else []:
        try:
            suite = json.loads(p.read_text(encoding="utf-8"))
            pl_ = bakeoff.plan(suite, inv, cfg) if inv else None
        except Exception as e:  # noqa: BLE001
            rows.append({"file": p.name, "error": f"{type(e).__name__}: {e}"}); continue
        name = suite.get("suite") or p.stem
        rec = out_root / name
        sub = None
        try:
            sub = json.loads((rec / "plan.json").read_text(encoding="utf-8")).get("submitted")
        except (OSError, ValueError):
            pass
        rows.append({"file": p.name, "suite": name, "graph": suite.get("graph", "sdxl"), "note": suite.get("_comment") or suite.get("note"),
                     "checkpoints": len(pl_["checkpoints"]) if pl_ else None, "loras": len(pl_["loras"]) if pl_ else None,
                     "renders": len(pl_["jobs"]) if pl_ else None, "minutes": pl_["estimate_min"] if pl_ else None,
                     "submitted": sub, "report": f"/out/bakeoff/{name}/index.html" if (rec / "index.html").exists() else None,
                     "grids": [f"/out/bakeoff/{name}/{g.name}" for g in sorted(rec.glob("grid_*.png"))[:6]] if rec.is_dir() else []})
    return {"suites": rows, "inventory": len(inv), "error": err}


def bakeoff_act(cfg: dict, game: str, action: str, file: str, who: str | None) -> dict:
    from .. import cli
    _need(who, "a bake-off")
    p = cfgmod.path_of(cfg, "games") / game / "bakeoff" / Path(str(file)).name
    if not p.is_file():
        raise FinishRefused(f"no suite {file}")
    if action == "queue":
        rc, out = _printed(cli.cmd_bakeoff, cfg, ["submit", str(p)])
        _sign(cfg, game, who, "queue", f"bake-off · {p.stem}", note=(out.splitlines() or [""])[-1][:300])
        return {"ok": rc == 0, "message": "Queued — read the printout." if rc == 0 else "It did not queue — the printout says why.", "printed": out}
    if action == "report":
        name = json.loads(p.read_text(encoding="utf-8")).get("suite") or p.stem
        rc, out = _printed(cli.cmd_bakeoff, cfg, ["report", name])
        return {"ok": rc == 0, "message": "The report is made." if rc == 0 else "No report — the printout says why.", "printed": out,
                "report": f"/out/bakeoff/{name}/index.html"}
    raise FinishRefused(f"unknown {action}")


# ------------------------------------------------------------------ outside tools (screen 10)
def handoffs(cfg: dict) -> dict:
    from .. import handoff as ho
    base = cfgmod.path_of(cfg, "out") / "handoff"
    rows = []
    for mp in sorted(base.glob("*/handoff.json"), key=lambda p: p.stat().st_mtime, reverse=True) if base.is_dir() else []:
        try:
            man = json.loads(mp.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        done = mp.parent / "done"
        try:
            picked, extra, notes = ho._match(man.get("entries") or [], done)
        except Exception:  # noqa: BLE001
            picked, extra, notes = {}, [], []
        missing = [e["file"] for e in man.get("entries") or [] if e["job"] not in picked]
        rows.append({"name": man.get("name") or mp.parent.name, "created": man.get("created"), "entries": len(man.get("entries") or []),
                     "back": len(picked), "missing": missing, "extra": extra, "notes": notes + (man.get("notes") or []),
                     "in": str(mp.parent / "in"), "done": str(done), "brought_in": man.get("brought_in") or man.get("handed_in")})
    from . import sprites
    return {"handoffs": rows, "tools": sprites.tools(cfg, "")["tools"]}


def hand_in(cfg: dict, game: str, name: str, tool: str | None, who: str | None) -> dict:
    from .. import handoff as ho
    _need(who, "bringing a hand-off back")
    try:
        r = ho.hand_in(cfg, name, tool=tool or None, submit=True)
    except ho.HandoffError as e:
        return {"ok": False, "message": str(e)}
    _sign(cfg, game, who, "queue", f"hand-in · {name}", note=f"brought back from the outside tool{(' (' + tool + ')') if tool else ''}")
    n = len(r.get("jobs") or r.get("submitted") or []) if isinstance(r, dict) else 0
    return {"ok": True, "message": f"Brought back — {n} picture(s) go through the forge again (kit companions rebuilt where it's a scene).",
            "result": {k: v for k, v in (r or {}).items() if k in ("name", "jobs", "submitted", "missing", "extra", "notes", "tool")}}


def open_folder(cfg: dict, path: str) -> dict:
    """Explorer on a hand-off folder (only inside out/handoff)."""
    import subprocess
    p = Path(str(path)).resolve()
    base = (cfgmod.path_of(cfg, "out") / "handoff").resolve()
    if base not in p.parents or not p.is_dir():
        raise FinishRefused("only a hand-off folder can be opened from here")
    try:
        from . import osopen
        osopen.open_path(p)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": f"couldn't open it ({e}); it is at {p}"}
    return {"ok": True, "message": f"opened {p}"}


# ------------------------------------------------------------------ the model shelf (screen 9)
def models(cfg: dict, game: str, scan: bool = False) -> dict:
    """models_shelf.build — one row per file under the model folders: loads, licence colour, used by, verdict, size;
    the *safe to delete* totals. It deletes nothing. Without `scan` the last scan's inventory is reused (fast)."""
    from ..night4 import models_shelf
    p, totals = models_shelf.build(cfg, game, scan=scan)
    rows = json.loads(p.with_suffix(".json").read_text(encoding="utf-8"))
    keep = ("file", "path", "kind_dir", "gb", "loads", "group", "why", "licence", "approved", "runs", "last", "queued", "verdict",
            "reason", "needed_by", "safe_to_delete")
    rows = [{k: r.get(k) for k in keep} for r in rows]
    rows.sort(key=lambda r: (not r["safe_to_delete"], -(r.get("gb") or 0)))
    return {"rows": rows, "totals": totals, "report": "/out/reports/" + p.name, "made": datetime.now().isoformat(timespec="seconds")}
