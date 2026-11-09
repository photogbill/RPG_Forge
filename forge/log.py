"""Comprehensive logging: console + a daily file in logs/. Set FORGE_DEBUG=1 for DEBUG."""
from __future__ import annotations
import logging, os, sys
from datetime import datetime
from pathlib import Path

_configured = False


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
    fh = logging.FileHandler(log_dir / f"forge_{datetime.now():%Y-%m-%d}.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    root.addHandler(fh)
    _configured = True


def get(name: str) -> logging.Logger:
    return logging.getLogger("forge." + name)
