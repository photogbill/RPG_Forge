"""Chatterbox and Chatterbox Turbo (looked up 2026-11-16 — MIT): reference clips. Every file it makes carries an
inaudible watermark — said on its card. A second opinion. Not installed by the forge on its own."""
from __future__ import annotations

from pathlib import Path

from .. import tools

INFO = {"name": "Chatterbox", "version": "(pin on install)", "licence": {"code": "MIT", "weights": "MIT", "bundles": "read on install"},
        "languages": ["en"], "card": "wants", "can": ["reference", "seed"], "online": False,
        "watermark": "every file it makes carries an inaudible watermark (Resemble's Perth)", "install": "engines/voice/chatterbox"}


def installed() -> bool:
    return (tools.engines_dir() / "chatterbox" / "READY").exists()


def speak(text: str, voice: dict, out_wav: Path, seed: int = 1, device: str = "cuda") -> dict:
    return {"ok": False, "error": "Chatterbox is not installed here yet"}
