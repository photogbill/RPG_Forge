"""G13: the hand-off folder for an outside tool — tool register, out → stand-in tool → in round trip (missing,
extra and wrong-size files named), the two filing job types, approve's pre-flight and the tool's condition."""
import json

import numpy as np
import pytest
from PIL import Image

from forge import config as cfgmod, handoff as ho, manifest
from forge.night3b import handoff_jobs as hj, specs as sp
from test_night_report import world
from test_paint import FAKE_INFO
from test_scene import SceneComfy, DEPTH_INFO, ctx_with


class FakeQueue:
    def __init__(self):
        self.batches = []

    def submit_batch(self, b):
        self.batches.append(b)
        return [f"Q{i}" for i in range(len(b["jobs"]))]


def picture(w, h, seed=1):
    rng = np.random.default_rng(seed)
    a = rng.integers(0, 255, (h, w, 3), dtype=np.uint8)
    return Image.fromarray(a)


def done_job(jobs, out, jid, kind="paint", **kw):
    od = out / jid
    od.mkdir(parents=True)
    lic = [{"role": "checkpoint", "file": "sd_xl_base_1.0.safetensors", "license": "CreativeML Open RAIL++-M", "commercial_ok": True}]
    if kind == "kit":
        (od / "01_scene_paint").mkdir()
        picture(64, 36).save(od / "01_scene_paint" / "raw.png")
        picture(128, 72, 2).save(od / "scene.png")
        (od / "prov.json").write_text(json.dumps({"set": True, "slot_name": "scene", "slots": {"_main": "scene.png"},
                                                  "licences": lic}))
        (od / "layers.json").write_text(json.dumps({"cuts": [0.3, 0.7]}))
        (od / "job.json").write_text(json.dumps({"type": "scene_kit", "normals": {"strength": 1.5}}))
        job = {"id": jid, "type": "scene_kit", "batch": "maps/b1", "name": jid}
    else:
        picture(64, 36, 3).save(od / "raw.png")
        picture(128, 72, 4).save(od / "painting.png")
        (od / "prov.json").write_text(json.dumps({"checkpoint": "sd_xl_base_1.0.safetensors", "licences": lic}))
        job = {"id": jid, "type": "scene_paint", "batch": "maps/b1", "name": jid, "result": {"outputs": ["painting.png"]}}
    job.update(kw)
    (jobs / "done" / f"{jid}.json").write_text(json.dumps(job))


def test_tool_register(tmp_path):
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "licences.json").write_text(json.dumps({"some.safetensors": {"license": "x", "commercial_ok": True}}))
    k = ho.add_tool("Upscaler Pro", "6.2.2", True, "annual revenue under US$1M", "vendor page 2026-11-09", root=tmp_path)
    assert k == "Upscaler Pro 6.2.2"
    tools = ho.load_tools(tmp_path)
    assert list(tools) == [k] and tools[k]["licence_condition"] == "annual revenue under US$1M" and tools[k]["commercial_ok"] is True
    data = json.loads((tmp_path / "models" / "licences.json").read_text())
    assert "some.safetensors" in data                      # the model licences beside it are kept
    with pytest.raises(ho.HandoffError):
        ho.tool_key("a/b", "1")
    with pytest.raises(ho.HandoffError, match="model licence"):
        ho.add_tool("some.safetensors", "", True, root=tmp_path)
    # approve prints the tool's condition like any other
    conds = manifest.licence_conditions({}, [{"file": k}], root=tmp_path)
    assert conds == [f"{k} (outside tool): annual revenue under US$1M"]


def test_round_trip_with_a_stand_in_tool(tmp_path):
    cfg, jobs, out = world(tmp_path)
    done_job(jobs, out, "J1")
    done_job(jobs, out, "J2", kind="kit")
    done_job(jobs, out, "J3")
    done_job(jobs, out, "J4")
    done_job(jobs, out, "OTHER", batch="elsewhere")
    man = ho.hand_out(cfg, ["maps/b1"], to=str(out / "handoff" / "t1" / "in"))
    base = out / "handoff" / "t1"
    assert man["name"] == "t1" and [e["job"] for e in man["entries"]] == ["J1", "J2", "J3", "J4"]
    assert {p.name for p in (base / "in").iterdir()} == {"J1__raw.png", "J2__raw.png", "J3__raw.png", "J4__raw.png"}
    assert all(e["target_size"] == [128, 72] for e in man["entries"]) and man["entries"][1]["kit"] is True
    readme = (base / "README.txt").read_text(encoding="utf-8")
    assert "make it 128x72" in readme and str(base / "done") in readme
    # the stand-in "tool": a plain resize, with its own tag added to the names (and one JPG, one half size)
    for f in (base / "in").iterdir():
        im = Image.open(f)
        jid = f.name.split("__")[0]
        if jid == "J1":
            im.resize((128, 72), Image.LANCZOS).save(base / "done" / (f.stem + "-tool-std-2x.png"))
        elif jid == "J2":
            im.resize((128, 72), Image.LANCZOS).save(base / "done" / (f.stem + "-tool.jpg"), quality=95)
        elif jid == "J3":
            im.resize((100, 100)).save(base / "done" / (f.stem + "-tool.png"))     # wrong shape
        # J4 never comes back
    picture(10, 10).save(base / "done" / "stray_picture.png")
    q = FakeQueue()
    rep = ho.hand_in(cfg, "t1", tool="Upscaler Pro 6.2.2", queue=q, root=tmp_path)
    assert [f["job"] for f in rep["filed"]] == ["J1", "J2"]
    assert rep["missing"] == ["J4__raw.png"]
    assert len(rep["wrong_size"]) == 1 and rep["wrong_size"][0].startswith("J3__raw-tool.png")
    assert rep["extra"] == ["stray_picture.png"]
    assert rep["warnings"] and "no licence on file" in rep["warnings"][0]       # tmp register is empty
    b = q.batches[0]
    assert b["batch"] == "handoff/t1" and [j["type"] for j in b["jobs"]] == ["handoff_file", "handoff_kit"]
    assert all(j["priority"] == 10 and j["tool"] == "Upscaler Pro 6.2.2" for j in b["jobs"])
    for j in b["jobs"]:
        spec = {"handoff_file": sp.HANDOFF_FILE, "handoff_kit": sp.HANDOFF_KIT}[j["type"]]
        assert all(j.get(k) for k in spec["required"])
        assert Image.open(cfgmod.ROOT / j["input"] if not j["input"].startswith("/") else j["input"]).size == (128, 72)
    # a second `in` with the same tool on file in the handoff remembers it
    rep2 = ho.hand_in(cfg, "t1", queue=FakeQueue(), root=tmp_path, submit=False)
    assert rep2["tool"] == "Upscaler Pro 6.2.2" and rep2["jobs"] == []


def test_same_shape_is_resized_and_named(tmp_path):
    cfg, jobs, out = world(tmp_path)
    done_job(jobs, out, "J1")
    ho.hand_out(cfg, ["J1"], name="t2")
    base = out / "handoff" / "t2"
    Image.open(base / "in" / "J1__raw.png").resize((256, 144)).save(base / "done" / "J1__raw_x4.png")
    rep = ho.hand_in(cfg, "t2", tool="T 1", queue=FakeQueue(), root=tmp_path)
    assert rep["filed"] and any("resized to 128x72" in n for n in rep["notes"])
    assert Image.open(base / "filed" / "J1.png").size == (128, 72)


def test_handoff_file_and_kit_jobs(tmp_path):
    cfg, jobs, out = world(tmp_path)
    done_job(jobs, out, "J1")
    done_job(jobs, out, "J2", kind="kit")
    ctx = ctx_with(SceneComfy(info={**FAKE_INFO, **DEPTH_INFO}))
    ret = tmp_path / "ret.png"
    picture(128, 72, 9).save(ret)
    o1 = out / "H1"; o1.mkdir()
    job = {"id": "H1", "type": "handoff_file", "input": str(ret), "source_job": "J1",
           "tool": "Nobody Tool 0.1", "target": [128, 72], "name": "h1"}
    res = hj.handoff_file(job, ctx, o1)
    assert res["outputs"] == ["painting.png", "contact.png"] and (o1 / "contact.png").exists()
    prov = json.loads((o1 / "prov.json").read_text())
    tool = [l for l in prov["licences"] if l["role"] == "outside_tool"][0]
    assert tool["file"] == "Nobody Tool 0.1" and tool["commercial_ok"] is None and "not on file" in tool["license"]
    assert prov["commercial_ok"] is False and prov["inputs"][0].endswith("raw.png")
    parts, _read = manifest.collect_models(cfg, o1)
    assert "Nobody Tool 0.1" in parts.values() and "sd_xl_base_1.0.safetensors" in parts.values()
    assert ho.tools_in_job(cfg, "H1") == ["Nobody Tool 0.1"]
    # the wrong size is refused with a plain message
    with pytest.raises(ValueError, match="handoff in"):
        hj.handoff_file({**job, "target": [64, 64]}, ctx, o1)
    # a kit: six files, a set provenance with the depth model and the tool
    o2 = out / "H2"; o2.mkdir()
    kjob = {"id": "H2", "type": "handoff_kit", "input": str(ret), "source_job": "J2",
            "tool": "Nobody Tool 0.1", "name": "h2"}
    res = hj.handoff_kit(kjob, ctx, o2)
    for f in ("scene.png", "scene_n.png", "scene_e.png", "scene_back.png", "scene_over.png", "scene_depth.png", "contact.png"):
        assert (o2 / f).exists(), f
    kprov = json.loads((o2 / "prov.json").read_text())
    assert kprov["set"] is True and kprov["slots"]["_main"] == "scene.png" and not kprov["missing_slots"]
    roles = [l["role"] for l in kprov["licences"]]
    assert "depth_model" in roles and "outside_tool" in roles and "checkpoint" in roles
    assert np.array_equal(np.asarray(Image.open(o2 / "scene.png")), np.asarray(Image.open(ret).convert("RGB")))


def test_approve_preflight_asks_for_a_missing_tool(tmp_path, monkeypatch):
    cfg, jobs, out = world(tmp_path)
    (tmp_path / "models").mkdir()
    od = out / "H9"; od.mkdir(parents=True)
    (od / "prov.json").write_text(json.dumps({"licences": [{"role": "outside_tool", "file": "Upscaler Pro 6.2.2"}]}))
    said = []
    answers = iter(["yes", "yes", "annual revenue under US$1M", "vendor page"])
    ho.approve_preflight(cfg, "H9", ask=lambda q: next(answers), out=said.append, interactive=True, root=tmp_path)
    assert any("not on file" in s for s in said)
    rec = ho.load_tools(tmp_path)["Upscaler Pro 6.2.2"]
    assert rec["commercial_ok"] is True and rec["licence_condition"] == "annual revenue under US$1M"
    said.clear()
    ho.approve_preflight(cfg, "H9", out=said.append, interactive=False, root=tmp_path)
    assert said and "condition: annual revenue under US$1M" in said[0]
    said.clear()
    od2 = out / "H8"; od2.mkdir()
    (od2 / "prov.json").write_text(json.dumps({"licences": [{"role": "outside_tool", "file": "Other 2"}]}))
    ho.approve_preflight(cfg, "H8", out=said.append, interactive=False, root=tmp_path)
    assert any("handoff_tool_add.bat" in s for s in said)
