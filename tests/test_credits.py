"""G8: credits — zero approvals is a valid report; a populated _provenance folder lists each model once, counts files,
and shouts about a missing provenance file or an unknown licence."""
import json

from forge import credits
from test_night_report import world


def test_empty_and_populated(tmp_path):
    cfg, jobs, out = world(tmp_path)
    assets = tmp_path / "Game" / "project" / "assets"
    games = tmp_path / "games" / "tg"
    games.mkdir(parents=True)
    (games / "forge.game.json").write_text(json.dumps({"game_root": str(tmp_path / "Game"), "asset_root": str(assets)}))
    cfg["paths"]["games"] = str(tmp_path / "games")
    p, g = credits.write(cfg, "tg")
    assert g["approved"] == 0 and not g["problems"] and "Nothing has been approved" in p.read_text(encoding="utf-8")
    prov = assets / "_provenance"
    prov.mkdir(parents=True)
    ok = [{"role": "checkpoint", "file": "ArtUniverseSDXL_v8.safetensors", "license": "RAIL++-M", "commercial_ok": True},
          {"role": "upscaler", "file": "RealESRGAN_x4plus.pth", "license": "BSD-3-Clause", "commercial_ok": True}]
    (prov / "scenes__a.json").write_text(json.dumps({"licences": ok}))
    (prov / "scenes__b.json").write_text(json.dumps({"licences": ok[:1] + [{"role": "lora1", "file": "x.safetensors",
                                                                          "license": "unknown", "commercial_ok": None}]}))
    (games / "approved.json").write_text(json.dumps({"scenes/a": {}, "scenes/b": {}, "scenes/c": {"licences": ok}}))
    p, g = credits.write(cfg, "tg")
    by = {m["file"]: m for m in g["models"]}
    assert by["ArtUniverseSDXL_v8.safetensors"]["files"] == 3 and by["RealESRGAN_x4plus.pth"]["files"] == 2   # c counts from approved.json
    assert any("scenes/c" in x and "NO provenance" in x for x in g["problems"])
    assert any("x.safetensors" in x for x in g["problems"])
    assert "PROBLEMS" in p.read_text(encoding="utf-8")
