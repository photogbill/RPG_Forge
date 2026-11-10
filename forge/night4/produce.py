"""Production (Night 4, F3): what the game is missing → one planned queue that can run for days.

    plan(cfg, game)     every wanted item that is not delivered → one job (or a reason it waits / is William's),
                        in order: the first-hour eight (Bill's house first), then by first appearance in the story;
                        kits before states; a town painted in one sitting on one family seed. Prints count, GPU hours
                        (measured s/render where the forge has history) and disk. Writes
                        games/<game>/batches/produce_plan.json (+ .md). Nothing is queued.
    queue(cfg, game)    refuses while any referenced {{block}} is a TODO placeholder or missing (naming them), or a
                        prompt still says TODO, or the disk would fall under the guard; otherwise submits the plan
                        through submit (character inheritance, --skip-done) in priority lanes.
    status(cfg)         one screen: done / running / left / ETA / failed by cause, for the produce batches.

Towns (game plan 27 §0a, William 2026-11-10): every map draft carries its town, era, state and the town's look words
as `meta`, and references {{culture.<town>}} (and {{fate.<fate>}}) — placeholders Fable fills from the look words.
A War or After state is a scene_state on its Peace base when the greybox change is under 35 %, a fresh kit on the
same seed when it is not (the plan says which). A street with enclaves is one base painting plus one scene_state per
enclave block (Little Texas and Little New York share the town's bones and differ in what was hung on them).
"""
from __future__ import annotations
import json
import logging
import shutil
import zlib
from datetime import datetime
from pathlib import Path

from .. import config as cfgmod

log = logging.getLogger("forge.produce")

LANES = {"first": 60, "story": 50, "rest": 40, "states": 35, "icons": 30, "other": 25}
FAMILY_SEED = 1001
DRAWN = "William draws it (sprite_intake.bat <sheet> <character> [variant], then approve)"
FALLBACK_SEC = {"scene_kit": 240.0, "scene_big": 900.0, "scene_state": 120.0, "scene_paint": 150.0, "render": 20.0,
                "prop": 60.0, "sleeve": 40.0, "icon": 20.0, "scene_card": 60.0, "character_set": 160.0}
FALLBACK_MB = {"scene_kit": 40.0, "scene_big": 160.0, "scene_state": 40.0, "scene_paint": 25.0, "render": 2.0,
               "prop": 3.0, "sleeve": 3.0, "icon_batch": 1.0, "scene_card": 6.0, "character_set": 20.0}
KIND_RANK = {"scene": 0, "scene_state": 1, "enclave": 2}


def town_word(s) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in str(s).lower()).strip("_")


def town_seed(town: str | None) -> int:
    return FAMILY_SEED + (zlib.crc32(str(town).encode()) % 9000 if town else 0)


# ------------------------------------------------------------------ state of every wanted item
def done_index(cfg: dict) -> dict[str, list[dict]]:
    """Finished jobs by the wanted item they were made for: `_wanted`, meta.wanted, or (for vignette batches) the
    batch file's folder + job name."""
    idx: dict[str, list[dict]] = {}
    for p in sorted((cfgmod.path_of(cfg, "jobs") / "done").glob("*.json")):
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        w = j.get("_wanted") or (j.get("meta") or {}).get("wanted")
        if w:
            idx.setdefault(w, []).append({"id": j["id"], "type": j.get("type")})
        elif j.get("batch") and j.get("name"):
            idx.setdefault(f"@{j['batch']}/{j['name']}", []).append({"id": j["id"], "type": j.get("type")})
    return idx


def item_states(cfg: dict, game: str, wanted: dict | None = None) -> dict[str, dict]:
    from .. import manifest
    from . import deliver as dl
    wanted = wanted or manifest.load_wanted(cfg, game)
    approved = manifest.load_approved(cfg, game)
    ledger = dl.live(cfg, game)
    out = {}
    for name, w in wanted["items"].items():
        led = ledger.get(name)
        if led and (not w.get("sha1") or w.get("sha1") == led.get("sha1")):
            st = "delivered"
        elif name in approved:
            st = "delivered" if not w.get("sha1") or not led else "stale"
        elif w.get("exists"):
            st = "stand-in"
        else:
            st = "missing"
        out[name] = {"state": st, "approved": approved.get(name), "delivery": led}
    return out


# ------------------------------------------------------------------ drafting
def _words(name: str) -> str:
    return name.split("/")[-1].replace("placeholder", "").replace("_", " ").strip()


def _batch_jobs(cfg: dict, game: str) -> dict[str, tuple[str, dict]]:
    """Jobs in the game's own batch files that already name a wanted item (by `_wanted`, or a vignette batch whose
    file name holds the folder: gate_law_cards.json → vignettes/gate_law/<job name>)."""
    out = {}
    d = cfgmod.path_of(cfg, "games") / game / "batches"
    for p in sorted(d.glob("*.json")):
        if p.stem.startswith(("draft", "produce", "charset")):
            continue
        try:
            b = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(b, dict) or b.get("_draft"):
            continue
        for j in b.get("jobs") or []:
            full = {**(b.get("defaults") or {}), **j, "batch": b.get("batch") or p.stem}
            if j.get("_wanted"):
                out[j["_wanted"]] = (p.stem, full)
            elif j.get("name"):
                out[f"@{p.stem}/{j['name']}"] = (p.stem, full)
    return out


def _covered(name: str, batch_jobs: dict) -> tuple[str, dict] | None:
    if name in batch_jobs:
        return batch_jobs[name]
    parts = name.split("/")
    if len(parts) >= 3:
        for key, val in batch_jobs.items():
            if key.startswith("@") and key.endswith("/" + parts[-1]) and parts[-2] in key:
                return val
    return None


def _rendered(name: str, idx: dict, cover: tuple[str, dict] | None) -> list[dict]:
    hits = list(idx.get(name) or [])
    if cover:
        hits += idx.get(f"@{cover[1].get('batch')}/{cover[1].get('name')}") or []
    return hits


def _order(cfg: dict, game: str) -> tuple[list[str], list[str]]:
    p = cfgmod.path_of(cfg, "games") / game / "produce_order.json"
    if not p.exists():
        return [], []
    d = json.loads(p.read_text(encoding="utf-8"))
    return list(d.get("first_hour") or []), list(d.get("story") or [])


def _state_choice(base_gb: str | None, state_gb: str | None) -> tuple[str, str, float | None]:
    """'state' (scene_state on the base) or 'kit' (a fresh kit on the same seed), with the measured change."""
    if not (base_gb and state_gb and Path(base_gb).exists() and Path(state_gb).exists()):
        return "wait", "both greyboxes are needed to measure the change", None
    from PIL import Image
    import numpy as np
    from ..ops import state_mask as sm
    a, b = Image.open(base_gb).convert("RGB"), Image.open(state_gb).convert("RGB")
    if a.size != b.size:
        return "kit", f"greyboxes differ in size ({a.size} vs {b.size})", None
    share = float((np.asarray(sm.changed(a, b)) > 0).mean())
    if share <= sm.MAX_SHARE:
        return "state", f"{share:.0%} of the frame changed — under the {sm.MAX_SHARE:.0%} limit: a scene_state on the base", share
    return "kit", f"{share:.0%} changed — over {sm.MAX_SHARE:.0%}: a fresh kit on the town's seed", share


def _enclave_mask(cfg: dict, game: str, mid: str, enc: dict, size) -> str | None:
    from PIL import Image, ImageDraw
    blk = enc.get("block")
    if not (blk and size):
        return None
    d = cfgmod.path_of(cfg, "games") / game / "plan_masks"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{mid}__{town_word(enc.get('from') or enc.get('name') or 'enclave')}.png"
    im = Image.new("L", (int(size[0]), int(size[1])), 0)
    ImageDraw.Draw(im).rectangle([int(v) for v in blk], fill=255)
    im.save(p)
    return str(p.relative_to(cfgmod.path_of(cfg, "games").parent)) if cfgmod.ROOT in p.parents else str(p)


PLACEHOLDER_TEXT = {"culture": "TODO the culture of {w} (from its four look words: {ctx})",
                    "fate": "TODO what '{w}' did to a place", "enclave": "TODO what settlers from {w} hung on the street",
                    "place": "TODO the picture of {ctx}", "state": "TODO only what changed in {ctx}",
                    "sleeve": "TODO cover art from the lyrics of {ctx}", "era": "TODO the {w} era", "skin": "TODO skin: {w}",
                    "layout": "TODO the layout words of the {w} family", "icon": "TODO icon family: {w}"}


def _ensure_blocks(cfg: dict, game: str, wanted: dict[str, str]) -> list[str]:
    """Add a TODO placeholder (Fable's to write) for every block the plan references that the library lacks.
    `wanted`: {block name: context for the placeholder text (the game's own words)}."""
    from .. import prompts as pl
    lib = pl.load(cfg, game)
    new = [n for n in wanted if n not in lib["blocks"]]
    if not new:
        return []
    p = pl.folder(cfg, game) / "night4.json"
    d = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"blocks": {}}
    for n in new:
        shelf, _, what = n.partition(".")
        d.setdefault("blocks", {})[n] = PLACEHOLDER_TEXT.get(shelf, "TODO {ctx}").format(w=what, ctx=wanted[n] or what)[:400]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    return new


def _own_words(jobs: list[dict], items: dict) -> dict[str, str]:
    """Turn brief's literal TODO prompt text into per-item blocks (so Fable's words live in the library and survive
    the next plan), and collect every block the plan references → {block: context}."""
    from .. import prompts as pl
    need: dict[str, str] = {}
    for j in jobs:
        w = items.get((j.get("meta") or {}).get("wanted") if isinstance((j.get("meta") or {}).get("wanted"), str) else "", {}) or {}
        mid = town_word(j.get("name") or "")
        ctx = f"{w.get('name_in_game') or j.get('_name_in_game') or j.get('name')}: {(j.get('_notes') or w.get('notes') or '')[:240]}".strip(": ")
        t = str(j.get("prompt") or "")
        for lit, block in ((", TODO: the picture in plain words", ", {{place.%s}}" % mid),
                           ("TODO: the picture in plain words", "{{place.%s}}" % mid),
                           ("TODO: only what changed", "{{state.%s}}" % mid),
                           ("TODO: the moment in plain words", "{{place.%s}}" % mid)):
            if lit in t:
                t = t.replace(lit, block)
        if "TODO: from the lyrics of" in t:
            t = t[:t.index("TODO: from the lyrics of")] + "{{sleeve.%s}}" % mid
            ctx = f"'{j.get('title')}' ({j.get('artist') or ''})"
        j["prompt"] = t
        for f in ("prompt", "negative"):
            for ref in pl.refs(j.get(f)):
                if ref == "character":                    # the registry slot, filled at submit — not a library block
                    continue
                need.setdefault(ref, ctx if ref.split(".")[0] in ("place", "state", "sleeve") else
                                (w.get("look") or "") if ref.startswith("culture.") else "")
    return need


def plan(cfg: dict, game: str = "turing_accords", refresh: bool = True, generate_sprites: bool = False) -> dict:
    from .. import manifest, brief_missing
    from . import characters as chm
    B = brief_missing.draft(cfg, game, refresh)            # refreshes wanted.json when the game folder is readable
    notes = list(B["notes"])
    wanted = manifest.load_wanted(cfg, game)
    items = wanted["items"]
    states = item_states(cfg, game, wanted)
    idx = done_index(cfg)
    covers = _batch_jobs(cfg, game)
    first, story = _order(cfg, game)
    rank = {m: i for i, m in enumerate(first)}
    rank.update({m: 100 + i for i, m in enumerate(story) if m not in rank})
    jobs, waiting, by_hand, rendered = [], [], [], []
    map_jobs = {j["name"]: j for j in B["draft"]["jobs"]}
    held = {r["map"]: r for r in B["table"] if r.get("type") == "-"}

    # ---------------------------------------------------------------- maps (towns, states, enclaves)
    for name, w in sorted(items.items()):
        if w.get("kind") != "scene" or w.get("set_of"):
            continue
        mid = name.split("/", 1)[1]
        if states[name]["state"] == "delivered":
            continue
        hits = _rendered(name, idx, None)
        town, era, mstate, fate = w.get("town"), w.get("era"), w.get("map_state"), w.get("fate")
        meta = {"wanted": name, "town": town, "era": era, "state": mstate, "look": w.get("look"), "fate": fate}
        r = rank.get(mid, 1000)
        lane = "first" if mid in first else ("story" if mid in rank else "rest")
        if mid in held:
            waiting.append({"name": name, "why": held[mid]["why"], "waits_on": held[mid]["waits_on"], "town": town})
            continue
        j = dict(map_jobs.get(mid) or {})
        if not j:
            continue
        refs = []
        if town:
            refs.append("{{culture.%s}}" % town_word(town))
        if fate:
            refs.append("{{fate.%s}}" % town_word(fate))
        if refs:
            j["prompt"] = ", ".join([str(j.get("prompt") or "")] + refs).strip(", ")
        if town and "seed" not in j:
            j["seed"] = town_seed(town)                     # a town in one sitting on one family seed
        why = ""
        if j.get("type") == "scene_state":
            base = items.get(f"scenes/{w.get('state_of')}") or {}
            choice, why, share = _state_choice(j.get("greybox_base"), j.get("greybox_state"))
            if choice == "kit":
                j = {"type": "scene_kit", "name": mid, "target": w.get("target_size"), "prompt": j["prompt"],
                     "init": j.get("greybox_state"), "denoise": 0.55, "control": {"type": "canny", "strength": 0.6},
                     "seed": town_seed(town or base.get("town"))}
            lane = "states"
        j["meta"] = {**(j.get("meta") or {}), **{k: v for k, v in meta.items() if v}}
        j["batch"] = f"produce/{lane}"
        j["priority"] = LANES[lane]
        j["_order"] = [r, town or "", KIND_RANK.get("scene_state" if j["type"] == "scene_state" else "scene", 0), mid]
        j["_why"] = why or "missing" if states[name]["state"] == "missing" else (why or states[name]["state"])
        if hits:
            rendered.append({"name": name, "jobs": [h["id"] for h in hits[-3:]], "type": j["type"]})
        jobs.append(j)
        # enclaves: per-block repaints of this map once its base is approved
        for enc in w.get("enclaves") or []:
            frm = town_word(enc.get("from") or enc.get("name") or "enclave")
            base_ok = name in manifest.load_approved(cfg, game)
            ent = {"name": f"{name}#{frm}", "town": town, "enclave": enc.get("name") or frm}
            if not base_ok:
                waiting.append({**ent, "why": "an enclave block of " + mid, "waits_on": f"{name} to be approved"})
                continue
            mask = _enclave_mask(cfg, game, mid, enc, w.get("target_size"))
            ap = manifest.load_approved(cfg, game)[name]
            jobs.append({"type": "scene_state", "name": f"{mid}__{frm}", "base": f"out/{ap['job_id']}", "mask": mask,
                         "prompt": "{{enclave.%s}}, {{culture.%s}}" % (frm, town_word(town or mid)),
                         "seed": town_seed(town), "batch": "produce/states", "priority": LANES["states"],
                         "meta": {**{k: v for k, v in meta.items() if v}, "enclave": enc.get("name") or frm},
                         "_order": [r, town or "", KIND_RANK["enclave"], mid], "_why": "an enclave block"})

    # ---------------------------------------------------------------- characters: sprites and portraits
    reg = {}
    for cid in chm.all_ids(cfg, game):
        try:
            ch = chm.load(cfg, game, cid)
        except chm.CharacterError:
            continue
        for vn, v in (ch.get("variants") or {}).items():
            for k, val in (v.get("wanted") or {}).items():
                if isinstance(val, str) and not k.startswith("_"):
                    reg[val] = (cid, vn, v, k)
    icon_items: dict[str, list[dict]] = {}
    for name, w in sorted(items.items()):
        k = w.get("kind")
        if k in ("scene", "scene_slot") or states[name]["state"] == "delivered":
            continue
        hits = _rendered(name, idx, None)
        if name.startswith("placeholder/") and k == "sleeve":
            by_hand.append({"name": name, "what": "the generic stand-in sleeve — not art to paint"}); continue
        if k == "sprite_sheet":
            who = reg.get(name)
            if generate_sprites and who and who[2].get("prompt"):
                jobs.append({"type": "character_set", "character": who[0], "variant": who[1], "parts": ["turnaround"],
                             "name": f"{who[0]}_{who[1]}_sheet", "batch": "produce/other", "priority": LANES["other"],
                             "meta": {"wanted": name}, "_order": [2000, "", 0, name], "_why": "generator road (F2)"})
            else:
                by_hand.append({"name": name, "what": DRAWN + (f" — registry: {who[0]}/{who[1]}" if who else "")})
            continue
        if k == "portrait":
            who = reg.get(name)
            if who and who[2].get("prompt"):
                jobs.append({"type": "render", "character": who[0], "variant": who[1], "name": f"portrait_{who[0]}_{who[1]}",
                             "prompt": "{{character}}, {{pose.portrait}}, {{mood.neutral}}", "size": [896, 1152],
                             "batch": "produce/other", "priority": LANES["other"], "meta": {"wanted": name},
                             "_order": [2100, "", 0, name], "_why": "portrait from the registry (deliver --fit crops it)"})
            else:
                waiting.append({"name": name, "why": "portrait", "waits_on": "its character's registry entry "
                                f"(characters.bat show {name.split('portrait_')[-1]})"})
            continue
        if k == "icon":
            cat = town_word(w.get("category") or "misc") or "misc"
            icon_items.setdefault(cat, []).append({"id": name.split("/", 1)[1], "name": w.get("name_in_game") or _words(name),
                                                   "description": w.get("description") or "", "wanted": name})
            continue
        cover = _covered(name, covers)
        hits = _rendered(name, idx, cover)
        if hits:
            rendered.append({"name": name, "jobs": [h["id"] for h in hits[-3:]], "type": hits[-1].get("type")})
            continue
        if cover:
            j = {k2: v for k2, v in cover[1].items()}
            j.update({"batch": "produce/other", "priority": LANES["other"], "meta": {"wanted": name, "from_batch": cover[0]},
                      "_order": [3000, "", 0, name], "_why": f"the job in batches/{cover[0]}.json"})
            jobs.append(j)
            continue
        tgt = w.get("target_size") or [512, 512]
        base = {"batch": "produce/other", "priority": LANES["other"], "meta": {"wanted": name},
                "_order": [3000, "", 0, name], "_why": w.get("state") or states[name]["state"]}
        words = (w.get("name_in_game") or _words(name)) + (f", {w['description']}" if w.get("description") else "") + \
                (f", {w['notes']}" if w.get("notes") and k not in ("sprite_sheet", "tileset") else "")
        if k == "prop":
            jobs.append({**base, "type": "prop", "name": name.split("/")[-1], "prompt": f"{{{{style.prop}}}}, {words}",
                         "target_h": int(tgt[1])})
        elif k == "sleeve":
            jobs.append({**base, "type": "sleeve", "name": name.split("/")[-1], "title": w.get("title") or _words(name),
                         "artist": w.get("artist") or "", "prompt": "{{style.sleeve}}, TODO: from the lyrics of '%s'"
                         % (w.get("title") or _words(name))})
        elif k == "vignette":
            jobs.append({**base, "type": "scene_paint", "name": name.split("/")[-1], "target": tgt,
                         "prompt": f"{{{{style.vignette}}}}, {words or 'TODO: the moment in plain words'}"})
        elif k == "enemy":
            jobs.append({**base, "type": "prop", "name": name.split("/")[-1], "prompt": f"{{{{style.enemy}}}}, {words}",
                         "target_h": int(tgt[1]) if tgt else 216})
        elif k == "ui":
            jobs.append({**base, "type": "render", "name": name.split("/")[-1], "prompt": f"{{{{ui.house}}}}, {words}",
                         "size": [1024, 1024], "_then": "nine_slice / button_states on the result (G12)"})
        else:
            by_hand.append({"name": name, "what": f"{k}: by hand ({w.get('notes') or 'no draft for this kind'})"})
    for cat, its in sorted(icon_items.items()):
        jobs.append({"type": "icon_batch", "name": f"icons_{cat}", "items": its, "category": cat,
                     "prompt": "{{icon.house}}, {{icon.%s}}, {name}: {description}" % cat,
                     "seeds": {cat: FAMILY_SEED + zlib.crc32(cat.encode()) % 9000},
                     "batch": "produce/icons", "priority": LANES["icons"], "meta": {"wanted": [i["wanted"] for i in its]},
                     "_order": [4000, cat, 0, cat], "_why": f"{len(its)} icon(s), one hand per category"})
    new_blocks = _ensure_blocks(cfg, game, _own_words(jobs, items))
    bumps_p = cfgmod.path_of(cfg, "games") / game / "priority_bumps.json"
    bumps = json.loads(bumps_p.read_text(encoding="utf-8")) if bumps_p.exists() else {}
    for j in jobs:
        w = (j.get("meta") or {}).get("wanted")
        if isinstance(w, str) and w in bumps:
            j["priority"] = int(j.get("priority") or 0) + 10 * int(bumps[w]["bump"])
            j["_order"] = [-1] + list(j["_order"][1:])
            j["_why"] = f"called out in playtest ({bumps[w]['bump']}×) — " + str(j.get("_why") or "")
    jobs.sort(key=lambda j: tuple(j["_order"]))
    est = estimate(cfg, jobs)
    out = {"batch": "produce", "_draft": True, "_plan": True, "_made": datetime.now().isoformat(timespec="seconds"),
           "_review": "Made by produce plan. Do not submit this file directly — produce.bat queue checks every block "
                      "and the disk first. Edit any job freely; rerun plan to rebuild it from the game.",
           "_notes": notes, "_estimate": est, "_waiting": waiting, "_by_hand": by_hand, "_rendered": rendered,
           "_new_blocks": new_blocks, "defaults": {"game": game}, "jobs": jobs}
    p = cfgmod.path_of(cfg, "games") / game / "batches" / "produce_plan.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    (p.with_suffix(".md")).write_text(to_markdown(out), encoding="utf-8", newline="\n")
    log.info("produce plan: %d job(s), %d waiting, %d by hand, %d rendered awaiting approval, %.1f GPU h",
             len(jobs), len(waiting), len(by_hand), len(rendered), est["gpu_hours"])
    return {**out, "_file": str(p)}


# ------------------------------------------------------------------ estimates
def _dir_mb(p: Path) -> float:
    tot = 0
    for f in p.rglob("*"):
        try:
            if f.is_file():
                tot += f.stat().st_size
        except OSError:
            pass
    return tot / 1e6


def measured(cfg: dict, sample: int = 12) -> tuple[dict, dict, dict]:
    """(seconds per job type, MB per job type, how many runs each figure rests on) from finished jobs."""
    from .. import eta
    hist = eta.history(cfg, 1500)
    secs, _ = eta.per_type(hist, 30)
    counts = {}
    for h in hist:
        counts[h["type"]] = counts.get(h["type"], 0) + 1
    mb: dict[str, list[float]] = {}
    out_root = cfgmod.path_of(cfg, "out")
    done = sorted((cfgmod.path_of(cfg, "jobs") / "done").glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in done[:600]:
        try:
            t = json.loads(p.read_text(encoding="utf-8")).get("type")
        except (OSError, ValueError):
            continue
        if len(mb.setdefault(t, [])) < sample and (out_root / p.stem).exists():
            mb[t].append(_dir_mb(out_root / p.stem))
    import statistics
    return secs, {t: statistics.median(v) for t, v in mb.items() if v}, counts


def estimate(cfg: dict, jobs: list[dict]) -> dict:
    secs, mb, counts = measured(cfg)
    tot_s, tot_mb, basis = 0.0, 0.0, {}
    for j in jobs:
        t = j["type"]
        n = len(j.get("items") or []) if t == "icon_batch" else (len(j.get("renders") or j.get("parts") or [1]) if t == "character_set" else 1)
        per_t = "icon" if t == "icon_batch" else t
        s = secs.get(per_t) or FALLBACK_SEC.get(per_t, 60.0)
        m = mb.get(t) or FALLBACK_MB.get(t, 10.0) * (n if t == "icon_batch" else 1)
        if t == "scene_kit" and j.get("target") and secs.get(t) is None:
            s *= max(1.0, (j["target"][0] * j["target"][1]) / (1920 * 1080))
        tot_s += s * n
        tot_mb += m
        basis[t] = f"{s:.0f} s/{'icon' if t == 'icon_batch' else 'job'} " + (f"(measured, {counts.get(per_t)} runs)" if secs.get(per_t) else "(estimated)")
    from .guard import free_gb
    free = free_gb(cfg)
    return {"jobs": len(jobs), "gpu_hours": round(tot_s / 3600, 1), "disk_gb": round(tot_mb / 1000, 1),
            "free_gb": round(free, 1), "basis": basis}


def to_markdown(p: dict) -> str:
    e = p["_estimate"]
    L = [f"# Production plan — {p['_made']}", "",
         f"**{e['jobs']} job(s)** · about **{e['gpu_hours']} GPU hours** · about **{e['disk_gb']} GB** of output "
         f"(free now: {e['free_gb']} GB)", ""]
    L += [f"> {n}" for n in p.get("_notes") or []]
    L += ["", "| # | lane | type | name | town | why |", "|---|---|---|---|---|---|"]
    for i, j in enumerate(p["jobs"], 1):
        m = j.get("meta") or {}
        L.append(f"| {i} | {j['batch'].split('/')[-1]} | {j['type']} | {j.get('name')} | {m.get('town') or ''} | {j.get('_why', '')} |")
    if p.get("_rendered"):
        L += ["", "## Rendered already — approve one (not queued again)", ""]
        L += [f"- `{r['name']}` ← {', '.join(r['jobs'])}" for r in p["_rendered"]]
    if p.get("_waiting"):
        L += ["", "## Waiting", ""]
        L += [f"- `{w['name']}` — {w['why']}; waits on {w['waits_on']}" for w in p["_waiting"]]
    if p.get("_by_hand"):
        L += ["", "## William's (by hand)", ""]
        L += [f"- `{b['name']}` — {b['what']}" for b in p["_by_hand"]]
    L += ["", "## Basis of the estimate", ""] + [f"- {t}: {b}" for t, b in e["basis"].items()]
    if p.get("_new_blocks"):
        L += ["", f"New placeholder blocks added to prompts/night4.json: {', '.join(p['_new_blocks'])}"]
    return "\n".join(L) + "\n"


# ------------------------------------------------------------------ queue
def blockers(cfg: dict, game: str, jobs: list[dict]) -> dict[str, list[str]]:
    """{problem: [job names]} — unknown blocks, TODO blocks, prompts that still say TODO."""
    from .. import prompts as pl
    from . import characters as chm
    lib = pl.load(cfg, game)
    out: dict[str, list[str]] = {}

    def look(text, who):
        for ref in pl.refs(text):
            if ref not in lib["blocks"]:
                out.setdefault(f"{{{{{ref}}}}} is not in the library", []).append(who)
            elif str(lib["blocks"][ref]).strip().upper().startswith("TODO"):
                out.setdefault(f"{{{{{ref}}}}} is a TODO placeholder", []).append(who)
            else:
                look(lib["blocks"][ref], who)
        if "TODO" in pl.REF.sub("", str(text or "")):
            out.setdefault("the prompt itself still says TODO", []).append(who)

    for j in jobs:
        who = str(j.get("name") or j.get("type"))
        texts = [j.get(f) for f in ("prompt", "negative", "style_prefix")]
        if j.get("character"):
            try:
                if j.get("type") == "character_set":
                    from . import charset
                    charset.expand_set(cfg, {**j, "game": game})
                else:
                    r = chm.resolve(cfg, {**j, "game": game})
                    texts = [r.get(f) for f in ("prompt", "negative", "style_prefix")]
            except Exception as e:  # noqa: BLE001
                out.setdefault(str(e), []).append(who)
                continue
        for t in texts:
            if t:
                look(t, who)
    return out


def queue(cfg: dict, game: str = "turing_accords", lanes: list[str] | None = None, kinds: list[str] | None = None,
          dry: bool = False, force_disk: bool = False) -> dict:
    p = cfgmod.path_of(cfg, "games") / game / "batches" / "produce_plan.json"
    if not p.exists():
        raise FileNotFoundError("no plan yet — run produce.bat plan first")
    data = json.loads(p.read_text(encoding="utf-8"))
    jobs = [j for j in data["jobs"] if (not lanes or j["batch"].split("/")[-1] in lanes) and (not kinds or j["type"] in kinds)]
    if not jobs:
        return {"queued": 0, "refused": {}, "note": "nothing in the plan matches that selection"}
    bad = blockers(cfg, game, jobs)
    if bad:
        return {"queued": 0, "refused": bad, "jobs": len(jobs)}
    est = estimate(cfg, jobs)
    guard = float(cfg.get("disk_guard_gb", 40))
    if not force_disk and est["free_gb"] - est["disk_gb"] < guard:
        return {"queued": 0, "refused": {f"disk: {est['disk_gb']} GB needed, {est['free_gb']} GB free, guard {guard:.0f} GB "
                                         "(free space first, or --force-disk)": []}, "jobs": len(jobs)}
    clean = [{k: v for k, v in j.items() if not k.startswith("_") or k in ("_wanted", "_notes")} for j in jobs]
    batch = {"batch": "produce", "game": game, "defaults": {"game": game}, "jobs": clean}
    if dry:
        return {"queued": 0, "dry": True, "would_queue": len(clean), "estimate": est}
    inc = Path(cfg.get("incoming_dir") or (cfgmod.ROOT / "_incoming")) / f"produce_{datetime.now():%Y%m%d-%H%M%S}.json"
    inc.parent.mkdir(parents=True, exist_ok=True)
    inc.write_text(json.dumps(batch, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    from ..cli_night4 import cmd_submit
    rc = cmd_submit(cfg, [str(inc), "--skip-done"])
    return {"queued": len(clean) if rc == 0 else 0, "rc": rc, "file": str(inc), "estimate": est}


# ------------------------------------------------------------------ status
def status(cfg: dict, prefix: str = "produce") -> dict:
    from .. import eta
    from ..night_report import cause
    jobs_dir = cfgmod.path_of(cfg, "jobs")
    counts, fails, pend = {}, {}, []
    for sub in ("done", "running", "pending", "paused", "failed"):
        n = 0
        for f in (jobs_dir / sub).glob("*.json"):
            try:
                j = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not str(j.get("batch", "")).startswith(prefix):
                continue
            n += 1
            if sub == "failed":
                c = cause(j.get("error"))
                fails[c] = fails.get(c, 0) + 1
            if sub in ("pending", "paused"):
                pend.append(j)
        counts[sub] = n
    secs, _ = eta.per_type(eta.history(cfg, 800))
    left_s = sum((secs.get("icon" if j.get("type") == "icon_batch" else j.get("type")) or FALLBACK_SEC.get(j.get("type"), 60.0))
                 * (len(j.get("items") or []) if j.get("type") == "icon_batch" else 1) for j in pend)
    from . import guard as gd
    return {"counts": counts, "failed_by_cause": fails, "eta_hours": round(left_s / 3600, 1),
            "free_gb": round(gd.free_gb(cfg), 1), "guard": gd.read(cfg)}
