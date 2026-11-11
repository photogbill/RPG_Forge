"""Make a picture (BUILD 12 — spec §6 screen 2): a form by kind, not a prompt box.

    kinds(cfg, game)            what can be made, each kind's fields in plain words with the game's defaults filled in,
                                the characters (registry) and towns (wanted list) a picture can inherit from
    preview(cfg, game, form)    the job(s) the form makes; the prompt expanded read-only with every library block marked
                                (written · not written yet · not in the library); every refusal named beside its field
    queue(cfg, game, form, who) the same job(s) through submit (the character shim, prompt expansion, the never-list) —
                                the batch file is written to _incoming/ and submit's printout is shown as is

A character's variant fills in its recipe (night4/characters.resolve — the job's own keys win; `{{character}}` in the
prompt puts the variant's prompt at that point). A town adds `{{culture.<town>}}` (and `{{fate.<fate>}}`) and the
town's family seed, as produce plan does. "For" a wanted item records `_wanted` so the Wanted board follows it and
takes the item's size. Nothing here decides a look: the look words are the prompt library's.
"""
from __future__ import annotations
import contextlib, io, json, os, re
from datetime import datetime
from pathlib import Path

from .. import config as cfgmod
from ..log import get
from . import journal

log = get("suite")

# name, label, kind of input, help — a field missing from a job type's spec is never shown for it
F = {
    "prompt": ("What to paint", "text", "Plain words and {{blocks}} from the prompt library. With a character, {{character}} puts the variant's own prompt there."),
    "negative": ("What to keep out", "text", "Empty = the game's default negative."),
    "target": ("Size in the game", "size", "Width × height of the finished picture."),
    "size": ("Render size", "size", "The size it is painted at before cutting or scaling."),
    "init": ("Start from (greybox or picture)", "path", "A greybox or picture to paint over — a path, or out/<job id>."),
    "denoise": ("How far from the start picture", "number", "0 keeps it, 1 ignores it."),
    "base": ("The painting to change", "path", "out/<job id> of the painted scene (or its kit folder)."),
    "mask": ("Mask (what changes)", "path", "A black-and-white picture; white is repainted. Or give the two greyboxes instead."),
    "greybox_base": ("Greybox before", "path", "The scene's greybox as it was."),
    "greybox_state": ("Greybox after", "path", "The greybox in its new state — the difference becomes the mask."),
    "expressions": ("Expressions", "list", "One per picture, same face: e.g. neutral, smile, resolve."),
    "out_size": ("Portrait size in the game", "size", ""),
    "canvas": ("Icon canvas", "number", "Pixels; 256 by default, 512 for hi-res."),
    "tile_size": ("Tile size", "number", "Pixels in the game."),
    "target_h": ("Height in the game", "number", "Pixels."),
    "variants": ("Variations", "number", "How many takes in one job."),
    "photo": ("Photograph", "path", "A path to your photograph (never copied); it must be cleared in refs.local.json."),
    "parts": ("Parts", "choices", "moods, battle, turnaround"),
    "steps": ("Steps", "number", ""), "cfg": ("Guidance (cfg)", "number", ""),
    "sampler": ("Sampler", "word", ""), "checkpoint": ("Model (checkpoint)", "word", "Empty = the game's default."),
    "count": ("Takes", "number", ""),
    "input": ("The picture to make seamless", "path", "A texture: a path, or out/<job id>/<file>."),
    "heal": ("How to heal the seam", "word", "auto (inpaint on a GPU, blend otherwise), inpaint, or blend."),
}
KINDS = {
    "scene_kit": {"label": "A scene — the six-file kit", "fields": ["prompt", "negative", "target", "init", "denoise", "checkpoint"],
                  "town": True, "character": False, "for": "scene"},
    "scene_big": {"label": "A big scene (larger than one pass)", "fields": ["prompt", "negative", "target", "init", "checkpoint"],
                  "town": True, "character": False, "for": "scene"},
    "scene_state": {"label": "A state of a painted scene (War, After, a change)", "fields": ["base", "prompt", "mask", "greybox_base", "greybox_state", "denoise"],
                    "town": True, "character": False, "for": "scene"},
    "portrait": {"label": "A portrait set — one face, several expressions", "fields": ["prompt", "expressions", "size", "out_size", "negative", "checkpoint"],
                 "town": False, "character": True, "for": "portrait"},
    "character_set": {"label": "A character's set — moods, battle pose, turnaround", "fields": ["parts"],
                      "town": False, "character": "required", "for": "sprite_sheet"},
    "icon": {"label": "An item icon", "fields": ["prompt", "canvas", "negative", "checkpoint"], "town": False, "character": False, "for": "icon"},
    "prop": {"label": "A prop", "fields": ["prompt", "size", "target_h", "variants", "negative"], "town": True, "character": False, "for": "prop"},
    "tile_texture": {"label": "A texture (a tileable surface)", "fields": ["prompt", "size", "tile_size", "variants", "negative"],
                     "town": True, "character": False, "for": "tileset"},
    "photo_plate": {"label": "One of your photographs, painted as a plate", "fields": ["photo", "prompt", "target", "denoise"],
                    "town": True, "character": False, "for": "scene"},
    "tileable": {"label": "Make a texture tile seamlessly", "fields": ["input", "heal", "prompt"],
                 "town": False, "character": False, "for": "tileset"},
    "render": {"label": "A plain render — see what a model does", "fields": ["prompt", "negative", "size", "steps", "cfg", "sampler", "checkpoint"],
               "town": False, "character": True, "for": None},
}
MAX_TAKES = 24


class MakeRefused(ValueError):
    pass


def _spec(t: str) -> dict:
    from .. import schema
    if t not in schema.JOB_TYPES:
        schema._plugins()
    return schema.JOB_TYPES.get(t) or {}


def _game_root(cfg: dict, game: str) -> Path | None:
    from . import games
    try:
        r = games.game_root(cfg, game)
        return r if r and r.is_dir() else None
    except Exception:  # noqa: BLE001
        return None


def kinds(cfg: dict, game: str) -> dict:
    from .. import manifest
    from . import cast
    gcfg = cfgmod.game_config(cfg, game)
    out = []
    for t, k in KINDS.items():
        sp = _spec(t)
        if not sp:
            continue
        opt = sp.get("optional") or {}
        fields = []
        for f in k["fields"]:
            if f not in opt and f not in (sp.get("required") or []):
                continue
            label, kind, helptext = F.get(f, (f, "word", ""))
            d = opt.get(f)
            if f == "target" and t in ("scene_kit", "scene_big", "photo_plate") and gcfg.get("scene_size"):
                d = gcfg["scene_size"]
            if f == "negative" and gcfg.get("negative"):
                helptext = f"Empty = the game's default: “{gcfg['negative'][:90]}…”"
            if f == "checkpoint" and gcfg.get("checkpoint"):
                helptext = f"Empty = the game's default ({gcfg['checkpoint']})."
            fields.append({"name": f, "label": label, "input": kind, "help": helptext, "default": d,
                           "required": f in (sp.get("required") or [])})
        out.append({"type": t, "label": k["label"], "needs": sp.get("needs"), "doc": sp.get("doc", "")[:400],
                    "fields": fields, "town": k["town"], "character": k["character"], "for_kind": k["for"]})
    try:
        items = manifest.load_wanted(cfg, game).get("items") or {}
    except Exception:  # noqa: BLE001
        items = {}
    towns: dict[str, dict] = {}
    for w in items.values():
        if w.get("town"):
            towns.setdefault(w["town"], {"town": w["town"], "fate": w.get("fate"), "look": w.get("look")})
    wanted = [{"name": n, "kind": w.get("kind"), "target_size": w.get("target_size"), "town": w.get("town")}
              for n, w in sorted(items.items()) if not w.get("set_of")]
    return {"kinds": out, "characters": [{"id": c["id"], "name": c["name"], "variants": c["variants"], "stub": c.get("stub")}
                                         for c in cast.listing(cfg, game)],
            "towns": sorted(towns.values(), key=lambda t: t["town"]), "wanted": wanted,
            "defaults": {k: gcfg.get(k) for k in ("checkpoint", "negative", "style_prefix", "scene_size")}}


# ------------------------------------------------------------------ form → job(s)
def _size(v):
    if v in (None, "", []):
        return None
    if isinstance(v, (list, tuple)) and len(v) == 2:
        return [int(v[0]), int(v[1])]
    m = re.match(r"^\s*(\d+)\s*[x×,* ]\s*(\d+)\s*$", str(v))
    if not m:
        raise ValueError("a size is width × height, like 1920 × 1080")
    return [int(m.group(1)), int(m.group(2))]


def _value(kind: str, v):
    if v in (None, ""):
        return None
    if kind == "size":
        return _size(v)
    if kind == "number":
        f = float(v)
        return int(f) if f.is_integer() else f
    if kind == "list":
        return [x.strip() for x in (v if isinstance(v, list) else str(v).split(",")) if str(x).strip()]
    if kind == "choices":
        return [x.strip() for x in (v if isinstance(v, list) else str(v).split(",")) if str(x).strip()] or None
    return str(v).strip()


def build(cfg: dict, game: str, form: dict) -> tuple[list[dict], list[dict]]:
    """(jobs, problems) — problems are {"field", "message"}; jobs are what submit would get."""
    from ..night4 import produce
    t = str(form.get("type") or "")
    if t not in KINDS:
        raise MakeRefused(f"'{t}' is not a kind this form makes")
    k = KINDS[t]
    problems: list[dict] = []
    job: dict = {"type": t, "game": game, "batch": f"make/{t}"}
    for f in k["fields"]:
        kind = F.get(f, (f, "word", ""))[1]
        try:
            v = _value(kind, (form.get("fields") or {}).get(f))
        except ValueError as e:
            problems.append({"field": f, "message": str(e)})
            continue
        if v is not None:
            job[f] = v
    ch, var = str(form.get("character") or "").strip(), str(form.get("variant") or "").strip() or None
    if ch:
        if not k["character"]:
            problems.append({"field": "character", "message": "this kind doesn't take a character"})
        else:
            job["character"] = ch
            if var:
                job["variant"] = var
    elif k["character"] == "required":
        problems.append({"field": "character", "message": "choose whose set it is"})
    town = str(form.get("town") or "").strip()
    if town:
        if not k["town"]:
            problems.append({"field": "town", "message": "this kind doesn't take a town"})
        else:
            try:
                from .. import manifest
                items = manifest.load_wanted(cfg, game).get("items") or {}
            except Exception:  # noqa: BLE001
                items = {}
            fate = next((w.get("fate") for w in items.values() if w.get("town") == town and w.get("fate")), None)
            refs = ["{{culture.%s}}" % produce.town_word(town)] + (["{{fate.%s}}" % produce.town_word(fate)] if fate else [])
            if "prompt" in job:
                job["prompt"] = ", ".join([job["prompt"]] + [r for r in refs if r not in job["prompt"]])
            job["meta"] = {**(job.get("meta") or {}), "town": town, **({"fate": fate} if fate else {})}
            job.setdefault("seed", produce.town_seed(town))
    wanted = str(form.get("for") or "").strip()
    if wanted:
        try:
            from .. import manifest
            w = (manifest.load_wanted(cfg, game).get("items") or {}).get(wanted)
        except Exception:  # noqa: BLE001
            w = None
        if not w:
            problems.append({"field": "for", "message": f"'{wanted}' is not in this game's wanted list"})
        else:
            job["_wanted"] = wanted
            job["meta"] = {**(job.get("meta") or {}), "wanted": wanted}
            if "target" in KINDS[t]["fields"] and not job.get("target") and w.get("target_size"):
                job["target"] = list(w["target_size"])
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", str(form.get("name") or "").strip()).strip("_")
    job["name"] = name or (wanted.split("/")[-1] if wanted else f"{t}_{datetime.now():%m%d_%H%M}")
    seed = (form.get("fields") or {}).get("seed", form.get("seed"))
    try:
        seed = int(seed) if seed not in (None, "", "-1", -1) else None
    except (TypeError, ValueError):
        problems.append({"field": "seed", "message": "a seed is a whole number (or empty for a new one each take)"})
        seed = None
    try:
        takes = max(1, min(MAX_TAKES, int(form.get("takes") or 1)))
    except (TypeError, ValueError):
        problems.append({"field": "takes", "message": "how many is a whole number"})
        takes = 1
    if seed is not None:
        job["seed"] = seed
    jobs = []
    for i in range(takes):
        j = dict(job)
        if takes > 1:
            j["name"] = f"{job['name']}_{i + 1:02d}"
            if isinstance(job.get("seed"), int):
                j["seed"] = job["seed"] + i                          # neighbouring seeds: the same family, a different take
        jobs.append(j)
    return jobs, problems


def _field_of(message: str) -> str:
    m = re.search(r"field '([a-z_]+)'", message)
    if m:
        return m.group(1)
    for f in ("prompt", "negative", "character", "variant", "photo", "base", "mask", "target", "seed"):
        if f in message:
            return f
    return "prompt"


def preview(cfg: dict, game: str, form: dict) -> dict:
    from .. import prompts as pl, schema
    from ..night4 import characters as chm, produce
    from . import cast
    jobs, problems = build(cfg, game, form)
    j = jobs[0]
    lib = pl.load(cfg, game)
    shown = dict(j)
    if j.get("character") and j["type"] != "character_set":
        try:
            shown = chm.resolve(cfg, j, game)
        except Exception as e:  # noqa: BLE001
            problems.append({"field": "character", "message": str(e)})
    elif j["type"] == "character_set" and j.get("character"):
        from ..night4 import charset
        try:
            full = charset.expand_set(cfg, j, game)
            shown = {**shown, "prompt": (full.get("prompt_template") or {}).get("prompt"), "renders": len(full["renders"])}
        except Exception as e:  # noqa: BLE001
            problems.append({"field": "character", "message": str(e)})
            try:
                _vn, v = chm.variant(chm.load(cfg, game, j["character"]), j.get("variant"))
                shown = {**shown, "prompt": v.get("prompt"), "negative": v.get("negative")}
            except Exception:  # noqa: BLE001
                pass
    expanded, blocks = {}, {}
    for f in ("prompt", "negative"):
        text = shown.get(f)
        if not text:
            continue
        blocks[f] = cast.block_states(text, lib)
        try:
            expanded[f] = pl.expand_text(text, lib["blocks"])
        except pl.PromptError as e:
            expanded[f] = None
            if j["type"] != "character_set":              # the set's own refusal is already listed under character
                problems.append({"field": f if f in KINDS[j["type"]]["fields"] else "character", "message": str(e)})
    for p in schema.validate({k: v for k, v in j.items() if not k.startswith("_")}):
        problems.append({"field": _field_of(p), "message": p})
    if j["type"] == "photo_plate" and j.get("photo"):
        from ..night4 import photo as ph
        try:
            ph.guard(cfg, game, Path(str(j["photo"])))
        except ph.PeopleGuard as e:                  # the people guard: nobody, or William himself (his cameo ruling)
            problems.append({"field": "photo", "message": str(e)})
    hits = pl.never_hits({f: expanded.get(f) for f in ("prompt", "negative") if expanded.get(f)}, pl.never_words(lib))
    if hits:
        problems.append({"field": "prompt", "message": f"the prompt contains {', '.join(hits)} — on the never-list"})
    seen, uniq = set(), []
    for p in problems:
        key = (p["field"], p["message"])
        if key not in seen:
            seen.add(key)
            uniq.append(p)
    est = produce.estimate(cfg, jobs)
    return {"ok": True, "jobs": [{k: v for k, v in x.items()} for x in jobs], "shown": {k: shown.get(k) for k in ("prompt", "negative", "checkpoint", "seed", "size", "target", "renders") if shown.get(k) is not None},
            "expanded": expanded, "blocks": blocks, "problems": uniq, "can_queue": not uniq,
            "estimate": {"gpu_hours": est["gpu_hours"], "disk_gb": est["disk_gb"], "free_gb": est["free_gb"]}}


def queue(cfg: dict, game: str, form: dict, who: str | None) -> dict:
    from .. import cli
    if not who:
        raise MakeRefused("set who you are first (top right) — a queued picture is signed")
    pv = preview(cfg, game, form)
    if not pv["can_queue"]:
        return {"ok": False, "message": "Not queued — " + "; ".join(f"{p['field']}: {p['message']}" for p in pv["problems"]),
                "problems": pv["problems"]}
    jobs = pv["jobs"]
    inc = Path(cfg.get("incoming_dir") or (cfgmod.ROOT / "_incoming"))
    inc.mkdir(parents=True, exist_ok=True)
    p = inc / f"make_{jobs[0]['type']}_{datetime.now():%Y%m%d-%H%M%S}.json"
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps({"batch": f"make/{jobs[0]['type']}", "game": game, "defaults": {"game": game}, "jobs": jobs},
                              indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    os.replace(tmp, p)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cli.cmd_submit(cfg, [str(p)])
    printed = buf.getvalue().strip()
    root = _game_root(cfg, game)
    if root is not None:
        try:
            journal.append(root, who, "queue", f"make · {jobs[0]['type']} · {jobs[0]['name']}", link=str(p),
                           note=(f"queued {len(jobs)} take(s)" if rc == 0 else "did not submit") + (f" for {jobs[0]['_wanted']}" if jobs[0].get("_wanted") else ""))
        except Exception as e:  # noqa: BLE001
            log.warning("make: journal line not written (%s)", e)
    return {"ok": rc == 0, "message": (f"Queued {len(jobs)} take(s) — the worker makes them after what's already waiting."
                                       if rc == 0 else "It did not submit — the printout says why."), "printed": printed, "file": str(p)}
