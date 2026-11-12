"""What the app tells you to run — one table, per computer (BUILD 27).

The forge's messages say "run handoff_in.bat <name>", "submit.bat it", "the same as pause.bat". On Windows those words
stay exactly as they are. On a Mac (or Linux) **no .bat is ever shown**: each one is said as the button in the suite that
does it, or as `./forge.command <the same words>` (forge.command runs `python -m forge <words>`), or — for what only the
PC with the art worker can do — as that plainly.

`say(text)` rewrites one message; `deep(obj)` rewrites every string in a response. The server runs every JSON answer and
the page itself through them on a Mac.
"""
from __future__ import annotations
import re

from . import osopen, settings

# bat stem → ("cli", "<python -m forge words>")  |  ("button", "<where in the suite>")  |  ("pc", "<what it is>")
TABLE: dict[str, tuple[str, str]] = {
    "forge": ("cli", "suite"), "ui": ("button", "Art → Queue & pictures"),
    "pause": ("button", "the art worker’s ■ Stop button in the sidebar"), "resume": ("button", "Home → ⟲ Resume"),
    "approve": ("cli", "approve"), "brief": ("cli", "brief"), "characters": ("cli", "characters"), "credits": ("cli", "credits"),
    "deliver": ("cli", "deliver"), "eta": ("cli", "eta"), "feedback_in": ("cli", "feedback-in"),
    "handoff_in": ("cli", "handoff in"), "handoff_out": ("cli", "handoff out"), "handoff_tool_add": ("cli", "handoff tool add"),
    "housekeeping": ("cli", "housekeeping"), "kit_check": ("cli", "kit check"), "licence": ("cli", "models licence"),
    "licences": ("cli", "licences"), "mail": ("button", "Messages"), "models_report": ("cli", "models-report"),
    "night_report": ("cli", "report night"), "op": ("cli", "op"), "paint_missing": ("cli", "brief missing"),
    "produce": ("cli", "produce"), "produce_watch": ("cli", "produce watch"), "prompts": ("button", "Workshop → Prompt library"),
    "rate": ("cli", "rate"), "retry_failed": ("cli", "retry"), "review": ("cli", "review"), "review_compact": ("cli", "review --compact"),
    "scan_models": ("button", "Workshop → Models → Scan"), "sprite_intake": ("button", "Characters → Sprite intake"),
    "submit": ("cli", "submit"), "wanted": ("button", "Art → Wanted"), "bakeoff_report": ("cli", "bakeoff report"),
    "run_tests": ("text", "venv-mac/bin/python -m pytest (in Terminal, in the forge's folder)"),
    # the GPU side — only the PC with the art worker
    "run_worker": ("pc", "the art worker"), "run_cpu_worker": ("pc", "the CPU worker"), "start_comfy": ("pc", "ComfyUI"),
    "install": ("pc", "the GPU side's install"), "install_comfy": ("pc", "ComfyUI's install"),
    "install_comfy_aux": ("pc", "ComfyUI's extra nodes"), "install_comfy_faces": ("pc", "ComfyUI's face nodes"),
    "install_comfy_gguf": ("pc", "ComfyUI's GGUF nodes"), "doctor": ("pc", "the worker's check-up"),
    "bakeoff": ("pc", "a bake-off"), "bakeoff_finish": ("pc", "a bake-off"), "bakeoff_flux": ("pc", "a bake-off"), "bakeoff_klein_finish": ("pc", "a bake-off"), "bakeoff_samplers_tonight": ("pc", "a bake-off"), "bakeoff_next_tests": ("pc", "a bake-off"),
    "sprite_1_start": ("pc", "the sprite test, step 1 (it starts the worker)"),
    "sprite_2_look": ("cli", "bakeoff report sprite_samplers_v2"), "sprite_3_finished": ("cli", "resume"),
    "floor_plans": ("cli", "layout sheets"), "bakeoff_materials": ("pc", "the materials bake-off"),
    "ff_list_for_claude": ("pc", "the Filter Forge list (Filter Forge is on the Windows PC)"),
    "bakeoff_new_models": ("pc", "a bake-off"), "bakeoff_styles": ("pc", "a bake-off"), "bakeoff_tonight": ("pc", "a bake-off"),
    "pull_flux": ("pc", "a model download"), "pull_model": ("pc", "a model download"), "pull_quality": ("pc", "a model download"),
    "filter_forge": ("pc", "Filter Forge"), "filter_forge_proof": ("pc", "Filter Forge"), "push": ("pc", "pushing to GitHub"),
    "publish": ("pc", "publishing"), "test_tools": ("pc", "the tools test"),
}
BAT = re.compile(r"\b([A-Za-z0-9_]+)\.bat\b")
DEFAULT_PC = "the Windows PC with the art worker"


def worker_pc() -> str:
    """What this computer calls the PC the art worker runs on (local/suite.json → worker_pc)."""
    return str(settings.load().get("worker_pc") or DEFAULT_PC)


def keep_bats() -> bool:
    """Windows keeps its .bat words; so does Linux (a session's shell, where nobody double-clicks). A Mac never sees one."""
    return osopen.system() != "mac"


def _words(stem: str) -> str:
    kind, words = TABLE.get(stem.lower(), ("cli", stem.lower().replace("_", "-")))
    if kind in ("button", "text"):
        return words
    if kind == "pc":
        return f"{words} (on {worker_pc()})"
    return "./forge.command " + words


def say(text: str, page: bool = False) -> str:
    """One message, in this computer's words. `page`: the text is a page's source (HTML with script in it), so the
    words put in carry no straight quote that could end a string in its code."""
    if keep_bats() or not isinstance(text, str) or ".bat" not in text:
        return text

    def one(m: re.Match) -> str:
        w = _words(m.group(1))
        return w.replace("'", "’").replace('"', "”") if page else w
    t = BAT.sub(one, text)
    return t.replace("a .bat", "a script").replace(".bat", "")


def deep(obj):
    """Every string in a response, in this computer's words."""
    if keep_bats():
        return obj
    if isinstance(obj, str):
        return say(obj)
    if isinstance(obj, list):
        return [deep(x) for x in obj]
    if isinstance(obj, dict):
        return {k: deep(v) for k, v in obj.items()}
    return obj
