"""The rulings book (BUILD 17, suite spec §8 B4) — every answer the owner has given, in one dated, searchable book.

What stops the same question being asked twice. Three kinds of entry, all read live from the game's own folder:

* **answer** — a question in the Mail that someone answered (a choice, or words). The question, the answer in the
  answerer's words, the date, the letter, and what it changed (`applies_to` → the value it set), if anything.
* **marked** — a line in the game's notes marked with ✦ (the owner's ruling mark). Which files are read is the game
  adapter's `ruling_files()` (default: the game folder's top-level `*.md`; a pattern starting with "!" leaves files out —
  a generated report that only repeats status marks). A line that only *explains* the mark
  ("✦ is the owner's ruling") is skipped.
* **recorded** — a ruling written straight into the book (`<game_root>/rulings/rulings.jsonl`, append-only), e.g. one the
  owner gave in a chat. A person records in their own name; an assistant may record only with `source` — where the
  person said it, in their words — and the entry says who wrote it down. A recorded ruling may be **pinned** to a data
  field (`applies_to` {file, pointer} + `value`); the book then warns whenever the data says something else.

A ruling is never edited or deleted. `retire(id)` (a person only) adds a line saying it no longer holds and why; the
book hides it from checks but keeps it, marked.

Before anyone asks the owner anything: `check(root, question)` → the rulings that already answer it. `mail.send` runs it
for every question an assistant sends and refuses a question already ruled on, unless the question says why it is
being asked again (`asked_again`). Nothing here names a game.
"""
from __future__ import annotations
import hashlib, json, math, os, re, secrets
from datetime import datetime
from pathlib import Path

from ..log import get
from . import journal, settings

log = get("suite")
MARK = "✦"
DEFAULT_FILES = ("*.md",)
SKIP_DIRS = {"_workbench_backups", "_workbench_tmp", "_to_delete", "_xfer", "journal", "notes", "rulings", ".git"}

# the mark explained, not used — "✦ is William's ruling", "unless it carries ✦", "(✦ = …)", "`✦`"
_EXPLAINS = re.compile(r"(`✦`|✦\s*(=|is\s+(the\s+owner|\w+'s|his|her|their|a)\b|marks?\b|means\b)|carr(y|ies)\s+✦|"
                       r"(marked|with|a|no|or)\s+✦\s*(\)|,|\.|$| or| and| —))", re.I)
_DATE = re.compile(r"(20\d\d-\d\d-\d\d)(?:[ T]?(\d{1,2}:\d\d))?")
_TIME = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")
_HEAD = re.compile(r"^(#{1,6})\s+(.*)$")
_MD = re.compile(r"(\*\*|__|`|\*(?=\S)|(?<=\S)\*)")

STOP = set("""a about above after again against all also am an and any are as at be because been before being below
between both but by can could did do does doing down during each else ever every few for from further had has have having
he her here hers him his how i if in into is it its itself just let like make may me might more most much must my no nor
not now of off on once one only or other our out over own per same she should so some such than that the their them then
there these they this those through to too under until up upon us very was we were what when where which while who whom
why will with would yet you your yours should shall want wants going gets get got let's it's i'm don't do we'll let's
question answer ruling please think thing things way ask asks asked say says said tell yes okay ok one two""".split())


class AlreadyRuled(ValueError):
    """A question that the book already answers. The message names the ruling(s)."""

    def __init__(self, hits: list[dict]):
        self.hits = hits
        lines = []
        for h in hits:
            r = h["rulings"][0]
            lines.append(f"“{h['question']}” — already ruled ({r['when'] or 'undated'}, {r['where']}): {r['text'][:220]}")
        super().__init__("Not sent — the rulings book already answers this; ask again only with a reason "
                         "(asked_again on the question):\n" + "\n".join(lines))


# ---------------------------------------------------------------- words
def _stem(w: str) -> str:
    if w.endswith("'s"):
        w = w[:-2]
    for suf, rep in (("ies", "y"), ("ing", ""), ("ed", ""), ("es", ""), ("s", "")):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)] + rep
    return w


def words(text: str) -> list[str]:
    out = []
    for w in re.findall(r"[a-z0-9][a-z0-9'’]*", str(text).lower().replace("’", "'")):
        w = w.strip("'")
        if len(w) < 3 and not w.isdigit():
            continue
        if w in STOP:
            continue
        out.append(_stem(w))
    return out


def _clean(s: str) -> str:
    s = _MD.sub("", s)
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    return " ".join(s.split())


def _norm(s: str) -> str:
    return " ".join(words(s))


# ---------------------------------------------------------------- the marked lines in the game's notes
def ruling_files(root: Path, adp=None) -> list[str]:
    globs = DEFAULT_FILES
    if adp is not None and callable(getattr(adp, "ruling_files", None)):
        try:
            globs = tuple(adp.ruling_files()) or DEFAULT_FILES
        except Exception as e:  # noqa: BLE001 — a broken hook falls back to the default, never breaks the book
            log.warning("rulings: the adapter's ruling_files() failed (%s); reading %s", e, DEFAULT_FILES)
    seen: set[str] = set()
    root = Path(root)
    from fnmatch import fnmatch
    skip = [g[1:] for g in globs if g.startswith("!")]          # "!REPORT.md" — a generated report, not rulings
    for g in globs:
        if g.startswith("!"):
            continue
        for p in root.glob(g):
            if not p.is_file() or p.suffix.lower() not in (".md", ".txt"):
                continue
            rel = p.relative_to(root).as_posix()
            if SKIP_DIRS & set(rel.split("/")[:-1]) or any(fnmatch(rel, x) for x in skip):
                continue
            seen.add(rel)
    return sorted(seen)


def _when_of(text: str, heads: list[str], fallback: str) -> tuple[str, str]:
    m = _DATE.search(text)
    if m:
        return (m.group(1) + (" " + m.group(2).zfill(5) if m.group(2) else "")), "line"
    day = None
    for h in reversed(heads):
        hm = _DATE.search(h)
        if hm:
            day = hm.group(1)
            break
    tm = _TIME.search(text) if MARK in text else None
    if day:
        return (day + (f" {int(tm.group(1)):02d}:{tm.group(2)}" if tm else "")), "heading"
    return fallback, "file"


def scan_file(root: Path, rel: str) -> list[dict]:
    p = Path(root) / rel
    try:
        raw = p.read_text(encoding="utf-8-sig", errors="replace")
        mdate = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d")
    except OSError as e:
        log.warning("rulings: %s not read (%s)", rel, e)
        return []
    lines = raw.replace("\r\n", "\n").split("\n")
    out, heads, fence = [], [], False
    i = 0
    while i < len(lines):
        l = lines[i]
        if l.strip().startswith("```"):
            fence = not fence
            i += 1
            continue
        if fence:
            i += 1
            continue
        hm = _HEAD.match(l)
        if hm:
            depth = len(hm.group(1))
            heads = heads[: depth - 1] + [hm.group(2)]
        if MARK not in l or _EXPLAINS.search(l) and l.count(MARK) == 1 and len(_clean(l)) < 160:
            i += 1
            continue
        if l.lstrip().startswith("|"):                      # a table row: only when the marked cell says something
            cells = [c for c in l.strip().strip("|").split("|") if MARK in c]
            if all(len(words(c.replace(MARK, ""))) <= 3 for c in cells):
                i += 1
                continue
        start, block = i + 1, [l]
        if hm or l.strip().startswith(">"):                  # a marked heading or quote: the paragraph under it
            j = i + 1
            while j < len(lines) and len(block) < 6 and lines[j].strip() and not _HEAD.match(lines[j]):
                block.append(lines[j])
                j += 1
            if len(block) == 1 and j < len(lines) - 1 and not lines[j].strip():
                j += 1
                while j < len(lines) and len(block) < 6 and lines[j].strip() and not _HEAD.match(lines[j]):
                    block.append(lines[j])
                    j += 1
        else:                                               # a bullet or paragraph: its own continuation lines
            j = i + 1
            while (j < len(lines) and len(block) < 4 and lines[j].strip() and not _HEAD.match(lines[j])
                   and not re.match(r"^\s*([-*+]|\d+\.)\s", lines[j]) and not lines[j].lstrip().startswith("|")
                   and not l.lstrip().startswith("|")):
                block.append(lines[j])
                j += 1
        text = _clean(" ".join(x.strip().lstrip("-*+>| ").strip() for x in block))
        if len(text) > 900:
            k = text.find(MARK)
            a = max(0, k - 250)
            text = ("…" if a else "") + text[a:a + 880] + "…"
        when, basis = _when_of(" ".join(block), heads, mdate)
        h = hashlib.sha1(_norm(text).encode("utf-8")).hexdigest()[:10]
        out.append({"id": f"m:{h}", "kind": "marked", "text": text, "when": when, "when_basis": basis, "file": rel,
                    "line": start, "heading": _clean(heads[-1]) if heads else "", "where": f"{rel}:{start}"})
        i += 1
    return out


# ---------------------------------------------------------------- answers in the Mail
def _answers(root: Path) -> list[dict]:
    from . import mail
    letters = mail.all_letters(root)
    by_id = {l.id: l for l in letters}
    out = []
    for key, a in mail.answered_ids(letters).items():
        lid, _, qid = key.partition("#")
        l = by_id.get(lid)
        q = next((x for x in (l.questions if l else []) if str(x.get("id")) == qid), None)
        if not q:
            continue
        choice = a.get("choice")
        said = str(a.get("text") or "").strip()
        note = str(a.get("note") or "").strip()
        ans = " — ".join(x for x in (str(choice) if choice is not None else "", said, note) if x)
        value, at = None, q.get("applies_to")
        if a.get("applied") and a["applied"].get("ok"):
            value = a["applied"].get("value")
        elif at and choice is not None:
            for c in q.get("choices") or []:
                if (c.get("label") if isinstance(c, dict) else c) == choice:
                    value = c.get("value", choice) if isinstance(c, dict) else c
        e = {"id": f"a:{lid}#{qid}", "kind": "answer", "question": str(q.get("question") or ""), "answer": ans,
             "text": f"{q.get('question')} → {ans}", "when": str(a.get("date") or "")[:16].replace("T", " "),
             "when_basis": "letter", "by": a.get("by"), "asked_by": l.sender if l else "", "letter": lid, "reply": a.get("in"),
             "where": f"mail {a.get('in') or lid}", "qid": qid, "why": str(q.get("why") or "")}
        if at and value is not None:
            e["applies_to"], e["value"] = at, value
        out.append(e)
    return out


# ---------------------------------------------------------------- recorded rulings
def path(root: Path) -> Path:
    return Path(root) / "rulings" / "rulings.jsonl"


def _recorded_raw(root: Path) -> list[dict]:
    p = path(root)
    if not p.is_file():
        return []
    out = []
    for raw in p.read_text(encoding="utf-8").splitlines():
        if raw.strip():
            try:
                out.append(json.loads(raw))
            except ValueError:
                continue
    return out


def _append(root: Path, entry: dict) -> None:
    p = path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(p), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, (json.dumps(entry, ensure_ascii=False) + "\n").encode("utf-8"))
    finally:
        os.close(fd)
    _CACHE.pop(str(Path(root).resolve()), None)


def record(root: Path, who: str, text: str, by: str | None = None, source: str = "", question: str = "",
           applies_to: dict | None = None, value=None, when: datetime | None = None, tags=None) -> dict:
    """Write a ruling into the book. `who` writes it down; `by` made it (default: who). An assistant may only write down
    someone else's ruling, with `source` saying where they said it, in their words."""
    if not who:
        raise ValueError("a ruling is signed — set who you are first")
    by = (by or who).strip()
    if not str(text).strip():
        raise ValueError("the ruling is empty")
    if settings.is_assistant(by):
        raise ValueError(f"a ruling is a person's to make — {by} can write one down, with where it was said, but not make it")
    if settings.is_assistant(who) and not str(source).strip():
        raise ValueError("an assistant writing down a ruling says where the person said it, in their words (source)")
    if applies_to is not None and (not isinstance(applies_to, dict) or not applies_to.get("file") or "pointer" not in applies_to):
        raise ValueError("applies_to is {file, pointer}")
    when = when or settings.now()
    e = {"id": f"r:{when:%Y%m%d-%H%M%S}-{secrets.token_hex(2)}", "time": when.isoformat(timespec="seconds"), "by": by,
         "recorded_by": who, "text": " ".join(str(text).split())}
    for k, v in (("source", str(source).strip()), ("question", str(question).strip())):
        if v:
            e[k] = v
    if applies_to is not None:
        e["applies_to"], e["value"] = {"file": applies_to["file"], "pointer": applies_to["pointer"]}, value
    if tags:
        e["tags"] = list(tags)
    _append(root, e)
    journal.append(root, who, "note", "rulings", note=f"ruling recorded ({by}): {e['text'][:300]}", when=when)
    return e


def retire(root: Path, who: str, ruling_id: str, why: str, when: datetime | None = None) -> dict:
    """A ruling that no longer holds: one line saying so (a person only). Nothing is deleted."""
    if not who or settings.is_assistant(who):
        raise ValueError("retiring a ruling is a person's decision")
    if not str(why).strip():
        raise ValueError("say why it no longer holds")
    when = when or settings.now()
    e = {"retire": ruling_id, "time": when.isoformat(timespec="seconds"), "by": who, "why": str(why).strip()}
    _append(root, e)
    journal.append(root, who, "note", "rulings", note=f"retired {ruling_id}: {e['why']}", when=when)
    return e


def _recorded(root: Path) -> tuple[list[dict], dict]:
    out, retired = [], {}
    for e in _recorded_raw(root):
        if "retire" in e:
            retired[e["retire"]] = e
            continue
        if not e.get("id") or not e.get("text"):
            continue
        r = {**e, "kind": "recorded", "when": str(e.get("time", ""))[:16].replace("T", " "), "when_basis": "recorded",
             "where": "the rulings book" + (f" — {e['source']}" if e.get("source") else "")}
        out.append(r)
    return out, retired


# ---------------------------------------------------------------- the book
_CACHE: dict[str, tuple[tuple, dict]] = {}


def _signature(root: Path, files: list[str]) -> tuple:
    sig = []
    for rel in files + ["rulings/rulings.jsonl"]:
        try:
            st = (Path(root) / rel).stat()
            sig.append((rel, st.st_mtime_ns, st.st_size))
        except OSError:
            sig.append((rel, 0, 0))
    from . import mail
    md = mail.mail_dir(root)
    for sub in ("to_*", "archive"):
        for d in md.glob(sub):
            try:
                sig.append((d.name, d.stat().st_mtime_ns, len(os.listdir(d))))
            except OSError:
                pass
    return tuple(sig)


def book(root: Path, adp=None) -> dict:
    """{"rulings": [...newest first], "retired": {id: why}, "files": [...], "idf": {...}}. Cached until a source changes."""
    root = Path(root)
    files = ruling_files(root, adp)
    key = str(root.resolve())
    sig = _signature(root, files)
    hit = _CACHE.get(key)
    if hit and hit[0] == sig:
        return hit[1]
    entries: list[dict] = []
    seen: dict[str, dict] = {}
    for rel in files:
        for e in scan_file(root, rel):
            k = _norm(e["text"])
            if k in seen:
                seen[k].setdefault("also", []).append(e["where"])
                continue
            seen[k] = e
            entries.append(e)
    try:
        entries += _answers(root)
    except Exception as e:  # noqa: BLE001 — a broken letter doesn't take the book down
        log.warning("rulings: answers in the Mail not read (%s)", e)
    rec, retired = _recorded(root)
    entries += rec
    for e in entries:
        if e["id"] in retired:
            e["retired"] = {"by": retired[e["id"]]["by"], "why": retired[e["id"]]["why"], "time": retired[e["id"]]["time"]}
        e["_w"] = words(" ".join([e.get("text", ""), e.get("question", ""), e.get("heading", ""), e.get("why", "")]))
        if e["kind"] == "marked":           # where the marks fall, in words — the ruling is what follows a mark
            parts = e["text"].split(MARK)
            e["_marks"] = [len(words(MARK.join(parts[:k]))) for k in range(1, len(parts))]
    df: dict[str, int] = {}
    for e in entries:
        for w in set(e["_w"]):
            df[w] = df.get(w, 0) + 1
    n = max(1, len(entries))
    idf = {w: math.log(1 + n / c) for w, c in df.items()}
    entries.sort(key=lambda e: (str(e.get("when") or ""), e["id"]), reverse=True)
    b = {"rulings": entries, "retired": retired, "files": files, "idf": idf, "n": n}
    _CACHE[key] = (sig, b)
    log.info("rulings: book for %s — %d ruling(s) from %d file(s), the Mail and the book", root.name, len(entries), len(files))
    return b


def public(e: dict) -> dict:
    return {k: v for k, v in e.items() if not k.startswith("_")}


def _score(qw: list[str], e: dict, idf: dict, default_idf: float) -> tuple[float, float, list[str]]:
    """(coverage of the question's weight, total shared weight, shared words)."""
    if not qw:
        return 0.0, 0.0, []
    qs = set(qw)
    es = set(e["_w"])
    shared = sorted(qs & es)
    tot = sum(idf.get(w, default_idf) for w in qs)
    got = sum(idf.get(w, default_idf) for w in shared)
    return (got / tot if tot else 0.0), got, shared


def search(root: Path, query: str, adp=None, limit: int = 30, kinds=None, include_retired: bool = False) -> list[dict]:
    b = book(root, adp)
    entries = [e for e in b["rulings"] if (include_retired or not e.get("retired")) and (not kinds or e["kind"] in kinds)]
    q = str(query or "").strip()
    if not q:
        return [public(e) for e in entries[:limit]]
    qw = words(q)
    default_idf = math.log(1 + b["n"])
    phrase = q.lower()
    hits = []
    for e in entries:
        cov, got, shared = _score(qw, e, b["idf"], default_idf)
        exact = phrase in e.get("text", "").lower() or phrase in e.get("question", "").lower()
        if not shared and not exact:
            continue
        hits.append((cov + (0.5 if exact else 0), got, e, shared))
    hits.sort(key=lambda h: (h[0], h[1]), reverse=True)
    return [{**public(e), "score": round(c, 3), "matched": s} for c, _g, e, s in hits[:limit]]


def _window_cover(qset: set, toks: list[str], idf: dict, default_idf: float, width: int = 36,
                  marks: list[int] | None = None) -> tuple[float, set]:
    """The most of the question's weight found inside any `width`-word stretch of the ruling (a long paragraph that
    mentions the same words far apart is not an answer). With `marks`, a stretch must start near a ✦ (from 12 words
    before one to 40 after): the words a mark rules on, not the explanation around them."""
    best, best_set = 0.0, set()
    pos = [(i, w) for i, w in enumerate(toks) if w in qset]
    for k, (i, _w) in enumerate(pos):
        if marks is not None and not any(-12 <= i - m <= 40 for m in marks):
            continue
        got = set()
        for j, w2 in pos[k:]:
            if j - i >= width:
                break
            got.add(w2)
        wt = sum(idf.get(w, default_idf) for w in got)
        if wt > best:
            best, best_set = wt, got
    return best, best_set


def check(root: Path, question: str, adp=None, limit: int = 3) -> list[dict]:
    """The rulings that already answer `question` (best first), or []. Deliberately strict, so that it catches a
    question asked again rather than a cousin of one: the same question answered in the Mail always matches; otherwise
    a ruling must hold, within one short stretch, most of the question's weight and its two rarest words."""
    b = book(root, adp)
    qn = _norm(question)
    qw = words(question)
    out = []
    qset = set(qw)
    default_idf = math.log(1 + b["n"])
    idf = b["idf"]
    ranked = sorted(qset, key=lambda w: idf.get(w, default_idf), reverse=True)
    top = set(ranked[:2])
    tot = sum(idf.get(w, default_idf) for w in qset)
    for e in b["rulings"]:
        if e.get("retired"):
            continue
        if qn and _norm(e.get("question", "")) == qn:
            out.append((2.0, e, sorted(qset)))
            continue
        if len(qset) < 3 or not tot:
            continue                    # too few words to judge by — only the same question matches
        got, hit = _window_cover(qset, e["_w"], idf, default_idf, marks=e.get("_marks"))
        cov = got / tot
        if cov >= 0.7 and top <= hit and len(hit) >= 3:
            out.append((cov, e, sorted(hit)))
    out.sort(key=lambda t: t[0], reverse=True)
    return [{**public(e), "score": round(c, 3), "matched": s} for c, e, s in out[:limit]]


def check_questions(root: Path, questions, adp=None) -> list[dict]:
    """[{id, question, rulings: [...]}] for every question the book already answers (and that doesn't say why it is
    asked again)."""
    out = []
    for q in questions or []:
        if isinstance(q, str):
            q = {"question": q}
        if str(q.get("asked_again") or "").strip():
            continue
        hits = check(root, str(q.get("question") or ""), adp)
        if hits:
            out.append({"id": q.get("id"), "question": q.get("question"), "rulings": hits})
    return out


# ---------------------------------------------------------------- data that says something else
def _value_at(adp, file: str, pointer: str):
    from .jsondoc import split_pointer
    v = adp.load(file)
    for part in split_pointer(pointer):
        if isinstance(v, list):
            v = v[int(part)]
        elif isinstance(v, dict):
            v = v[part]
        else:
            raise KeyError(pointer)
    return v


def conflicts(root: Path, adp, file: str | None = None) -> list[dict]:
    """Every pinned ruling whose field says something else now (or no longer exists). `file` narrows to one data file."""
    if adp is None:
        return []
    out = []
    for e in book(root, adp)["rulings"]:
        at = e.get("applies_to")
        if not at or e.get("retired") or "value" not in e:
            continue
        if file and at.get("file") != file:
            continue
        try:
            now = _value_at(adp, at["file"], at.get("pointer", ""))
            missing = False
        except (KeyError, IndexError, ValueError, OSError, TypeError) as ex:
            now, missing = None, True
            log.info("rulings: %s pinned to %s#%s, which isn't there (%s)", e["id"], at.get("file"), at.get("pointer"), ex)
        if missing or now != e["value"]:
            out.append({"ruling": public(e), "file": at["file"], "pointer": at.get("pointer", ""), "ruled": e["value"],
                        "now": now, "missing": missing,
                        "message": (f"{at['file']}#{at.get('pointer', '')} is gone, but a ruling says it is "
                                    f"{json.dumps(e['value'], ensure_ascii=False)}" if missing else
                                    f"{at['file']}#{at.get('pointer', '')} is {json.dumps(now, ensure_ascii=False)}, but "
                                    f"the ruling of {e.get('when') or 'an undated day'} says {json.dumps(e['value'], ensure_ascii=False)}")})
    return out


def after_edit(adp, rel: str, who: str, touched=None) -> list[dict]:
    """Called by the safe-save path after a change to `rel`: the conflicts on the fields it touched (`touched(pointer)`
    → bool; None = the whole file), journalled once each."""
    try:
        cs = [c for c in conflicts(adp.root, adp, rel) if touched is None or touched(c["pointer"])]
    except Exception as e:  # noqa: BLE001 — a check that can't run never undoes a save
        log.warning("rulings: conflict check after %s failed (%s)", rel, e)
        return []
    for c in cs:
        try:
            journal.append(adp.root, who, "conflict", f"{c['file']}#{c['pointer']}", note=c["message"],
                           link=c["ruling"]["id"])
        except Exception as e:  # noqa: BLE001
            log.warning("rulings: conflict not journalled (%s)", e)
    return cs


def summary(root: Path, adp=None) -> dict:
    b = book(root, adp)
    live = [e for e in b["rulings"] if not e.get("retired")]
    by = {}
    for e in live:
        by[e["kind"]] = by.get(e["kind"], 0) + 1
    return {"count": len(live), "by_kind": by, "retired": len(b["rulings"]) - len(live), "files": len(b["files"]),
            "conflicts": len(conflicts(root, adp)) if adp is not None else None}
