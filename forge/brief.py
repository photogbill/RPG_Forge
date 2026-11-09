"""Batch drafts from the game's own data (roadmap F10), for Claude or Fable to edit rather than write from zero.

    python -m forge brief maps    [--game turing_accords]   one painted-background job per map (data/maps/*.json)
    python -m forge brief sleeves [--game turing_accords]   one sleeve job per record (data/records.json)
    python -m forge brief icons   [--game turing_accords]   one icon job per item (data/items.json)

Drafts are written to games/<game>/batches/draft_<what>.json and are marked `"_draft": true` — the prompts are the
game's own notes put into words, not art direction. Edit them (and delete `_draft`) before submitting. A map
whose greybox render exists (assets/scenes/<id>_greybox.png, from the game's greybox_to_painted.py) becomes a
`scene_kit` repainting it with a canny ControlNet so the layout holds; otherwise a `scene_kit` painted from the prompt at the
map's ×3 size. Either way the job makes the six-file scene set (painting, _n, _e, _back, _over, _depth).
"""
from __future__ import annotations
import json, re
from datetime import datetime
from pathlib import Path

from . import config as cfgmod

TIME_WORDS = {"day": "daylight", "dusk": "dusk light", "night": "night, artificial light", "interior": "interior light",
              "dawn": "dawn light"}


def _clean(notes: str) -> str:
    """Drop the bible's section references ('05.7 / 15.2 —') and parentheticals that cite docs."""
    s = re.sub(r"^\s*[\d.]+(\s*/\s*[\d.]+)*\s*[—-]\s*", "", notes or "")
    s = re.sub(r"\((?:[^()]*\b\d{2}\.\d[^()]*)\)", "", s)
    return re.sub(r"\s+", " ", s).strip(" .")


def game_root(cfg: dict, game: str) -> Path:
    r = cfgmod.game_config(cfg, game).get("game_root")
    if not r:
        raise ValueError(f"games/{game}/forge.game.json has no game_root")
    return Path(r)


def maps(cfg: dict, game: str) -> dict:
    root = game_root(cfg, game)
    mdir = root / "project" / "data" / "maps"
    jobs = []
    for m in sorted(mdir.glob("*.json")):
        if m.name.endswith(".painted.json"):
            continue
        d = json.loads(m.read_text(encoding="utf-8"))
        mid = d.get("id") or m.stem
        rows = d.get("rows") or []
        ts = int(d.get("tile_size", 32))
        target = [max((len(r) for r in rows), default=20) * ts * 3, max(1, len(rows)) * ts * 3]
        time = (d.get("lighting") or {}).get("time")
        words = [f"{d.get('name') or mid}", _clean(d.get("notes", ""))]
        if time:
            words.append(TIME_WORDS.get(time, time))
        prompt = ", ".join(w for w in words if w)
        greybox = root / "project" / "assets" / "scenes" / f"{mid}_greybox.png"
        job = {"name": mid, "prompt": prompt, "target": target, "camera": "high top-down view matching the map layout",
               "_source": f"data/maps/{m.name}", "_wanted": f"scenes/{mid}"}
        # N3: a map is painted as a scene_kit — the painting plus normals, glow, parallax planes and depth, one job
        if greybox.exists():
            job.update({"type": "scene_kit", "init": str(greybox), "denoise": 0.55,
                        "control": {"type": "canny", "strength": 0.6},
                        "_note": "sweep denoise with a plain repaint first if the layout drifts; a scene_kit makes one set"})
        else:
            job.update({"type": "scene_kit",
                        "_note": "no greybox yet — run the game's tools/greybox_to_painted.py, then re-run brief to get a layout-locked kit"})
        job["prompt"] = f"{job['prompt']}, {job.pop('camera')}"
        jobs.append(job)
    return {"batch": "draft_maps", "_draft": True, "_made": datetime.now().isoformat(timespec="seconds"),
            "_review": "prompts are the map notes put into words — edit each before submitting; delete _draft when done",
            "defaults": {"game": game}, "approved": [], "jobs": jobs}


def sleeves(cfg: dict, game: str) -> dict:
    recs = json.loads((game_root(cfg, game) / "project" / "data" / "records.json").read_text(encoding="utf-8"))
    jobs = []
    for rid, r in recs.items():
        if not isinstance(r, dict) or not r.get("sleeve"):
            continue
        jobs.append({"name": rid, "title": r.get("title", rid), "artist": r.get("singer", ""),
                     "label": f"Album {r.get('album_no', '')}".strip(), "prompt": f"cover art for the song '{r.get('title', rid)}'",
                     "_wanted": f"sleeves/{rid}", "_album": r.get("album"), "_era": r.get("era"),
                     "_lyrics": r.get("lyrics_path")})
    return {"batch": "draft_sleeves", "_draft": True, "_made": datetime.now().isoformat(timespec="seconds"),
            "_review": "every prompt is a placeholder — write each from the song's lyrics (the canon) before submitting",
            "defaults": {"type": "sleeve", "game": game, "layout": "band", "out_size": 1024}, "approved": [], "jobs": jobs}


def icons(cfg: dict, game: str) -> dict:
    items = json.loads((game_root(cfg, game) / "project" / "data" / "items.json").read_text(encoding="utf-8"))
    jobs = []
    for iid, it in items.items():
        if not isinstance(it, dict) or not it.get("name"):
            continue
        desc = it.get("desc") or ""
        jobs.append({"name": iid, "prompt": f"{it['name']}" + (f", {desc.rstrip('.')}" if desc else ""),
                     "_kind": it.get("kind"), "_wanted": f"icons/{iid}"})
    return {"batch": "draft_icons", "_draft": True, "_made": datetime.now().isoformat(timespec="seconds"),
            "_review": "prompts are the item name + description — make each a concrete object before submitting",
            "defaults": {"type": "icon", "game": game, "canvas": 256}, "approved": [], "jobs": jobs}


KINDS = {"maps": maps, "sleeves": sleeves, "icons": icons}


def write(cfg: dict, game: str, kind: str) -> tuple[Path, int]:
    data = KINDS[kind](cfg, game)
    out = cfgmod.path_of(cfg, "games") / game / "batches" / f"draft_{kind}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    return out, len(data["jobs"])
