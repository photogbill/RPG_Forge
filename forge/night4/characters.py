"""The character registry (Night 4, F2): one file per character, every variant's recipe in one place.

    games/<game>/characters/<id>.json
    {"id": "hero", "name": "Hero", "asymmetric": true,
     "variants": {"armoured": {"prompt": "{{char.hero.base}}, {{char.hero.armoured}}", "negative": "…",
                               "checkpoint": "…", "sampler": "dpmpp_2m", "scheduler": "karras", "steps": 28,
                               "seed": 24101, "references": ["D:\\…"], "asymmetric": true,
                               "wanted": {"field_sheet": "placeholder/hero_hero", "portrait": "…",
                                          "battle_pose": null, "portrait_moods": ["neutral", …]}}}}

A job may say `"character": "hero", "variant": "armoured"` and inherit the variant's recipe: prompt, negative,
checkpoint, loras, sampler, scheduler, steps, cfg, seed, size. The job's own keys always win. A job whose `prompt`
contains `{{character}}` gets the variant's prompt put in at that point instead (so a pose or a mood can be added
around the face). The job records `character`, `variant` and `character_registry` (a hash of the file), so a
picture can be traced back to the recipe that made it.

Tonight inheritance runs in a submit shim (forge/cli_night4.py wraps `submit`); WIRE_NIGHT_4.md moves it into
submit proper. Look words are Fable's: the shipped blocks are TODO placeholders and refuse to expand.

    python -m forge characters list | show <id> | check [<id>] | stubs     (characters.bat)
"""
from __future__ import annotations
import hashlib
import json
import logging
from pathlib import Path

from .. import config as cfgmod

log = logging.getLogger("forge.characters")

INHERIT = ("prompt", "negative", "checkpoint", "loras", "sampler", "scheduler", "steps", "cfg", "seed", "size", "graph",
           "style_prefix")
SLOT = "{{character}}"


class CharacterError(ValueError):
    pass


def folder(cfg: dict, game: str) -> Path:
    return cfgmod.path_of(cfg, "games") / game / "characters"


def load(cfg: dict, game: str, cid: str) -> dict:
    p = folder(cfg, game) / f"{cid}.json"
    if not p.exists():
        have = ", ".join(sorted(x.stem for x in folder(cfg, game).glob("*.json"))) or "none"
        raise CharacterError(f"no character '{cid}' in games/{game}/characters/ (have: {have})")
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as e:
        raise CharacterError(f"{p.name} is not valid JSON: {e}")
    d["_file"] = str(p)
    d["_hash"] = hashlib.sha1(p.read_bytes()).hexdigest()[:10]
    return d


def all_ids(cfg: dict, game: str) -> list[str]:
    return sorted(p.stem for p in folder(cfg, game).glob("*.json"))


def variant(ch: dict, name: str | None) -> tuple[str, dict]:
    vs = ch.get("variants") or {}
    if not vs:
        raise CharacterError(f"character '{ch.get('id')}' has no variants yet")
    if name is None:
        name = ch.get("default_variant") or next(iter(vs))
    if name not in vs:
        raise CharacterError(f"character '{ch.get('id')}' has no variant '{name}' (has: {', '.join(vs)})")
    return name, vs[name]


def is_asymmetric(ch: dict, vname: str | None = None) -> bool:
    if vname and vname in (ch.get("variants") or {}):
        v = ch["variants"][vname]
        if "asymmetric" in v:
            return bool(v["asymmetric"])
    return bool(ch.get("asymmetric"))


def resolve(cfg: dict, job: dict, game: str | None = None) -> dict:
    """A copy of the job with its character's variant filled in (job keys win). Jobs with no `character` are
    returned unchanged."""
    cid = job.get("character")
    if not cid:
        return job
    g = job.get("game") or game or "turing_accords"
    ch = load(cfg, g, str(cid))
    vname, v = variant(ch, job.get("variant"))
    out = dict(job)
    for k in INHERIT:
        if k not in v or v[k] is None:
            continue
        if k == "prompt" and job.get("prompt") and SLOT in str(job["prompt"]):
            out["prompt"] = str(job["prompt"]).replace(SLOT, str(v["prompt"]))
            continue
        if k not in job or job[k] is None:
            out[k] = v[k]
    if out.get("prompt") and SLOT in str(out["prompt"]):
        raise CharacterError(f"character '{cid}' variant '{vname}' has no prompt to put in for {SLOT}")
    out["variant"] = vname
    out["character_registry"] = ch["_hash"]
    return out


def resolve_batch(cfg: dict, data: dict) -> tuple[dict, int]:
    """A batch or single job with every character job resolved. Returns (data, how many were)."""
    if isinstance(data, dict) and "jobs" in data:
        d = data.get("defaults", {})
        g = data.get("game") or d.get("game")
        n = 0
        jobs = []
        for j in data["jobs"]:
            full = {**d, **j}
            if full.get("character"):
                jobs.append(resolve(cfg, full, g)); n += 1
            else:
                jobs.append(full)
        return {**data, "defaults": {}, "jobs": jobs}, n
    if isinstance(data, dict) and data.get("character"):
        return resolve(cfg, data), 1
    return data, 0


def check(cfg: dict, game: str, cid: str | None = None) -> list[str]:
    """Problems: unknown prompt blocks, TODO blocks (fine, but listed), missing reference files, missing models,
    wanted names that are not in wanted.json."""
    from .. import prompts as pl
    lib = pl.load(cfg, game)
    try:
        from .. import manifest
        wanted = manifest.load_wanted(cfg, game)["items"]
    except Exception:  # noqa: BLE001
        wanted = None
    out = []
    for i in ([cid] if cid else all_ids(cfg, game)):
        try:
            ch = load(cfg, game, i)
        except CharacterError as e:
            out.append(str(e)); continue
        for vn, v in (ch.get("variants") or {}).items():
            tag = f"{i}/{vn}"
            for f in ("prompt", "negative"):
                for ref in pl.refs(v.get(f)):
                    if ref not in lib["blocks"]:
                        out.append(f"{tag}: {f} uses {{{{{ref}}}}}, which is not in the prompt library")
                    elif str(lib["blocks"][ref]).strip().upper().startswith("TODO"):
                        out.append(f"{tag}: {{{{{ref}}}}} is still a placeholder (Fable's to write)")
            for r in v.get("references") or []:
                if not Path(r).exists():
                    out.append(f"{tag}: reference picture not found here: {r}")
            for k, val in (v.get("wanted") or {}).items():
                if isinstance(val, str) and not k.startswith("_") and wanted is not None and val not in wanted:
                    out.append(f"{tag}: wanted.{k} = '{val}' is not in wanted.json (the game has no slot of that name yet)")
            if v.get("seed") in (None, -1):
                out.append(f"{tag}: no locked seed — every render will be a different face")
    return out


def stubs(cfg: dict, game: str) -> list[str]:
    """Empty registry files for every cast member the game names that has none: from the game's characters.json if
    readable, otherwise from the hero_/npc_/portrait_ names in wanted.json. Never overwrites a file."""
    from .. import manifest
    gcfg = cfgmod.game_config(cfg, game)
    root = Path(gcfg.get("game_root") or "")
    names: dict[str, dict] = {}
    src = None
    cj = root / "project" / "data" / "characters.json"
    if cj.exists():
        try:
            data = json.loads(cj.read_text(encoding="utf-8"))
            items = data.items() if isinstance(data, dict) else ((d.get("id"), d) for d in data if isinstance(d, dict))
            for k, v in items:
                if k:
                    names[str(k)] = {"name": (v or {}).get("name") or str(k), "source": "data/characters.json"}
            src = str(cj)
        except (OSError, ValueError):
            names = {}
    if not names:
        for n, w in manifest.load_wanted(cfg, game)["items"].items():
            stem = n.split("/")[-1]
            for pre, kind in (("hero_", "field_sheet"), ("npc_", "field_sheet"), ("portrait_", "portrait")):
                if stem.startswith(pre):
                    cid = stem[len(pre):]
                    names.setdefault(cid, {"name": cid.replace("_", " ").title(), "source": "wanted.json", "wanted": {}})
                    names[cid].setdefault("wanted", {})[kind] = n
        src = "wanted.json"
    d = folder(cfg, game)
    d.mkdir(parents=True, exist_ok=True)
    made = []
    for cid, info in sorted(names.items()):
        p = d / f"{cid}.json"
        if p.exists():
            continue
        rec = {"id": cid, "name": info["name"], "_stub": f"made from {src} — fill in when the character is drawn",
               "asymmetric": None, "default_variant": "default",
               "variants": {"default": {"prompt": None, "negative": None, "checkpoint": None, "sampler": None,
                                        "scheduler": None, "steps": None, "seed": None, "references": [],
                                        "wanted": info.get("wanted") or {}}}}
        p.write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
        made.append(cid)
    log.info("character stubs: made %d from %s", len(made), src)
    return made


def summary(cfg: dict, game: str) -> list[dict]:
    rows = []
    for i in all_ids(cfg, game):
        try:
            ch = load(cfg, game, i)
        except CharacterError as e:
            rows.append({"id": i, "error": str(e)}); continue
        for vn, v in (ch.get("variants") or {}).items():
            rows.append({"id": i, "variant": vn, "stub": bool(ch.get("_stub")), "seed": v.get("seed"),
                         "checkpoint": v.get("checkpoint"), "asymmetric": is_asymmetric(ch, vn),
                         "wanted": v.get("wanted") or {}})
    return rows
