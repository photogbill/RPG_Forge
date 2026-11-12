"""The materials bake-off: which source makes the best surface for each material.

Three sources, head to head, on the same material list:
  sdxl          a place checkpoint (txt2img through the bake-off machinery), prompted for a flat top-down material
  klein         FLUX.2 [klein] 4B (Apache-2.0), the same prompts
  filter_forge  Filter Forge texture filters (its command-line renderer, the filter_forge job type) — matched to each
                material by the words in the filter's name; a material no filter matches is listed, never guessed

Everything is post-processed the same way in report.py (made seamless, normals, scored). The weathering pass (the
War and the After from the Peace tile) is planned from the picks: img2img repaints with the material's era words
against Filter Forge effect filters.

This module only *plans*: it writes bake-off suites and job lists. Queuing them is the person's (bakeoff_materials.bat).
"""
from __future__ import annotations
import json
import re
from pathlib import Path

PREFIX = ("seamless tileable texture, flat top-down orthographic view straight down at {words}, even diffuse light, "
          "no shadows, no perspective, no horizon, no objects, fills the whole frame edge to edge, highly detailed, 8k")
NEGATIVE = ("perspective, horizon, sky, wall, objects, furniture, people, text, letters, logo, watermark, border, frame, "
            "vignette, cast shadows, lighting gradient, blurry, low quality")

# The generic first pass. A game's adapter gives its own list (material_list) and may add words, eras and its places.
# words: what the prompt says · ff: words a Filter Forge filter's name may carry · weather: what the War / After do to it
DEFAULT: list[dict] = [
    {"id": "dirt_road", "name": "dirt road", "words": "packed dirt road with wheel ruts, loose dust and small stones", "ff": ["dirt", "soil", "earth", "path"]},
    {"id": "gravel", "name": "gravel road", "words": "loose grey gravel road surface, scattered pebbles of mixed size", "ff": ["gravel", "pebble", "stones"]},
    {"id": "cracked_asphalt", "name": "cracked asphalt", "words": "cracked grey asphalt road surface with faded paint flecks", "ff": ["asphalt", "tarmac", "road"]},
    {"id": "poured_concrete", "name": "poured concrete", "words": "smooth poured concrete slab with fine pores and hairline cracks", "ff": ["concrete", "cement"]},
    {"id": "scorched_concrete", "name": "scorched concrete", "words": "concrete slab blackened by fire, soot streaks and spalling", "ff": ["concrete", "burn", "scorch"]},
    {"id": "rusted_steel", "name": "rusted steel deck", "words": "rusted steel deck plates with rivets and flaking paint", "ff": ["rust", "steel", "metal", "iron"]},
    {"id": "diamond_plate", "name": "diamond plate", "words": "worn diamond plate steel floor, scuffed raised pattern", "ff": ["diamond", "tread", "checker plate", "metal plate"]},
    {"id": "foundry_floor", "name": "foundry floor", "words": "industrial foundry floor, oil-stained concrete with metal filings and scorch marks", "ff": ["concrete", "industrial", "oil", "factory"]},
    {"id": "cave_rock", "name": "cave rock", "words": "rough dark cave rock floor, uneven stone", "ff": ["rock", "stone", "cave"]},
    {"id": "wet_cave_rock", "name": "wet cave rock", "words": "wet glistening cave rock with shallow puddles", "ff": ["rock", "wet", "stone"]},
    {"id": "desert_sand", "name": "desert sand", "words": "fine desert sand with wind ripples and scattered pebbles", "ff": ["sand", "desert", "dune"]},
    {"id": "hardpan", "name": "hardpan", "words": "cracked dry desert hardpan clay, polygonal cracks", "ff": ["dry", "cracked earth", "clay", "mud crack"]},
    {"id": "fused_glass", "name": "fused glass", "words": "ground fused into glassy green-black slag, bubbles and fractures", "ff": ["glass", "obsidian", "lava"]},
    {"id": "mud", "name": "mud", "words": "dark wet mud with boot prints and puddles", "ff": ["mud", "dirt", "soil"]},
    {"id": "grass", "name": "grass", "words": "short green grass lawn, some clover", "ff": ["grass", "lawn", "turf"]},
    {"id": "rubble", "name": "rubble", "words": "broken concrete and brick rubble with weeds growing through", "ff": ["rubble", "debris", "gravel", "rocks"]},
    {"id": "brick", "name": "brick", "words": "red brick paving laid in a running bond, worn mortar", "ff": ["brick"]},
    {"id": "cinder_block", "name": "cinder block", "words": "grey cinder block wall seen face-on, mortar lines", "ff": ["block", "cinder", "breeze"]},
    {"id": "tile_floor", "name": "tile floor (clinic)", "words": "white ceramic square floor tiles with grey grout, a clinic floor", "ff": ["tile", "ceramic"]},
    {"id": "linoleum", "name": "linoleum (school)", "words": "speckled school linoleum floor, scuff marks", "ff": ["linoleum", "vinyl", "terrazzo"]},
    {"id": "wood_plank", "name": "wood plank", "words": "weathered wooden floor planks with nail heads", "ff": ["wood", "plank", "parquet"]},
    {"id": "worn_carpet", "name": "carpet (worn)", "words": "worn low-pile carpet with a faded pattern and stains", "ff": ["carpet", "fabric", "rug"]},
    {"id": "machine_plating", "name": "war-machine plating", "words": "dark armoured machine plating, panel seams, scorched and scratched", "ff": ["armor", "armour", "panel", "sci-fi", "plating"]},
    {"id": "shanty_tin", "name": "shanty tin", "words": "corrugated tin sheets patched together, rust and rivets", "ff": ["corrugated", "tin", "sheet metal"]},
    {"id": "sandbag", "name": "sandbag", "words": "stacked sandbags seen from above, burlap weave", "ff": ["sandbag", "burlap", "sack"]},
]

ERA_WORDS = {"war": "the same surface during a war: scorch marks, fresh damage, soot, scattered debris",
             "after": "the same surface twenty years after a war: weathered, faded, grime, weeds in the cracks, patched repairs"}
WEATHER_FF = ["rust", "grime", "dirt", "weather", "aged", "burn", "scorch", "crack", "grunge", "dust"]

SUITES = {"sdxl": "materials_sdxl_v1", "klein": "materials_klein_v1", "ff": "materials_ff_v1", "weather": "weathering_v1"}


def prompts(materials: list[dict]) -> dict[str, str]:
    return {m["id"]: PREFIX.format(words=m["words"]) for m in materials}


def suites(game: str, materials: list[dict], sdxl_checkpoint: str = "ArtUniverseSDXL_v8.safetensors",
           klein_checkpoints: list[str] | None = None, seeds: list[int] | None = None, size: int = 1024) -> list[dict]:
    """The two txt2img bake-off suites (same prompts, same seed, square)."""
    p = prompts(materials)
    seeds = seeds or [1001]
    common = {"game": game, "loras": [], "include_no_lora": True, "skip": {"checkpoints": [], "loras": []},
              "seeds": seeds, "size": [size, size], "negative": NEGATIVE,
              "categories": {"materials": {"size": [size, size], "prompts": p}}}
    sdxl = {"suite": SUITES["sdxl"], **common, "checkpoints": [sdxl_checkpoint], "steps": 28, "cfg": 6.0,
            "sampler": "dpmpp_2m", "scheduler": "karras", "seconds_per_render": 10.0,
            "_comment": "Materials bake-off (BUILD 30), source 2: the place checkpoint, a flat top-down material per prompt. "
                        "Report: tiles report (bakeoff_materials.bat writes it when you run it again)."}
    klein = {"suite": SUITES["klein"], **common, "graph": "flux2_klein", "base_override": "flux2",
             "checkpoint_kinds": ["unet", "unknown", "checkpoint"],
             "checkpoints": klein_checkpoints or ["flux-2-klein-4b.safetensors", "flux-2-klein-base-4b.safetensors"],
             "steps": None, "cfg": None, "sampler": "euler", "scheduler": "simple", "seconds_per_render": 20.0,
             "_comment": "Materials bake-off (BUILD 30), source 3: FLUX.2 [klein] 4B (Apache-2.0) — distilled and base. "
                         "The 9B is non-commercial and is not in this suite."}
    return [sdxl, klein]


def _words(name: str) -> str:
    return re.sub(r"[_\-]+", " ", name).lower()


def match_filters(materials: list[dict], listing: dict[str, list[dict]], per_material: int = 2,
                  chosen: dict | None = None) -> tuple[dict, list]:
    """Texture filters for each material, best first. `chosen` — {material id: [filter file stems or names]} — is a
    person's (or a session's) pick by the filters' real names and wins; otherwise a filter whose name carries one of the
    material's words (more words matched, then seamless presets). Returns ({material id: [filter rows]}, [unmatched])."""
    rows = [r for rs in (listing or {}).values() for r in rs if r.get("kind") == "texture"]
    found, missing = {}, []
    by_key = {}
    for r in rows:
        for k in (Path(str(r.get("file") or "")).stem.lower(), str(r.get("name") or "").lower()):
            by_key.setdefault(k, r)
    for m in materials:
        if chosen is not None and chosen.get(m["id"]) == []:
            missing.append(m["id"])                  # "none fits" is a pick too: no word-guess behind it
            continue
        picks = [by_key[str(k).lower()] for k in (chosen or {}).get(m["id"], []) if str(k).lower() in by_key]
        if picks:
            found[m["id"]] = picks[:max(per_material, len(picks))]
            continue
        scored = []
        for r in rows:
            nm = _words(str(r.get("name") or "")) + " " + _words(Path(str(r.get("file") or "")).stem)
            hits = sum(1 for w in m.get("ff") or [] if re.search(r"\b" + re.escape(w.lower()) + r"\b", nm))
            if hits:
                scored.append((-hits, 0 if r.get("seamless_presets") else 1, str(r.get("name")), r))
        scored.sort(key=lambda t: t[:3])
        if scored:
            found[m["id"]] = [t[3] for t in scored[:per_material]]
        else:
            missing.append(m["id"])
    return found, missing


def ff_jobs(game: str, materials: list[dict], listing: dict, size: int = 2048, per_material: int = 2,
            chosen: dict | None = None) -> tuple[list[dict], list[str]]:
    """filter_forge jobs for the materials bake-off (a seamless preset when the filter has one; made tileable in the
    forge either way, so every source is measured the same). Priority 1: they run first — quick CPU renders — so a
    Filter Forge problem shows within minutes, not after a night of SDXL and Klein."""
    found, missing = match_filters(materials, listing, per_material, chosen)
    jobs = []
    for m in materials:
        for r in found.get(m["id"], []):
            preset = (r.get("seamless_presets") or [0])[0]
            stem = Path(str(r.get("file"))).stem
            jobs.append({"type": "filter_forge", "game": game, "name": f"mat_{m['id']}_{_slug(stem)}",
                         "batch": f"bakeoff/{SUITES['ff']}", "filter": r["path"], "preset": int(preset),
                         "size": [size, size], "channels": ["final"], "seamless": bool(r.get("seamless_presets")),
                         "tileable": True, "slot_name": "texture", "priority": 1,
                         "meta": {"suite": SUITES["ff"], "category": "materials", "prompt_id": m["id"],
                                  "checkpoint": f"filter_forge:{stem}", "lora": None, "seed": 0}})
    return jobs, missing


def weathering_jobs(game: str, picks: dict, materials: list[dict], listing: dict | None = None,
                    denoise: tuple = (0.35, 0.5), chosen: dict | None = None) -> tuple[list[dict], list[str]]:
    """The War and the After from each picked Peace tile: img2img repaints (each denoise) against Filter Forge effect
    filters whose names say weathering. picks: {material id: {"image": path to the picked, processed tile}}."""
    by_id = {m["id"]: m for m in materials}
    all_fx = [r for rs in (listing or {}).values() for r in rs if r.get("kind") == "effect"]
    by_key = {}
    for r in all_fx:
        for k in (Path(str(r.get("file") or "")).stem.lower(), str(r.get("name") or "").lower()):
            by_key.setdefault(k, r)
    effects = [r for r in all_fx if any(re.search(r"\b" + w + r"\b", _words(str(r.get("name") or ""))) for w in WEATHER_FF)]
    per_era = {era: [by_key[str(k).lower()] for k in (chosen or {}).get(era, []) if str(k).lower() in by_key]
               for era in ERA_WORDS}                     # a pick by real name (the War burns, the After weathers) wins
    jobs, notes = [], []
    for mid, pk in sorted(picks.items()):
        m = by_id.get(mid)
        if not m or not pk.get("image"):
            continue
        for era in [e for e in (m.get("eras") or ["peace", "war", "after"]) if e in ERA_WORDS]:
            words = (m.get("weather") or {}).get(era) or ERA_WORDS[era]
            for dn in denoise:
                jobs.append({"type": "repaint", "game": game, "name": f"weather_{mid}_{era}_{int(dn * 100)}",
                             "batch": f"bakeoff/{SUITES['weather']}", "init": pk["image"], "denoise": [dn],
                             "prompt": PREFIX.format(words=f"{m['words']}, {words}"), "refine": False,
                             "meta": {"suite": SUITES["weather"], "category": era, "prompt_id": mid,
                                      "checkpoint": f"img2img_{int(dn * 100)}", "lora": None, "seed": 0}})
            for r in (per_era.get(era) or effects[:2]):
                stem = Path(str(r.get("file"))).stem
                jobs.append({"type": "filter_forge", "game": game, "name": f"weather_{mid}_{era}_{_slug(stem)}",
                             "batch": f"bakeoff/{SUITES['weather']}", "filter": r["path"], "preset": 0,
                             "input": pk["image"], "channels": ["final"], "tileable": True, "slot_name": "texture",
                             "meta": {"suite": SUITES["weather"], "category": era, "prompt_id": mid,
                                      "checkpoint": f"filter_forge:{stem}", "lora": None, "seed": 0}})
    if not effects and not any(per_era.values()):
        notes.append("no Filter Forge effect filter's name says weathering (rust, grime, dirt, burn, crack…) — only the "
                     "img2img side is planned; name one with --ff-filter to add it")
    return jobs, notes


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "x"


def write_suites(game_dir: Path, suites_: list[dict]) -> list[Path]:
    out = []
    d = Path(game_dir) / "bakeoff"
    d.mkdir(parents=True, exist_ok=True)
    for s in suites_:
        p = d / f"{s['suite']}.json"
        p.write_text(json.dumps(s, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        out.append(p)
    return out
