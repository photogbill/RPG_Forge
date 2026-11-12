"""Which computer this is, and opening a file or folder the way a double-click would (BUILD 27).

One place for each thing that differs between Windows, macOS and Linux:
- `system()` → "windows" | "mac" | "linux" (from sys.platform, so a test can play any of them);
- `open_path(p)` → Explorer / the default program on Windows (`os.startfile`), `open` on macOS, `xdg-open` on Linux.
Every caller in the forge goes through `open_path`; nothing else calls startfile or xdg-open.
"""
from __future__ import annotations
import os, subprocess, sys
from pathlib import Path


def system() -> str:
    p = sys.platform
    if p.startswith("win"):
        return "windows"
    if p == "darwin":
        return "mac"
    return "linux"


def opener() -> list[str] | None:
    """The command that opens a path on this computer (None on Windows: os.startfile does it)."""
    s = system()
    return None if s == "windows" else (["open"] if s == "mac" else ["xdg-open"])


def open_path(p) -> None:
    """Open a file or folder as a double-click would. Raises OSError when it can't."""
    p = str(Path(p))
    cmd = opener()
    if cmd is None:
        os.startfile(p)                       # noqa: S606 — Explorer / the default program, as a double-click
        return
    subprocess.Popen(cmd + [p], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
