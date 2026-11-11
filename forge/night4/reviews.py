"""Compact review sheets for Night 4 (≤ 12 cells, numbered, labels in the picture — readable by Fable):

    character_sheet(cfg, id)   every variant and mood of one face, both roads (character_set renders and drawn sheets
                               through sprite_intake) — does the face hold?
    town_sheet(cfg, town)      every painting of one town (states, eras, enclaves) — does it hold together?
    atlas_sheet(cfg)           one painting per town side by side — do the towns differ? (the check that matters)

→ out/review/<name>/sheet_NN.jpg (+ review_index.json: cell → job id and file)."""
from __future__ import annotations
import json
from pathlib import Path

from PIL import Image

from .. import config as cfgmod
from ..review_compact import pages, save_jpeg, sheet

CELLS = 12


def _done(cfg: dict) -> list[dict]:
    d = cfgmod.path_of(cfg, "jobs") / "done"
    out = []
    for p in sorted(d.glob("*.json")):
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not j.get("tombstone"):
            out.append(j)
    return out


def _write(cfg: dict, name: str, cells: list[tuple[Path, str, str]], title: str) -> tuple[list[Path], int]:
    if not cells:
        raise ValueError(f"nothing finished to show for {name}")
    dest = cfgmod.path_of(cfg, "out") / "review" / name
    dest.mkdir(parents=True, exist_ok=True)
    paths, index = [], {}
    for k, page in enumerate(pages(cells, CELLS), 1):
        ims, labs = [], []
        for i, (p, lab, jid) in enumerate(page, 1):
            im = Image.open(p)
            if im.mode == "RGBA":
                bg = Image.new("RGBA", im.size, (40, 40, 46, 255)); bg.alpha_composite(im); im = bg
            ims.append(im.convert("RGB")); labs.append(lab)
            index[f"{k}:{i}"] = {"job": jid, "file": str(p), "label": lab}
        out = dest / f"sheet_{k:02d}.jpg"
        save_jpeg(sheet(ims, labs, f"{title} — page {k}"), out)
        paths.append(out)
    (dest / "review_index.json").write_text(json.dumps(index, indent=1, ensure_ascii=False), encoding="utf-8")
    return paths, len(cells)


def character_sheet(cfg: dict, cid: str) -> tuple[list[Path], int]:
    out_root = cfgmod.path_of(cfg, "out")
    cells: list[tuple[Path, str, str]] = []
    for j in _done(cfg):
        if j.get("character") != cid:
            continue
        o = out_root / j["id"]
        v = j.get("variant") or "-"
        if j.get("type") == "character_set":
            for p in sorted((o / "moods").glob("*.png")):
                cells.append((p, f"{v} · mood {p.stem} · seed {((j.get('renders') or [{}])[0]).get('seed')}", j["id"]))
            for f, lab in (("battle.png", "battle pose"), ("sheet.png", "sheet (generated)")):
                if (o / f).exists():
                    cells.append((o / f, f"{v} · {lab}", j["id"]))
        elif j.get("type") == "sprite_intake" and (o / "sheet.png").exists():
            cells.append((o / "sheet.png", f"{v} · drawn sheet {Path(j.get('input', '')).name}", j["id"]))
        elif j.get("type") in ("render", "portrait", "scene_paint") and (o / "render.png").exists():
            cells.append((o / "render.png", f"{v} · {j.get('type')} {j.get('name', '')}", j["id"]))
    if not cells:
        raise ValueError(f"no finished pictures of '{cid}' yet (character_set, sprite_intake or a job with "
                         f"\"character\": \"{cid}\")")
    cells.sort(key=lambda c: c[1])
    return _write(cfg, f"character_{cid}", cells, f"{cid}: every variant and mood")


def _painting(o: Path) -> Path | None:
    for f in ("scene.png", "inpaint.png", "render.png"):
        if (o / f).exists():
            return o / f
    hits = sorted(o.glob("scene_*.png"))
    return hits[0] if hits else None


def _town_jobs(cfg: dict) -> dict[str, list[dict]]:
    """Paintings grouped by town: a job's meta.town / town, else the town of its map in wanted.json."""
    from .. import manifest
    try:
        items = manifest.load_wanted(cfg, cfgmod.default_game(cfg))["items"]
    except Exception:  # noqa: BLE001
        items = {}
    town_of = {n.split("/", 1)[1]: w.get("town") for n, w in items.items() if w.get("kind") == "scene" and w.get("town")}
    out: dict[str, list[dict]] = {}
    for j in _done(cfg):
        if j.get("type") not in ("scene_kit", "scene_paint", "repaint", "scene_big", "scene_state", "photo_plate",
                                 "handoff_kit"):
            continue
        meta = j.get("meta") or {}
        town = meta.get("town") or j.get("town") or town_of.get(str(j.get("name")))
        if town:
            out.setdefault(str(town), []).append(j)
    return out


def town_sheet(cfg: dict, town: str | None) -> tuple[list[Path], int]:
    if not town:
        raise ValueError("usage: review --town <town id>")
    groups = _town_jobs(cfg)
    if town not in groups:
        raise ValueError(f"no finished paintings of town '{town}' (towns with paintings: {', '.join(sorted(groups)) or 'none'})")
    out_root = cfgmod.path_of(cfg, "out")
    cells = []
    for j in groups[town]:
        p = _painting(out_root / j["id"])
        if p:
            meta = j.get("meta") or {}
            lab = " · ".join(str(x) for x in (j.get("name"), meta.get("era"), meta.get("state"), meta.get("enclave")) if x)
            cells.append((p, lab, j["id"]))
    return _write(cfg, f"town_{town}", cells, f"town {town}: does it hold together?")


def atlas_sheet(cfg: dict) -> tuple[list[Path], int]:
    groups = _town_jobs(cfg)
    if not groups:
        raise ValueError("no finished paintings carry a town yet (produce plan puts meta.town on every map job)")
    out_root = cfgmod.path_of(cfg, "out")
    cells = []
    for town, jobs in sorted(groups.items()):
        # the town's base (Peace / first) painting: prefer a job with no state
        jobs = sorted(jobs, key=lambda j: (bool((j.get("meta") or {}).get("state")), j["id"]))
        for j in jobs:
            p = _painting(out_root / j["id"])
            if p:
                cells.append((p, f"{town} · {j.get('name')}", j["id"])); break
    return _write(cfg, "atlas", cells, "atlas: one painting per town — do they differ?")
