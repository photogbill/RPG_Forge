"""Floor-plan commands (BUILD 29) — the generator from the command line (the Art → Floor plans tab uses the same calls).

    python -m forge layout archetypes                          the archetype library (◆ proposals, ✦ rulings)
    python -m forge layout sheets [--game <id>]                every place the game can lay out: suggested archetypes and why, unknowns
    python -m forge layout generate <place> --era war|after [--archetype <id>] [--seed 1] [--count 4] [--game <id>]
                                                               candidates (one per seed) → out/layout/<game>/<place>/<era>/<archetype>/seed_<n>/
    python -m forge layout show <folder> [--map <id>]          a written plan as text (S = spawn, @ = the story element)
    python -m forge layout check <folder>                      the plan's checks and the game's own map rules, again
    python -m forge layout approve <folder> [--who "<name>"]   a person only: copy the maps into the game (never over another map)
"""
from __future__ import annotations
import json
from pathlib import Path


def _opts(args):
    pos, o, i = [], {}, 0
    while i < len(args):
        a = args[i]
        if a.startswith("--"):
            k = a[2:]
            if i + 1 < len(args) and not args[i + 1].startswith("--"):
                o[k] = args[i + 1]
                i += 2
                continue
            o[k] = True
        else:
            pos.append(a)
        i += 1
    return pos, o


def _game(cfg, o):
    from . import config as cfgmod
    from .suite import games
    gid = o.get("game") if isinstance(o.get("game"), str) else cfgmod.default_game(cfg)
    adp = games.adapter(cfg, gid) if gid and games.has_adapter(cfg, gid) else None
    return gid, adp


def cmd_layout(cfg: dict, args: list[str]) -> int:
    from .layout import archetypes, store, town
    pos, o = _opts(args)
    sub = pos[0] if pos else ""
    if sub == "archetypes":
        for a in archetypes.listing():
            print(f"{a['mark']} {a['id']:18} {a['name']}  [{a['rule']}]")
            print(f"     {a['pitch']}")
            print(f"     story: war — {a['story']['war']} · after — {a['story']['after']}")
            print(f"     upgrades: war — {a['upgrade']['war']} · after — {a['upgrade']['after']}\n")
        return 0
    if sub == "sheets":
        gid, adp = _game(cfg, o)
        sheets = adp.town_sheets() if adp else []
        if not sheets:
            print(f"the game '{gid}' offers no town sheets (its adapter has no town_sheets yet)")
            return 1
        for s in sheets:
            arch = s.get("archetypes", {})
            print(f"{s['id']:20} fate {s.get('fate')!s:9} war: {', '.join(arch.get('war', {}).get('ids') or ['—'])} "
                  f"· after: {', '.join(arch.get('after', {}).get('ids') or ['—'])} ({arch.get('after', {}).get('how', '')})")
            for w in arch.get("after", {}).get("why") or []:
                print(f"{'':22}because {w}")
            for u in s.get("unknowns") or []:
                print(f"{'':22}unknown: {u}")
        return 0
    if sub == "generate":
        if len(pos) < 2 or o.get("era") not in ("war", "after"):
            print("usage: layout generate <place> --era war|after [--archetype <id>] [--seed 1] [--count 4]")
            return 2
        gid, adp = _game(cfg, o)
        place, era = pos[1], o["era"]
        sheets = {s["id"]: s for s in (adp.town_sheets() if adp else [])}
        if place not in sheets:
            print(f"no town sheet '{place}' in {gid} — `layout sheets` lists them")
            return 1
        gs = sheets[place]
        sheet = adp.sheet_for(gs, era) if hasattr(adp, "sheet_for") else gs
        aid = o.get("archetype") if isinstance(o.get("archetype"), str) else None
        if not aid:
            ids = (gs.get("archetypes", {}).get(era) or {}).get("ids") or []
            if not ids:
                print(f"{place} has no archetype yet (nothing on its sheet suggests one) — pass --archetype <id>")
                return 1
            aid = ids[0]
            print(f"archetype: {aid} ({(gs['archetypes'][era]).get('how')}) — pass --archetype to choose another")
        seed0 = int(o.get("seed") or 1)
        count = int(o.get("count") or 4)
        px = int(o.get("px") or 32)
        worst = 0
        for seed in range(seed0, seed0 + count):
            fol = store.folder(cfg, gid, place, era, aid, seed)
            p = town.generate(sheet, aid, era, seed)
            try:
                s = store.write(p, fol, adp, sheet, px=px)
            except store.LayoutError as e:
                print(f"seed {seed}: {e}")
                worst = max(worst, 1)
                continue
            bad = len(s["problems"]) + len(s["game_problems"])
            print(f"seed {seed}: {len(s['maps'])} maps, attempt {p.attempt}, "
                  f"{'clean' if not bad else str(bad) + ' problems'} → {fol}")
            for q in (s["problems"] + s["game_problems"])[:5]:
                print(f"    {q}")
            worst = max(worst, 1 if bad else 0)
        return worst
    if sub in ("show", "check", "approve"):
        if len(pos) < 2:
            print(f"usage: layout {sub} <folder>")
            return 2
        fol = Path(pos[1])
        ps = json.loads((fol / "plan_set.json").read_text(encoding="utf-8"))
        if sub == "show":
            mid = o.get("map") if isinstance(o.get("map"), str) else ps["top"]
            m = json.loads((fol / f"{mid}.json").read_text(encoding="utf-8"))
            lay = json.loads((fol / f"{mid}.layout.json").read_text(encoding="utf-8"))
            rows = [list(r) for r in m["rows"]]
            for e in m.get("entities") or []:
                if e.get("type") == "spawn" and e.get("name") == "start":
                    rows[e["y"]][e["x"]] = "S"
            st = lay.get("story")
            if st:
                for y in range(st["y"], st["y"] + st["h"]):
                    for x in range(st["x"], st["x"] + st["w"]):
                        rows[y][x] = "@"
            print(f"{mid} — {lay.get('archetype')} {lay.get('era')} seed {lay.get('seed')}")
            print("\n".join("".join(r) for r in rows))
            for n in lay.get("notes") or []:
                print(f"  · {n}")
            return 0
        gid, adp = _game(cfg, o)
        if sub == "check":
            maps = {mid: json.loads((fol / f"{mid}.json").read_text(encoding="utf-8")) for mid in ps["maps"]}
            probs = list(ps.get("problems") or []) + (adp.layout_check(maps) if adp and hasattr(adp, "layout_check") else [])
            print("clean" if not probs else "\n".join(probs))
            why = store.protected(fol)
            if why:
                print(f"(protected: {why})")
            return 1 if probs else 0
        from .suite import settings
        who = o.get("who") if isinstance(o.get("who"), str) else settings.identity()
        try:
            s = store.approve(fol, adp, who)
        except (store.LayoutError, ValueError) as e:
            print(f"not approved: {e}")
            return 1
        print(f"approved by {s['approved_by']}: {len(s['installed'])} maps written into the game")
        return 0
    print(__doc__)
    return 2


COMMANDS = {"layout": cmd_layout}
