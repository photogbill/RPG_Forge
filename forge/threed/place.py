"""Places (BUILD 34): a place plan becomes a stage the game walks. Game-neutral: nothing here names a game.

A place plan (`<id>.place.json`) is the stage proof's scene plan grown up. Units are metres; x runs east and y south (the
floor plans' own axes); up is z.

    id, name, size [w, d]
    road        {"type": "dirt" | "gravel" | "street"}   dirt raises a puff of dust at the feet; the others do not
    ground      [{mat, rect [x, y, w, d] | ellipse [cx, cy, rx, ry] | poly [[x, y], ...], walk}]
    solids      [...]   plan-built: modelled whole by the compiler (forge/threed/blender/build_stage.py) — walls,
                        chimneys, furniture, fences — in the proof's format (rect or circle, h, z, mat, face)
    things      [{id, kind building|prop|vehicle|tree|panel|body, at [x, y], turn, footprint [x, y, w, d],
                  size_m {height|width|depth}, tier, words, species, seed, enter plan-built|shell|closed,
                  door [x, y], closed_line, first {where, order}}]
                        generated things: each goes on the game's world list and stands in the stage as a labelled grey
                        box of its real size until its model is delivered
    lighting    {ambient, zones, lights [{id, at, z, colour, power, radius}]}   the plan's lamps are real lights
    anchors     {name: [x, y]}                                                   spawns, doors, where a cue stands

Compiling a place (`compile_place`):
    (a) `<id>.stage.glb` — the ground's kerbs and the plan-built solids, modelled (Blender, no graphics card);
    (b) `games/<game>/wanted_3d/<id>.json` — every generated thing the place needs, in story order, with its tier and
        real size; a thing whose look nobody has written is held, with "needs_words" (the build guesses no looks);
    (c) `<id>.things.json` — what stands where: the model's world-list id, where, which way, its real size and the grey
        box's size until it is made.
`from_town()` writes a town's floor-plan layout (BUILD 29) out as a place plan.
"""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path

log = logging.getLogger("forge.threed")

ROAD_TYPES = ("dirt", "gravel", "street")
ROAD_MATS = {"dirt": "dirt_road", "gravel": "gravel", "street": "asphalt"}
DUST = {"dirt": True, "gravel": False, "street": False}
THING_KINDS = ("building", "prop", "vehicle", "tree", "panel", "body")
ENTER = ("plan-built", "shell", "closed")
BOX_HEIGHT = {"building": 6.0, "prop": 1.0, "vehicle": 1.8, "tree": 9.0, "panel": 1.8, "body": 1.72}
WORLD_KIND = {"building": "building", "prop": "prop", "vehicle": "prop", "tree": "tree", "panel": "panel", "body": "body"}
WORLD_TIER = {"building": "large_prop", "vehicle": "large_prop", "tree": "large_prop", "panel": "large_prop",
              "prop": "small_prop", "body": "named"}


class PlaceError(ValueError):
    pass


# ------------------------------------------------------------------------------------------------ reading and checking
def load(path) -> dict:
    p = Path(path)
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise PlaceError(f"{p.name} can't be read: {e}") from e
    return d


def check(place: dict) -> list[str]:
    """What is wrong with a place plan, in words (empty = nothing)."""
    out = []
    if not place.get("id"):
        out.append("the place has no id")
    size = place.get("size") or []
    if len(size) != 2 or min(float(v) for v in size) <= 0:
        out.append("the place's size must be [width, depth] in metres")
    road = (place.get("road") or {}).get("type")
    if road and road not in ROAD_TYPES:
        out.append(f"road type must be one of {', '.join(ROAD_TYPES)} (not {road!r})")
    seen = set()
    for t in place.get("things") or []:
        tid = t.get("id")
        if not tid:
            out.append("a thing has no id")
            continue
        if tid in seen:
            out.append(f"{tid} is in the place twice")
        seen.add(tid)
        if t.get("kind") not in THING_KINDS:
            out.append(f"{tid}: kind must be one of {', '.join(THING_KINDS)}")
        if not (t.get("at") or t.get("footprint")):
            out.append(f"{tid}: where does it stand? (at or footprint)")
        if t.get("enter") and t["enter"] not in ENTER:
            out.append(f"{tid}: enter must be one of {', '.join(ENTER)}")
        if t.get("kind") == "building" and t.get("enter", "closed") == "closed" and t.get("door") and not t.get("closed_line"):
            out.append(f"{tid}: a door that doesn't open says why, in the town's own words (closed_line)")
    for s in place.get("solids") or []:
        if not s.get("mat") or not (s.get("rect") or s.get("circle")):
            out.append(f"solid {s.get('id', '?')}: a solid needs a material and a rect or circle")
    return out


# ------------------------------------------------------------------------------------------------ the things
def _box(t: dict) -> list[float]:
    """The grey box's size (w, d, h in metres) until the model is delivered: from the footprint, else the real size."""
    s = t.get("size_m") or {}
    fp = t.get("footprint")
    if fp:
        w, d = float(fp[2]), float(fp[3])
    else:
        w = float(s.get("width") or s.get("depth") or (s.get("height") or 1.0) * 0.6)
        d = float(s.get("depth") or w)
    h = float(s.get("height") or BOX_HEIGHT.get(t.get("kind"), 1.0))
    return [round(w, 3), round(d, 3), round(h, 3)]


def _at(t: dict) -> list[float]:
    if t.get("at"):
        return [float(t["at"][0]), float(t["at"][1])]
    fp = t["footprint"]
    return [float(fp[0]) + float(fp[2]) / 2, float(fp[1]) + float(fp[3]) / 2]


def _turn(t: dict) -> float:
    """Degrees about the upright: a model's front faces south (toward +y) at 0; a door facing a street sets it."""
    if t.get("turn") is not None:
        return float(t["turn"])
    if t.get("door") and t.get("front"):
        dx, dy = t["front"][0] - t["door"][0], t["front"][1] - t["door"][1]
        return float((math.degrees(math.atan2(-dx, dy))) % 360)
    return 0.0


def world_id(place: dict, t: dict) -> str:
    """The model's id on the world list: its own `model` when it shares one (the court's houses can share a shell),
    else the place's id and the thing's."""
    return str(t.get("model") or f"{place['id']}_{t['id']}")


def wanted_entries(place: dict, start_order: float = 0.0) -> list[dict]:
    """Every generated thing the place needs, as world-list entries, in the order the place gives them. Plan-built things
    are not on it: the compiler models them. A thing with no words is held and says so (no look is guessed)."""
    out, seen = [], set()
    where = place.get("name") or place["id"]
    for k, t in enumerate(place.get("things") or []):
        if t.get("enter") == "plan-built" or t.get("plan_built"):
            continue
        wid = world_id(place, t)
        if wid in seen:
            continue
        seen.add(wid)
        kind = WORLD_KIND[t["kind"]]
        e = {"id": wid, "kind": kind, "tier": t.get("tier") or WORLD_TIER[t["kind"]],
             "first": {"where": f"{where}" + (f": {t['first']['where']}" if (t.get("first") or {}).get("where") else ""),
                       "order": float((t.get("first") or {}).get("order", start_order + k / 100.0))},
             "from_place": place["id"]}
        size = dict(t.get("size_m") or {})
        if not size:
            w, d, h = _box(t)
            size = {"height": h} if kind in ("building", "tree") else {"width": max(w, d)}
        e["real_size_m"] = size
        if kind == "tree":
            e["species"] = t.get("species") or "broadleaf"
            e["seed"] = int(t.get("seed") or 11)
        elif kind == "panel":
            e["panel"] = dict(t.get("panel") or {})
        else:
            words = str(t.get("words") or "").strip()
            if words:
                e["words"] = words
            else:
                e.update(words="", hold=True, needs_words=f"the place plan doesn't say what {t.get('label') or t['id']} "
                                                        "looks like — ask (no look is guessed)")
        for k2 in ("glow", "flame", "back_words", "back_image", "adopt", "adopt_picture"):
            if t.get(k2):
                e[k2] = t[k2]
        out.append(e)
    return out


def things_list(place: dict) -> dict:
    """What stands where on the stage: the game reads this beside the compiled model."""
    rows = []
    for t in place.get("things") or []:
        rows.append({"id": t["id"], "kind": t["kind"], "model": None if t.get("enter") == "plan-built" else world_id(place, t),
                     "label": t.get("label") or t["id"].replace("_", " "), "at": _at(t), "turn": round(_turn(t), 2),
                     "box_m": _box(t), "enter": t.get("enter") or ("closed" if t["kind"] == "building" else None),
                     "door": t.get("door"), "closed_line": t.get("closed_line"), "plan_built": t.get("enter") == "plan-built"})
    return {"place": place["id"], "name": place.get("name") or place["id"], "size": place.get("size"),
            "road": (place.get("road") or {}).get("type"), "dust": DUST.get((place.get("road") or {}).get("type") or "", False),
            "things": rows, "anchors": place.get("anchors") or {}, "lights": (place.get("lighting") or {}).get("lights") or []}


def write_wanted(games_root: Path, gid: str, place: dict, start_order: float = 0.0) -> Path:
    """`games/<game>/wanted_3d/<place>.json`. What a person changed on an entry that is already there (rank, hold, words
    written in, a tier) is kept: the compiler only adds what is new and refreshes where and how big."""
    p = Path(games_root) / gid / "wanted_3d" / f"{place['id']}.json"
    old = {}
    if p.exists():
        try:
            old = {e["id"]: e for e in json.loads(p.read_text(encoding="utf-8")).get("entries") or [] if isinstance(e, dict)}
        except (OSError, ValueError):
            old = {}
    fresh = wanted_entries(place, start_order)
    out = []
    for e in fresh:
        o = old.pop(e["id"], None)
        if o:
            keep = dict(o)
            keep.update(first=e["first"], real_size_m=e["real_size_m"], from_place=place["id"])
            if keep.get("words"):
                keep.pop("needs_words", None)
            out.append(keep)
        else:
            out.append(e)
    for o in old.values():                       # gone from the plan: kept, held, and said so — never dropped silently
        o = dict(o, hold=True, gone_from_place=f"no longer in {place['id']}'s plan")
        out.append(o)
    p.parent.mkdir(parents=True, exist_ok=True)
    doc = {"_about": f"What the place '{place.get('name') or place['id']}' needs (written by compile_place, BUILD 34). Every "
                     "generated thing the stage shows as a grey box until its model is delivered. Words you write in are "
                     "kept when the place is compiled again.", "entries": out}
    p.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


# ------------------------------------------------------------------------------------------------ compiling
def run_build_stage(env, plan_path: Path, out: Path, minutes: float = 15, python=None) -> dict:
    """The plan-built solids, modelled by forge/threed/blender/build_stage.py in the rigging tools' Blender."""
    from .env import run_blender
    code, lines = run_blender(env, "build_stage.py", ["--plan", str(plan_path), "--out", str(out)], minutes, log=log,
                              python=python)
    line = next((ln for ln in lines if ln.startswith("STAGE ")), "")
    if line and Path(out).exists():
        return {"ok": True, **json.loads(line[6:])}
    tail = [ln for ln in lines if ln.strip()][-4:]
    return {"ok": False, "error": (f"exit {code}: " if code not in (-2,) else "") + " / ".join(tail)[:600]}


def compile_place(cfg: dict | None, gid: str, place_path, out_dir, env=None, python=None, games_root=None,
                  minutes: float = 15) -> dict:
    """(a) the stage model, (b) the world-list entries, (c) the placed-things list. Returns a report."""
    place = load(place_path)
    if env is None:
        from .env import from_cfg
        env = from_cfg(cfg)
    probs = check(place)
    if probs:
        return {"ok": False, "error": "; ".join(probs), "problems": probs}
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    model = out / f"{place['id']}.stage.glb"
    things = out / f"{place['id']}.things.json"
    # the compiler reads the proof's format: solids, plus the ground's kerbs and the plan-built things' own solids
    plan = {k: place.get(k) for k in ("id", "size", "ground", "solids", "lighting", "anchors")}
    plan["solids"] = list(place.get("solids") or [])
    plan_path = out / f"{place['id']}.compile_plan.json"
    plan_path.write_text(json.dumps(plan, indent=1), encoding="utf-8")
    rep = {"ok": True, "place": place["id"], "lines": []}
    if plan["solids"]:
        r = run_build_stage(env, plan_path, model, minutes=minutes, python=python)
        if not r["ok"]:
            return {"ok": False, "error": r["error"], "place": place["id"]}
        rep.update(model=str(model), faces=r.get("faces"), meshes=r.get("meshes"))
        rep["lines"].append(f"Stage model: {r.get('faces', '?')} faces in {r.get('meshes', '?')} meshes, from "
                            f"{len(plan['solids'])} plan-built solids.")
    else:
        rep["lines"].append("No plan-built solids: the stage is its ground and its generated things.")
    tl = things_list(place)
    things.write_text(json.dumps(tl, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    rep["things"] = str(things)
    rep["lines"].append(f"Placed things: {len(tl['things'])} ({sum(1 for t in tl['things'] if t['plan_built'])} plan-built, "
                        f"the rest grey boxes until their models are delivered).")
    if games_root is not None:
        w = write_wanted(Path(games_root), gid, place, start_order=float(place.get("story_order") or 0.0))
        n = len(json.loads(w.read_text(encoding="utf-8"))["entries"])
        held = sum(1 for e in json.loads(w.read_text(encoding="utf-8"))["entries"] if e.get("needs_words"))
        rep["wanted"] = str(w)
        rep["lines"].append(f"World list: {n} things in {w.name}" + (f" ({held} held: nobody has written what they look like)"
                                                                     if held else "") + ".")
    for ln in rep["lines"]:
        log.info("  %s", ln)
    return rep


# ------------------------------------------------------------------------------------------------ a town's layout
def _rects(rows: list[list[str]], want: set) -> list[list[int]]:
    """Cells of the wanted kinds merged into rectangles (greedy: runs along x, then grown down while they match)."""
    H = len(rows)
    W = len(rows[0]) if H else 0
    used = [[False] * W for _ in range(H)]
    out = []
    for y in range(H):
        x = 0
        while x < W:
            if rows[y][x] in want and not used[y][x]:
                k = rows[y][x]
                x1 = x
                while x1 + 1 < W and rows[y][x1 + 1] == k and not used[y][x1 + 1]:
                    x1 += 1
                y1 = y
                while y1 + 1 < H and all(rows[y1 + 1][i] == k and not used[y1 + 1][i] for i in range(x, x1 + 1)):
                    y1 += 1
                for yy in range(y, y1 + 1):
                    for xx in range(x, x1 + 1):
                        used[yy][xx] = True
                out.append([x, y, x1 - x + 1, y1 - y + 1, k])
                x = x1 + 1
            else:
                x += 1
    return out


def from_town(layout: dict, grid: list[list[str]], sheet: dict | None = None, metres_per_tile: float = 1.0,
              entities: list | None = None) -> dict:
    """A town's floor-plan layout (BUILD 29: the layout record, its grid of tile kinds, its entities) written out as a
    place plan. Ground and roads by the town's road type; every building a thing with an id, a footprint, a facing and a
    real size; fences as plan-built solids; spawns and doors as anchors. Looks come from the town's sheet only: a
    building the sheet says nothing about has no words (and is held on the world list)."""
    sheet = sheet or {}
    m = float(metres_per_tile)
    road = str(sheet.get("road") or sheet.get("road_type") or "street").lower()
    road = road if road in ROAD_TYPES else "street"
    ground_mat = str(sheet.get("ground") or "grass")
    mats = {"road": ROAD_MATS[road], "path": "path", "ground": ground_mat, "field": "field", "floor": "plank",
            "rubble": "rubble", "bridge": "plank", "glass": "glass_fused", "water": "water", "door": "path"}
    walk = {"water": False}
    ground = []
    for x, y, w, h, k in _rects(grid, set(mats)):
        ground.append({"mat": mats[k], "rect": [x * m, y * m, w * m, h * m], **({"walk": False} if not walk.get(k, True) else {})})
    solids = []
    for i, (x, y, w, h, k) in enumerate(_rects(grid, {"fence"})):
        solids.append({"id": f"fence_{i + 1}", "mat": "fence", "rect": [x * m, y * m, w * m, h * m], "h": 1.1})
    looks = sheet.get("looks") or {}
    storey = float(sheet.get("storey_m") or 3.2)
    things = []
    for k, b in enumerate(layout.get("buildings") or []):
        x, y, w, h = b["rect"]
        storeys = int((sheet.get("storeys") or {}).get(b["kind"], 1))
        t = {"id": b["id"], "kind": "building", "label": b.get("label") or b["kind"],
             "footprint": [x * m, y * m, w * m, h * m], "size_m": {"height": round(storeys * storey + 1.5, 2)},
             "enter": "shell" if b.get("interior") else "closed", "first": {"order": k / 100.0}}
        if b.get("door"):
            t["door"] = [(b["door"][0] + 0.5) * m, (b["door"][1] + 0.5) * m]
            if b.get("front"):
                t["front"] = [(b["front"][0] + 0.5) * m, (b["front"][1] + 0.5) * m]
            if not b.get("interior"):
                cl = (sheet.get("closed_lines") or {}).get(b["kind"])
                if cl:
                    t["closed_line"] = cl
        words = looks.get(b["id"]) or looks.get(b["kind"])
        if words:
            t["words"] = words
        things.append(t)
    anchors = {}
    for e in entities or []:
        if e.get("type") == "spawn" and e.get("x") is not None:
            anchors[str(e.get("name") or "start")] = [(e["x"] + 0.5) * m, (e["y"] + 0.5) * m]
        if e.get("type") == "door" and e.get("x") is not None:
            anchors[str(e.get("id"))] = [(e["x"] + 0.5) * m, (e["y"] + 0.5) * m]
    H, W = len(grid), (len(grid[0]) if grid else 0)
    unknown = []
    if not sheet.get("road"):
        unknown.append("road type: the town's sheet doesn't say (dirt, gravel or street) — street used until it's asked")
    if not sheet.get("looks"):
        unknown.append("what the buildings look like: the town's sheet doesn't say — every building is held until it's asked")
    return {"id": layout.get("id") or sheet.get("id") or "place", "name": layout.get("name") or sheet.get("name") or "",
            "_from": f"forge.threed.place.from_town: layout {layout.get('id')} (seed {layout.get('seed')}, attempt "
                     f"{layout.get('attempt')}), {m} m a tile",
            "size": [W * m, H * m], "road": {"type": road}, "ground": ground, "solids": solids, "things": things,
            "lighting": {"lights": []}, "anchors": anchors, "unknowns": unknown}
