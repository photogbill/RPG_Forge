"""The Mail — correspondence between the people and the assistants working on a game (suite spec §7, BUILD 03).

Letters are plain files in the game's own folder, readable without the suite:

    <game_root>/mail/to_<group>/<yyyymmdd-HHMMSS>_<from>_<subject>.md     a letter to someone in that group
    <game_root>/mail/archive/…                                             put away (moved, never deleted)
    <game_root>/mail/drafts/…                                              not sent yet
    <game_root>/mail/state.json                                            who has read what (letters are never rewritten)

A recipient's *group* is the first word of their name, lower-case (two names that start with the same word share a folder).
No name is built in: a correspondent is whoever signs a letter.

One letter = a small header, the letter in ordinary prose, and — when it asks things — a `questions` block (JSON).
A reply that answers carries an `answers` block. A question: id, question, why, recommendation, default (what the
sender does if it isn't answered), choices (labels, or {"label", "value"}; "something else" is always allowed as free
text) and optionally applies_to {"file", "pointer"} — the data field a chosen answer sets. Sending a reply applies
those through the safe-save path (validated, backed up, journalled) and records what happened in the reply.
Free-text answers change nothing; they wait for whoever reads the mail. A question answered "talk to me" or "later"
stays open on its thread, as does one nobody answered.
"""
from __future__ import annotations
import json, os, re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..log import get
from . import journal, settings

log = get("suite")
HEADER_KEYS = ("from", "to", "subject", "date", "thread", "in_reply_to", "status", "attachments")
FENCE = re.compile(r"^```(questions|answers)\s*\n(.*?)\n```\s*$", re.S | re.M)


def slug(s: str, n: int = 40) -> str:
    return (re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")[:n].strip("-")) or "letter"


def group_of(name: str) -> str:
    first = (str(name).strip().split() or ["someone"])[0]
    return slug(first, 24)


def mail_dir(root: Path) -> Path:
    return Path(root) / "mail"


def folder_for(name: str) -> str:
    return f"to_{group_of(name)}"


@dataclass
class Letter:
    id: str
    folder: str
    headers: dict
    body: str
    questions: list = field(default_factory=list)
    answers: list = field(default_factory=list)

    def h(self, k: str, default: str = "") -> str:
        return str(self.headers.get(k) or default)

    @property
    def sender(self) -> str:
        return self.h("from")

    @property
    def to(self) -> str:
        return self.h("to")

    @property
    def subject(self) -> str:
        return self.h("subject")

    @property
    def date(self) -> str:
        return self.h("date")

    @property
    def thread(self) -> str:
        return self.h("thread") or self.id

    @property
    def attachments(self) -> list[str]:
        return [a.strip() for a in self.h("attachments").split("|") if a.strip()]

    def first_line(self, n: int = 140) -> str:
        for l in self.body.splitlines():
            l = l.strip()
            if l and not l.endswith(",") and not l.startswith(("#", "**To", "**From", "**Subject", "*(", "_(")):
                return l if len(l) <= n else l[: n - 1] + "…"
        return ""

    def as_dict(self) -> dict:
        return {"id": self.id, "folder": self.folder, "from": self.sender, "to": self.to, "subject": self.subject,
                "date": self.date, "thread": self.thread, "in_reply_to": self.h("in_reply_to") or None,
                "status": self.h("status"), "attachments": self.attachments, "body": self.body,
                "questions": self.questions, "answers": self.answers, "first_line": self.first_line()}


# ---------------------------------------------------------------- the file format
def render(headers: dict, body: str, questions=None, answers=None) -> str:
    """One letter's text. Deterministic: the same inputs always give the same bytes (the GUI and the command line
    both write through here)."""
    lines = ["---"]
    for k in HEADER_KEYS:
        v = headers.get(k)
        if k == "attachments" and isinstance(v, (list, tuple)):
            v = " | ".join(v)
        lines.append(f"{k}: {'' if v is None else ' '.join(str(v).split())}")
    lines += ["---", "", body.strip("\n"), ""]
    for name, block in (("questions", questions), ("answers", answers)):
        if block:
            lines += [f"```{name}", json.dumps(block, ensure_ascii=False, indent=1), "```", ""]
    return "\n".join(lines)


def parse(text: str, letter_id: str = "", folder: str = "") -> Letter:
    text = text.replace("\r\n", "\n")
    headers: dict = {}
    rest = text
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            for line in text[4:end].splitlines():
                k, sep, v = line.partition(":")
                if sep:
                    headers[k.strip().lower()] = v.strip()
            rest = text[end + 5:]
    blocks = {"questions": [], "answers": []}
    for m in FENCE.finditer(rest):
        try:
            v = json.loads(m.group(2))
            blocks[m.group(1)] = v if isinstance(v, list) else []
        except ValueError:
            log.warning("mail: %s has a %s block that is not JSON — shown as text", letter_id, m.group(1))
            continue
    body = FENCE.sub("", rest).strip("\n")
    for i, q in enumerate(blocks["questions"]):
        if isinstance(q, dict) and not q.get("id"):
            q["id"] = f"q{i + 1}"
    return Letter(letter_id, folder, headers, body, blocks["questions"], blocks["answers"])


# ---------------------------------------------------------------- reading the mailbox
def _files(root: Path):
    d = mail_dir(root)
    if not d.is_dir():
        return
    for sub in sorted(p for p in d.iterdir() if p.is_dir()):
        if not (sub.name.startswith("to_") or sub.name in ("archive", "drafts")):
            continue
        for f in sorted(sub.glob("*.md")):
            yield sub.name, f


def all_letters(root: Path) -> list[Letter]:
    out = []
    for folder, f in _files(root):
        try:
            out.append(parse(f.read_text(encoding="utf-8"), f.stem, folder))
        except OSError as e:
            log.warning("mail: %s unreadable (%s)", f, e)
    return out


def find(root: Path, letter_id: str) -> Letter | None:
    for folder, f in _files(root):
        if f.stem == letter_id:
            return parse(f.read_text(encoding="utf-8"), f.stem, folder)
    return None


def _path_of(root: Path, letter_id: str) -> Path | None:
    for _folder, f in _files(root):
        if f.stem == letter_id:
            return f
    return None


def _state(root: Path) -> dict:
    try:
        d = json.loads((mail_dir(root) / "state.json").read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_state(root: Path, st: dict) -> None:
    p = mail_dir(root) / "state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name("state.json.tmp")
    tmp.write_text(json.dumps(st, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, p)


def is_read(root: Path, who: str, letter_id: str, st: dict | None = None) -> bool:
    st = _state(root) if st is None else st
    return letter_id in set((st.get("read") or {}).get(who) or [])


def mark_read(root: Path, who: str, letter_id: str, read: bool = True) -> None:
    st = _state(root)
    r = set((st.setdefault("read", {}).get(who)) or [])
    (r.add if read else r.discard)(letter_id)
    st["read"][who] = sorted(r)
    _save_state(root, st)


def box(root: Path, who: str, which: str = "inbox", query: str | None = None) -> list[dict]:
    """A mailbox as `who` sees it, newest first: inbox (letters to their group), sent, drafts, archive."""
    me_folder = folder_for(who)
    st = _state(root)
    letters = all_letters(root)
    opened = open_questions_by_letter(letters)
    out = []
    for l in letters:
        if which == "inbox":
            ok = l.folder == me_folder
        elif which == "sent":
            ok = l.sender == who and l.folder != "drafts"
        elif which == "drafts":
            ok = l.folder == "drafts" and l.sender == who
        elif which == "archive":
            ok = l.folder == "archive" and (l.sender == who or group_of(l.to) == group_of(who))
        else:
            ok = l.folder != "drafts" and (l.sender == who or group_of(l.to) == group_of(who))     # "all", for search
        if not ok:
            continue
        if query:
            hay = " ".join([l.sender, l.to, l.subject, l.body, json.dumps(l.questions, ensure_ascii=False)]).lower()
            if not all(w in hay for w in query.lower().split()):
                continue
        d = l.as_dict()
        d.pop("body")
        d["unread"] = which in ("inbox", "all") and l.folder == me_folder and not is_read(root, who, l.id, st)
        d["open_questions"] = opened.get(l.id, 0)
        d["n_questions"] = len(l.questions)
        out.append(d)
    out.sort(key=lambda d: d["date"], reverse=True)
    return out


def unread_count(root: Path, who: str) -> int:
    return sum(1 for d in box(root, who, "inbox") if d["unread"])


def thread(root: Path, thread_id: str, letters: list[Letter] | None = None) -> list[Letter]:
    letters = all_letters(root) if letters is None else letters
    return sorted((l for l in letters if l.thread == thread_id and l.folder != "drafts"), key=lambda l: l.date)


def answered_ids(letters: list[Letter]) -> dict[str, dict]:
    """question key "<letter id>#<question id>" → the answer that settled it (a choice or free text; not talk/later)."""
    done: dict[str, dict] = {}
    by_id = {l.id: l for l in letters}
    for l in sorted(letters, key=lambda x: x.date):
        for a in l.answers or []:
            if not isinstance(a, dict) or a.get("talk") or a.get("later"):
                continue
            if a.get("choice") is None and not str(a.get("text") or "").strip():
                continue
            src = a.get("letter") or l.h("in_reply_to")
            if src in by_id:
                done[f"{src}#{a.get('id')}"] = {**a, "in": l.id, "by": l.sender, "date": l.date}
    return done


def open_questions_by_letter(letters: list[Letter]) -> dict[str, int]:
    done = answered_ids(letters)
    return {l.id: sum(1 for q in l.questions if f"{l.id}#{q.get('id')}" not in done) for l in letters if l.questions}


def thread_view(root: Path, letter_id: str, who: str) -> dict:
    l = find(root, letter_id)
    if l is None:
        raise FileNotFoundError(letter_id)
    letters = all_letters(root)
    th = thread(root, l.thread, letters)
    done = answered_ids(letters)
    talk = {}
    for x in th:
        for a in x.answers or []:
            if isinstance(a, dict) and (a.get("talk") or a.get("later")):
                talk[f"{a.get('letter') or x.h('in_reply_to')}#{a.get('id')}"] = "talk" if a.get("talk") else "later"
    cards = []
    for x in th:
        d = x.as_dict()
        d["unread"] = x.folder == folder_for(who) and not is_read(root, who, x.id)
        for q in d["questions"]:
            key = f"{x.id}#{q.get('id')}"
            q["answer"] = done.get(key)
            q["parked"] = talk.get(key) if key not in done else None
        cards.append(d)
    open_n = sum(1 for c in cards for q in c["questions"] if not q["answer"])
    return {"thread": l.thread, "subject": th[0].subject if th else l.subject, "letters": cards, "open_questions": open_n}


def correspondents(root: Path, who: str | None = None) -> list[str]:
    names = set()
    for l in all_letters(root):
        names |= {n for n in (l.sender, l.to) if n}
    try:
        names |= {e.get("who") for e in journal.read(root) if e.get("who")}
    except OSError:
        pass
    if who:
        names.add(who)
    return sorted(names)


# ---------------------------------------------------------------- writing
def _new_id(root: Path, folder: str, when: datetime, frm: str, subject: str) -> str:
    base = f"{when:%Y%m%d-%H%M%S}_{slug(frm, 20)}_{slug(subject, 40)}"
    lid, n = base, 1
    while (mail_dir(root) / folder / f"{lid}.md").exists():
        n += 1
        lid = f"{base}-{n}"
    return lid


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, p)


def normalise_questions(questions) -> list[dict]:
    out = []
    for i, q in enumerate(questions or []):
        if isinstance(q, str):
            q = {"question": q}
        q = dict(q)
        q.setdefault("id", f"q{i + 1}")
        if not str(q.get("question") or "").strip():
            raise ValueError(f"question {q['id']} has no question in it")
        out.append(q)
    return out


def send(root: Path, frm: str, to: str, subject: str, body: str, questions=None, answers=None, thread_id: str | None = None,
         in_reply_to: str | None = None, attachments=None, when: datetime | None = None, draft: bool = False,
         log_it: bool = True, adp=None) -> Letter:
    """Write a letter (or a draft). The one function the GUI, `mail.bat` and sessions all use.

    BUILD 17: an assistant's questions are checked against the rulings book first (rulings.check_questions — `adp` says
    which files hold the game's rulings); a question the book already answers is refused (rulings.AlreadyRuled) unless
    it carries `asked_again` — why it is being asked once more."""
    if not frm or not to:
        raise ValueError("a letter needs a sender and a recipient")
    if not str(subject).strip():
        raise ValueError("a letter needs a subject")
    when = when or settings.now()
    questions = normalise_questions(questions)
    if questions and not draft and settings.is_assistant(frm):
        from . import rulings
        hits = rulings.check_questions(root, questions, adp)
        if hits:
            journal.append(root, frm, "refused", "rulings", note="a letter's question was already ruled on: " +
                           "; ".join(f"{h['id']} ↔ {h['rulings'][0]['id']}" for h in hits), when=when)
            raise rulings.AlreadyRuled(hits)
    folder = "drafts" if draft else folder_for(to)
    lid = _new_id(root, folder, when, frm, subject)
    headers = {"from": frm, "to": to, "subject": subject, "date": when.isoformat(timespec="seconds"),
               "thread": thread_id or lid, "in_reply_to": in_reply_to or "", "status": "draft" if draft else "sent",
               "attachments": list(attachments or [])}
    text = render(headers, body, questions, answers)
    _write(mail_dir(root) / folder / f"{lid}.md", text)
    if log_it and not draft:
        note = f"{len(questions)} question(s)" if questions else None
        if answers:
            note = f"answered {sum(1 for a in answers if not a.get('talk') and not a.get('later'))} of {len(answers)}"
        journal.append(root, frm, "letter", f"mail/{folder}/{lid}.md", note=f"to {to}: {subject}" + (f" — {note}" if note else ""),
                       when=when)
    log.info("mail: %s → %s: %s (%s)", frm, to, subject, "draft" if draft else folder)
    return parse(text, lid, folder)


def apply_answers(adp, letters: dict, answers: list[dict], who: str) -> list[dict]:
    """Make the change each chosen answer asks for (applies_to), through the safe-save path. `letters` maps letter id
    → Letter (an answer names its letter). Returns the answers with `applied` filled in: {"ok", "message", "file",
    "pointer", "value"} — or none when nothing was to be changed."""
    from . import safesave
    out = []
    for a in answers:
        a = dict(a)
        letter = letters.get(a.get("letter"))
        q = next((x for x in (letter.questions if letter else []) if x.get("id") == a.get("id")), None)
        at = (q or {}).get("applies_to")
        if q and at and a.get("choice") is not None and not a.get("talk") and not a.get("later"):
            value, found = None, False
            for c in q.get("choices") or []:
                label = c.get("label") if isinstance(c, dict) else c
                if label == a["choice"]:
                    value, found = (c.get("value", label) if isinstance(c, dict) else c), True
            if not found:
                a["applied"] = {"ok": False, "message": "that answer isn't one of the question's choices — nothing changed"}
            elif adp is None:
                a["applied"] = {"ok": False, "message": "the game's adapter isn't available — nothing changed; whoever reads this applies it"}
            else:
                r = safesave.edit(adp, at["file"], [("put", at["pointer"], value)], who,
                                  reason=f"answer to “{q.get('question')}” ({letter.id})", kind="edit")
                if r.get("proposed"):
                    msg = f"proposed to {r['proposed']['to']} (they approved what it changes)"
                elif r.get("ok"):
                    msg = "changed" if r.get("changed") else "already so — nothing to change"
                elif r.get("conflict"):
                    msg = "the file changed underneath — nothing written; say it again after a look"
                else:
                    msg = "refused: " + "; ".join(r.get("refused") or [])
                a["applied"] = {"ok": bool(r.get("ok")), "message": msg, "file": at["file"], "pointer": at["pointer"],
                                "value": value, "backup": r.get("backup")}
        out.append(a)
    return out


def reply(root: Path, letter_id: str, frm: str, body: str = "", answers=None, adp=None, when: datetime | None = None,
          attachments=None) -> Letter:
    """Answer a letter — one reply for the whole letter. Chosen answers with applies_to are applied first; the reply
    says what was applied and which questions stay open."""
    orig = find(root, letter_id)
    if orig is None:
        raise FileNotFoundError(letter_id)
    when = when or settings.now()
    answers = [dict(a, letter=a.get("letter") or letter_id) for a in (answers or []) if a.get("id")]
    srcs = {orig.id: orig}
    for a in answers:
        if a["letter"] not in srcs:
            other = find(root, a["letter"])
            if other is not None and other.thread == orig.thread:
                srcs[other.id] = other
    answers = apply_answers(adp, srcs, answers, frm) if answers else []
    settled = {(a["letter"], a["id"]) for a in answers if not a.get("talk") and not a.get("later")
               and (a.get("choice") is not None or str(a.get("text") or "").strip())}
    asked = [(l.id, q.get("id")) for l in srcs.values() for q in l.questions]
    still = [k for k in asked if k not in settled]
    tail = []
    def _say(a):
        x = a["applied"]
        return f"{x['file']}#{x['pointer']} → {json.dumps(x['value'], ensure_ascii=False)}"
    changed = [a for a in answers if (a.get("applied") or {}).get("message") == "changed"]
    same = [a for a in answers if (a.get("applied") or {}).get("message", "").startswith("already so")]
    other = [a for a in answers if a.get("applied") and a not in changed and a not in same]
    if changed:
        tail.append("Changed through the suite (checked, backed up, logged): " + "; ".join(_say(a) for a in changed) + ".")
    if same:
        tail.append("Already so, nothing to change: " + "; ".join(_say(a) for a in same) + ".")
    for a in other:
        tail.append(f"{a['id']}: {a['applied']['message']}.")
    if still and asked:
        tail.append(f"Still open: {len(still)} of {len(asked)} — " + ", ".join(qid for _l, qid in still) + ".")
    text = body.strip()
    if tail:
        text = (text + "\n\n" if text else "") + "\n".join(f"*{t}*" for t in tail)
    subj = orig.subject if orig.subject.lower().startswith("re:") else f"Re: {orig.subject}"
    return send(root, frm, orig.sender, subj, text or "(answers below)", answers=answers or None, thread_id=orig.thread,
                in_reply_to=orig.id, attachments=attachments, when=when)


def archive(root: Path, who: str, letter_id: str) -> Path:
    p = _path_of(root, letter_id)
    if p is None:
        raise FileNotFoundError(letter_id)
    if p.parent.name == "archive":
        return p
    dest = mail_dir(root) / "archive" / p.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    os.replace(p, dest)
    journal.append(root, who, "letter", f"mail/archive/{p.name}", note="archived")
    return dest


def unarchive(root: Path, who: str, letter_id: str) -> Path:
    p = _path_of(root, letter_id)
    if p is None or p.parent.name != "archive":
        raise FileNotFoundError(letter_id)
    to = parse(p.read_text(encoding="utf-8"), p.stem, "archive").to
    dest = mail_dir(root) / folder_for(to) / p.name
    os.replace(p, dest)
    journal.append(root, who, "letter", f"mail/{dest.parent.name}/{p.name}", note="back from the archive")
    return dest


def send_draft(root: Path, draft_id: str, when: datetime | None = None) -> Letter:
    p = mail_dir(root) / "drafts" / f"{draft_id}.md"
    d = parse(p.read_text(encoding="utf-8"), draft_id, "drafts")
    sent = send(root, d.sender, d.to, d.subject, d.body, d.questions or None, d.answers or None,
                thread_id=d.h("thread") if d.h("in_reply_to") else None, in_reply_to=d.h("in_reply_to") or None,
                attachments=d.attachments, when=when)
    done = mail_dir(root) / "drafts" / "_sent" / p.name
    done.parent.mkdir(parents=True, exist_ok=True)
    os.replace(p, done)                      # never deleted: a sent draft is kept under drafts/_sent/
    return sent


def save_draft(root: Path, frm: str, to: str, subject: str, body: str, questions=None, draft_id: str | None = None,
               when: datetime | None = None) -> Letter:
    """A new draft, or (draft_id) the same draft rewritten in place."""
    if draft_id:
        p = mail_dir(root) / "drafts" / f"{draft_id}.md"
        if not p.exists():
            raise FileNotFoundError(draft_id)
        when = when or settings.now()
        headers = {"from": frm, "to": to, "subject": subject or "(no subject)", "date": when.isoformat(timespec="seconds"),
                   "thread": draft_id, "in_reply_to": "", "status": "draft", "attachments": []}
        text = render(headers, body, normalise_questions(questions))
        _write(p, text)
        return parse(text, draft_id, "drafts")
    return send(root, frm, to or "(nobody yet)", subject or "(no subject)", body, questions, draft=True, when=when)


def send_edited_draft(root: Path, draft_id: str, frm: str, to: str, subject: str, body: str, questions=None,
                      when: datetime | None = None, adp=None) -> Letter:
    """Send what the draft now says, and put the draft away under drafts/_sent/ (never deleted)."""
    sent = send(root, frm, to, subject, body, questions, when=when, adp=adp)
    p = mail_dir(root) / "drafts" / f"{draft_id}.md"
    if p.exists():
        done = mail_dir(root) / "drafts" / "_sent" / p.name
        done.parent.mkdir(parents=True, exist_ok=True)
        os.replace(p, done)
    return sent
