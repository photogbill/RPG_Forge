"""The daily redo (BUILD 82, 2026-11-19): what did not pass goes back in line once a day, by the forge's own buttons.

The rule it keeps (the art-around-the-clock note, 2026-11-19, rule 3): "What fails a check goes back in line once a day
by itself (the redo step). A thing held three times goes on a short 'needs better words' list for the next Fable, not
around the loop forever." It is the first game's `redo_held_1118.py` (Fable, 2026-11-18) made general, with BUILD 78's
permissions kept:

  failed                                   -> Try again (anyone's; keeps what it had)
  held by the picture gate, loose pieces   -> Make again (anyone's; a fresh picture, the old folder kept, renamed)
  held for its colours, or for a lean      -> Approve everything here (BUILD 78's world_approve_all) — releasing is the
                                              person's, or an assistant's for the person when "<assistant> may approve
                                              for me" is on; signed "<assistant>, for <person>". With it off: left, and said.
  held on purpose, waiting for its words,  -> left alone, and said so
  which way is up unclear, anything else
  put back three times and still not past  -> not put back again: written to NEEDS_BETTER_WORDS.md for the next Claude

    redo.plan(cfg, gid)            what it would do, changing nothing
    redo.do(cfg, gid, who=...)     do it; writes out/3d/world/<game>/REDO_<date>.txt and _redo_counts.json

Nothing here names a game. It approves nothing new: a released thing goes on to Art -> Review & approve as BUILD 78's
button sends it. The thing the world queue has in hand is neither failed nor held, so it is never touched.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from ..log import get

log = get("redo")

TIRED_AFTER = 3                      # put back this many times and still not past: a person (or Claude) rewrites its words
WHO = "Art around the clock (the daily redo, BUILD 82)"


# ------------------------------------------------------------------------------------------------ where things are
def _wd(cfg, gid) -> Path:
    from . import world
    return world.world_dir(cfg, gid)


def counts_path(cfg, gid) -> Path:
    return _wd(cfg, gid) / "_redo_counts.json"


def read_counts(cfg, gid) -> dict:
    p = counts_path(cfg, gid)
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except (OSError, ValueError):
        log.warning("redo: %s could not be read — counting from nothing", p)
        return {}


def _write_json(p: Path, data) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".part")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


# ------------------------------------------------------------------------------------------------ why it is held (BUILD 84)
def reason_of(st: dict) -> str:
    """What keeps a thing back, as one short key that two holds can be compared by: the picture gate's measure (pose, limbs,
    proportions), loose pieces, the error's first words for a failure. Two holds in a row for the same key mean the words
    (or the thing) need changing, not another try."""
    why = " ".join(str(w) for w in (st.get("why") or []))
    if st.get("held_by") == "picture gate":
        keys = [k for k in ("limbs", "pose", "proportions") if f"{k}:" in why.replace("—", ":").replace(" - ", ":")]
        return "picture gate: " + (", ".join(keys) or "missed")
    if why.startswith("Loose pieces") or "Loose pieces" in why:
        return "loose pieces"
    if st.get("state") == "failed":
        return "failed: " + str(st.get("error") or "")[:60]
    return (why or "held")[:60]


# ------------------------------------------------------------------------------------------------ what it would do
def plan(cfg, gid, counts: dict | None = None) -> dict:
    """{"again": [...], "fresh": [...], "release": {"count", "lines", "groups"}, "left": [(id, why)], "tired": [...]}"""
    from . import world
    counts = read_counts(cfg, gid) if counts is None else counts
    items, _ = world.merged(cfg, gid)
    again, fresh, left, tired, hashes = [], [], [], [], {}
    for e in items:
        st = e.get("st") or {}
        state, eid = e.get("state"), e["id"]
        if e.get("superseded_by"):
            continue
        why = [str(w) for w in (st.get("why") or [])]
        if e.get("needs_words") or e.get("hold"):
            if state in ("failed", "held"):
                left.append((eid, "held on purpose, or waiting for its words"))
            continue
        if state == "failed":
            target = again
        elif state != "held":
            continue
        elif st.get("held_by") == "picture gate" or any(w.startswith("Loose pieces") for w in why):
            target = fresh
        else:
            continue                 # colours, a lean, which way is up, a real fault: BUILD 78's plan says (below)
        try:
            h = world.making_hash(e)
        except Exception:  # noqa: BLE001 — an entry the hash can't read is counted as it stands
            h = ""
        hashes[eid] = h
        c = counts.get(eid) or {}
        n = int(c.get("n") or 0)
        if c.get("hash") and h and c["hash"] != h:
            n = 0                    # its words (or anything it is made from) changed since: the count starts over
        reason = reason_of(st)
        twice = n >= 1 and c.get("reason") == reason and target is fresh     # BUILD 84: held twice running for one reason
        if n >= TIRED_AFTER or twice:
            tired.append({"id": eid, "kind": e.get("kind"), "words": str(e.get("words") or "")[:160], "times": n + 1 if twice else n,
                          "why": (why[0] if why else (st.get("error") or "no reason written"))[:200], "state": state,
                          "reason": reason, "twice": bool(twice)})
        else:
            target.append(eid)
            hashes[eid + "#reason"] = reason
    release = {"count": 0, "lines": [], "groups": {}, "left_lines": []}
    try:
        from ..suite import approve_all
        wp = approve_all.world_plan(cfg, gid)
        release = {"count": wp["count"], "lines": wp["lines"], "groups": wp["groups"], "left_lines": wp["left"]}
        for eid in wp["groups"].get("unclear") or []:
            left.append((eid, "which way is up is for a person to say"))
        for eid in wp["groups"].get("repair") or []:
            if eid not in fresh and not any(t["id"] == eid for t in tired):
                left.append((eid, "a real fault that is not a loose piece — needs a look"))
    except Exception as ex:  # noqa: BLE001 — the redo still puts back what it can
        log.warning("redo: Approve everything here could not plan (%s)", ex)
        release["error"] = f"{type(ex).__name__}: {ex}"[:300]
    return {"again": again, "fresh": fresh, "release": release, "left": left, "tired": tired, "hashes": hashes}


# ------------------------------------------------------------------------------------------------ doing it
def do(cfg, gid, who: str = WHO, releases: bool = True, approver: str = "Claude Fable", now: datetime | None = None) -> dict:
    """Put back in line what can go, release what the setting allows, list what is tired. Returns a summary dict
    (and writes it, in words, to REDO_<date>.txt beside the world list's report)."""
    from . import world
    now = now or datetime.now()
    counts = read_counts(cfg, gid)
    p = plan(cfg, gid, counts)
    lines = [f"=== the daily redo, {now:%Y-%m-%d %H:%M} ({who}) ==="]
    out = {"at": now.isoformat(timespec="seconds"), "again": [], "fresh": [], "released": [], "release_refused": [],
           "release_skipped": "", "tired": p["tired"], "left": p["left"], "errors": []}

    # 1. releases, through BUILD 78's own button and its own permission
    if releases and p["release"]["count"]:
        try:
            from ..suite import approve_all
            if approve_all.may_approve(cfg, gid, approver):
                r = approve_all.world_approve_all(cfg, gid, approver)
                out["released"] = [d["id"] for d in r.get("done") or []]
                out["release_refused"] = r.get("refused") or []
                lines.append(f"Approve everything here (World list), by Fable's standing rule: {r.get('message')}")
                for d in r.get("done") or []:          # BUILD 84: each thing, and for a body the gain it went at
                    lines.append(f"    {d['id']}: {d.get('what')}" + (f" — {d['how']}" if d.get("how") else ""))
            else:
                out["release_skipped"] = f"\"{approver} may approve for me\" is off — {p['release']['count']} wait for a person"
                lines.append(f"Releases: not done — {out['release_skipped']} (3D -> World list -> Approve everything here).")
        except Exception as ex:  # noqa: BLE001
            out["errors"].append(f"releases: {type(ex).__name__}: {ex}"[:300])
            lines.append(f"Releases: NOT done — {type(ex).__name__}: {ex}"[:300])
    elif not releases and p["release"]["count"]:
        out["release_skipped"] = f"releases switched off for the redo — {p['release']['count']} wait"
        lines.append(f"Releases: {out['release_skipped']}.")

    # 2. failed -> Try again
    if p["again"]:
        try:
            r = world.try_again(cfg, gid, p["again"], who)
            out["again"] = list(r.get("again") or [])
            lines.append(f"Try again (failed): {r.get('message')}  {', '.join(out['again'])}")
        except Exception as ex:  # noqa: BLE001
            out["errors"].append(f"try again: {type(ex).__name__}: {ex}"[:300])
            lines.append(f"Try again: NOT done — {type(ex).__name__}: {ex}"[:300])

    # 3. picture gate / loose pieces -> Make again
    for eid in p["fresh"]:
        try:
            r = world.make_again(cfg, gid, eid, who)
            if r.get("ok"):
                out["fresh"].append(eid)
            lines.append(f"Make again: {r.get('message')}")
        except Exception as ex:  # noqa: BLE001 — one thing's trouble does not stop the rest
            out["errors"].append(f"make again {eid}: {type(ex).__name__}: {ex}"[:300])
            lines.append(f"Make again: {eid} NOT done — {type(ex).__name__}: {ex}"[:300])

    # 4. count what was put back; list what is tired
    stamp = now.isoformat(timespec="seconds")
    for eid, what in [(i, "try again") for i in out["again"]] + [(i, "make again") for i in out["fresh"]]:
        c = counts.get(eid) or {"n": 0, "history": []}
        h = p["hashes"].get(eid, "")
        if c.get("hash") and h and c["hash"] != h:
            c = {"n": 0, "history": list(c.get("history") or [])}
        c["n"] = int(c.get("n") or 0) + 1
        c["hash"] = h
        c["last"] = stamp
        c["reason"] = p["hashes"].get(eid + "#reason", "")           # BUILD 84: what held it this time
        c["history"] = (list(c.get("history") or []) + [{"at": stamp, "what": what}])[-10:]
        counts[eid] = c
    _write_json(counts_path(cfg, gid), counts)
    write_tired(cfg, gid, p["tired"], now)
    if p["tired"]:
        lines.append(f"Not put back again: {len(p['tired'])} — held twice running for the same reason, or {TIRED_AFTER} times; "
                     f"their words need rewriting (NEEDS_BETTER_WORDS.md, for Fable):")
        lines += [f"    {t['id']}: {t.get('reason') or t['why'][:80]}" + (" (twice running)" if t.get("twice") else
                                                                          f" ({t['times']} times)") for t in p["tired"]]
    if p["left"]:
        lines.append(f"Left alone: {len(p['left'])}")
        lines += [f"    {eid}: {why}" for eid, why in p["left"]]
    if not (out["again"] or out["fresh"] or out["released"]):
        lines.append("Nothing needed putting back.")
    out["lines"] = lines
    rep = _wd(cfg, gid) / f"REDO_{now:%Y-%m-%d}.txt"
    rep.parent.mkdir(parents=True, exist_ok=True)
    with open(rep, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n\n")
    out["report"] = str(rep)
    log.info("redo: %d try again, %d make again, %d released, %d tired, %d left, %d errors", len(out["again"]),
             len(out["fresh"]), len(out["released"]), len(p["tired"]), len(p["left"]), len(out["errors"]))
    return out


def write_tired(cfg, gid, tired: list[dict], now: datetime | None = None) -> Path:
    """NEEDS_BETTER_WORDS.md: the short list for the next Claude — each thing, what it is, why it keeps missing."""
    now = now or datetime.now()
    p = _wd(cfg, gid) / "NEEDS_BETTER_WORDS.md"
    head = (f"# Needs better words — {gid}\n\n*Written by the daily redo (BUILD 82; BUILD 84), {now:%Y-%m-%d %H:%M}. Each of "
            f"these was held twice running for the same reason, or put back in line {TIRED_AFTER} times, and still did not pass, "
            f"so the redo stopped putting it back: the same words would fail the same way. Rewrite its words on the world list "
            f"(or change what it is), then Make again in 3D -> World list. The count starts over by itself once its words "
            f"change.*\n\n")
    if not tired:
        body = "Nothing is waiting for better words.\n"
    else:
        body = "| Thing | Kind | Times | Held for | Why it keeps missing | Its words now |\n|---|---|---|---|---|---|\n" + "".join(
            f"| {t['id']} | {t.get('kind') or ''} | {t['times']}{' (twice running)' if t.get('twice') else ''} | "
            f"{str(t.get('reason') or '').replace('|', '/')} | {t['why'].replace('|', '/')} | "
            f"{t['words'].replace('|', '/')} |\n" for t in tired)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(head + body, encoding="utf-8")
    return p
