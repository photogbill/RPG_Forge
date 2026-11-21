"""Kokoro-82M (looked up 2026-11-16 — Apache-2.0): stock voices only; small enough for a processor — the one that works
while the card is busy, and on a Mac. Not installed by the forge on its own."""
from __future__ import annotations

from pathlib import Path

from .. import tools

INFO = {"name": "Kokoro-82M", "version": "(pin on install)", "licence": {"code": "Apache-2.0", "weights": "Apache-2.0", "bundles": "read on install"},
        "languages": ["en", "and more"], "card": "can", "can": ["preset", "seed"], "online": False, "watermark": None,
        "install": "engines/voice/kokoro (its own environment)"}


def installed() -> bool:
    return (tools.engines_dir() / "kokoro" / "READY").exists()


def speak(text: str, voice: dict, out_wav: Path, seed: int = 1, device: str = "cpu") -> dict:
    return {"ok": False, "error": "Kokoro is not installed here yet"}
