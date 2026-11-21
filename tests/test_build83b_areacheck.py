"""BUILD 83 Part B, first slice: an area's things delivered, its people described (2026-11-19)."""
from __future__ import annotations

import json

from forge.threed import areacheck


def _status(*rows):
    return {"items": [{"id": i, "kind": "prop", "file": "games/g1/wanted_3d/court.json", "shown": s, "state": s, "why": w}
                      for i, s, w in rows]}


def _cfg(tmp_path):
    return {"_root": str(tmp_path), "paths": {"out": str(tmp_path / "out"), "games": str(tmp_path / "games")},
            "allow_external_paths": True}


def test_all_delivered_and_people_described_pass(tmp_path):
    gr = tmp_path / "game"
    (gr / "data" / "people").mkdir(parents=True)
    (gr / "data" / "people" / "court.json").write_text(json.dumps([{"prompt": "a"}, {"prompt": "b"}]), encoding="utf-8")
    r = areacheck.check(_cfg(tmp_path), "g1", "court", status=_status(("chair", "delivered", []), ("bed", "delivered", [])),
                        game_root=gr)
    assert r["passed"] == 2 and r["flagged"] == 0
    assert (tmp_path / "out" / "areas" / "g1" / "court" / "report.md").read_text(encoding="utf-8").count("✔") == 2


def test_stand_ins_left_and_nobody_described_are_flagged_by_name(tmp_path):
    r = areacheck.check(_cfg(tmp_path), "g1", "court",
                        status=_status(("chair", "delivered", []), ("bed", "held", ["Sits level: leans 6°"]),
                                       ("other", "made", [])), game_root=tmp_path / "game")
    d = next(c for c in r["checks"] if c["id"] == "delivered")
    assert d["ok"] is False and [f["id"] for f in d["flags"]] == ["bed", "other"] and "greybox" in d["line"]   # made is not delivered
    p = next(c for c in r["checks"] if c["id"] == "people")
    assert p["ok"] is False and "data/people/court.json" in p["line"]
    assert "1 scale" in r["not_built_yet"]


def test_a_place_with_nothing_on_the_list_is_not_a_pass(tmp_path):
    r = areacheck.check(_cfg(tmp_path), "g1", "court", status={"items": []}, game_root=None, write=False)
    assert all(c["ok"] is None for c in r["checks"]) and r["passed"] == 0
