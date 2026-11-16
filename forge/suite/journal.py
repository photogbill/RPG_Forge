"""The journal — one line per action anyone takes through the suite (William's rule, suite spec §8 rule 1).

`<game_root>/journal/<yyyy-mm>.jsonl`, one JSON object per line: when, **who** (the signed name), what kind, which
object, before → after, a link, a note. An edit, an approval, a flag, a note, a music assignment, a letter, a queued
render, a delivery — every one appends here, from the GUI and from Claude sessions alike (`append()`; command line:
`python -m forge journal add …`). `WORKBENCH_LOG.md` in the game folder is a readable view of the newest entries,
rebuilt after each append — not a second record.

Appends are single writes that the operating system puts at the end of the file atomically, so the GUI and a session
can write at the same time without a lock file (a session's shell cannot delete files, so lock files would be left
behind). On Windows that takes a handle opened for appending only (FILE_APPEND_DATA): Python's O_APPEND there is the C
runtime's "seek to the end, then write", and two writers at once could land on the same spot and one line was lost
(fixed 2026-11-15, the journal test that failed now and then). A torn last line (a power cut mid-write) no longer eats
the next entry either: the next append starts on a fresh line.
"""
from __future__ import annotations
import json, os, threading
from datetime import datetime
from pathlib import Path

from ..log import get
from . import settings

log = get("suite")
VIEW_ENTRIES = 300
_LOCK = threading.Lock()          # writers inside this process take turns; other processes rely on the atomic append
KINDS = ("edit", "approve", "flag", "draft", "note", "propose", "accept", "decline", "music", "letter", "queue",
         "deliver", "conflict", "refused", "test", "session", "setting", "order", "seen", "art")


def folder(game_root: Path) -> Path:
    return Path(game_root) / "journal"


def _short(v, n: int = 2000):
    if isinstance(v, str) and len(v) > n:
        return v[:n] + f"… ({len(v)} characters)"
    return v


def append(game_root: Path, who: str, kind: str, obj: str | None = None, before=None, after=None,
           link: str | None = None, note: str | None = None, when: datetime | None = None, view: bool = True) -> dict:
    if not who:
        raise ValueError("a journal line needs a name (who) — set the identity first")
    when = when or settings.now()
    entry = {"time": when.isoformat(timespec="seconds"), "who": str(who), "kind": str(kind)}
    for k, v in (("obj", obj), ("before", before), ("after", after), ("link", link), ("note", note)):
        if v is not None:
            entry[k] = _short(v)
    d = folder(game_root)
    d.mkdir(parents=True, exist_ok=True)
    line = (json.dumps(entry, ensure_ascii=False) + "\n").encode("utf-8")
    path = d / f"{when:%Y-%m}.jsonl"
    with _LOCK:
        if not _ends_with_newline(path):
            line = b"\n" + line          # the file ends in a torn line: keep it on its own line, keep this entry whole
        _append_bytes(path, line)
    log.info("journal: %s %s %s %s", entry["who"], entry["kind"], entry.get("obj", ""), entry.get("note", "") or "")
    if view:
        try:
            write_view(game_root)
        except OSError as e:          # the record is the .jsonl; a view that cannot be rewritten is only a warning
            log.warning("journal: WORKBENCH_LOG.md not rewritten: %s", e)
    return entry


def _ends_with_newline(path: Path) -> bool:
    """True when the file is empty, missing, or its last byte is a newline."""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            if f.tell() == 0:
                return True
            f.seek(-1, os.SEEK_END)
            return f.read(1) == b"\n"
    except FileNotFoundError:
        return True


def _append_bytes(path: Path, data: bytes) -> None:
    """One write at the end of the file, atomic against other writers (other threads and other processes)."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
                                    wintypes.DWORD, wintypes.HANDLE]
        k32.CreateFileW.restype = wintypes.HANDLE
        k32.WriteFile.argtypes = [wintypes.HANDLE, wintypes.LPCVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                                  wintypes.LPVOID]
        k32.WriteFile.restype = wintypes.BOOL
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        FILE_APPEND_DATA, SYNCHRONIZE = 0x0004, 0x00100000
        SHARE_ALL, OPEN_ALWAYS, NORMAL = 0x1 | 0x2 | 0x4, 4, 0x80
        h = k32.CreateFileW(str(path), FILE_APPEND_DATA | SYNCHRONIZE, SHARE_ALL, None, OPEN_ALWAYS, NORMAL, None)
        if h in (None, 0) or h == ctypes.c_void_p(-1).value:
            raise OSError(ctypes.get_last_error(), "the journal could not be opened for appending", str(path))
        try:
            done = wintypes.DWORD(0)
            if not k32.WriteFile(h, data, len(data), ctypes.byref(done), None) or done.value != len(data):
                raise OSError(ctypes.get_last_error(), "the journal line was not written whole", str(path))
        finally:
            k32.CloseHandle(h)
        return
    fd = os.open(str(path), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)   # POSIX: O_APPEND writes are atomic
    try:
        os.write(fd, data)
    finally:
        os.close(fd)


def read(game_root: Path, since: str | None = None, who: str | None = None, kinds=None, limit: int | None = None) -> list[dict]:
    """Entries oldest first. `since` is an ISO time (string compare works: the format is fixed)."""
    out: list[dict] = []
    d = folder(game_root)
    if not d.is_dir():
        return out
    for p in sorted(d.glob("*.jsonl")):
        if since and p.stem < since[:7]:
            continue
        for raw in p.read_text(encoding="utf-8", errors="replace").splitlines():
            if not raw.strip():
                continue
            try:
                e = json.loads(raw)
            except ValueError:
                continue                    # a torn line (power cut mid-write) is skipped, not fatal
            if since and str(e.get("time", "")) <= since:
                continue
            if who and e.get("who") != who:
                continue
            if kinds and e.get("kind") not in kinds:
                continue
            out.append(e)
    return out[-limit:] if limit else out


def _fmt(v) -> str:
    if v is None:
        return ""
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    s = s.replace("\n", " ⏎ ")
    return s if len(s) <= 220 else s[:217] + "…"


def write_view(game_root: Path) -> Path:
    entries = read(game_root)[-VIEW_ENTRIES:]
    lines = ["# Workbench log — a readable view of the journal", "",
             f"*Rebuilt after every journal line; the record itself is `journal/*.jsonl`. Newest first; the last {VIEW_ENTRIES}.*", ""]
    for e in reversed(entries):
        head = f"- **{e.get('time', '?').replace('T', ' ')}** · {e.get('who', '?')} · {e.get('kind', '?')}"
        if e.get("obj"):
            head += f" · `{e['obj']}`"
        lines.append(head)
        if "before" in e or "after" in e:
            lines.append(f"  - before: {_fmt(e.get('before'))}")
            lines.append(f"  - after: {_fmt(e.get('after'))}")
        if e.get("note"):
            lines.append(f"  - {_fmt(e['note'])}")
        if e.get("link"):
            lines.append(f"  - see {e['link']}")
    p = Path(game_root) / "WORKBENCH_LOG.md"
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, p)
    return p
