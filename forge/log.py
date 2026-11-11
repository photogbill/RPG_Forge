"""Comprehensive logging: console + a daily file in logs/. Set FORGE_DEBUG=1 for DEBUG."""
from __future__ import annotations
import logging, os, sys
from datetime import datetime
from pathlib import Path

_configured = False


class DailyFileHandler(logging.FileHandler):
    """forge_<date>.log that rolls over at midnight (wiring day W6): when a record's date differs from the open file's,
    the file is closed and forge_<new date>.log is opened. A worker running for days writes each day to its own file.
    `clock` is for tests."""

    def __init__(self, log_dir: Path, clock=datetime.now, encoding: str = "utf-8"):
        self.log_dir = Path(log_dir)
        self.clock = clock
        self.day = clock().date()
        super().__init__(self._path(self.day), encoding=encoding, delay=False)

    def _path(self, day) -> str:
        return str(self.log_dir / f"forge_{day:%Y-%m-%d}.log")

    def emit(self, record: logging.LogRecord) -> None:
        today = self.clock().date()
        if today != self.day:
            self.acquire()
            try:
                if self.stream:
                    self.stream.close()
                self.day = today
                self.baseFilename = os.path.abspath(self._path(today))
                self.stream = self._open()
            finally:
                self.release()
        super().emit(record)


def setup(log_dir: Path) -> None:
    global _configured
    if _configured:
        return
    log_dir.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if os.environ.get("FORGE_DEBUG") else logging.INFO
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%H:%M:%S")
    root = logging.getLogger("forge")
    root.setLevel(logging.DEBUG)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(level)
    ch.setFormatter(fmt)
    root.addHandler(ch)
    fh = DailyFileHandler(log_dir)                    # W6: a new file each day, even for a worker that runs for days
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    root.addHandler(fh)
    _configured = True


def get(name: str) -> logging.Logger:
    return logging.getLogger("forge." + name)
