"""Don't wait for me — the owner's standing instruction for questions nobody has answered yet (2026-11-17).

The owner: "an option … that lets me automatically select the default options or defer to [an assistant], that way we
don't get bogged down by my schedule. We can always fix things or tweak them later." No name is built in: who the
questions are left to is whoever the person picks from the game's own correspondents.

**The setting** (this install, `local/suite.json` → `nowait`; a person sets it, never an assistant):

* `wait`     — as before: an open question waits for its answer.
* `default`  — an open question an assistant asked takes the answer its sender said it would go with: its `default`
               ("what the sender does if it isn't answered"), or — with no default — its `recommendation`. A question
               with neither is left to the named assistant (as under `defer`) — or, with nobody named, waits.
* `defer`    — every open question is left to the named assistant (`defer_to`, the person's pick) to decide.

`after_hours` is how long a letter waits for the person first (0 = not at all).

**What a stand-in answer is.** One more letter on the question's own thread, addressed to the person, carrying an
ordinary `answers` block whose entries are marked `stand_in` ("default" | "recommendation" | "deferred") and `for`
(the person it stands in for). Because it is an ordinary answer, the question is no longer open anywhere — Tasks, the
badges, Home. Because it is marked, it is never the person's ruling: the rulings book lists it as *provisional*, the
letter says so, and **the person's own answer, whenever it comes, replaces it** (a later answer always wins;
mail.answered_ids). A default the forge takes is signed by the question's sender — it is that sender's stated
fallback — and its data change (applies_to) goes through the safe-save path in the sender's name, so anything a person
approved becomes a proposal to them, never an overwrite. Nobody's name is put on words they didn't choose: the letter
says the forge wrote it and under whose instruction.

**Left to an assistant.** `<game_root>/mail/deferred.json` says which open questions are whose call, and a work order
(priority now) puts it on that assistant's list. `decide()` is how they answer — a stand-in letter in their own name.
A question the person answers themself in the meantime simply stops being deferred (`tidy()`).

What this does not touch: a task that needs a file only the person has, pictures waiting for approval, a music brief,
a build the game's queue marks as waiting. Those still wait. Questions "parked" with *talk to me* / *later* are left
alone by the sweep too — the person said they want a say.
"""
from __future__ import annotations
import json, os
from datetime import datetime
from pathlib import Path

from ..log import get as _log
from . import journal, mail, orders, settings

log = _log("suite")
KEY = "nowait"
MODES = ("wait", "default", "defer")
HOURS = (0, 4, 12, 24, 48)
WORD = {"default": "the default", "recommendation": "the recommendation", "deferred": "decided"}


class NoWaitRefused(ValueError):
    """The rule said no; nothing was written."""


# ---------------------------------------------------------------- the setting
def get(path: Path | None = None) -> dict:
    d = settings.load(path).get(KEY)
    d = d if isinstance(d, dict) else {}
    try:
        hours = max(0.0, float(d.get("after_hours") or 0))
    except (TypeError, ValueError):
        hours = 0.0
    return {"mode": d.get("mode") if d.get("mode") in MODES else "wait", "after_hours": hours,
            "defer_to": " ".join(str(d.get("defer_to") or "").split()) or None, "person": d.get("person") or None,
            "set_at": d.get("set_at") or None}


def set_mode(who: str | None, mode: str, after_hours=None, defer_to: str | None = None, path: Path | None = None,
             now: datetime | None = None) -> dict:
    """A person's standing instruction. `who` becomes the person the forge stands in for."""
    if not who:
        raise NoWaitRefused("set who you are first — this is your standing instruction, and it is signed")
    if settings.is_assistant(who):
        raise NoWaitRefused("whether questions wait for a person is that person's to decide — an assistant can't set it")
    if mode not in MODES:
        raise NoWaitRefused(f"the choices are {', '.join(MODES)}")
    cur = get(path)
    try:
        hours = cur["after_hours"] if after_hours is None or after_hours == "" else max(0.0, float(after_hours))
    except (TypeError, ValueError):
        raise NoWaitRefused("how long to wait first is a number of hours")
    to = " ".join(str(defer_to or cur["defer_to"] or "").split()) or None
    if to and not settings.is_assistant(to):
        raise NoWaitRefused(f"questions can be left to an assistant, not to {to}")
    if mode == "defer" and not to:
        raise NoWaitRefused("pick who the questions are left to first (the list beside the buttons)")
    now = now or settings.now()
    d = {"mode": mode, "after_hours": hours, "defer_to": to, "person": who, "set_at": now.isoformat(timespec="seconds")}
    settings.update(path, **{KEY: d})
    log.info("nowait: %s set '%s' (after %sh, left to %s)", who, mode, hours, to)
    return get(path)


def describe(st: dict) -> str:
    after = "" if not st["after_hours"] else f" once a letter has waited {st['after_hours']:g} h"
    if st["mode"] == "default":
        rest = f"goes to {st['defer_to']}" if st["defer_to"] else "still waits (nobody is named to leave it to)"
        return f"open questions take their default{after}; one with no default {rest}"
    if st["mode"] == "defer":
        return f"open questions are left to {st['defer_to']}{after}"
    return "open questions wait for their answer"


# ---------------------------------------------------------------- which questions are whose call
def _deferred_path(root: Path) -> Path:
    return mail.mail_dir(root) / "deferred.json"


def deferred(root: Path) -> dict:
    """{"<letter id>#<question id>": {"to", "for", "at", "how"}} — as written; `pending()` is the live view."""
    try:
        d = json.loads(_deferred_path(root).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_deferred(root: Path, d: dict) -> None:
    p = _deferred_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(d, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, p)


def _key(letter_id: str, q: dict) -> str:
    return f"{letter_id}#{q.get('id')}"


def _parked(letters) -> set[str]:
    """Questions someone answered with "talk to me" or "later" (and nothing since)."""
    out = set()
    for l in letters:
        for a in l.answers or []:
            if isinstance(a, dict) and (a.get("talk") or a.get("later")):
                out.add(f"{a.get('letter') or l.h('in_reply_to')}#{a.get('id')}")
    return out


def _same(a: str | None, b: str | None) -> bool:
    return " ".join(str(a or "").lower().split()) == " ".join(str(b or "").lower().split())


def pending(root: Path, who: str | None = None, letters=None) -> list[dict]:
    """The questions left to an assistant and still open, oldest first: one row per letter —
    {"letter", "subject", "from", "to", "for", "at", "questions": [the question dicts]}. `who` narrows to one name."""
    letters = mail.all_letters(root) if letters is None else letters
    done = mail.answered_ids(letters)
    by_id = {l.id: l for l in letters}
    rows: dict[tuple, dict] = {}
    for key, d in deferred(root).items():
        lid, _, qid = key.partition("#")
        l = by_id.get(lid)
        if l is None or key in done or (who and not _same(d.get("to"), who)):
            continue
        q = next((x for x in l.questions if str(x.get("id")) == qid), None)
        if q is None:
            continue
        r = rows.setdefault((lid, d.get("to")), {"letter": lid, "subject": l.subject, "from": l.sender, "to": d.get("to"),
                                                 "for": d.get("for"), "at": d.get("at"), "questions": []})
        r["questions"].append(q)
        r["at"] = min(str(r["at"] or ""), str(d.get("at") or "")) or r["at"]
    return sorted(rows.values(), key=lambda r: str(r["at"] or ""))


def deferred_keys(root: Path) -> dict[str, dict]:
    """Every deferral on file (answered or not) — for a page that already knows which questions are open."""
    return deferred(root)


# ---------------------------------------------------------------- what a question's own fallback is
def resolution(q: dict) -> dict | None:
    """What the question's sender said they'd go with: {"how": "default"|"recommendation", "choice"|"text": …}, or None.
    When the words are one of the question's choices it is that choice (so applies_to takes effect); otherwise they are
    kept as words, which change nothing in the data."""
    labels = [(c.get("label") if isinstance(c, dict) else c) for c in q.get("choices") or []]
    for how in ("default", "recommendation"):
        said = " ".join(str(q.get(how) or "").split())
        if not said:
            continue
        for lab in labels:
            if _same(lab, said) or _same(str(lab).rstrip(".!"), said.rstrip(".!")):
                return {"how": how, "choice": lab}
        return {"how": how, "text": said}
    return None


def _answer_words(a: dict) -> str:
    return str(a["choice"]) if a.get("choice") is not None else str(a.get("text") or "")


# ---------------------------------------------------------------- writing stand-in answers
def _order_for(root: Path, to: str, letter_id: str) -> dict | None:
    return next((o for o in orders.listing(root, to, "open") if o.get("nowait") == letter_id), None)


def _defer(root: Path, l, qs: list[dict], person: str, to: str, how: str, now: datetime) -> list[str]:
    d = deferred(root)
    keys = []
    for q in qs:
        k = _key(l.id, q)
        d[k] = {"to": to, "for": person, "at": now.isoformat(timespec="seconds"), "how": how}
        keys.append(k)
    if not keys:
        return keys
    _save_deferred(root, d)
    if _order_for(root, to, l.id) is None:
        orders.add(root, person, to, f"Your call: the open questions in “{l.subject}”",
                   detail=(f"{person} isn't waiting on these ({'their standing instruction' if how == 'standing' else 'they said so on the letter'}, "
                           f"Don't wait for me). Decide them as you judge best — "
                           f"python -m forge nowait pending · nowait decide {l.id} --answers a.json — "
                           f"and say why in the letter. {person}'s own answer replaces yours whenever it comes."),
                   priority="now", obj=f"mail:{l.id}", when=now, effort="ten minutes", extra={"nowait": l.id})
    journal.append(root, person, "task", f"mail:{l.id}", when=now,
                   note=f"left to {to} ({'standing instruction' if how == 'standing' else 'on the letter'}): " +
                        ", ".join(str(q.get("id")) for q in qs))
    return keys


def _stand_in_letter(root: Path, adp, l, picks: list[tuple[dict, dict]], person: str, how: str, st: dict,
                     now: datetime):
    """One letter from the question's sender to the person: the sender's own fallback, taken. `picks`: (question, resolution)."""
    answers = []
    for q, r in picks:
        a = {"id": q.get("id"), "letter": l.id, "stand_in": r["how"], "for": person}
        a["choice" if "choice" in r else "text"] = r.get("choice", r.get("text"))
        answers.append(a)
    answers = mail.apply_answers(adp, {l.id: l}, answers, l.sender)
    lines = []
    for (q, r), a in zip(picks, answers):
        line = f"- **{q.get('question')}** → {_answer_words(a)} *({l.sender}'s {'default' if r['how'] == 'default' else 'recommendation'})*"
        if a.get("applied"):
            x = a["applied"]
            line += f" — `{x.get('file')}#{x.get('pointer')}`: {x['message']}" if x.get("file") else f" — {x['message']}"
        lines.append(line)
    why = (f"{person}'s standing instruction (Don't wait for me, set {str(st.get('set_at') or '')[:16].replace('T', ' ')})"
           if how == "standing" else f"{person} said so on the letter (Take the defaults)")
    body = (f"These went ahead without waiting — {why}:\n\n" + "\n".join(lines) +
            f"\n\nNone of this is {person}'s ruling. Answer the original letter whenever you like and that answer "
            f"replaces these.\n\n*The forge wrote this letter from what {l.sender} said they would do if the "
            f"questions weren't answered; nobody typed it.*")
    sent = mail.send(root, l.sender, person, f"Went ahead: {l.subject}", body, answers=answers, thread_id=l.thread,
                     in_reply_to=l.id, when=now, log_it=False)
    journal.append(root, l.sender, "letter", f"mail/{sent.folder}/{sent.id}.md", when=now,
                   note=f"to {person}: stand-in answers — {len(answers)} question(s) took {l.sender}'s own fallback "
                        f"(written by the forge; {why})")
    return sent


def settle(root: Path, adp, letter_id: str, person: str, mode: str, how: str = "letter", st: dict | None = None,
           now: datetime | None = None, skip_parked: bool = False, letters=None) -> dict:
    """Stop one letter's open questions waiting on `person`: `mode` "default" (take each sender's fallback; the rest go
    to the named assistant, or keep waiting when nobody is named) or "defer" (all of them go to the named assistant).
    Returns {"taken": [...], "deferred": [...], "waiting": n still open and nobody's call, "letter": the stand-in
    letter's id or None}."""
    if mode not in ("default", "defer"):
        raise NoWaitRefused("take the defaults, or leave them to an assistant")
    st = st or get()
    to = st.get("defer_to")
    if mode == "defer" and not to:
        raise NoWaitRefused("pick who the questions are left to first")
    if to and not settings.is_assistant(to):
        raise NoWaitRefused(f"questions can be left to an assistant, not to {to}")
    now = now or settings.now()
    letters = mail.all_letters(root) if letters is None else letters
    l = next((x for x in letters if x.id == letter_id), None)
    if l is None:
        raise FileNotFoundError(letter_id)
    if not settings.is_assistant(l.sender):
        raise NoWaitRefused(f"{l.sender} is a person — their questions wait for a person's answer")
    if mail.group_of(l.to) != mail.group_of(person):
        raise NoWaitRefused(f"that letter is to {l.to}, not to {person}")
    done, parked, dfr = mail.answered_ids(letters), (_parked(letters) if skip_parked else set()), deferred(root)
    open_qs = [q for q in l.questions if _key(l.id, q) not in done and _key(l.id, q) not in parked]
    picks, rest = [], []
    for q in open_qs:
        r = resolution(q) if mode == "default" else None
        if r:
            picks.append((q, r))
        elif to and (_key(l.id, q) not in dfr or not _same(dfr[_key(l.id, q)].get("to"), to)):
            rest.append(q)
    out = {"taken": [], "deferred": [], "letter": None,
           "waiting": 0 if to else sum(1 for q in open_qs if not any(q is p for p, _r in picks) and _key(l.id, q) not in dfr)}
    if picks:
        sent = _stand_in_letter(root, adp, l, picks, person, how, st, now)
        out["letter"] = sent.id
        out["taken"] = [{"letter": l.id, "id": a.get("id"), "answer": _answer_words(a), "how": a.get("stand_in"),
                         "applied": (a.get("applied") or {}).get("message")} for a in sent.answers]
    if rest:
        _defer(root, l, rest, person, to, how, now)
        out["deferred"] = [{"letter": l.id, "id": q.get("id"), "to": to} for q in rest]
    return out


def sweep(root: Path, adp=None, now: datetime | None = None, path: Path | None = None) -> dict:
    """Carry out the standing instruction on everything waiting right now. Safe to run any number of times; with the
    setting on `wait` it only tidies. Run by the suite when Tasks opens and by `python -m forge nowait sweep`."""
    st = get(path)
    now = now or settings.now()
    out = {"mode": st["mode"], "taken": [], "deferred": [], "letters": []}
    try:
        tidy(root, now=now)
    except OSError as e:
        log.warning("nowait: tidy failed (%s)", e)
    person = st["person"]
    if st["mode"] == "wait" or not person:
        return out
    letters = mail.all_letters(root)
    done, parked, dfr = mail.answered_ids(letters), _parked(letters), deferred(root)
    mine = mail.folder_for(person)
    for l in letters:
        if not l.questions or not settings.is_assistant(l.sender):
            continue
        if l.folder != mine and not (l.folder == "archive" and mail.group_of(l.to) == mail.group_of(person)):
            continue
        try:
            age_h = (now - datetime.fromisoformat(l.date[:19])).total_seconds() / 3600
        except ValueError:
            age_h = 1e9
        if age_h < st["after_hours"]:
            continue
        waiting = [q for q in l.questions if _key(l.id, q) not in done and _key(l.id, q) not in parked]
        if st["mode"] == "defer" or not any(resolution(q) for q in waiting):
            waiting = [q for q in waiting if _key(l.id, q) not in dfr]       # already left to someone: nothing new to do
            if not st["defer_to"]:
                waiting = []                                                 # nobody named to leave them to: they wait
        if not waiting:
            continue
        try:
            r = settle(root, adp, l.id, person, st["mode"], how="standing", st=st, now=now, skip_parked=True)
        except (NoWaitRefused, OSError, ValueError) as e:
            log.warning("nowait: %s left waiting (%s)", l.id, e)
            continue
        if r["taken"] or r["deferred"]:
            out["letters"].append(l.id)
            out["taken"] += r["taken"]
            out["deferred"] += r["deferred"]
    if out["taken"] or out["deferred"]:
        log.info("nowait: sweep for %s (%s) — %d answer(s) taken, %d left to %s, over %d letter(s)", person, st["mode"],
                 len(out["taken"]), len(out["deferred"]), st["defer_to"] or "nobody", len(out["letters"]))
    return out


def tidy(root: Path, now: datetime | None = None) -> int:
    """Deferrals whose question has since been answered are dropped, and a "your call" work order with nothing left to
    decide is closed. Returns how many deferrals went."""
    d = deferred(root)
    if not d:
        return 0
    letters = mail.all_letters(root)
    done = mail.answered_ids(letters)
    ids = {l.id for l in letters}
    gone = [k for k in d if k in done or k.partition("#")[0] not in ids]
    if not gone:
        return 0
    for k in gone:
        d.pop(k)
    _save_deferred(root, d)
    left = {k.partition("#")[0] for k in d}
    for _f, o in list(orders._all(root)):
        if o.get("status") == "open" and o.get("nowait") and o["nowait"] not in left:
            who = (done.get(next((k for k in gone if k.startswith(o["nowait"] + "#")), ""), {}) or {}).get("by") or o.get("by")
            orders.close(root, o["id"], who, note="every question on the letter is answered", when=now)
    return len(gone)


def decide(root: Path, adp, letter_id: str, who: str, answers: list[dict], body: str = "",
           now: datetime | None = None):
    """An assistant answers the questions left to them — a stand-in letter in their own name, to the person.
    `answers`: [{"id", "choice" | "text", "note"?}]. Every one must be a question left to `who` and still open."""
    if not who or not settings.is_assistant(who):
        raise NoWaitRefused("this is for the assistant the questions were left to — a person simply answers the letter")
    now = now or settings.now()
    letters = mail.all_letters(root)
    l = next((x for x in letters if x.id == letter_id), None)
    if l is None:
        raise FileNotFoundError(letter_id)
    row = next((r for r in pending(root, who, letters) if r["letter"] == letter_id), None)
    if row is None:
        raise NoWaitRefused(f"nothing on that letter is left to {who} (python -m forge nowait pending)")
    mine = {str(q.get("id")): q for q in row["questions"]}
    out = []
    for a in answers or []:
        qid = str(a.get("id"))
        if qid not in mine:
            raise NoWaitRefused(f"question '{qid}' isn't one left to {who} on that letter (open ones: {', '.join(mine)})")
        if a.get("choice") is None and not str(a.get("text") or "").strip():
            raise NoWaitRefused(f"question '{qid}' has no answer in it — a choice, or words")
        x = {"id": mine[qid].get("id"), "letter": letter_id, "stand_in": "deferred", "for": row["for"]}
        for k in ("choice", "text", "note"):
            if a.get(k) is not None and str(a.get(k)).strip() != "":
                x[k] = a[k]
        out.append(x)
    if not out:
        raise NoWaitRefused("no answers given")
    out = mail.apply_answers(adp, {l.id: l}, out, who)
    lines = []
    for a in out:
        line = f"- **{mine[str(a['id'])].get('question')}** → {_answer_words(a)}"
        if a.get("note"):
            line += f" — {a['note']}"
        if a.get("applied"):
            x = a["applied"]
            line += f" *(`{x.get('file')}#{x.get('pointer')}`: {x['message']})*" if x.get("file") else f" *({x['message']})*"
        lines.append(line)
    person = row["for"] or l.to
    text = ((body.strip() + "\n\n") if body.strip() else "") + \
        f"You left these to me, so I decided them:\n\n" + "\n".join(lines) + \
        f"\n\nThey stand until you say otherwise — answer the original letter and your answer replaces mine."
    sent = mail.send(root, who, person, f"Decided for you: {l.subject}", text, answers=out, thread_id=l.thread,
                     in_reply_to=l.id, when=now, log_it=False)
    journal.append(root, who, "letter", f"mail/{sent.folder}/{sent.id}.md", when=now,
                   note=f"to {person}: stand-in answers — decided {len(out)} question(s) {person} left to {who}")
    tidy(root, now=now)
    return sent


# ---------------------------------------------------------------- what went ahead (so it can be looked over, and changed)
def decided(root: Path, person: str | None = None, letters=None) -> list[dict]:
    """Every stand-in answer still in force (the person hasn't answered since), newest first."""
    letters = mail.all_letters(root) if letters is None else letters
    by_id = {l.id: l for l in letters}
    out = []
    for key, a in mail.answered_ids(letters).items():
        if not a.get("stand_in"):
            continue
        if person and a.get("for") and mail.group_of(a["for"]) != mail.group_of(person):
            continue
        lid, _, qid = key.partition("#")
        l = by_id.get(lid)
        q = next((x for x in (l.questions if l else []) if str(x.get("id")) == qid), None)
        if q is None:
            continue
        out.append({"letter": lid, "id": qid, "subject": l.subject, "question": q.get("question"),
                    "answer": _answer_words(a), "note": a.get("note"), "how": a["stand_in"], "by": a.get("by"),
                    "date": a.get("date"), "reply": a.get("in"), "applied": (a.get("applied") or {}).get("message"),
                    "go": f"messages/inbox/{lid}"})
    return sorted(out, key=lambda d: str(d["date"]), reverse=True)


def view(root: Path, who: str | None) -> dict:
    """For the page: the setting, in words; who questions can be left to; what went ahead; what is someone's call."""
    st = get()
    names = sorted({n for n in mail.correspondents(root) if settings.is_assistant(n)} | ({st["defer_to"]} if st["defer_to"] else set()))
    letters = mail.all_letters(root)
    pend = pending(root, None, letters)
    return {"setting": st, "says": describe(st), "hours": list(HOURS), "assistants": names,
            "mine": bool(who) and not settings.is_assistant(who),
            "decided": decided(root, st["person"] or who, letters)[:60],
            "left": [{"letter": r["letter"], "subject": r["subject"], "to": r["to"], "count": len(r["questions"]),
                      "go": f"messages/inbox/{r['letter']}"} for r in pend]}
