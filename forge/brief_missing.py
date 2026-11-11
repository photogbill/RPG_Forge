""""Paint what the game is missing" (Night 3, G10) and room families (G11) — one draft for everything.

    python -m forge brief missing [--game <id>] [--no-refresh]      (paint_missing.bat)

Refresh wanted.json from the game (read-only; if the game folder is not readable, the last wanted.json is used and the
report says so), then for every painted-map slot with no approved art write ONE draft job, choosing the type by the
facts:
    map ≤ one frame (the game's scene_size, 1920×1080)        → scene_kit
    map larger than one frame                                  → scene_kit with big: true (scene_big paints it — small,
                                                                 climbed ≤ 2× per step — then the companions; wiring day W4)
    a state of a map whose base painting is approved           → scene_state (mask from the two greyboxes)
    a state whose base is not approved yet                     → held back, listed as "waiting for its base"
Each draft carries the map's notes (as `_notes`), its skin word and era as prompt-library references
(`{{skin.<word>}}`, `{{era.<word>}}`), its greybox as the control image and the map's pixel size.

Room families (G11): maps that share a layout — the same `template`, or an identical greybox — are drafted as one
family: one shared control image and seed, the layout words written once (`{{layout.<template>}}`), only the skin and
era references differing per member. `review --family <template>` puts the members side by side once rendered.

Fields read from a map (data/maps/<id>.json) or its wanted.json entry, all optional: `template` (or `layout_template`),
`skin`, `era`, `state_of` (or `base_map`) — the map this one is a state of. Drafts only: nothing is submitted.
"""
from __future__ import annotations
import hashlib, json
from datetime import datetime
from pathlib import Path

from . import config as cfgmod

FAMILY_SEED = 1001


def _read_json(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    except (OSError, ValueError):
        return None


def _hash(p: Path) -> str | None:
    try:
        return hashlib.sha1(p.read_bytes()).hexdigest()[:16] if p.exists() else None
    except OSError:
        return None


def _f(*vals):
    for v in vals:
        if v not in (None, "", []):
            return v
    return None


def facts(cfg: dict, game: str, refresh: bool = True) -> dict:
    """wanted.json (refreshed if the game folder is readable) + each map's own fields."""
    from . import manifest
    gcfg = cfgmod.game_config(cfg, game)
    root = Path(gcfg.get("game_root") or "")
    notes = []
    readable = (root / "project" / "data" / "maps").exists()
    if refresh and readable:
        try:
            manifest.refresh_wanted(cfg, game)
        except Exception as e:  # noqa: BLE001
            notes.append(f"could not refresh wanted.json ({e}) — used the last one")
    elif refresh:
        notes.append(f"game folder not readable here ({root}) — worked from the last wanted.json")
    wanted = manifest.load_wanted(cfg, game)
    approved = manifest.load_approved(cfg, game)
    maps = {}
    for name, w in wanted["items"].items():
        if w.get("kind") != "scene" or w.get("set_of"):
            continue
        mid = name.split("/", 1)[1]
        m = _read_json(root / "project" / "data" / "maps" / f"{mid}.json") if readable else None
        m = m or {}
        gb = w.get("greybox")
        gbp = (root / gb) if gb else None
        maps[mid] = {
            "id": mid, "wanted": name, "target": w.get("target_size"), "notes": _f(m.get("notes"), w.get("notes")) or "",
            "name": _f(m.get("name"), w.get("name_in_game")) or mid,
            "template": _f(m.get("template"), m.get("layout_template"), w.get("template")),
            "skin": _f(m.get("skin"), w.get("skin")), "era": _f(m.get("era"), w.get("era")),
            "state_of": _f(m.get("state_of"), m.get("base_map"), w.get("state_of")),
            "greybox": str(gbp) if gbp is not None else None, "greybox_hash": _hash(gbp) if gbp is not None else None,
            "approved": name in approved, "approved_job": (approved.get(name) or {}).get("job_id"),
        }
    frame = tuple(gcfg.get("scene_size") or (1920, 1080))
    return {"maps": maps, "notes": notes, "frame": frame, "readable": readable, "wanted_exported": wanted.get("exported")}


def _word(s) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in str(s).lower()).strip("_")


def _refs(m: dict, family: bool) -> list[str]:
    r = ["{{style.house}}"]
    if family and m.get("template"):
        r.append("{{layout.%s}}" % _word(m["template"]))
    if m.get("skin"):
        r.append("{{skin.%s}}" % _word(m["skin"]))
    if m.get("era"):
        r.append("{{era.%s}}" % _word(m["era"]))
    return r


def families(maps: dict) -> dict[str, list[str]]:
    """{family key: [map ids]} for groups of two or more sharing a template or an identical greybox."""
    groups: dict[str, list[str]] = {}
    for mid, m in maps.items():
        if m.get("state_of"):
            continue
        key = f"template:{m['template']}" if m.get("template") else (f"greybox:{m['greybox_hash']}" if m.get("greybox_hash") else None)
        if key:
            groups.setdefault(key, []).append(mid)
    return {k: sorted(v) for k, v in groups.items() if len(v) > 1}


def draft(cfg: dict, game: str, refresh: bool = True) -> dict:
    F = facts(cfg, game, refresh)
    maps, frame = F["maps"], F["frame"]
    fams = families(maps)
    fam_of = {mid: k for k, ids in fams.items() for mid in ids}
    jobs, table = [], []
    for mid, m in sorted(maps.items()):
        if m["approved"]:
            continue
        tw, th = (m["target"] or [frame[0], frame[1]])
        base = maps.get(m["state_of"]) if m.get("state_of") else None
        fk = fam_of.get(mid)
        row = {"map": mid, "size": f"{tw}x{th}", "family": fk.split(":", 1)[1] if fk else None}
        if m.get("state_of"):
            if base is None or not base["approved"]:
                table.append({**row, "type": "-", "why": f"a state of {m['state_of']}", "waits_on": f"{m['state_of']} to be approved"})
                continue
            if not (m.get("greybox") and base.get("greybox")):
                table.append({**row, "type": "-", "why": f"a state of {m['state_of']}",
                              "waits_on": "greybox renders of both maps (the mask is what changed between them)"})
                continue
            job = {"type": "scene_state", "name": mid, "base": f"out/{base['approved_job']}",
                   "greybox_base": base["greybox"], "greybox_state": m["greybox"],
                   "prompt": ", ".join(_refs(m, False)[1:] + ["TODO: only what changed"]).strip(", "),
                   "seed": FAMILY_SEED}
            why = f"a state of {m['state_of']}, whose painting is approved"
        else:
            big = tw > frame[0] or th > frame[1]
            refs = _refs(m, bool(fk))
            job = {"type": "scene_kit", "name": mid, "target": [tw, th], **({"big": True, "depth_resolution": 2048} if big else {}),
                   "prompt": ", ".join(refs) + ("" if fk else ", TODO: the picture in plain words")}
            if m.get("greybox"):
                job["init"] = m["greybox"]
                if not big:
                    job.update({"denoise": 0.55, "control": {"type": "canny", "strength": 0.6}})
            if fk:
                lead = maps[fams[fk][0]]
                if lead.get("greybox"):
                    job["init"] = lead["greybox"]                 # one shared control image for the whole family
                job["seed"] = FAMILY_SEED
                job["meta"] = {"family": fk.split(":", 1)[1], "member": mid, "skin": m.get("skin"), "era": m.get("era")}
            why = (f"{tw}x{th} is larger than one frame ({frame[0]}x{frame[1]})" if big else "fits one frame")
            if fk:
                why += f"; family {fk.split(':', 1)[1]} ({len(fams[fk])} members)"
        job.update({"_notes": m["notes"], "_wanted": m["wanted"], "_name_in_game": m["name"]})
        jobs.append(job)
        table.append({**row, "type": job["type"], "big": bool(job.get("big")), "why": why, "waits_on": "" if m.get("greybox") or job["type"] == "scene_state"
                      else "nothing (no greybox yet: painted from the prompt — re-run after the game renders one)"})
    out = {"batch": "draft_missing", "_draft": True, "_made": datetime.now().isoformat(timespec="seconds"),
           "_review": "Every {{block}} must exist in games/<game>/prompts/ before this submits (submit refuses unknown or "
                      "TODO blocks). Write the TODO picture words, delete _draft, then submit.",
           "_facts": {"notes": F["notes"], "wanted_exported": F["wanted_exported"], "frame": list(frame),
                      "families": {k.split(':', 1)[1]: v for k, v in fams.items()}},
           "defaults": {"game": game}, "approved": [], "jobs": jobs}
    return {"draft": out, "table": table, "notes": F["notes"]}


def write(cfg: dict, game: str, refresh: bool = True) -> tuple[Path, Path, dict]:
    r = draft(cfg, game, refresh)
    p = cfgmod.path_of(cfg, "games") / game / "batches" / "draft_missing.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(r["draft"], indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    L = ["# What the game is missing", "", *[f"> {n}" for n in r["notes"]], "",
         "| map | size | job type | why | waits on |", "|---|---|---|---|---|"]
    for t in r["table"]:
        L.append(f"| {t['map']} | {t['size']} | {t['type']}{' (big)' if t.get('big') else ''} | {t['why']} | {t['waits_on']} |")
    rep = cfgmod.path_of(cfg, "out") / "reports" / f"missing_{datetime.now():%Y-%m-%d}.md"
    rep.parent.mkdir(parents=True, exist_ok=True)
    rep.write_text("\n".join(L) + "\n", encoding="utf-8")
    return p, rep, r
