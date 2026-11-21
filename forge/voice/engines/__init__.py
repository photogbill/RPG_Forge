"""One small contract, any number of voice engines (BUILD 71 part 5). An engine is one file here and one install script:

    INFO = {"name", "version", "licence": {"code", "weights", "bundles"}, "languages", "card": "wants" | "no" | "can",
            "can": ["preset", "described", "reference", "delivery", "seed"], "online": False, "watermark": None | "words",
            "install": "how it is installed (into engines/voice/<name>/)"}
    def speak(text, voice: dict, out_wav: Path, seed: int, device: str) -> dict   # {"ok", "seconds", "timing"?: [...]}

`voice` holds what the card says: {"way": "preset" | "described" | "reference", "preset", "description", "clip", "clip_text",
"delivery"}. The pane shows only the controls an engine `can`. An engine marked online is never handed a file.
"""
from __future__ import annotations

import importlib
import pkgutil

from ..licences import gate

WAYS = ("preset", "described", "reference")


def names() -> list[str]:
    return sorted(m.name for m in pkgutil.iter_modules(__path__) if not m.name.startswith("_"))


def get(name: str):
    return importlib.import_module(f"{__name__}.{name}")


def describe(name: str) -> dict:
    m = get(name)
    ok, why = gate(m.INFO["licence"])
    return {**m.INFO, "id": name, "licence_ok": ok, "licence_why": why, "installed": installed(name)}


def installed(name: str) -> bool:
    m = get(name)
    f = getattr(m, "installed", None)
    return bool(f()) if callable(f) else False


def all_engines() -> list[dict]:
    return [describe(n) for n in names()]
