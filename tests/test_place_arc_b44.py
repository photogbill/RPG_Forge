"""BUILD 44 part 8 — a round hall as a place plan, the forge's half: an `arc` solid (a curved band) and a row of `seats`
pass the plan's check, a bad arc is named; a placed thing's `z` (hung, or on a tier) reaches the placed-things list; a
thing whose model is already on another world list (`listed_in`) is not put on this place's list; the compiler's new
shapes are behind names a plan must use (an older plan never meets them); and, where a real Blender's Python is on
this machine, an arc, a seat row and a cone compile into the stage model. Game-neutral."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from forge.threed import place

REPO = Path(__file__).resolve().parents[1]
BUILD_STAGE = REPO / "forge" / "threed" / "blender" / "build_stage.py"


def hall() -> dict:
    return {"id": "round_hall", "name": "A round hall", "size": [40, 60], "base_z": -2.5,
            "ground": [{"mat": "plank", "rect": [2, 2, 36, 20]}],
            "solids": [
                {"id": "tier1_slab", "mat": "plaster", "arc": [20, 40, 13.5, 16.5, 0, 180], "z": 3.0, "h": 0.35},
                {"id": "ring", "mat": "ceiling", "arc": [20, 40, 8, 15, 0, 360], "z": 22.0, "h": 0.3},
                {"id": "row_1", "mat": "velvet", "arc": [20, 15, 15.5, 16.0, 70, 110], "z": -1.0, "h": 0.9,
                 "seats": {"pitch": 0.55, "people": 0.9, "seed": 3, "empty": [[20.0, 30.75]]}},
                {"id": "side_row", "mat": "velvet", "rect": [5, 30, 0.4, 8], "z": 3.0, "h": 0.9, "facing": "e",
                 "seats": {"pitch": 0.72, "people": 1.0, "seed": 4}},
                {"id": "pine_tier", "mat": "leaves", "cyl": [10, 10, 2.0], "z": 1.0, "h": 4.0, "top_r": 0.0},
                {"id": "wall_n", "mat": "plaster", "rect": [0, 0, 40, 0.3], "h": 6.0}],
            "floors": [{"rect": [10, 30, 20, 5], "z": -1.0}, {"arc": [20, 40, 13.5, 16.5, 0, 180], "z": 3.0}],
            "things": [
                {"id": "chandelier", "kind": "prop", "model": "hall_chandelier", "listed_in": "hall_list", "at": [20, 40], "z": 16.5,
                 "size_m": {"width": 6.0}},
                {"id": "lectern", "kind": "prop", "at": [20, 10], "words": "a plain oak lectern", "size_m": {"height": 1.2}}],
            "anchors": {"start": [20, 12]}}


def test_arcs_and_seats_pass_the_check():
    assert place.check(hall()) == []


def test_a_bad_arc_is_named():
    p = hall()
    p["solids"].append({"id": "backwards", "mat": "plaster", "arc": [0, 0, 5, 3, 0, 90], "h": 1})
    p["solids"].append({"id": "short", "mat": "plaster", "arc": [0, 0, 3], "h": 1})
    probs = place.check(p)
    assert any("backwards" in x and "arc" in x for x in probs)
    assert any("short" in x for x in probs)


def test_a_thing_keeps_its_height():
    rows = {r["id"]: r for r in place.things_list(hall())["things"]}
    assert rows["chandelier"]["z"] == 16.5
    assert "z" not in rows["lectern"]                      # no z: the game stands it on the floor under it, as before


def test_a_model_on_another_list_is_not_listed_again():
    ids = [e["id"] for e in place.wanted_entries(hall())]
    assert "hall_chandelier" not in ids
    assert "round_hall_lectern" in ids


def test_the_new_shapes_are_named_only_where_a_plan_names_them():
    src = BUILD_STAGE.read_text(encoding="utf-8")
    assert 'if s.get("seats") and ("arc" in s or "rect" in s)' in src
    assert 'if "arc" in s:' in src
    assert 'r_top=(float(s["top_r"]) if s.get("top_r") is not None else None)' in src


def _blender_python():
    for p in (os.environ.get("FORGE_BPY"), "/home/claude/bpyenv/bin/python"):
        if p and Path(p).exists():
            try:
                subprocess.run([p, "-c", "import bpy"], check=True, capture_output=True, timeout=120)
                return p
            except Exception:
                continue
    return None


@pytest.mark.skipif(_blender_python() is None, reason="no Blender Python (bpy) on this machine")
def test_a_round_hall_compiles(tmp_path):
    py = _blender_python()
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps(hall()), encoding="utf-8")
    out = tmp_path / "hall.glb"
    r = subprocess.run([py, str(BUILD_STAGE), "--plan", str(plan), "--out", str(out)], capture_output=True, text=True, timeout=600)
    # (bpy as a Python module can crash as the interpreter closes, after the export: the STAGE line and the file are the proof)
    line = next((ln for ln in r.stdout.splitlines() if ln.startswith("STAGE ")), None)
    assert line is not None, r.stderr[-2000:]
    rep = json.loads(line[6:])
    assert out.exists() and rep["faces"] > 2000 and rep["solids"] == 6
