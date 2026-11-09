"""Unit tests for the CPU side. Run: python -m pytest -q"""
import json, sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from forge.ops import palette as pal, pixelize as pix, alpha as al, sheet as sh, tiles as tl, godot  # noqa: E402
from forge import schema, config as cfgmod  # noqa: E402
from forge.queue import Queue, run_worker  # noqa: E402
from forge.engines import comfy  # noqa: E402


# ------------------------------------------------------------------ palette
def test_palette_loads_and_dedupes(tmp_path):
    p = tmp_path / "p.hex"
    p.write_text("#ff0000\n00ff00\n#ff0000\n0000ff\n")
    rgb = pal.load_palette(p)
    assert rgb.shape == (3, 3)
    assert rgb[0].tolist() == [255, 0, 0]


def test_shipped_palettes_have_64():
    for name in ("resurrect-64", "endesga-64"):
        rgb = pal.load_palette(ROOT / "palettes" / f"{name}.hex")
        assert rgb.shape == (64, 3), name


def test_oklab_roundtrip_sanity():
    lab = pal.srgb_to_oklab(np.array([[0, 0, 0], [255, 255, 255]], dtype=np.uint8))
    assert lab[0, 0] == pytest.approx(0.0, abs=1e-6)
    assert lab[1, 0] == pytest.approx(1.0, abs=1e-3)


def test_snap_nearest_and_alpha():
    rgb = pal.load_palette(ROOT / "palettes" / "resurrect-64.hex")
    sn = pal.Snapper(rgb)
    im = Image.new("RGBA", (4, 1), (0, 0, 0, 0))
    im.putpixel((0, 0), (255, 255, 255, 255))   # pure white exists in the palette
    im.putpixel((1, 0), (250, 250, 250, 255))   # near white → white
    im.putpixel((2, 0), (46, 34, 47, 255))      # #2e222f exactly
    out, idx = sn.snap(im)
    px = out.load()
    assert px[0, 0] == (255, 255, 255, 255)
    assert px[1, 0] == (255, 255, 255, 255)
    assert px[2, 0] == (46, 34, 47, 255)
    assert px[3, 0][3] == 0, "transparent stays transparent"
    assert pal.report(out, rgb)["off_palette_colors"] == 0


def test_snap_hysteresis_keeps_previous_when_close():
    rgb = np.array([[100, 100, 100], [104, 104, 104]], dtype=np.uint8)
    sn = pal.Snapper(rgb)
    im = Image.new("RGB", (1, 1), (103, 103, 103))  # nearest is index 1
    _, idx = sn.snap(im)
    assert idx[0, 0] == 1
    _, idx2 = sn.snap(im, prev_idx=np.array([0]), hysteresis=0.05)
    assert idx2[0, 0] == 0, "with hysteresis the pixel stays on its previous colour"


# ------------------------------------------------------------------ pixelize
def _pixel_art_upscaled(scale: int, seed: int = 1) -> Image.Image:
    rng = np.random.default_rng(seed)
    small = rng.integers(0, 256, size=(24, 32, 3), dtype=np.uint8)
    im = Image.fromarray(small, "RGB").resize((32 * scale, 24 * scale), Image.NEAREST)
    return im


@pytest.mark.parametrize("scale", [4, 6, 8])
def test_detect_grid_finds_scale(scale):
    im = _pixel_art_upscaled(scale)
    s, ox, oy, conf = pix.detect_grid(im)
    assert s == scale, (s, conf)
    assert (ox, oy) == (0, 0)


def test_downscale_cells_mode_recovers_source():
    rng = np.random.default_rng(3)
    small = rng.integers(0, 256, size=(10, 12, 3), dtype=np.uint8)
    big = Image.fromarray(small, "RGB").resize((12 * 5, 10 * 5), Image.NEAREST)
    back = pix.downscale_cells(big, 5, 0, 0, method="mode")
    assert back.size == (12, 10)
    assert np.array_equal(np.asarray(back)[..., :3], small)


def test_detect_grid_rejects_photo_like_noise():
    rng = np.random.default_rng(5)
    noise = Image.fromarray(rng.integers(0, 256, size=(96, 128, 3), dtype=np.uint8), "RGB")
    s, *_ = pix.detect_grid(noise)
    assert s == 1


# ------------------------------------------------------------------ alpha
def test_remove_flat_background_keeps_interior_holes():
    im = Image.new("RGB", (40, 40), (255, 0, 255))
    dr = ImageDraw.Draw(im)
    dr.rectangle([8, 8, 31, 31], fill=(30, 60, 90))
    dr.rectangle([16, 16, 23, 23], fill=(255, 0, 255))  # a magenta window inside the object
    out = al.remove_flat_background(im, (255, 0, 255), tolerance=20)
    px = out.load()
    assert px[0, 0][3] == 0
    assert px[10, 10][3] == 255
    assert px[18, 18][3] == 255, "interior key-coloured pixels are not reachable by the flood and survive"
    trimmed = al.trim(out)
    assert trimmed.size == (24, 24)
    padded = al.pad_to(trimmed, (48, 72), "bottom")
    assert padded.size == (48, 72)
    assert padded.load()[24, 71][3] == 255


# ------------------------------------------------------------------ sheets
def test_contact_and_pack_sheets():
    frames = [Image.new("RGBA", (20, 30), (200, 50, 50, 255)) for _ in range(9)]
    cs = sh.contact_sheet(frames, [f"f{i}" for i in range(9)], cols=4, cell=(64, 64), title="t")
    assert cs.size[0] == 8 + 4 * (64 + 8)
    sheet, meta = sh.pack_frames(frames, cols=8)
    assert meta["rows"] == 2 and sheet.size == (160, 60)


# ------------------------------------------------------------------ tiles
def test_seamless_lowers_seam_score():
    rng = np.random.default_rng(7)
    base = rng.integers(0, 256, size=(64, 64, 3), dtype=np.uint8).astype(np.float64)
    # smooth it so there is structure, and add a strong left-right gradient so the seam is bad
    grad = np.linspace(0, 120, 64)[None, :, None]
    im = Image.fromarray(np.clip(base * 0.3 + grad, 0, 255).astype(np.uint8), "RGB")
    before = tl.seam_score(im)
    after = tl.seam_score(tl.make_seamless(im))
    assert after < before
    strip = tl.jitter_variants(im.convert("RGBA"), n=3)
    assert strip.size == (64 * 3, 64)


# ------------------------------------------------------------------ godot
def test_tileset_tres_matches_engine_shape():
    text = godot.tileset_tres("res://assets/tiles.png", 32, 3, [False, True, False])
    assert 'texture_region_size = Vector2i(32, 32)' in text
    assert text.count("physics_layer_0/polygon_0") == 1
    assert "1:0/0/physics_layer_0" in text


# ------------------------------------------------------------------ schema + queue
def test_schema_validate():
    assert schema.validate({"type": "scene_card", "prompt": "x"}) == []
    assert schema.validate({"type": "scene_card"}) != []
    assert schema.validate({"type": "nope"})[0].startswith("unknown job type")
    assert schema.validate({"type": "contact_sheet", "inputs": "a.png"}) != []
    job = schema.with_defaults({"type": "scene_card", "prompt": "x"})
    assert job["variants"] == 1 and job["snap"] is True
    assert "scene_card" in schema.render_docs()


def test_queue_lifecycle(tmp_path):
    q = Queue(tmp_path / "jobs", tmp_path / "out")
    jid = q.submit({"type": "contact_sheet", "name": "t", "inputs": ["a.png"]})
    assert q.status()["pending"] == 1
    claimed = q.claim()
    assert claimed is not None and claimed[0] == jid
    assert q.status() == {"pending": 0, "running": 1, "done": 0, "failed": 0}
    q.finish(jid, result={"files": 1})
    assert q.status()["done"] == 1
    receipt = json.loads((tmp_path / "out" / jid / "job.json").read_text())
    assert receipt["result"]["files"] == 1 and "finished_at" in receipt


def test_queue_batch_and_worker_runs_cpu_jobs(tmp_path):
    q = Queue(tmp_path / "jobs", tmp_path / "out")
    img = tmp_path / "in.png"
    Image.new("RGBA", (16, 16), (10, 200, 30, 255)).save(img)
    ids = q.submit_batch({"batch": "b", "defaults": {"palette": "resurrect-64"},
                          "jobs": [{"type": "palette_snap", "name": "snap", "inputs": [str(img)]},
                                   {"type": "contact_sheet", "name": "cs", "inputs": [str(img)]},
                                   {"type": "scene_card", "name": "gpu_only", "prompt": "x"}]})
    assert len(ids) == 3
    from forge.jobs import get_handlers; HANDLERS = get_handlers()
    from forge.jobs.common import Context
    ctx = Context(cfg=cfgmod.load(), palettes_dir=ROOT / "palettes", root=ROOT)
    ran = run_worker(q, HANDLERS, ctx, gpu=False, once=True)
    assert ran == 2, "the CPU worker runs the two CPU jobs and leaves the GPU job pending"
    st = q.status()
    assert st["done"] == 2 and st["pending"] == 1 and st["failed"] == 0
    snapped = Image.open(tmp_path / "out" / ids[0] / "in.png")
    assert pal.report(snapped, pal.load_palette(ROOT / "palettes" / "resurrect-64.hex"))["off_palette_colors"] == 0
    assert (tmp_path / "out" / ids[0] / "prov.json").exists()
    assert (tmp_path / "out" / ids[1] / "contact.png").exists()


def test_worker_records_failures(tmp_path):
    q = Queue(tmp_path / "jobs", tmp_path / "out")
    q.submit({"type": "contact_sheet", "name": "bad", "inputs": [str(tmp_path / "missing.png")]})
    from forge.jobs import get_handlers; HANDLERS = get_handlers()
    from forge.jobs.common import Context
    ctx = Context(cfg=cfgmod.load(), palettes_dir=ROOT / "palettes", root=ROOT)
    run_worker(q, HANDLERS, ctx, gpu=False, once=True)
    st = q.status()
    assert st["failed"] == 1
    failed = json.loads(next((tmp_path / "jobs" / "failed").glob("*.json")).read_text())
    assert "FileNotFoundError" in failed["error"] and "traceback" in failed


# ------------------------------------------------------------------ comfy templates
def test_workflow_fill_and_placeholders():
    wf = comfy.load_workflow("txt2img_sdxl")
    filled = comfy.fill(wf, {"prompt": "a cat", "negative": "dog", "seed": 7, "width": 512, "height": 256,
                             "steps": 20, "cfg": 5.5, "checkpoint": "x.safetensors", "batch": 2})
    assert filled["3"]["inputs"]["seed"] == 7 and isinstance(filled["3"]["inputs"]["seed"], int)
    assert filled["5"]["inputs"]["width"] == 512 and filled["5"]["inputs"]["batch_size"] == 2
    assert filled["3"]["inputs"]["cfg"] == 5.5
    with pytest.raises(ValueError):
        comfy.fill(wf, {"prompt": "a cat"})
    inline = comfy.fill({"a": "{{style}} :: {{prompt}}"}, {"style": "pixel art", "prompt": "cat"})
    assert inline["a"] == "pixel art :: cat"


def test_config_refuses_external_paths():
    cfg = cfgmod.load()
    cfg["paths"]["out"] = "C:/Users/someone/AppData/forge" if sys.platform == "win32" else "/tmp/forge-out"
    with pytest.raises(ValueError):
        cfgmod.path_of(cfg, "out")
