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
    "bakeoff": ("pc", "a bake-off"), "bakeoff_finish": ("pc", "a bake-off"), "bakeoff_flux": ("pc", "a bake-off"), "bakeoff_klein_finish": ("pc", "a bake-off"), "bakeoff_samplers_tonight": ("pc", "a bake-off"), "bakeoff_next_tests": ("pc", "a bake-off"), "first_place": ("pc", "a bake-off"), "materials_round2": ("pc", "the materials bake-off"), "ff_palette": ("pc", "the Filter Forge palette"), "ff_picks": ("pc", "the Filter Forge picks"), "redo_bodies": ("pc", "the redo of the bodies"), "compare_vehicles": ("pc", "the vehicle comparison"), "trellis_weights": ("pc", "the TRELLIS.2 model files"), "trellis_weights_2": ("pc", "the Pixal3D model files"), "trellis_trial": ("pc", "the image-to-3D trial"), "trellis_compare": ("pc", "the image-to-3D comparison"), "trellis_skip_current": ("pc", "dropping ComfyUI's current job"), "trellis_character": ("pc", "the 3D character body test"), "trellis_rig_install": ("pc", "the rigging ComfyUI install"), "trellis_rig_trial": ("pc", "the rigging trial"), "trellis_rig_trial_2": ("pc", "the rigging trial, second pass"), "trellis_cast_overnight": ("pc", "the overnight cast test"), "trellis_cast_overnight_2": ("pc", "the overnight cast test, next pass"), "material_maker": ("pc", "Material Maker, with its data kept beside the forge"), "silo_mission_run": ("pc", "a game's 3D run"), "silo_mission_run_2": ("pc", "a game's 3D run, second part"), "make_what_we_need": ("pc", "the world queue"),
    "sprite_1_start": ("pc", "the sprite test, step 1 (it starts the worker)"),
    "sprite_2_look": ("cli", "bakeoff report sprite_samplers_v2"), "sprite_3_finished": ("cli", "resume"),
    "floor_plans": ("cli", "layout sheets"), "bakeoff_materials": ("pc", "the materials bake-off"),
    "ff_list_for_claude": ("pc", "the Filter Forge list (Filter Forge is on the Windows PC)"),
    "bakeoff_new_models": ("pc", "a bake-off"), "bakeoff_styles": ("pc", "a bake-off"), "bakeoff_tonight": ("pc", "a bake-off"),
    "pull_flux": ("pc", "a model download"), "pull_model": ("pc", "a model download"), "pull_quality": ("pc", "a model download"),
    "filter_forge": ("pc", "Filter Forge"), "filter_forge_proof": ("pc", "Filter Forge"), "push": ("pc", "pushing to GitHub"),
    "publish": ("pc", "publishing"), "test_tools": ("pc", "the tools test"),
    "finale_overnight": ("pc", "the opera finale's overnight run (Blender and ComfyUI on the Windows PC)"),
    "finale_needs": ("pc", "the opera finale's overnight run"), "opera_finale": ("pc", "the opera finale in Blender"),
    "opera_house": ("pc", "the opera house in Blender"), "ff_picks_third_look": ("pc", "Filter Forge"),
    "opera_ceiling": ("pc", "the opera house's painted dome (ComfyUI on the Windows PC)"),
    # (BUILD 73 session: the dome's touch-up tools of 2026-11-17 were missing here, which turned the BUILD 27 check red)
    "opera_ceiling_touch": ("pc", "the opera dome's touch-up (ComfyUI on the Windows PC)"),
    "opera_ceiling_touch_choose": ("pc", "choosing the opera dome's touch-up"),
    "opera_ceiling_touch_look": ("pc", "looking at the opera dome's touch-up"), "ff_picks_last_four": ("pc", "Filter Forge"),
    # BUILD 77 — the ground (CPU only; runs on a Mac too)
    "terrain_bake": ("cli", "terrain bake"), "terrain_profile": ("cli", "terrain profile"),
    # BUILD 74 — the same person, changed (a bake-off: the card)
    "same_person_bakeoff": ("pc", "the same-person bake-off"),
    # BUILD 71 — the voice bench's tools (each in its own folder; a Mac fetches its own build)
    "get_rhubarb": ("cli", "voice get rhubarb"), "get_whisper": ("cli", "voice get whisper"),
    # BUILD 78 — changes a session left waiting for the world queue to be idle (the world queue runs on the Windows PC)
    "put_in_waiting_changes": ("pc", "putting in the changes that waited for the world queue"),
    # BUILD 82 / 83 — new .bat files written while the queue ran (their rows waited for a session that could edit this file)
    "art_around_the_clock": ("pc", "art around the clock (the never-stop launcher)"),
    "art_around_the_clock_at_logon": ("pc", "starting art around the clock when Windows starts"),
    "art_around_the_clock_not_at_logon": ("pc", "no longer starting art around the clock when Windows starts"),
    "make_enemies_and_redo": ("pc", "the enemies' run and the redo"),
    "mcp_check": ("pc", "checking the forge's connector"),
    "mcp_extension": ("pc", "making the forge's connector as an extension file for the Claude app"),
    "mcp_setup": ("pc", "setting up the forge's connector for the Claude app"),
    "review_songs": ("text", "venv-mac/bin/python -m forge.song_review (in Terminal, in the forge's folder)"),
    # BUILD 87 — materials (Filter Forge and Material Maker are on the Windows PC; the sheets are numpy and run anywhere)
    "materials_1_filter_forge": ("pc", "the materials' Filter Forge channels (Filter Forge is on the Windows PC)"),
    "materials_2_all_picks": ("pc", "the Filter Forge channels of every kept pick"),
    "materials_3_material_maker": ("pc", "the Material Maker graphs (Material Maker and the graphics card are on the Windows PC)"),
    "materials_sheets": ("text", "venv-mac/bin/python -m forge.materials sheets (in Terminal, in the forge's folder)"),
    # BUILD 91 — icons and portraits from the made models (Blender on the processor; runs where the forge's Blender is)
    "icons_from_models": ("pc", "the icons and portraits taken from the made 3D models (Blender on the Windows PC)"),
    "portraits_painted": ("pc", "painting the portraits over the bodies (the graphics card in the Windows PC)"),
    # BUILD 43 — the opera, filmed (Blender renders on the Windows PC; the checks and beat maps run anywhere) — merged in by Lane 3
    "opera_film": ("pc", "the opera film in Blender"),
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
