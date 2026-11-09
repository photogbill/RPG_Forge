#!/usr/bin/env python3
"""Export what the Turing Accords game wants in art → games/turing_accords/wanted.json (roadmap F4).

Read-only on the game folder. Run it from either repo:
    python games/turing_accords/export_wanted.py "D:\\Turing Accords Game"       (or: python -m forge wanted --refresh)

What counts as "wanted" (every file the game loads by path, so real art can replace it with no code change):
  * project/assets/placeholder/*.png   — make_placeholders.py's greybox set: tiles, 8-facing sheets, portraits, props
  * project/assets/vignettes/**.png    — Set_Piece cards (Gate Law …)
  * project/assets/scenes/<map>.png    — one painted background per map in project/data/maps (10.1b; 1920×1080 or
                                          the map's own ×3 size; a <map>.painted.json, if present, names the file)
                                          + its five optional set companions <map>_n/_e/_back/_over/_depth.png
                                          (kind "scene_slot", `set_of` the painting; approve them with --set)
  * sleeves from project/data/records.json (`sleeve` res:// paths)
  * icons named by items.json `icon` fields, if any
Names are the path under project/assets/ without the extension: "placeholder/hero_sarah", "scenes/bills_house".
Sizes: `size` is the file on disk now (if any); `target_size` is what 10.1b asks for (everything ×3).
"""
from __future__ import annotations
import json, struct, sys
from datetime import datetime
from pathlib import Path

SCALE = 3          # 10.1b: Night 1 pixels → painted pixels
TILE = 32
# The painted scene is a set of six files (21_Build_Plan_Night_2.md §3b): the painting plus these five companions,
# all at the painting's size except _back (wider by the overscan on each side). They are optional — a room without
# them still works — so `wanted --missing` hides them unless asked.
SCENE_SLOTS = (("_n", "normals, OpenGL convention (green = up)"), ("_e", "additive glow, emissive colours on black"),
               ("_back", "far parallax plane, opaque, wider by its overscan each side"),
               ("_over", "walk-behind plane, RGBA"), ("_depth", "16-bit grey depth, white = near"))
BACK_OVERSCAN = 48   # scene_layers' default, px per side


def png_size(p: Path) -> list[int] | None:
    try:
        with open(p, "rb") as f:
            head = f.read(24)
        if head[:8] != b"\x89PNG\r\n\x1a\n":
            return None
        w, h = struct.unpack(">II", head[16:24])
        return [int(w), int(h)]
    except OSError:
        return None


def _kind(stem: str) -> str:
    if stem == "tiles":
        return "tileset"
    if stem.startswith(("hero_", "npc_")):
        return "sprite_sheet"
    if stem.startswith("portrait_"):
        return "portrait"
    if "sleeve" in stem:
        return "sleeve"
    return "prop"


def _res(path: str) -> str:
    return "project/" + path[len("res://"):] if path.startswith("res://") else path


def export(game_root: str | Path) -> dict:
    root = Path(game_root)
    proj = root / "project"
    assets = proj / "assets"
    if not assets.exists():
        raise FileNotFoundError(f"{assets} not found — is '{root}' the game folder?")
    items: dict[str, dict] = {}

    def put(name, path, kind, notes="", target=None, source=""):
        p = root / path
        size = png_size(p) if p.exists() else None
        if target is None and size:
            target = [size[0] * SCALE, size[1] * SCALE]
        items[name] = {"name": name, "path": path.replace("\\", "/"), "kind": kind, "exists": p.exists(), "size": size,
                       "target_size": target, "notes": notes, "source": source}

    for p in sorted((assets / "placeholder").glob("*.png")):
        k = _kind(p.stem)
        note = {"sprite_sheet": "8 facings S,SW,W,NW,N,NE,E,SE in one row (Player.direction_index)",
                "tileset": "atlas strip in MapParser.TILE_ATLAS order; tiles.tres collision must match",
                "portrait": "dialogue portrait"}.get(k, "")
        put(f"placeholder/{p.stem}", f"project/assets/placeholder/{p.name}", k, note, source="make_placeholders.py")
    for p in sorted((assets / "vignettes").rglob("*.png")):
        rel = p.relative_to(assets).with_suffix("").as_posix()
        put(rel, f"project/assets/{p.relative_to(assets).as_posix()}", "vignette", source="Set_Pieces")
    maps = proj / "data" / "maps"
    for m in sorted(maps.glob("*.json")):
        if m.name.endswith(".painted.json"):
            continue
        try:
            d = json.loads(m.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        mid = d.get("id") or m.stem
        bg = f"project/assets/scenes/{mid}.png"
        target = None
        painted = maps / f"{mid}.painted.json"
        if painted.exists():
            try:
                pd = json.loads(painted.read_text(encoding="utf-8"))
                bg = _res(pd.get("background") or bg) if str(pd.get("background", "")).startswith("res://") else \
                    ("project/" + pd["background"] if pd.get("background") else bg)
                if pd.get("size"):
                    target = [int(pd["size"][0]), int(pd["size"][1])]
            except (OSError, ValueError, KeyError, TypeError):
                pass
        if target is None and d.get("rows"):
            ts = int(d.get("tile_size", TILE))
            target = [max(len(r) for r in d["rows"]) * ts * SCALE, len(d["rows"]) * ts * SCALE]
        greybox = f"project/assets/scenes/{mid}_greybox.png"
        note = (d.get("notes") or "")[:240]
        put(f"scenes/{mid}", bg, "scene", note, target=target, source=f"data/maps/{m.name}")
        items[f"scenes/{mid}"]["greybox"] = greybox if (root / greybox).exists() else None
        items[f"scenes/{mid}"]["name_in_game"] = d.get("name")
        items[f"scenes/{mid}"]["slots"] = [f"scenes/{mid}{sfx}" for sfx, _ in SCENE_SLOTS]
        stem = bg[:-4] if bg.lower().endswith(".png") else bg
        for sfx, what in SCENE_SLOTS:
            st = None
            if target:
                st = [target[0] + 2 * BACK_OVERSCAN, target[1]] if sfx == "_back" else list(target)
            put(f"scenes/{mid}{sfx}", f"{stem}{sfx}.png", "scene_slot", what, target=st, source=f"data/maps/{m.name}")
            items[f"scenes/{mid}{sfx}"].update({"set_of": f"scenes/{mid}", "slot": sfx, "optional": True})
    rec_path = proj / "data" / "records.json"
    if rec_path.exists():
        recs = json.loads(rec_path.read_text(encoding="utf-8"))
        for rid, r in recs.items():
            if not isinstance(r, dict) or not r.get("sleeve"):
                continue
            path = _res(r["sleeve"])
            put(f"sleeves/{rid}", path, "sleeve", f"{r.get('title', '')} — {r.get('singer', '')} ({r.get('album', '')})",
                target=[384, 384], source="data/records.json")
            items[f"sleeves/{rid}"].update({"title": r.get("title"), "artist": r.get("singer"), "album": r.get("album")})
    it_path = proj / "data" / "items.json"
    if it_path.exists():
        for iid, it in json.loads(it_path.read_text(encoding="utf-8")).items():
            if isinstance(it, dict) and it.get("icon"):
                put(f"icons/{iid}", _res(it["icon"]), "icon", it.get("name", ""), target=[256, 256], source="data/items.json")
    return {"game": "turing_accords", "game_root": str(root), "exported": datetime.now().isoformat(timespec="seconds"),
            "count": len(items), "items": items}


def main(argv: list[str]) -> int:
    root = argv[1] if len(argv) > 1 else r"D:\Turing Accords Game"
    data = export(root)
    out = Path(__file__).with_name("wanted.json")
    out.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    print(f"wrote {out}: {data['count']} wanted files")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
