"""G14: the Filter Forge driver — task XML for the three uses (seamless texture, extra channels, photo effect) built
from the renderer's documented vocabulary, the refusals, a fake renderer's outputs collected (its own -normal suffix
included), the normal map's convention measured and fixed, the seam score, the version read from the exe."""
import json
import xml.etree.ElementTree as ET

import numpy as np
import pytest
from PIL import Image

from forge.night3b import ffdriver as ff
from forge.ops import lighting
from test_scene import ctx_with

FFXML = """<?xml version="1.0" encoding="utf-8"?>
<Filter>
 <Components>
  <Result id="result"><Source source="x"/><FilterType value="{ft}"/></Result>
  {image}
  <PerlinNoise2 id="p1"/>
 </Components>
 <Presets>
  <Preset><Settings size_factor="1" variation="5" seamless="true" antialiasing="2" map_type="0" edges_only="true" clip_hdr_for_result="true"/></Preset>
  <Preset><Settings size_factor="1.5" variation="9" seamless="false" antialiasing="2" map_type="0" edges_only="true" clip_hdr_for_result="true"/></Preset>
 </Presets>
 <Information author="test" name-en="{name}" major_version="1" minor_version="0"/>
</Filter>
"""


def fixture_filter(tmp_path, name="Library_999-2", effect=False, ft=1):
    p = tmp_path / f"{name}.ffxml"
    p.write_text(FFXML.format(ft=ft, image='<Image2 id="img"/>' if effect else "", name="Test " + ("Effect" if effect else "Stone")),
                 encoding="utf-8")
    return p


def parse(xml):
    return ET.fromstring(xml.split("\n", 1)[1])


def test_read_filter_and_ids(tmp_path):
    info = ff.read_filter(fixture_filter(tmp_path))
    assert info["name"] == "Test Stone" and info["kind"] == "texture" and info["filter_type"] == "legacy surface"
    assert info["library_id"] == "999-2" and [p["seamless"] for p in info["presets"]] == [True, False]
    assert ff.read_filter(fixture_filter(tmp_path, "Mine", effect=True, ft=0))["kind"] == "effect"
    assert ff.read_filter(fixture_filter(tmp_path, "Mine2"))["library_id"] is None


def test_task_xml_seamless_texture(tmp_path):
    f = fixture_filter(tmp_path)
    out = tmp_path / "out"
    xml, rows, info, notes = ff.task_xml({"filter": str(f), "preset": 0, "size": [1024, 1024], "seamless": True,
                                          "channels": ["final"], "slot_name": "ground"}, out)
    t = parse(xml)
    assert t.tag == "Tasks" and len(t.findall("Task")) == 1
    task = t.find("Task")
    assert [c.tag for c in task] == ["Image", "Selection", "Result", "Filter", "Preset"]
    img = task.find("Image").attrib
    assert img == {"value": "", "width": "1024", "height": "1024"}
    res = task.find("Result")
    assert res.get("format") == "PNG" and res.get("path").endswith("ground_final.png")
    assert res.find("Options/BitDepth").get("value") == "16"
    assert task.find("Filter").get("value") == str(f) and task.find("Preset").get("value") == "0"
    ro = t.find("GlobalSettings/RenderingOptions")
    assert ro.find("NormalMapFlipY").get("value") == "true"                 # OpenGL, per the help
    assert ro.find("TemporaryFilesLocation").get("value").startswith(str(out.resolve()))
    assert t.find("GlobalSettings/BitmapFormatOptions/PNG/BitDepth").get("value") == "16"
    # the renderer insists on every format section, as in its BatchSample.xml
    assert [c.tag for c in t.find("GlobalSettings/BitmapFormatOptions")] == ["DefaultFormat", "BMP", "JPG", "TIF", "TGA", "PNG", "EXR", "PFM"]
    assert [c.tag for c in ro] == ["UseMultithreading", "Dither", "Progressive", "OptimizeBlurs", "AntiAliasBitmapComponentSources",
                                   "Jitter", "TemporaryFilesLocation", "RAMUsageLimit", "NormalMapFlipY"]
    assert rows == [{"channel": "final", "preset": 0, "result": str(out.resolve() / "ground_final.png")}] and not notes


def test_task_xml_channels_and_photo_effect(tmp_path):
    f = fixture_filter(tmp_path)
    out = tmp_path / "out"
    xml, rows, info, notes = ff.task_xml({"filter": str(f), "channels": {"final": 0, "normal": 2, "height": 3}}, out)
    t = parse(xml)
    assert [x.find("Preset").get("value") for x in t.findall("Task")] == ["0", "2", "3"]
    assert [r["channel"] for r in rows] == ["final", "normal", "height"]
    assert len(notes) == 2 and all("your own presets" in n for n in notes)
    # the photo effect: a picture in, no width/height (the output is the picture's size)
    e = fixture_filter(tmp_path, "Library_5075-4", effect=True, ft=0)
    pic = tmp_path / "frame.png"
    Image.new("RGB", (300, 200), (90, 80, 70)).save(pic)
    xml, rows, _i, _n = ff.task_xml({"filter": str(e), "preset": 1, "input": str(pic)}, out)
    img = parse(xml).find("Task/Image").attrib
    assert img == {"value": str(pic)}
    with pytest.raises(ValueError, match="effect filter"):
        ff.task_xml({"filter": str(e), "preset": 0}, out)


def test_refusals(tmp_path):
    f = fixture_filter(tmp_path)
    out = tmp_path / "out"
    with pytest.raises(ValueError, match="its own preset"):
        ff.task_xml({"filter": str(f), "channels": ["final", "normal"]}, out)
    with pytest.raises(ValueError, match="factory preset"):
        ff.task_xml({"filter": str(f), "channels": {"final": 0, "normal": 1}}, out)
    with pytest.raises(ValueError, match="Seamless Tiling off"):
        ff.task_xml({"filter": str(f), "preset": 1, "seamless": True}, out)
    with pytest.raises(ValueError, match="unknown channel"):
        ff.task_xml({"filter": str(f), "channels": {"final": 0, "sparkle": 5}}, out)
    with pytest.raises(ValueError, match=".ffxml"):
        ff.task_xml({"filter": str(tmp_path / "x.png")}, out)
    with pytest.raises(FileNotFoundError):
        ff.task_xml({"filter": str(tmp_path / "missing.ffxml")}, out)


def periodic(n=128):
    y, x = np.mgrid[0:n, 0:n] / n
    return (0.5 + 0.25 * np.sin(2 * np.pi * 3 * x) + 0.2 * np.cos(2 * np.pi * 2 * y))[..., None].repeat(3, -1)


def test_seam_score():
    s = ff.seam_score(periodic())
    assert s["x"] < 1.5 and s["y"] < 1.5
    ramp = np.linspace(0, 1, 128)[None, :, None].repeat(128, 0).repeat(3, 2)
    assert ff.seam_score(ramp)["x"] > 50


def height_dome(n=96):
    y, x = np.mgrid[0:n, 0:n]
    return np.clip(1 - ((x - n / 2) ** 2 + (y - n / 3) ** 2) / (n * n / 5), 0, 1)


def test_normal_convention():
    h = height_dome()
    hi = Image.fromarray((h * 255).astype(np.uint8)).convert("RGB")
    gl = np.asarray(lighting.normal_map(hi)).astype(float) / 255
    dx = np.asarray(lighting.normal_map(hi, invert_y=True)).astype(float) / 255
    assert ff.normal_convention(gl, h)["verdict"] == "opengl"
    assert ff.normal_convention(dx, h)["verdict"] == "directx"
    assert ff.normal_convention(np.full_like(gl, 0.5), h)["verdict"] == "unclear"


def test_pe_strings_and_doctor(monkeypatch):
    blob = b"MZ junk " + "ProductName".encode("utf-16-le") + b"\0\0" + "Filter Forge".encode("utf-16-le") + b"\0\0\0\0" + \
           "ProductVersion".encode("utf-16-le") + b"\0\0" + "9.006".encode("utf-16-le") + b"\0\0"
    info = ff.pe_strings(blob)
    assert info == {"ProductName": "Filter Forge", "ProductVersion": "9.006"} and ff.tool_key(info) == "Filter Forge 9.006"
    monkeypatch.setattr(ff, "tool_cfg", lambda cfg=None: {})
    assert "not installed" in ff.doctor_lines({})[0]
    monkeypatch.setattr(ff, "tool_cfg", lambda cfg=None: {"exe": "/nowhere/Bin/FFXCmdRenderer-x64.exe"})
    assert "does not exist" in ff.doctor_lines({})[0]


def fake_renderer(directx=True):
    """Stands in for FFXCmdRenderer: reads the task XML it is given and writes each Result — the normal map under
    Filter Forge's own '-normal' suffix, DirectX-style, so the forge has to notice and flip it."""
    def run(exe, task_file, out, timeout):
        t = ET.parse(task_file).getroot()
        h = height_dome(64)
        for task in t.findall("Task"):
            res = task.find("Result").get("path")
            ch = res.rsplit("_", 1)[1][:-4]
            if ch == "final":
                Image.fromarray((periodic(64) * 255).astype(np.uint8)).save(res)
            elif ch == "height":
                Image.fromarray((h * 65535).astype(np.uint16)).save(res)          # 16-bit grey, like the renderer
            elif ch == "normal":
                hi = Image.fromarray((h * 255).astype(np.uint8)).convert("RGB")
                lighting.normal_map(hi, invert_y=directx).save(res[:-4] + "-normal.png")
        return 0, f"Starting rendering task (1 of {len(t)}).\nTasks completed {len(t.findall('Task'))}. Tasks failed 0.\n"
    return run


def test_render_with_a_fake_renderer(tmp_path):
    f = fixture_filter(tmp_path)
    out = tmp_path / "out" / "FF1"
    out.mkdir(parents=True)
    ctx = ctx_with(None)
    job = {"id": "FF1", "type": "filter_forge", "name": "ff1", "filter": str(f), "seamless": True, "size": [64, 64],
           "channels": {"final": 0, "normal": 4, "height": 5}, "slot_name": "ground"}
    res = ff.render(job, ctx, out, runner=fake_renderer(directx=True))
    assert sorted(res["channels"]) == ["final", "height", "normal"]
    assert res["measured"]["normal_convention"]["verdict"] == "directx" and res["measured"]["normal_flipped_by_forge"] is True
    assert res["measured"]["seam"]["x"] < 1.5
    n = np.asarray(Image.open(out / "ground_n.png")).astype(float) / 255
    assert ff.normal_convention(n, height_dome(64))["verdict"] == "opengl"           # the game's slot is OpenGL
    prov = json.loads((out / "prov.json").read_text())
    assert prov["filter"] == f.name and prov["filter_library_id"] == "999-2" and prov["channels"] == {"final": 0, "normal": 4, "height": 5}
    assert prov["tasks"] == {"completed": 3, "failed": 0}
    assert prov["licences"][-1]["role"] == "outside_tool" and prov["licences"][-1]["file"].startswith("Filter Forge")
    assert (out / "tasks.xml").exists() and (out / "contact.png").exists() and (out / "render.log").exists()
    assert not list(out.glob("*.ffxml"))                                            # paths, never filter files
    # OpenGL already: left alone
    out2 = tmp_path / "out" / "FF2"; out2.mkdir()
    res2 = ff.render({**job, "id": "FF2"}, ctx, out2, runner=fake_renderer(directx=False))
    assert res2["measured"]["normal_convention"]["verdict"] == "opengl" and res2["measured"]["normal_flipped_by_forge"] is False


def test_render_failures_are_plain(tmp_path, monkeypatch):
    f = fixture_filter(tmp_path)
    out = tmp_path / "o"; out.mkdir()
    ctx = ctx_with(None)
    with pytest.raises(ff.FilterForgeError, match="wrote nothing"):
        ff.render({"filter": str(f), "preset": 0}, ctx, out, runner=lambda e, t, o, s: (3, "Filter 'x' could not be found.\n"))
    monkeypatch.setattr(ff, "tool_cfg", lambda cfg=None: {})
    with pytest.raises(ff.FilterForgeError, match="not set up"):
        ff.render({"filter": str(f), "preset": 0}, ctx, out)


def test_list_filters_reads_configured_folders(tmp_path, monkeypatch):
    lib = tmp_path / "lib"
    lib.mkdir()
    fixture_filter(lib)
    fixture_filter(lib, "Library_1-1", effect=True, ft=0)
    monkeypatch.setattr(ff, "tool_cfg", lambda cfg=None: {"library_dirs": [str(lib)]})
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    rows = ff.list_filters({})
    (label, items), = rows.items()
    assert str(lib) in label and [r["file"] for r in items] == ["Library_1-1.ffxml", "Library_999-2.ffxml"]
    assert items[1]["seamless_presets"] == [0] and items[0]["kind"] == "effect"
    assert ff.find_filter({}, "Library_999-2") == lib / "Library_999-2.ffxml"
    before = sorted((p.name, p.stat().st_mtime) for p in lib.iterdir())
    ff.read_filter(lib / "Library_999-2.ffxml")
    assert sorted((p.name, p.stat().st_mtime) for p in lib.iterdir()) == before       # read-only
