"""Writes the last test run's result to logs/tests_latest.txt, so Settings → About can show it (BUILD 26)."""
from __future__ import annotations
import time
from pathlib import Path

LOGS = Path(__file__).resolve().parents[1] / "logs"


def pytest_sessionfinish(session, exitstatus):
    try:
        tr = session.config.pluginmanager.get_plugin("terminalreporter")
        stats = tr.stats if tr else {}
        parts = [f"{len(stats[k])} {k}" for k in ("passed", "failed", "error", "skipped") if stats.get(k)]
        LOGS.mkdir(exist_ok=True)
        (LOGS / "tests_latest.txt").write_text(
            f"{time.strftime('%Y-%m-%d %H:%M')}  {', '.join(parts) or 'no tests ran'}  (exit {int(exitstatus)})\n", encoding="utf-8")
    except Exception:  # noqa: BLE001 — a record that can't be written never fails the run
        pass
