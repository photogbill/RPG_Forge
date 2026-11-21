"""Fable 2026-11-20 — delivering approved 3D models from the connector (models.deliver), in batches, signed for William.

William 15:45-15:51: "deliver them using the same connector" ... "yes please. Lets do that."
Tested with no game and no graphics card: the forge's own deliver() on a made-up approved.json, its copies in tmp_path.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from forge.suite import threed


@pytest.fixture
def world(tmp_path, monkeypatch):
    """Three approved models (two props, one body), a game folder, and the forge's ledger, journal and setting stood in."""
    forge_root = tmp_path / "forge"
    game_root = tmp_path / "game"
    tdir = forge_root / "games" / "g" / "threed"
    tdir.mkdir(parents=True)
    game_root.mkdir()
    appr = {}
    for kind, name in (("prop", "chair"), ("prop", "lamp"), ("body", "soprano")):
        src = forge_root / "out" / name / f"{name}.glb"
        src.parent.mkdir(parents=True)
        src.write_bytes(b"glTF" + name.encode() * 50)
        appr[f"{kind}/{name}"] = {"try": f"world-{name}-1", "files": [f"out/{name}/{name}.glb"],
                                  "dest": f"project/assets/models/{'bodies' if kind == 'body' else kind + 's'}/{name}.glb", "licences": ["MIT"],
                                  "by": "Claude Fable, for William", "at": "2026-11-20T15:00:00", "delivered": None}
    (tdir / "approved.json").write_text(json.dumps(appr), encoding="utf-8")

    from forge import config as cfgmod
    from forge.suite import games
    from forge.night4 import deliver as dl
    monkeypatch.setattr(cfgmod, "ROOT", forge_root)
    monkeypatch.setattr(threed, "tdir", lambda cfg, gid: tdir)
    monkeypatch.setattr(games, "game_root", lambda cfg, gid: game_root)
    monkeypatch.setattr(cfgmod, "path_of", lambda cfg, key: forge_root / key)
    ledger = []
    monkeypatch.setattr(dl, "ledger_add", lambda cfg, gid, row: ledger.append(row))
    signed = []
    monkeypatch.setattr(threed, "_sign", lambda cfg, gid, who, kind, obj, note="", link=None: signed.append((who, kind, obj)))
    monkeypatch.setattr(threed.motions, "refuse_test_dances", lambda files: None)
    allowed = {"on": True}

    def signer(cfg, gid, who, what="approving"):
        from forge.suite import approve_all
        if str(who).startswith("Claude"):
            if not allowed["on"]:
                raise approve_all.ApproveRefused(f"{what} is the person's — an assistant can't do it")
            return f"{who}, for William"
        return str(who)
    from forge.suite import approve_all
    monkeypatch.setattr(approve_all, "signer", signer)
    return {"tdir": tdir, "game": game_root, "ledger": ledger, "signed": signed, "allowed": allowed}


def _appr(w) -> dict:
    return json.loads((w["tdir"] / "approved.json").read_text(encoding="utf-8"))


def test_a_batch_delivers_only_its_limit_and_says_how_many_are_left(world):
    r = threed.deliver({}, "g", "Claude Fable", dry=False, limit=2)
    assert len(r["moved"]) == 2 and r["left_after"] == 1
    assert sum(1 for a in _appr(world).values() if a["delivered"]) == 2
    r2 = threed.deliver({}, "g", "Claude Fable", dry=False, limit=2)
    assert len(r2["moved"]) == 1 and r2["left_after"] == 0
    assert (world["game"] / "project/assets/models/props/chair.glb").exists()
    assert (world["game"] / "project/assets/models/bodies/soprano.glb").exists()


def test_only_takes_a_key_a_bare_id_or_a_try_id(world):
    r = threed.deliver({}, "g", "Claude Fable", dry=True, only=["prop/chair", "lamp", "world-soprano-1"])
    assert len(r["plan"]) == 3
    r = threed.deliver({}, "g", "Claude Fable", dry=False, only=["lamp"])
    assert [m["what"] for m in r["moved"]] == ["prop/lamp"]


def test_it_is_signed_for_william_and_refused_when_the_setting_is_off(world):
    threed.deliver({}, "g", "Claude Fable", dry=False, only=["chair"])
    assert world["signed"] and world["signed"][0][0] == "Claude Fable, for William"
    world["allowed"]["on"] = False
    with pytest.raises(threed.ThreeDRefused):
        threed.deliver({}, "g", "Claude Fable", dry=False, only=["lamp"])
    assert threed.deliver({}, "g", "William", dry=False, only=["lamp"])["moved"]   # the person may always


def test_an_approval_made_while_it_copies_is_not_lost(world, monkeypatch):
    real = threed.shutil.copyfile
    done = {"once": False}

    def copy_and_approve(src, dst, *a, **k):
        out = real(src, dst, *a, **k)
        if not done["once"]:
            done["once"] = True
            appr = _appr(world)
            appr["prop/new_thing"] = {"try": "world-new-1", "files": [], "dest": "x", "delivered": None}
            (world["tdir"] / "approved.json").write_text(json.dumps(appr), encoding="utf-8")
        return out
    monkeypatch.setattr(threed.shutil, "copyfile", copy_and_approve)
    threed.deliver({}, "g", "Claude Fable", dry=False, only=["chair"])
    a = _appr(world)
    assert "prop/new_thing" in a and a["prop/chair"]["delivered"]


def test_the_connector_offers_models_deliver_as_a_signed_change():
    from forge.mcpserver import ops
    o = ops.OPS["models.deliver"]
    assert o.kind == "change" and o.needs_who and o.dry is not None
    assert ops._deliver_input({}) == (None, ops.DELIVER_BATCH)
    assert ops._deliver_input({"ids": "chair", "limit": 999}) == (["chair"], 200)
