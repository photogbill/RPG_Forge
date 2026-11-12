"""File names the suite makes are valid on Windows, macOS and Linux (BUILD 27).

None of \\ / : * ? " < > |, no control characters, no trailing dot or space, no reserved Windows name (CON, PRN, AUX,
NUL, COM1–9, LPT1–9 — with or without an extension), at most 120 characters. `portable(name)` makes one; `problems(name)`
says what is wrong with one (a test runs every kind of name the suite writes through it).
"""
from __future__ import annotations
import re

BAD = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
MAX = 120


def problems(name: str) -> list[str]:
    out = []
    if not name:
        return ["empty"]
    if BAD.search(name):
        out.append("a character Windows or macOS refuses")
    if name[-1] in ". ":
        out.append("ends with a dot or a space")
    if name.split(".")[0].strip().lower() in RESERVED:
        out.append("a name Windows reserves")
    if len(name) > MAX:
        out.append(f"longer than {MAX} characters")
    return out


def portable(name: str, default: str = "file") -> str:
    n = BAD.sub("_", str(name)).strip()
    if len(n) > MAX:
        stem, dot, ext = n.rpartition(".")
        n = (stem[: MAX - len(ext) - 1] + "." + ext) if dot and len(ext) <= 8 else n[:MAX]
    n = n.rstrip(". ") or default
    if n.split(".")[0].strip().lower() in RESERVED:
        n = "_" + n
    return n
