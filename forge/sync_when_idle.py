"""Put in waiting changes when the world queue is idle (BUILD 78) — `put_in_waiting_changes.bat`.

The rule for a running worker (BUILD_RULES): a session may only add new files and plug-ins while the art worker or the
world queue runs; an edit to an existing file waits until the queue is idle. A session that has such edits leaves them
here as a *package* — `_xfer/waiting/<name>/` with `manifest.json` and the files under `files/` — and this puts them in:

1. If the world queue is running, it says so and asks. Only when the person types S does it ask the queue to stop after
   the thing in hand (nothing in hand is lost), and it waits for that. Close the window instead to leave everything.
2. Every file is checked against the copy the session started from: one that someone changed since is **not**
   overwritten — the whole package waits and the window says which file and why. Nothing half-done.
3. What each file was is kept in the package's `before/`; the package's tests run; if one fails, everything is put back.
4. The package's after-steps run (its own forge commands, e.g. putting failed things back in line), signed as the session.
5. The queue is started again if it was running, and the package is marked done (`APPLIED.txt`, with the report).

Nothing here is deleted, and nothing names a game.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from . import config as cfgmod

ROOT = cfgmod.ROOT
WAITING = ROOT / "_xfer" / "waiting"


def md5(p: Path) -> str | None:
    try:
        return hashlib.md5(Path(p).read_bytes()).hexdigest()
    except OSError:
        return None


def packages(base: Path = WAITING) -> list[Path]:
    return sorted(p for p in base.glob("*") if (p / "manifest.json").exists() and not (p / "APPLIED.txt").exists())


def check(pkg: Path, root: Path = ROOT) -> dict:
    """{"ok", "todo": [path], "already": [path], "conflicts": [{"path", "why"}]} — nothing is written."""
    man = json.loads((pkg / "manifest.json").read_text(encoding="utf-8"))
    todo, already, conflicts = [], [], []
    for f in man["files"]:
        rel = f["path"]
        src = pkg / "files" / rel
        if md5(src) != f["new_md5"]:
            conflicts.append({"path": rel, "why": "the package's own copy is damaged (its md5 differs) — ask the session for it again"})
            continue
        cur = md5(root / rel)
        if cur == f["new_md5"]:
            already.append(rel)
        elif cur == f.get("base_md5"):
            todo.append(rel)
        else:
            conflicts.append({"path": rel, "why": ("it was not there when the session started, and it is now" if f.get("base_md5") is None
                                                   else "it is gone" if cur is None else
                                                   "someone changed it since the session read it — it must be merged by hand, not overwritten")})
    return {"ok": not conflicts, "todo": todo, "already": already, "conflicts": conflicts, "manifest": man}


def apply(pkg: Path, root: Path = ROOT) -> dict:
    c = check(pkg, root)
    if not c["ok"]:
        return {**c, "applied": []}
    before = pkg / "before"
    applied = []
    for rel in c["todo"]:
        dst = root / rel
        if dst.exists():
            (before / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dst, before / rel)
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(dst.name + ".putting-in")
        shutil.copyfile(pkg / "files" / rel, tmp)
        os.replace(tmp, dst)
        applied.append(rel)
    bad = [rel for rel in applied if md5(root / rel) != next(f["new_md5"] for f in c["manifest"]["files"] if f["path"] == rel)]
    if bad:
        put_back(pkg, applied, root)
        return {**c, "ok": False, "applied": [], "conflicts": [{"path": b, "why": "the copy did not read back the same"} for b in bad]}
    return {**c, "applied": applied}


def put_back(pkg: Path, applied: list[str], root: Path = ROOT) -> list[str]:
    """Undo apply(): each file as it was (from before/); a file that was new is moved aside into before/_new/, not deleted."""
    done = []
    for rel in applied:
        b = pkg / "before" / rel
        dst = root / rel
        if b.exists():
            shutil.copyfile(b, dst)
        elif dst.exists():
            aside = pkg / "before" / "_new" / rel
            aside.parent.mkdir(parents=True, exist_ok=True)
            os.replace(dst, aside)
        done.append(rel)
    return done


def _queue(cfg: dict, gid: str) -> dict:
    from .threed import world
    return world.launcher_state(cfg, gid)


def _wait_idle(cfg: dict, gid: str, say=print) -> None:
    from .threed import world
    last = ""
    while _queue(cfg, gid).get("running"):
        try:
            s = world.status(cfg, gid)
            now = next((i["id"] for i in s["items"] if i["state"] == "making"), "")
        except Exception:  # noqa: BLE001
            now = ""
        if now != last:
            say(f"  … waiting for the queue to finish {now or 'the thing in hand'}")
            last = now
        time.sleep(15)


def run(argv: list[str] | None = None, ask=input, say=print) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cfg = cfgmod.load()
    gid = cfgmod.default_game(cfg)
    pk = packages()
    if not pk:
        say("Nothing is waiting to be put in.")
        return 0
    for p in pk:
        man = json.loads((p / "manifest.json").read_text(encoding="utf-8"))
        say(f"\n== {man.get('title') or p.name}  (from {man.get('by', 'a session')}, {man.get('at', '')})")
        for ln in man.get("says") or []:
            say("   " + ln)
    was_running = bool(_queue(cfg, gid).get("running"))
    if was_running:
        say("\nThe world queue is running. These changes go in only while it is stopped.")
        a = ask("Type S and press Enter to ask it to stop after the thing in hand (it starts again afterwards),\n"
                "or just close this window to leave everything as it is: ").strip().lower()
        if a != "s":
            say("Left as it is. Nothing was changed.")
            return 1
        from .threed import world
        # BUILD 84: a pause, not a stop — art around the clock (the never-stop launcher) waits and carries on afterwards
        world.ask_stop(cfg, gid, os.environ.get("FORGE_IDENTITY") or "put_in_waiting_changes.bat",
                       pause_for="putting in the changes that waited")
        _wait_idle(cfg, gid, say)
        say("  The queue has stopped.")
    code = 0
    try:
        for p in pk:
            code = max(code, _one(cfg, p, say))
    finally:
        if was_running:
            from .threed import world
            world.put_in_done(cfg, gid)
    if was_running:
        _start_queue(cfg, gid, say)
    return code


def _failing(tests: list[str]) -> tuple[set[str], str]:
    """The tests among `tests` that fail now (node ids), and pytest's last line. Only files that exist are run."""
    have = [t for t in tests if (ROOT / t.split("::")[0]).exists()]
    if not have:
        return set(), "(no tests yet)"
    t = subprocess.run([sys.executable, "-m", "pytest", "-q", "-rfE", "-p", "no:cacheprovider", *have], cwd=str(ROOT),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = t.stdout or ""
    bad = {ln.split(" ", 1)[1].split(" - ")[0].strip() for ln in out.splitlines() if ln.startswith(("FAILED ", "ERROR "))}
    if t.returncode not in (0, 1) and not bad:          # pytest could not run them at all
        bad = {f"(pytest exit {t.returncode})"}
    return bad, (out.strip().splitlines()[-1:] or ["(no output)"])[0]


def _one(cfg: dict, p: Path, say) -> int:
    man = json.loads((p / "manifest.json").read_text(encoding="utf-8"))
    report = [f"{datetime.now():%Y-%m-%d %H:%M:%S}  {man.get('title') or p.name}"]
    tests = man.get("tests") or []
    before_bad = set()
    if tests and check(p)["ok"]:
        say("Running its tests on the forge as it is now (so a test that already failed is not blamed on the change) …")
        before_bad, last = _failing(tests)
        say("   " + last)
        report.append("tests before: " + last)
        if before_bad:                             # 2026-11-20: named, so a failure nobody caused is not nameless for days
            report.append("failing before the change: " + ", ".join(sorted(before_bad)))
    r = apply(p)
    if not r["ok"]:
        say("\nNOT put in — nothing was changed:")
        for c in r["conflicts"]:
            say(f"   {c['path']}: {c['why']}")
        (p / "NOT_APPLIED.txt").write_text("\n".join(report + [f"{c['path']}: {c['why']}" for c in r["conflicts"]]) + "\n", encoding="utf-8")
        return 1
    say(f"\n{len(r['applied'])} file(s) put in ({len(r['already'])} were already there).")
    report.append(f"put in: {', '.join(r['applied']) or '—'}")
    if tests:
        say("Running its tests with the changes in …")
        after_bad, last = _failing(tests)
        say("   " + last)
        report.append("tests after: " + last)
        new_bad = sorted(after_bad - before_bad)
        if new_bad:
            put_back(p, r["applied"])
            (p / "tests_failed.txt").write_text("\n".join(new_bad) + "\n", encoding="utf-8")
            say("A test that passed before fails now — every file is back as it was: " + ", ".join(new_bad[:6]))
            (p / "NOT_APPLIED.txt").write_text("\n".join(report + ["new failures — put back:"] + new_bad) + "\n", encoding="utf-8")
            return 1
        if after_bad:
            say(f"   ({len(after_bad)} failed before the change as well — not this package's.)")
            for name in sorted(after_bad)[:12]:
                say("      " + name)
            report.append("failing after it as well (not this package's): " + ", ".join(sorted(after_bad)))
    env = dict(os.environ)
    if man.get("sign_as"):
        env["FORGE_IDENTITY"] = man["sign_as"]
    for step in man.get("after") or []:
        say("Then: " + " ".join(step["args"]) + (f"  — {step['why']}" if step.get("why") else ""))
        s = subprocess.run([sys.executable, "-m", "forge", *step["args"]], cwd=str(ROOT), env=env, capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
        out = ((s.stdout or "") + (s.stderr or "")).strip()
        for ln in out.splitlines()[-6:]:
            say("   " + ln)
        report.append(f"step {' '.join(step['args'])}: exit {s.returncode}: {out[-800:]}")
    for ln in man.get("then_tell") or []:
        say("\n" + ln)
    (p / "APPLIED.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
    return 0


def _start_queue(cfg: dict, gid: str, say) -> None:
    bat = ROOT / "make_what_we_need.bat"
    if os.name == "nt" and bat.exists():
        subprocess.Popen(f'start "RPG_Forge world queue" "{bat}"', shell=True, cwd=str(ROOT))
        say("\nThe world queue is starting again in its own window.")
    else:
        say("\nStart the world queue again when you like (make_what_we_need.bat).")


if __name__ == "__main__":
    sys.exit(run())
