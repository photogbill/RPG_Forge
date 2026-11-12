"""User Needs To Provide Image — the forge pool of pictures the forge can't make well (William, 2026-11-11: "anything
hard to generate, put that request into the forge pool and make a section for User Needs To Provide Image").

**The pool** is one forge-side file, `games/<game>/provide_requests.json`, so a session can add a request even when the
game's folder isn't reachable from where it runs (`python -m forge provide add …`). A request says what picture is
wanted, **why the forge can't make it** (what was tried and how it failed), **what would help** (a photo, a sketch, a
sheet you already have), how many, and where it goes in the game.

**The section** (Art → User Needs To Provide Image) shows each open request as a task card with a drop zone: the file
goes through the same door as every other task (`tasks.accept` — streamed, never half-written, journaled). To get
there, `sync()` files each open request as a work order for the game's owner, marked `"provide": <request id>`, once.
It runs whenever the section or Tasks is opened, so a request shows up without anyone running anything. A request
`on_hold` (waiting on a bake-off verdict, say) is listed in the section but not filed as a task until it is opened.

Request: {id, title, why, helps, kind: image|sheet|any, count, goes_to, priority: now|soon|someday, effort, by, added,
          status: open|on_hold|withdrawn, hold_until?}
"""
from __future__ import annotations
import json, os, re
from pathlib import Path

from ..log import get
from . import games, orders, settings

log = get("suite")

STATUSES = ("open", "on_hold", "withdrawn")
KINDS = ("image", "sheet", "any")


class ProvideRefused(ValueError):
    """The rule said no; nothing was written."""


def path(cfg: dict, gid: str) -> Path:
    return games.games_dir(cfg) / gid / "provide_requests.json"


def load(cfg: dict, gid: str) -> list[dict]:
    p = path(cfg, gid)
    try:
        d = json.loads(p.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as e:
        log.warning("provide: %s unreadable (%s) — treated as empty", p, e)
        return []
    rows = d.get("requests") if isinstance(d, dict) else d
    return [r for r in (rows or []) if isinstance(r, dict) and r.get("id")]


def _save(cfg: dict, gid: str, rows: list[dict]) -> None:
    p = path(cfg, gid)
    p.parent.mkdir(parents=True, exist_ok=True)
    keep = {}
    try:
        old = json.loads(p.read_text(encoding="utf-8-sig"))
        if isinstance(old, dict):
            keep = {k: v for k, v in old.items() if k != "requests"}
    except (OSError, ValueError):
        pass
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps({**keep, "requests": rows}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, p)


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_")[:48] or "request"


def add(cfg: dict, gid: str, by: str, title: str, why: str, helps: str, kind: str = "image", count: int = 1,
        goes_to: str | None = None, priority: str = "soon", effort: str | None = None, status: str = "open",
        hold_until: str | None = None, rid: str | None = None) -> dict:
    if not by:
        raise ProvideRefused("a request is signed — say who is asking")
    if not str(title).strip() or not str(why).strip() or not str(helps).strip():
        raise ProvideRefused("a request needs a title, why the forge can't make it, and what would help")
    if kind not in KINDS:
        raise ProvideRefused(f"kind is one of {', '.join(KINDS)}")
    if priority not in orders.PRIORITIES:
        raise ProvideRefused(f"priority is one of {', '.join(orders.PRIORITIES)}")
    if status not in STATUSES:
        raise ProvideRefused(f"status is one of {', '.join(STATUSES)}")
    rows = load(cfg, gid)
    rid = _slug(rid or title)
    base, n = rid, 1
    while any(r["id"] == rid for r in rows):
        n += 1
        rid = f"{base}_{n}"
    r = {"id": rid, "title": " ".join(str(title).split()), "why": str(why).strip(), "helps": str(helps).strip(),
         "kind": kind, "count": max(1, int(count or 1)), "goes_to": goes_to or f"reference/provided/{rid}",
         "priority": priority, "effort": effort or "ten minutes", "by": by,
         "added": settings.now().isoformat(timespec="seconds"), "status": status}
    if hold_until:
        r["hold_until"] = str(hold_until)
    rows.append(r)
    _save(cfg, gid, rows)
    log.info("provide: %s added request %s (%s)", by, rid, status)
    return r


def set_status(cfg: dict, gid: str, rid: str, status: str) -> dict:
    if status not in STATUSES:
        raise ProvideRefused(f"status is one of {', '.join(STATUSES)}")
    rows = load(cfg, gid)
    for r in rows:
        if r["id"] == rid:
            r["status"] = status
            if status != "on_hold":
                r.pop("hold_until", None)
            _save(cfg, gid, rows)
            return r
    raise FileNotFoundError(rid)


def _filed(root: Path) -> dict[str, dict]:
    """request id → its work order (any status), from the game's work orders."""
    out: dict[str, dict] = {}
    for _f, o in orders._all(root):
        if o.get("provide"):
            out[str(o["provide"])] = o
    return out


def _detail(r: dict) -> str:
    return f"Why the forge can't make it: {r['why']}\n\nWhat would help: {r['helps']}"


def sync(cfg: dict, gid: str) -> dict:
    """File every open, not-yet-filed request as a work order for the game's owner. Idempotent: a request is filed once,
    whatever later happens to its order. Returns {filed: [ids], unreachable: bool}."""
    root = games.game_root(cfg, gid)
    if not root or not root.is_dir():
        return {"filed": [], "unreachable": True}
    rows = load(cfg, gid)
    if not rows:
        return {"filed": [], "unreachable": False}
    owner = str(games.game_cfg(cfg, gid).get("owner") or "").strip()
    if not owner:
        log.warning("provide: %s has no owner in forge.game.json — nothing filed", gid)
        return {"filed": [], "unreachable": False, "no_owner": True}
    have = _filed(root)
    filed = []
    for r in rows:
        if r.get("status") != "open" or r["id"] in have:
            continue
        try:
            orders.add(root, r.get("by") or "Claude", owner, f"Picture needed: {r['title']}", detail=_detail(r),
                       priority=r.get("priority") or "soon", wants={"kind": r.get("kind") or "image", "count": r.get("count") or 1},
                       goes_to=r.get("goes_to") or f"reference/provided/{r['id']}", effort=r.get("effort"),
                       extra={"provide": r["id"]})
            filed.append(r["id"])
        except ValueError as e:
            log.warning("provide: could not file %s: %s", r["id"], e)
    if filed:
        log.info("provide: filed %d request(s) for %s: %s", len(filed), owner, ", ".join(filed))
    return {"filed": filed, "unreachable": False}


def view(cfg: dict, gid: str, who: str | None, ui_state=None) -> dict:
    """The section: sync, then the open cards (task cards marked provide) and the whole pool with each request's state."""
    from . import tasks
    s = sync(cfg, gid)
    root = games.game_root(cfg, gid)
    have = _filed(root) if root and root.is_dir() else {}
    cards = [c for c in tasks.gather(cfg, gid, who, ui_state) if c.get("provide")] if who else []
    pool = []
    for r in load(cfg, gid):
        o = have.get(r["id"])
        state = r.get("status")
        if o is not None:
            state = {"open": "waiting on you", "done": "provided", "dropped": "dismissed"}.get(o.get("status"), o.get("status"))
        pool.append({**r, "state": state, "received": (o or {}).get("received") or [],
                     "order": (o or {}).get("id")})
    return {"who": who, "cards": cards, "pool": pool, "unreachable": s.get("unreachable", False),
            "filed_now": s.get("filed", [])}
