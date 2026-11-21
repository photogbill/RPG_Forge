"""Approvals made easy (BUILD 78).

✦ William, 2026-11-17 23:36: "this is really confusing me, I need it to be an easy approval system, everything looks
great … I trust your judgement Claude, we're a team, i'm not a boss on this, i'm a coworker." 23:37: "I would rather
notice something wrong to fix later, than to go item by item which takes longer." 23:54: "it was always my intention
that you could approve as well."

Three things, and nothing in them names a game:

1. **Approve everything here.** Every page that holds things for a person — 3D → World list, Art → Review & approve —
   gets one button with the count on it. Before it is pressed the card says, one plain line a group, what will happen
   ("23 bodies go back for their skeleton and motions; nothing is remade"). What it does is what the page's own buttons
   do, one after another (Match and release, Straighten and release, Approve …): no new kind of approval is invented.
2. **An undo a thing.** Every thing the button touched is written in `out/approvals/<game>.jsonl` with its state from
   before; Undo puts that back while the thing is still where the button left it (still waiting in the queue, still
   waiting in Review & approve, approved but not delivered). Once it has moved on, Undo says so plainly and says what to
   do instead. Nothing is deleted, ever: a withdrawn try stays on disk, marked withdrawn.
3. **"<assistant> may approve for me."** A setting a person turns on or off (an assistant can't). With it on, the
   assistants it names may approve on the person's behalf, and their approval is written as "<assistant>, for <person>" — never as
   him. With it off, approving is the person's, as before. A game may say its default (`games/<id>/approvals.json`); the
   person's own choice on this computer (`local/suite.json` → `approvals`) wins. What it covers is approving made things —
   releases, matches, Review & approve. It never covers words: canon, lyrics, rulings and approved text stay the person's.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
from datetime import datetime
from pathlib import Path

from .. import config as cfgmod
from ..log import get

log = get("suite")


class ApproveRefused(ValueError):
    pass


# ------------------------------------------------------------------------------------------------ the setting
def _games(cfg: dict) -> Path:
    from ..threed import world
    return world.games_dir(cfg)


def _out(cfg: dict) -> Path:
    return cfgmod.path_of(cfg, "out") if cfg and "paths" in cfg and "out" in cfg["paths"] else \
        Path((cfg or {}).get("_root") or cfgmod.ROOT) / "out"


def _game_default(cfg: dict, gid: str) -> dict:
    p = _games(cfg) / gid / "approvals.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def setting(cfg: dict, gid: str) -> dict:
    """{"on", "assistants", "for", "where" ('this computer' | 'the game's default' | 'off by default'), "set_by", "set_at",
    "said"}. The person's own choice on this computer wins over the game's default."""
    from . import settings
    g = _game_default(cfg, gid)
    mine = ((settings.load().get("approvals") or {}).get(gid)) or {}
    base = {"on": bool(g.get("assistant_may_approve")), "assistants": [str(a) for a in g.get("assistants") or []],
            "for": str(g.get("for") or g.get("owner") or "the person"), "set_by": g.get("ruled_by"), "set_at": g.get("ruled_at"),
            "where": "the game's default" if g else "off by default", "why": g.get("why")}
    if isinstance(mine, dict) and "on" in mine:
        base.update(on=bool(mine["on"]), set_by=mine.get("by"), set_at=mine.get("at"), where="this computer")
        if mine.get("for"):
            base["for"] = str(mine["for"])
    names = " and ".join(base["assistants"]) or "an assistant"
    base["said"] = (f"{names} may approve for {base['for']} — written as \"{base['assistants'][0] if base['assistants'] else 'Claude'}, "
                    f"for {base['for']}\", never as {base['for']}." if base["on"] else
                    f"Only {base['for']} approves — an assistant marks, proposes or asks.")
    return base


def set_setting(cfg: dict, gid: str, on: bool, who: str | None) -> dict:
    """The person turns it on or off for this computer. An assistant can't — whether an assistant may approve is the
    person's to decide (the same rule as Don't wait for me)."""
    from . import settings
    if not who:
        raise ApproveRefused("say who you are first (top right)")
    if settings.is_assistant(who):
        raise ApproveRefused("whether an assistant may approve is the person's to decide — an assistant can't set it")
    d = settings.load()
    allm = dict(d.get("approvals") or {})
    allm[gid] = {"on": bool(on), "by": who, "at": datetime.now().isoformat(timespec="seconds")}
    settings.update(approvals=allm)
    return setting(cfg, gid)


# ------------------------------------------------------------------------------------------------ concurrence (Opus, 2026-11-20)
# William, 2026-11-20 23:08-23:10: "Go ahead and add Opus to the approval list, but only if i give concurrence" — asked
# which he meant, he chose "Opus approvals need my OK". So the game's approvals.json may name assistants under
# "assistants_with_concurrence": they may approve or deliver only while a concurrence the PERSON opened is live.
# The person opens one with concur.bat (it asks for nothing but a yes); it lasts CONCUR_MINUTES. An assistant must
# never write the concurrence file itself — that would be signing his OK for him.
CONCUR_MINUTES = 30


def _concur_path() -> Path:
    return cfgmod.ROOT / "local" / "approvals_concurrence.json"


def _matches(who: str, names: list) -> bool:
    w = str(who).strip().lower()
    return any(w == a.lower() or w.startswith(a.lower() + " ") or w.startswith(a.lower() + ",") for a in names)


def _concur_names(cfg: dict, gid: str) -> list:
    return [str(a) for a in (_game_default(cfg, gid).get("assistants_with_concurrence") or [])]


def concurrence(cfg: dict, gid: str) -> dict | None:
    """The live concurrence for this game, or None (none opened, or it has run out)."""
    try:
        d = json.loads(_concur_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    c = (d or {}).get(gid) if isinstance(d, dict) else None
    if not isinstance(c, dict):
        return None
    try:
        if datetime.now() >= datetime.fromisoformat(c["until"]):
            return None
    except (KeyError, ValueError, TypeError):
        return None
    return c


def open_concurrence(cfg: dict, gid: str, who: str | None, minutes: int = CONCUR_MINUTES) -> dict:
    """The person concurs: assistants under assistants_with_concurrence may approve for the next `minutes`."""
    from . import settings
    from datetime import timedelta
    if not who:
        raise ApproveRefused("say who you are first")
    if settings.is_assistant(who):
        raise ApproveRefused("concurrence is the person's to give — an assistant can't open it")
    now = datetime.now()
    try:
        d = json.loads(_concur_path().read_text(encoding="utf-8"))
        d = d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        d = {}
    d[gid] = {"by": str(who), "at": now.isoformat(timespec="seconds"),
              "until": (now + timedelta(minutes=int(minutes))).isoformat(timespec="seconds"),
              "for": _concur_names(cfg, gid)}
    _concur_path().parent.mkdir(parents=True, exist_ok=True)
    _concur_path().write_text(json.dumps(d, indent=1), encoding="utf-8")
    log.info("approvals: %s opened a concurrence for %s on %s until %s", who, d[gid]["for"], gid, d[gid]["until"])
    return d[gid]


def close_concurrence(cfg: dict, gid: str) -> None:
    try:
        d = json.loads(_concur_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if isinstance(d, dict) and d.pop(gid, None) is not None:
        _concur_path().write_text(json.dumps(d, indent=1), encoding="utf-8")
        log.info("approvals: concurrence on %s closed", gid)


def may_approve(cfg: dict, gid: str, who: str | None) -> bool:
    from . import settings
    if not who:
        return False
    if not settings.is_assistant(who):
        return True
    s = setting(cfg, gid)
    if s["on"] and _matches(who, s["assistants"]):
        return True
    if _matches(who, _concur_names(cfg, gid)):
        ok = concurrence(cfg, gid) is not None
        if not ok:
            log.info("approvals: %s needs the person's concurrence on %s (concur.bat) — none is live", who, gid)
        return ok
    return False


def signer(cfg: dict, gid: str, who: str | None, what: str = "approving") -> str:
    """The name an approval is written with: a person's own name; an assistant's as "<assistant>, for <person>" when the
    setting lets it; otherwise refused, saying why and how it can be allowed."""
    from . import settings
    if not who:
        raise ApproveRefused(f"say who you are first (top right) — {what} is signed")
    if not settings.is_assistant(who):
        return str(who)
    if ", for " in str(who):                 # already signed on someone's behalf (a second step of the same approval)
        base = str(who).split(", for ")[0]
        if may_approve(cfg, gid, base):
            return str(who)
    if may_approve(cfg, gid, who):
        c = concurrence(cfg, gid) if _matches(who, _concur_names(cfg, gid)) and not (
            setting(cfg, gid)["on"] and _matches(who, setting(cfg, gid)["assistants"])) else None
        if c:
            return f"{who}, for {setting(cfg, gid)['for']} (concurred {c['at'][11:16]})"
        return f"{who}, for {setting(cfg, gid)['for']}"
    if _matches(who, _concur_names(cfg, gid)):
        raise ApproveRefused(f"{what}: {who} may approve only with {setting(cfg, gid)['for']}'s concurrence — "
                             f"run concur.bat to give it (it lasts {CONCUR_MINUTES} minutes)")
    raise ApproveRefused(f"{what} is the person's — an assistant can't do it unless the person turns on "
                         f"\"{(setting(cfg, gid)['assistants'] or ['an assistant'])[0]} may approve for me\" (Settings → Approvals)")


# ------------------------------------------------------------------------------------------------ the undo log
def _log_path(cfg: dict, gid: str) -> Path:
    return _out(cfg) / "approvals" / f"{gid}.jsonl"


def _append(cfg: dict, gid: str, rec: dict) -> dict:
    p = _log_path(cfg, gid)
    p.parent.mkdir(parents=True, exist_ok=True)
    rec = {"uid": f"{datetime.now():%m%d%H%M%S}-{secrets.token_hex(3)}", "at": datetime.now().isoformat(timespec="seconds"), **rec}
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    return rec


def history(cfg: dict, gid: str, limit: int = 60) -> list[dict]:
    """The newest approvals first, each with whether it has been undone."""
    p = _log_path(cfg, gid)
    if not p.exists():
        return []
    recs, undone = [], set()
    for ln in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if r.get("kind") == "undo":
            undone.add(r.get("of"))
        else:
            recs.append(r)
    out = []
    for r in reversed(recs):
        r = {k: v for k, v in r.items() if k not in ("before", "before_entry", "before_extra")}
        r["undone"] = r["uid"] in undone
        out.append(r)
        if len(out) >= limit:
            break
    return out


def _find(cfg: dict, gid: str, uid: str) -> tuple[dict | None, bool]:
    p = _log_path(cfg, gid)
    rec, undone = None, False
    if p.exists():
        for ln in p.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if r.get("uid") == uid:
                rec = r
            if r.get("kind") == "undo" and r.get("of") == uid:
                undone = True
    return rec, undone


def _hash(d) -> str:
    return hashlib.sha1(json.dumps(d, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:12]


# ------------------------------------------------------------------------------------------------ 3D → World list
COLOUR = ("colour", "colour_face")


def world_plan(cfg: dict, gid: str, items: list | None = None) -> dict:
    """What Approve everything here would do on the World list: groups, a count and one plain line each.

    It approves what the forge can put right by itself — colours (matched, or as made where the entry says the match is
    worse: "release": "as made") and a lean (turned level, then its colours matched if they were the rest of it). A real
    fault is not an approval and is left, named, with what it needs: a loose piece, a picture the gate refused (no body
    was made from it yet), a thing whose up only a person can say. ◆ BUILD 78's reading — the person's to widen."""
    from ..threed import world
    if items is None:                       # BUILD 84 part 4: whoever has just read the list hands it over
        items, _ = world.merged(cfg, gid)
    groups = {k: [] for k in ("match_bodies", "match_things", "as_made_bodies", "as_made_things", "straighten", "gate",
                              "repair", "unclear", "failed")}
    for e in items:
        st = e["st"]
        if e.get("superseded_by") or e["hold"]:
            continue
        if e["state"] == "failed":
            groups["failed"].append(e["id"])
            continue
        if e["state"] != "held":
            continue
        bad = {r.get("check") for r in st.get("check_results") or [] if not r.get("ok")}
        lvl = world._leans(st)
        if st.get("held_by") == "picture gate":
            groups["gate"].append(e["id"])
        elif world._only_colour(st):
            as_made = str(e.get("release") or "").lower().replace("_", " ") == "as made"
            groups[("as_made_" if as_made else "match_") + ("bodies" if e["kind"] == "body" else "things")].append(e["id"])
        elif lvl and "isn't clear" in (lvl.get("line") or ""):
            groups["unclear"].append(e["id"])
        elif lvl and "level" in bad and bad <= {"level", *COLOUR}:
            groups["straighten"].append(e["id"])
        else:
            groups["repair"].append(e["id"])
    n = lambda k: len(groups[k])
    s = lambda k, one, many: one if n(k) == 1 else many
    lines = []
    if n("match_bodies"):
        lines.append(f"{n('match_bodies')} bod{s('match_bodies', 'y goes', 'ies go')} back for {s('match_bodies', 'its', 'their')} "
                     "skeleton and motions with one gain for the whole colour picture, worked out from the body as made "
                     "(brightness only, never a hue — where one gain can't bring a body inside the check, it goes at that gain "
                     "and the reason is written with it); nothing is remade.")
    if n("as_made_bodies"):
        lines.append(f"{n('as_made_bodies')} bod{s('as_made_bodies', 'y goes', 'ies go')} back for {s('as_made_bodies', 'its', 'their')} "
                     "skeleton and motions with the colours as made (the match was worse); nothing is remade.")
    if n("match_things"):
        lines.append(f"{n('match_things')} prop{s('match_things', ' or building takes its', 's and buildings take their')} matched "
                     "colours and go to Review & approve.")
    if n("as_made_things"):
        lines.append(f"{n('as_made_things')} prop{s('as_made_things', ' goes', 's go')} to Review & approve with the colours as made.")
    if n("straighten"):
        lines.append(f"{n('straighten')} that lean{s('straighten', 's', '')} as a whole {s('straighten', 'is', 'are')} turned level "
                     "(and {0} colours matched where that is the rest of it) and go{1} to Review & approve.".format(
                         s('straighten', 'its', 'their'), s('straighten', 'es', '')))
    left = []
    if n("gate"):
        left.append(f"{n('gate')} held by the picture gate — no body was made yet; each needs a look (make it from the last "
                    "picture, or make it again).")
    if n("repair"):
        left.append(f"{n('repair')} with a real fault (a loose piece and the like) — not an approval; each needs a look.")
    if n("unclear"):
        left.append(f"{n('unclear')} need{s('unclear', 's', '')} you to say which way is up.")
    if n("failed"):
        left.append(f"{n('failed')} failed while being made — not an approval; each has Try again or Make again.")
    total = sum(n(k) for k in ("match_bodies", "match_things", "as_made_bodies", "as_made_things", "straighten"))
    return {"page": "world", "count": total, "groups": groups, "lines": lines, "left": left,
            "nothing": "Nothing on the World list is waiting for a person." if not total else None}


def _snap_world(cfg, gid, eid) -> dict:
    from ..threed import world
    st = world.read_state(cfg, gid, eid)
    gate = world.item_dir(cfg, gid, eid) / "pictures" / f"{eid}.gate.json"
    extra = {"gate_json": json.loads(gate.read_text(encoding="utf-8")) if gate.exists() else None}
    return {"before": st, "before_extra": extra}


def world_approve_all(cfg: dict, gid: str, who: str | None, ids: list[str] | None = None, env=None, blender_python=None) -> dict:
    """Approve everything here, on the World list: each group by the page's own function. `ids` limits it to those
    (an untick on the card). Every thing touched gets a line in the undo log."""
    from ..threed import world
    by = signer(cfg, gid, who, "approving everything here")
    plan = world_plan(cfg, gid)
    pick = set(world.slug(i) for i in ids) if ids else None
    want = lambda k: [i for i in plan["groups"][k] if pick is None or i in pick]
    done, refused, batch = [], [], f"{datetime.now():%m%d%H%M%S}-{secrets.token_hex(2)}"

    def run(group, fn, label):
        todo = want(group)
        if not todo:
            return
        snaps = {i: _snap_world(cfg, gid, i) for i in todo}
        try:
            r = fn(todo)
        except Exception as ex:  # noqa: BLE001 — a group's trouble is said and the other groups still go
            log.warning("approve: %s failed (%s)", label, ex)
            r = {"released": [], "refused": [{"id": i, "why": f"{type(ex).__name__}: {ex}"[:300]} for i in todo]}
        for d in r.get("released") or []:
            i = d["id"]
            st = world.read_state(cfg, gid, i)
            rec = _append(cfg, gid, {"kind": "approve", "page": "world", "batch": batch, "id": i, "what": label, "by": by,
                                     "after_state": st.get("state"), "after_try": st.get("try"), "after_hash": _hash(st),
                                     **({"how": d["how"]} if d.get("how") else {}), **snaps[i]})
            done.append({"id": i, "what": label, "uid": rec["uid"], "to": st.get("state"), **({"how": d["how"]} if d.get("how") else {})})
        for x in (r.get("refused") or []) + (r.get("still_held") or []):
            refused.append({"id": x["id"], "why": x.get("why") or x.get("message")})

    run("match_bodies", lambda t: world.match_and_release(cfg, gid, t, by, env=env, blender_python=blender_python), "Match and release")
    run("match_things", lambda t: world.match_and_release(cfg, gid, t, by, env=env, blender_python=blender_python), "Match and release")
    run("as_made_bodies", lambda t: world.release_as_made(cfg, gid, t, by, env=env, blender_python=blender_python), "Release as made")
    run("as_made_things", lambda t: world.release_as_made(cfg, gid, t, by, env=env, blender_python=blender_python), "Release as made")

    def straighten_all(t):
        out = {"released": [], "refused": []}
        entries = {e["id"]: e for e in world.load(cfg, gid)[0]}
        for i in t:
            try:
                r = world.straighten(cfg, gid, i, by, env=env, blender_python=blender_python)
                if not r.get("ok") and world._only_colour(world.read_state(cfg, gid, i)):   # its colours were the rest of it
                    st = world.read_state(cfg, gid, i)
                    st["colour_offer"] = None          # the old offer was matched on the leaning model: match the level one
                    world.write_state(cfg, gid, i, st)
                    as_made = str((entries.get(i) or {}).get("release") or "").lower().replace("_", " ") == "as made"
                    r = (world.release_as_made if as_made else world.match_and_release)(cfg, gid, [i], by, env=env,
                                                                                       blender_python=blender_python)
                    r = {"ok": bool(r["released"]), "message": r["message"]}
                (out["released"] if r.get("ok") else out["refused"]).append({"id": i, "why": r.get("message")})
            except Exception as ex:  # noqa: BLE001 — one thing's trouble does not stop the rest
                out["refused"].append({"id": i, "why": f"{type(ex).__name__}: {ex}"[:300]})
        return out

    run("straighten", straighten_all, "Straighten and release")
    _journal(cfg, gid, by, f"Approve everything here (World list): {len(done)} released"
             + (f", {len(refused)} not" if refused else ""), batch)
    msg = (f"{len(done)} released, signed {by}." if done else "Nothing was released.") + \
          (" Not: " + "; ".join(f"{x['id']} ({x['why']})" for x in refused[:8]) if refused else "")
    return {"ok": not refused, "done": done, "refused": refused, "batch": batch, "by": by, "message": msg}


def _undo_world(cfg, gid, rec, by) -> dict:
    from ..threed import world
    i = rec["id"]
    st = world.read_state(cfg, gid, i)
    if _hash(st) != rec.get("after_hash"):
        moved = st.get("state")
        if moved == "making":
            return {"ok": False, "message": f"{i} is being made right now — wait for it, then turn it down in Review & approve if it's wrong."}
        if not (moved == rec.get("after_state") == "wanted"):
            return {"ok": False, "message": f"{i} has moved on since ({moved}) — " + (
                "turn it down in Art → Review & approve, or press Make again on the World list." if moved in ("made", "held")
                else "see it on the World list.")}
    if rec.get("after_try"):
        world.withdraw_try(cfg, gid, i, rec["after_try"], by, "undone: " + rec.get("what", "approval"))
    for kept, path in rec.get("restore_files") or []:          # BUILD 84: a file the approval changed in place goes back
        src, dst = world.root_of(cfg) / kept, world.root_of(cfg) / path
        if src.exists():
            import shutil
            shutil.copyfile(src, dst)
    before = dict(rec.get("before") or {})
    before.setdefault("history", [])
    before["history"] = list(before["history"]) + [{"at": world._now(), "state": f"undone ({rec.get('what')})", "by": by}]
    world.write_state(cfg, gid, i, before)
    g = (rec.get("before_extra") or {}).get("gate_json")
    if g is not None:
        world._write(world.item_dir(cfg, gid, i) / "pictures" / f"{i}.gate.json", g)
    return {"ok": True, "message": f"{i} is back as it was before {rec.get('what')} ({before.get('state') or 'wanted'})."}


def world_one_gain(cfg: dict, gid: str, who: str | None, ids: list[str], note: str = "") -> dict:
    """BUILD 84 part 1.5: bodies whose release put their colours through a curve, put right at one gain (world.one_gain_now)
    — released again if not yet on their skeleton, the colour picture swapped if made. Signed as approvals are, each with
    a line in the undo log (and the moving copy as it was, for Undo to put back)."""
    from ..threed import world
    by = signer(cfg, gid, who, "putting released bodies right at one gain")
    batch = f"{datetime.now():%m%d%H%M%S}-{secrets.token_hex(2)}"
    done, left = [], []
    for i in [world.slug(x) for x in ids]:
        snap = _snap_world(cfg, gid, i)
        try:
            r = world.one_gain_now(cfg, gid, i, by)
        except Exception as ex:  # noqa: BLE001 — one thing's trouble does not stop the rest
            r = {"ok": False, "id": i, "why": f"{type(ex).__name__}: {ex}"[:300]}
        if not r.get("ok"):
            left.append({"id": i, "why": r.get("why")})
            continue
        st = world.read_state(cfg, gid, i)
        rec = _append(cfg, gid, {"kind": "approve", "page": "world", "batch": batch, "id": i, "what": "Put right at one gain",
                                 "by": by, "how": r.get("how"), "note": note or None, "restore_files": r.get("files") or [],
                                 "after_state": st.get("state"), "after_try": st.get("try"), "after_hash": _hash(st), **snap})
        done.append({"id": i, "uid": rec["uid"], "to": r.get("to"), "how": r.get("how")})
    _journal(cfg, gid, by, f"Put right at one gain (BUILD 84): {len(done)} bodies" + (f", {len(left)} left" if left else ""), batch)
    msg = (f"{len(done)} put right at one gain, signed {by}." if done else "Nothing was put right.") + \
          (" Left: " + "; ".join(f"{x['id']} ({x['why']})" for x in left) if left else "")
    return {"ok": not left, "done": done, "left": left, "batch": batch, "by": by, "message": msg}


# ------------------------------------------------------------------------------------------------ Art → Review & approve
def _pictures_waiting(cfg: dict, gid: str, state) -> list[dict]:
    if state is None:
        return []
    from . import production
    try:
        return production.review(cfg, gid, state, limit=400)["waiting"]
    except Exception as ex:  # noqa: BLE001
        log.warning("approve: the pictures waiting could not be read (%s)", ex)
        return []


def review_plan(cfg: dict, gid: str, state=None) -> dict:
    """What Approve everything here would do on Review & approve: the 3D models waiting (each held for Deliver after its
    licence check), and the pictures waiting — the newest take for each wanted thing (older takes for the same thing are
    left: only one picture can be a wanted thing's). A kit is left for its table to be checked; a model or picture whose
    tools are not all known commercial-OK is left and said."""
    from . import threed
    r3 = threed.review_list(cfg, gid)
    models = [x["id"] for x in r3["waiting"] if x.get("commercial_ok")]
    not_ok = [x["id"] for x in r3["waiting"] if not x.get("commercial_ok")]
    pics, older, kits = [], [], []
    seen = set()
    for p in _pictures_waiting(cfg, gid, state):
        if p.get("set"):
            kits.append(p["id"])
            continue
        w = p.get("wanted")
        if not w:
            continue
        if w in seen:
            older.append(p["id"])
            continue
        seen.add(w)
        pics.append({"id": p["id"], "wanted": w})
    lines = []
    if models:
        lines.append(f"{len(models)} 3D model{'' if len(models) == 1 else 's'} {'is' if len(models) == 1 else 'are'} approved and held "
                     "for Deliver (the licence check runs on each; nothing goes into the game until Deliver).")
    if pics:
        lines.append(f"{len(pics)} picture{'' if len(pics) == 1 else 's'} {'is' if len(pics) == 1 else 'are'} approved — the newest take "
                     "for each wanted thing — and held for Deliver.")
    left = []
    if older:
        left.append(f"{len(older)} older take{'' if len(older) == 1 else 's'} of the same wanted things {'is' if len(older) == 1 else 'are'} left — not chosen.")
    if kits:
        left.append(f"{len(kits)} kit{'' if len(kits) == 1 else 's'} {'needs its' if len(kits) == 1 else 'need their'} table checked — left as {'it is' if len(kits) == 1 else 'they are'}.")
    if not_ok:
        left.append(f"{len(not_ok)} model{'' if len(not_ok) == 1 else 's'} made with a tool not known commercial-OK — left.")
    total = len(models) + len(pics)
    return {"page": "review", "count": total, "models": models, "pictures": pics, "lines": lines, "left": left,
            "nothing": "Nothing in Review & approve is waiting for a person." if not total else None}


def review_approve_all(cfg: dict, gid: str, who: str | None, state=None, ids: list[str] | None = None) -> dict:
    from . import threed
    from ..night4 import deliver as dl
    by = signer(cfg, gid, who, "approving everything here")
    plan = review_plan(cfg, gid, state)
    pick = set(ids) if ids else None
    done, refused, batch = [], [], f"{datetime.now():%m%d%H%M%S}-{secrets.token_hex(2)}"
    appr_p = threed.tdir(cfg, gid) / "approved.json"
    for tid in plan["models"]:
        if pick is not None and tid not in pick:
            continue
        try:
            t = threed.load_try(cfg, gid, tid)
            key = f"{t['kind']}/{t['who']}"
            before_entry = threed._read(appr_p, {}).get(key)
            threed.decide(cfg, gid, tid, "approve", by, note="Approve everything here")
            rec = _append(cfg, gid, {"kind": "approve", "page": "review", "what": "Approve (3D model)", "batch": batch, "id": tid,
                                     "key": key, "by": by, "before_entry": before_entry})
            done.append({"id": tid, "what": "3D model", "uid": rec["uid"]})
        except Exception as ex:  # noqa: BLE001 — the licence gate and a missing file refuse with their own words
            refused.append({"id": tid, "why": str(ex)[:300]})
    held_before = dl.held(cfg, gid)
    for p in plan["pictures"]:
        if pick is not None and p["id"] not in pick:
            continue
        try:
            dl.hold(cfg, p["id"], p["wanted"], gid)
            rec = _append(cfg, gid, {"kind": "approve", "page": "review", "what": "Approve (picture)", "batch": batch, "id": p["id"],
                                     "wanted": p["wanted"], "by": by, "before_entry": held_before.get(p["wanted"])})
            _sign(cfg, gid, by, "approve", p["wanted"], note=f"approved {p['id']} — held for delivery (Approve everything here)")
            done.append({"id": p["id"], "what": "picture", "uid": rec["uid"]})
        except Exception as ex:  # noqa: BLE001 — the licence gate refuses with its own words
            refused.append({"id": p["id"], "why": str(ex)[:300]})
    _journal(cfg, gid, by, f"Approve everything here (Review & approve): {len(done)} approved" + (f", {len(refused)} not" if refused else ""), batch)
    msg = (f"{len(done)} approved, signed {by} — held for Deliver." if done else "Nothing was approved.") + \
          (" Not: " + "; ".join(f"{x['id']} ({x['why']})" for x in refused[:8]) if refused else "")
    return {"ok": not refused, "done": done, "refused": refused, "batch": batch, "by": by, "message": msg}


def _undo_review(cfg, gid, rec, by) -> dict:
    from . import threed
    from ..night4 import deliver as dl
    if rec.get("what") == "Approve (3D model)":
        p = threed.tdir(cfg, gid) / "approved.json"
        appr = threed._read(p, {})
        cur = appr.get(rec["key"]) or {}
        if cur.get("try") != rec["id"]:
            return {"ok": False, "message": f"{rec['key']} has been approved again since (try {cur.get('try')}) — nothing undone."}
        if cur.get("delivered"):
            return {"ok": False, "message": f"{rec['key']} is already in the game — Deliver keeps what it replaced in out/_replaced/; "
                                            "put the old one back from there, or turn this one down and deliver its successor."}
        if rec.get("before_entry"):
            appr[rec["key"]] = rec["before_entry"]
        else:
            appr.pop(rec["key"], None)
        threed._write(p, appr)
        t = threed.load_try(cfg, gid, rec["id"])
        t["review"] = {**(t.get("review") or {}), "state": "waiting", "undone_by": by, "undone_at": datetime.now().isoformat(timespec="seconds")}
        threed._save_try(cfg, gid, t)
        return {"ok": True, "message": f"{rec['key']} is waiting in Review & approve again."}
    h = dl.held(cfg, gid)
    cur = h.get(rec["wanted"]) or {}
    if cur.get("job_id") != rec["id"]:
        return {"ok": False, "message": f"{rec['wanted']} is not held with {rec['id']} any more (delivered, or another take was "
                                        "approved since) — nothing undone."}
    if rec.get("before_entry"):
        h[rec["wanted"]] = rec["before_entry"]
    else:
        h.pop(rec["wanted"], None)
    dl._write(dl._gdir(cfg, gid) / "held.json", h)
    return {"ok": True, "message": f"{rec['wanted']}: {rec['id']} is waiting for a verdict again."}


# ------------------------------------------------------------------------------------------------ both pages
def plan(cfg: dict, gid: str, page: str, state=None) -> dict:
    p = world_plan(cfg, gid) if page == "world" else review_plan(cfg, gid, state)
    p["setting"] = setting(cfg, gid)
    p["recent"] = [r for r in history(cfg, gid, 80) if r.get("page") == page][:40]
    return p


def approve_everything(cfg: dict, gid: str, page: str, who: str | None, state=None, ids: list[str] | None = None,
                       env=None, blender_python=None) -> dict:
    if page == "world":
        return world_approve_all(cfg, gid, who, ids=ids, env=env, blender_python=blender_python)
    if page == "review":
        return review_approve_all(cfg, gid, who, state=state, ids=ids)
    raise ApproveRefused(f"there is no page called {page}")


def undo(cfg: dict, gid: str, uid: str, who: str | None) -> dict:
    """Undo one thing an approval touched. Anyone who may approve may undo (an assistant under the setting signs as one)."""
    by = signer(cfg, gid, who, "undoing an approval")
    rec, undone = _find(cfg, gid, uid)
    if rec is None:
        return {"ok": False, "message": "there is no such approval in the log"}
    if undone:
        return {"ok": False, "message": f"{rec.get('id')} was undone already"}
    r = _undo_world(cfg, gid, rec, by) if rec.get("page") == "world" else _undo_review(cfg, gid, rec, by)
    if r["ok"]:
        _append(cfg, gid, {"kind": "undo", "of": uid, "id": rec.get("id"), "page": rec.get("page"), "by": by})
        _journal(cfg, gid, by, f"undid {rec.get('what')} of {rec.get('id')}", rec.get("batch"))
    return r


def _sign(cfg, gid, who, kind, obj, note=""):
    from .threed import _sign as s
    s(cfg, gid, who, kind, obj, note=note)


def _journal(cfg, gid, by, note, batch=None):
    _sign(cfg, gid, by, "approve", "approvals", note + (f" (batch {batch})" if batch else ""))


# ------------------------------------------------------------------------------------------------ the suite's actions
def act(cfg: dict, gid: str, action: str, body: dict, who: str | None, state=None) -> dict:
    """approve_all · approve_undo · approve_setting (server.py routes every approve_* action here)."""
    try:
        if action == "approve_all":
            from ..threed.env import from_cfg
            page = str(body.get("page") or "")
            ids = [str(i) for i in body.get("ids") or []] or None
            return approve_everything(cfg, gid, page, who, state=state, ids=ids, env=from_cfg(cfg))
        if action == "approve_undo":
            return undo(cfg, gid, str(body.get("uid") or ""), who)
        if action == "approve_setting":
            s = set_setting(cfg, gid, bool(body.get("on")), who)
            _journal(cfg, gid, who, ("turned on" if s["on"] else "turned off") + f" \"{s['assistants'][0]} may approve for me\"")
            return {"ok": True, "setting": s, "message": s["said"]}
    except ApproveRefused as e:
        return {"ok": False, "message": str(e)}
    return {"ok": False, "message": f"unknown action {action}"}
