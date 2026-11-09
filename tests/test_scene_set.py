"""N4: the manifest knows the six scene slots, and approve --set copies them all or nothing with one licence check."""
import json

import pytest
from PIL import Image

from forge import manifest
from test_manifest import make_world

SFX = ("", "_n", "_e", "_back", "_over", "_depth")


def fake_kit_job(tmp_path, jid, checkpoint="sd_xl_base_1.0.safetensors", size=(480, 270), back_extra=96, drop=(), bad_size=None):
    out = tmp_path / "out" / jid
    out.mkdir(parents=True)
    slots = {}
    for sfx in SFX:
        if sfx in drop:
            continue
        w, h = size
        if sfx == "_back":
            w += back_extra
        if sfx == bad_size:
            w, h = w // 2, h // 2
        mode = "RGBA" if sfx == "_over" else ("I;16" if sfx == "_depth" else "RGB")
        im = Image.new(mode, (w, h)) if mode != "I;16" else Image.new("I;16", (w, h))
        im.save(out / f"scene{sfx}.png")
        slots[sfx or "_main"] = f"scene{sfx}.png"
    licences = [{"role": "checkpoint", "file": checkpoint}, {"role": "upscaler", "file": "RealESRGAN_x4plus.pth"},
                {"role": "depth_model", "file": "depth_anything_v2_vits.pth"}]
    (out / "prov.json").write_text(json.dumps({"job_id": jid, "type": "scene_kit", "set": True, "slots": slots,
                                               "licences": licences}), encoding="utf-8")
    step = out / "01_scene_paint"
    step.mkdir()
    (step / "prov.json").write_text(json.dumps({"checkpoint": checkpoint, "licences": licences[:2]}), encoding="utf-8")
    job = {"id": jid, "type": "scene_kit", "name": "bills_house", "batch": "cards", "game": "tg",
           "result": {"outputs": list(slots.values()), "slots": slots}}
    (tmp_path / "jobs" / "done" / f"{jid}.json").write_text(json.dumps(job), encoding="utf-8")
    return out


def test_wanted_lists_slots_optional_and_back_wider(tmp_path):
    cfg, root, assets = make_world(tmp_path)
    items = manifest.refresh_wanted(cfg, "tg")["items"]
    main = items["scenes/bills_house"]
    assert main["slots"] == [f"scenes/bills_house{s}" for s in SFX[1:]]
    n = items["scenes/bills_house_n"]
    assert n["optional"] and n["path"] == "project/assets/scenes/bills_house_n.png" and n["target_size"] == main["target_size"]
    assert items["scenes/bills_house_back"]["target_size"] == [main["target_size"][0] + 96, main["target_size"][1]]


def test_set_dry_run_lists_six_destinations_and_one_chain(tmp_path):
    cfg, root, assets = make_world(tmp_path)
    manifest.refresh_wanted(cfg, "tg")
    fake_kit_job(tmp_path, "K1")
    plan = manifest.approve_set(cfg, "K1", "scenes/bills_house", dry_run=True)
    assert len(plan["rows"]) == 6 and plan["dry_run"]
    assert [r["wanted"] for r in plan["rows"]] == [f"scenes/bills_house{s}" for s in SFX]
    files = [c["file"] for c in plan["licences"]]
    assert len(files) == len(set(files)) and "depth_anything_v2_vits.pth" in files       # once, depth model included
    assert not (assets / "scenes").exists()                                              # nothing copied


def test_set_copies_all_with_provenance_each(tmp_path):
    cfg, root, assets = make_world(tmp_path)
    manifest.refresh_wanted(cfg, "tg")
    fake_kit_job(tmp_path, "K2")
    manifest.approve_set(cfg, "K2", "scenes/bills_house")
    for s in SFX:
        assert (assets / "scenes" / f"bills_house{s}.png").exists()
        p = json.loads((assets / "_provenance" / f"scenes__bills_house{s}.json").read_text(encoding="utf-8"))
        assert p["set"] == "scenes/bills_house" and p["job_id"] == "K2"
    states = {x["name"]: x["state"] for x in manifest.status(cfg, "tg")}
    assert all(states[f"scenes/bills_house{s}"] == "approved" for s in SFX)


def test_set_is_all_or_nothing(tmp_path):
    cfg, root, assets = make_world(tmp_path)
    manifest.refresh_wanted(cfg, "tg")
    fake_kit_job(tmp_path, "K3", checkpoint="SomeCivitaiModel_v3.safetensors")
    with pytest.raises(manifest.ApproveError, match="NOTHING was copied"):
        manifest.approve_set(cfg, "K3", "scenes/bills_house")
    fake_kit_job(tmp_path, "K4", bad_size="_n")
    with pytest.raises(manifest.ApproveError, match="contract wants them equal"):
        manifest.approve_set(cfg, "K4", "scenes/bills_house")
    assert not (assets / "scenes").exists()
    with pytest.raises(manifest.ApproveError, match="slot of"):
        manifest.approve_set(cfg, "K4", "scenes/bills_house_n")


def test_set_with_a_dropped_plane_and_a_non_set_job(tmp_path):
    cfg, root, assets = make_world(tmp_path)
    manifest.refresh_wanted(cfg, "tg")
    fake_kit_job(tmp_path, "K5", drop=("_over",))
    plan = manifest.approve_set(cfg, "K5", "scenes/bills_house", dry_run=True)
    assert len(plan["rows"]) == 5 and plan["missing_slots"] == ["scenes/bills_house_over"]
    from test_manifest import fake_done_job
    fake_done_job(tmp_path, "J9", "sd_xl_base_1.0.safetensors", outputs=("scene.png",))
    with pytest.raises(manifest.ApproveError, match="not a scene set"):
        manifest.approve_set(cfg, "J9", "scenes/bills_house")
