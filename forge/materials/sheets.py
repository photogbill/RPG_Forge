"""The sheets a reviewer approves from (BUILD 87, Part 4), and a place's ground with its wear on and off (Part 3).

Everything a game decides is read from games/<id>/materials/materials.json — which surfaces are a town's, which
picture is each surface's, which decals lie where in which era, what the licence lines say. This module only draws.

    {"library": "games/<id>/ref/materials",                 the game's texture library (Filter Forge channel sets go beside)
     "cull": "<path>/_filter_forge_cull.json",              {"picks": [{"id", "verdict", "render_dir", "use", "name"}]}
     "licences": ["…", "…"],                                printed at the foot of every sheet
     "states": {"War": "broken", "After": "mended"},        which setting of a Material Maker graph each era wears
     "towns": {"<town>": {"label": "…", "materials": [{"word": "asphalt", "picks": ["9339-1"]},
                                                      {"word": "canvas", "graph": "canvas"}]}},
     "grounds": ["asphalt", …],                             library names that get three seeds and a mix
     "places": {"<place>": {"plan": "games/<id>/places/<place>.place.json", "window": [x, y, w, h], "stand": [x, y],
                            "eye_m": 1.7, "looks_at": [x, y], "materials": {"asphalt": {"pick": "9339-1", "tile_m": 4}},
                            "decals": {"crack": {"pick": "11797-2", "alpha_from": "dark", "tint": [r, g, b]}},
                            "layers": {"War": [{"decal": "crack", "at": [x, y], "size_m": 5, "turn": 20}], "After": []}}}}
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from .. import config as cfgmod
from . import look, mix


def game_file(root: Path, game: str) -> Path:
    return Path(root) / "games" / game / "materials" / "materials.json"


def load_game(root: Path, game: str) -> dict:
    p = game_file(root, game)
    if not p.is_file():
        raise FileNotFoundError(f"{p} is not there: a game says which materials are whose in that file (docs/MATERIALS.md)")
    return json.loads(p.read_text(encoding="utf-8"))


def _abs(root: Path, p) -> Path:
    q = Path(str(p))
    return q if q.is_absolute() else Path(root) / q


def pick_index(root: Path, cull_file: Path | None) -> dict[str, dict]:
    """{pick id: {"picture": Path | None, "name", "why"}} from a cull file (kept picks only)."""
    out: dict[str, dict] = {}
    if not cull_file or not Path(cull_file).is_file():
        return out
    for r in json.loads(Path(cull_file).read_text(encoding="utf-8")).get("picks", []):
        if r.get("verdict") != "keep":
            continue
        pic = _abs(root, r.get("render_dir") or "") / str(r.get("use") or "")
        ok = pic.is_file()
        out[str(r.get("id"))] = {"picture": pic if ok else None, "name": r.get("name"),
                                 "why": "" if ok else str(r.get("use") or "no picture named")}
    return out


def mm_done(root: Path, graph: str, setting: str | None) -> Path | None:
    """The newest finished mm_material render of a graph in a setting: its colour picture."""
    slot = graph + (f"_{setting}" if setting else "")
    best = None
    for d in sorted((Path(root) / "out").glob(f"*-mm_{slot}-*")):
        p = d / f"{slot}.png"
        if p.is_file():
            best = p
    return best


def town_rows(root: Path, game: dict, town: str, index: dict[str, dict], size: int = 512) -> tuple[list[Image.Image], list[dict]]:
    """One row a surface (a Material Maker surface: one row a state). Returns (rows, what is missing)."""
    spec = (game.get("towns") or {}).get(town) or {}
    rows, missing = [], []
    for m in spec.get("materials") or []:
        word = str(m.get("word"))
        if m.get("graph"):
            for era, setting in (game.get("states") or {"": None}).items():
                pic = mm_done(root, str(m["graph"]), setting)
                if pic is None:
                    missing.append({"word": word, "why": f"Material Maker graph '{m['graph']}' ({setting or 'as it is'}) has not been exported yet"})
                    continue
                s = look.load_set(pic, size)
                rows.append(look.material_row(s, f"{word} - {era or 'made'} ({setting})", note="Material Maker"))
        ids = [str(x) for x in (m.get("picks") or [])]
        if not ids:
            if not m.get("graph"):
                missing.append({"word": word, "why": m.get("note") or "no pick and no graph named"})
            continue
        for pid in ids:
            rec = index.get(pid)
            if rec is None or rec["picture"] is None:
                missing.append({"word": word, "pick": pid, "why": "not among the kept picks" if rec is None else rec["why"]})
                continue
            s = look.load_set(rec["picture"], size)
            true = not str(s["how"].get("normal", "")).startswith("guessed")
            rows.append(look.material_row(s, f"{word} - #{pid} {rec['name'] or ''}",
                                          note="Filter Forge, true channels" if true else "Filter Forge - NO CHANNEL SET YET: the normal is guessed"))
    return rows, missing


def town_sheet(root: Path, game: dict, town: str, index: dict[str, dict], size: int = 512) -> tuple[Image.Image | None, list[dict]]:
    spec = (game.get("towns") or {}).get(town) or {}
    rows, missing = town_rows(root, game, town, index, size)
    if not rows:
        return None, missing
    w = max(r.width for r in rows)
    head = _band(f"{spec.get('label') or town}: its materials - every channel, a piece under the lamp, a ball", w, 30, 17, (235, 230, 215))
    foot = [_band("Licences: " + "  |  ".join(game.get("licences") or ["(none given in the game's materials.json)"]), w, 22, 12, (190, 200, 190))]
    if missing:
        text = "Not on this sheet: " + "; ".join(x["word"] + (f" #{x['pick']}" if x.get("pick") else "") + f" ({x['why']})" for x in missing)
        per = max(40, int(w / 7.2))
        for i in range(0, min(len(text), per * 4), per):
            foot.append(_band(text[i:i + per], w, 20, 12, (230, 180, 150)))
    return look.stamp(look.stack([head] + rows + foot)), missing


def _band(text: str, w: int, h: int, font: int, fill) -> Image.Image:
    im = Image.new("RGB", (int(w), int(h)), (16, 16, 20))
    ImageDraw.Draw(im).text((8, max(2, (h - font) // 2 - 1)), look._ascii(text), font=look._font(font), fill=fill)
    return im


# ------------------------------------------------------------------ a place's ground, its wear on and off
def place_decals(root: Path, spec: dict, index: dict[str, dict], size: int = 512) -> tuple[dict[str, dict], list[str]]:
    lib, notes = {}, []
    for name, d in (spec.get("decals") or {}).items():
        rec = index.get(str(d.get("pick")))
        src = _abs(root, d["picture"]) if d.get("picture") else (rec or {}).get("picture")
        if src is None or not Path(src).is_file():
            notes.append(f"decal '{name}': its picture is not there (pick {d.get('pick')})")
            continue
        pic = look.load(src, size)
        if pic.shape[2] == 1:
            pic = np.repeat(pic, 3, axis=2)
        lib[name] = mix.make_decal(pic, str(d.get("alpha_from") or "dark"), float(d.get("strength") or 1.0), float(d.get("edge") or 0.18),
                                   d.get("tint"), str(d.get("relief") or "cut"), float(d.get("depth") or 6.0),
                                   rough_value=float(d.get("rough_value") or 0.9), seed=int(d.get("seed") or 3))
    return lib, notes


def place_pictures(root: Path, game: dict, place: str, index: dict[str, dict], px_per_m: float = 40.0,
                   size: tuple[int, int] = (1280, 720)) -> tuple[dict[str, Image.Image], Image.Image, list[str]]:
    """{layer name: the ground seen from the place's standing point}, the layers side by side seen from above, notes.
    The ground is drawn once; only the decal list differs between the pictures."""
    spec = (game.get("places") or {}).get(place)
    if not spec:
        raise ValueError(f"the game's materials.json has no place '{place}'")
    plan = json.loads(_abs(root, spec["plan"]).read_text(encoding="utf-8"))
    window = tuple(float(x) for x in spec["window"])
    mats, tile_m, notes = {}, {}, []
    for word, m in (spec.get("materials") or {}).items():
        rec = index.get(str(m.get("pick")))
        src = _abs(root, m["picture"]) if m.get("picture") else (rec or {}).get("picture")
        if src is None or not Path(src).is_file():
            notes.append(f"ground '{word}': its picture is not there (pick {m.get('pick')})")
            continue
        s = look.load_set(src, int(m.get("px") or 512))
        if str(s["how"].get("normal", "")).startswith("guessed"):
            notes.append(f"ground '{word}': no channel set yet - its relief is guessed from brightness")
        if m.get("rough") is not None and "none" in str(s["how"].get("roughness", "")):
            s["roughness"] = np.full(s["roughness"].shape, float(m["rough"]))
        mats[word] = s
        tile_m[word] = float(m.get("tile_m") or 3.0)
    ground, n2 = mix.ground_from_plan(plan, mats, window, px_per_m, tile_m)
    notes += n2
    decals, n3 = place_decals(root, spec, index)
    notes += n3
    views, tops = {}, []
    for layer, placed in (spec.get("layers") or {}).items():
        worn = mix.lay_in_metres(ground, window, placed, decals) if placed else ground
        v = mix.ground_view(worn, window, tuple(spec["stand"]), float(spec.get("eye_m") or 1.7), tuple(spec["looks_at"]), size)
        label = f"{plan.get('name', place)[:60]} - {layer}: {len(placed)} decal(s) on the same ground"
        views[layer] = look.stamp(look.to_image(v), f"{label} | the GROUND only (no buildings, no props) | " + look.PREVIEW_STAMP)
        top = look.to_image(worn["colour"])
        top.thumbnail((1100, 520), Image.LANCZOS)
        tops.append(look.stamp(top, f"{layer}, from above: {window[2]:.0f} m x {window[3]:.0f} m of the plan's ground"))
    return views, look.stack(tops), notes
