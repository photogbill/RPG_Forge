"""Qwen3-TTS (looked up 2026-11-16: https://github.com/QwenLM/Qwen3-TTS — Apache-2.0, models and tokenizers): described,
reference and preset voices, and instructions for delivery. First, because it does all three ways. Wants the card.
Not installed by the forge on its own: the install script is William's to run, after he has read the licence on the day."""
from __future__ import annotations

from pathlib import Path

from .. import tools

INFO = {"name": "Qwen3-TTS", "version": "(pin on install)", "licence": {"code": "Apache-2.0", "weights": "Apache-2.0", "bundles": "read on install"},
        "languages": ["en", "zh", "it", "and more"], "card": "wants", "can": ["preset", "described", "reference", "delivery", "seed"],
        "online": False, "watermark": None, "install": "engines/voice/qwen3_tts (its own environment) — install script to be written once William says which size"}


def installed() -> bool:
    return (tools.engines_dir() / "qwen3_tts" / "READY").exists()


def speak(text: str, voice: dict, out_wav: Path, seed: int = 1, device: str = "cuda") -> dict:
    return {"ok": False, "error": "Qwen3-TTS is not installed here yet"}
