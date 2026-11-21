"""Every area checked (BUILD 83 Part B) — the first two measured checks, 2026-11-19.

✦ William, 2026-11-19 04:44: "add the checklists to the build plan for every area, with the specification that Claude Fable
reviews and approves." ✦ 14:56: "What can you code, for real."

    areacheck.check(cfg, gid, place_id)   -> the report (and out/areas/<game>/<place>/report.json + report.md)

Built so far (Checklist A, BUILD 83 §B1):
  8  Delivered   — every thing the place puts on the world list is delivered into the game; nothing is still a stand-in
  10 People      — the place's people are described (<game folder>/data/people/<place>.json, BUILD_RULES)
Every other check is listed as "not built yet", never as a pass. Nothing here names a game, and nothing is changed but
the report.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

NOT_BUILT = ["1 scale", "2 stretch", "3 grounding", "4 clipping", "5 sharpness", "6 repeats", "7 dressing",
             "9 the look holds", "10 signature and music (people is built)"]


def report_dir(cfg, gid: str, pid: str) -> Path:
    from .. import config as cfgmod
    return cfgmod.path_of(cfg, "out") / "areas" / gid / pid


def check_delivered(things: list[dict]) -> dict:
    left = [t for t in things if str(t.get("shown") or "") != "delivered"]
    if not things:
        return {"id": "delivered", "ok": None, "line": "Delivered: the place has no things on the world list yet (compile it)."}
    if not left:
        return {"id": "delivered", "ok": True, "line": f"Delivered: all {len(things)} things are in the game."}
    return {"id": "delivered", "ok": False,
            "line": f"Delivered: {len(left)} of {len(things)} not yet in the game — any picture of this area is greybox.",
            "flags": [{"id": t["id"], "kind": t.get("kind"), "now": t.get("shown"), "why": (t.get("why") or [None])[0]}
                      for t in left]}


def check_people(game_root, pid: str) -> dict:
    if not game_root:
        return {"id": "people", "ok": None, "line": "People: the game folder is not set on this computer — not measurable."}
    p = Path(game_root) / "data" / "people" / f"{pid}.json"
    if not p.exists():
        return {"id": "people", "ok": False, "line": f"People: not described yet — write data/people/{pid}.json (its prompts, "
                "a person a line, BUILD 70 part 3)."}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        n = len(d) if isinstance(d, list) else len(d.get("people") or d.get("prompts") or [])
    except (OSError, ValueError) as ex:
        return {"id": "people", "ok": False, "line": f"People: data/people/{pid}.json could not be read ({ex})."}
    if not n:
        return {"id": "people", "ok": False, "line": f"People: data/people/{pid}.json has nobody in it."}
    return {"id": "people", "ok": True, "line": f"People: {n} described."}


def check(cfg, gid: str, pid: str, status: dict | None = None, game_root=None, write: bool = True) -> dict:
    from ..suite import games, places3d
    from . import world
    status = status if status is not None else world.status(cfg, gid)
    things = places3d.entries_for(status, pid)
    if game_root is None:
        try:
            game_root = games.game_root(cfg, gid)
        except Exception:  # noqa: BLE001
            game_root = None
    checks = [check_delivered(things), check_people(game_root, pid)]
    rep = {"place": pid, "game": gid, "at": datetime.now().isoformat(timespec="seconds"), "checks": checks,
           "passed": sum(1 for c in checks if c["ok"] is True), "flagged": sum(1 for c in checks if c["ok"] is False),
           "not_built_yet": NOT_BUILT, "fable_review": "Checklist B (Fable's eyes) and approval: BUILD 83 Part C, not built yet"}
    if write:
        d = report_dir(cfg, gid, pid)
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / "report.json.part"
        tmp.write_text(json.dumps(rep, indent=1, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, d / "report.json")
        md = [f"# Area check — {pid} ({rep['at']})", ""] + [("✔ " if c["ok"] else "✖ " if c["ok"] is False else "· ") + c["line"]
                                                             for c in checks]
        for c in checks:
            for f in c.get("flags") or []:
                md.append(f"    - {f['id']} ({f.get('kind')}): {f.get('now')}" + (f" — {f['why']}" if f.get("why") else ""))
        md += ["", "Not built yet: " + ", ".join(NOT_BUILT) + ".", rep["fable_review"]]
        (d / "report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
        rep["report"] = str(d / "report.md")
    return rep
