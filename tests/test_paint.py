"""F1–F3 + quality stages: graph surgery as dicts, CPU canny/overlay, and the paint handlers end to end against a
fake ComfyUI (no GPU): the graph each handler sends is checked, and the files it writes."""
import io, json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from forge.engines import graph_ops as go, sdxl_graph, flux1_graph, flux2_graph
from forge.ops import edges as ed, lighting as lt
from forge import config as cfgmod


def sdxl():
    return sdxl_graph.build("ArtUniverseSDXL_v8.safetensors", "a kitchen", "blurry", 5, 1344, 768, 25, 6.0)


def refs_ok(g):
    """Every link points at a node that exists, with a sane output index."""
    for k, n in g.items():
        for name, v in n["inputs"].items():
            if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str):
                assert v[0] in g, f"{k}.{name} → missing node {v[0]}"
                assert isinstance(v[1], int) and v[1] >= 0


# ------------------------------------------------------------------ graph_ops
def test_upscale_tail_and_raw_save():
    g = sdxl()
    raw = go.add_raw_save(g)
    go.add_upscale(g, "RealESRGAN_x4plus.pth", 1920, 1080, "center")
    refs_ok(g)
    assert g[raw]["inputs"]["images"] == ["7", 0] and g[raw]["inputs"]["filename_prefix"] == go.RAW_PREFIX
    final = g[go.save_node(g)]["inputs"]["images"][0]
    sc = g[final]
    assert sc["class_type"] == "ImageScale" and sc["inputs"]["width"] == 1920 and sc["inputs"]["crop"] == "center"
    up = g[sc["inputs"]["image"][0]]
    assert up["class_type"] == "ImageUpscaleWithModel"
    assert g[up["inputs"]["upscale_model"][0]]["inputs"]["model_name"] == "RealESRGAN_x4plus.pth"
    assert go.save_node(g) == "8"


def test_img2img_replaces_empty_latent_sdxl_and_flux1():
    g = sdxl()
    go.to_img2img(g, "forge/greybox.png", 0.55, 1216, 832)
    refs_ok(g)
    assert not go.nodes_of(g, *go.EMPTY_LATENTS)
    assert g["6"]["inputs"]["denoise"] == 0.55
    enc = g[g["6"]["inputs"]["latent_image"][0]]
    assert enc["class_type"] == "VAEEncode" and enc["inputs"]["vae"] == ["1", 2]
    assert g[enc["inputs"]["pixels"][0]]["inputs"]["crop"] == "disabled"
    f = flux1_graph.build("flux1-schnell-fp8.safetensors", "p", 1, 1024, 1024)
    go.to_img2img(f, "x.png", 0.6, 1024, 1024)
    refs_ok(f)
    assert f["8"]["inputs"]["denoise"] == 0.6 and g is not f


def test_img2img_flux2_splits_sigmas_and_batch_repeats():
    g = flux2_graph.build("flux-2-klein-4b-fp8.safetensors", "p", "", 1, 1024, 1024, batch=3)
    go.to_img2img(g, "x.png", 0.5, 1024, 1024)
    refs_ok(g)
    split = g[g["11"]["inputs"]["sigmas"][0]]
    assert split["class_type"] == "SplitSigmasDenoise" and g["11"]["inputs"]["sigmas"][1] == 1
    assert g[g["11"]["inputs"]["latent_image"][0]]["class_type"] == "RepeatLatentBatch"


def test_controlnet_union_rewires_conditioning():
    g = sdxl()
    go.add_controlnet(g, "xinsir-union-sdxl-promax.safetensors", "forge/control.png", 0.6, union_type="canny/lineart/anime_lineart/mlsd")
    refs_ok(g)
    ap = g[g["6"]["inputs"]["positive"][0]]
    assert ap["class_type"] == "ControlNetApplyAdvanced" and g["6"]["inputs"]["negative"] == [g["6"]["inputs"]["positive"][0], 1]
    assert ap["inputs"]["positive"] == ["2", 0] and ap["inputs"]["negative"] == ["3", 0] and ap["inputs"]["strength"] == 0.6
    st = g[ap["inputs"]["control_net"][0]]
    assert st["class_type"] == "SetUnionControlNetType" and st["inputs"]["type"].startswith("canny")


def test_refine_after_upscale_ksampler_and_flux2():
    g = sdxl()
    go.add_upscale(g, None, 1920, 1080)
    go.add_refine(g, 0.3)
    refs_ok(g)
    dec = g[g[go.save_node(g)]["inputs"]["images"][0]]
    k2 = g[dec["inputs"]["samples"][0]]
    assert k2["class_type"] == "KSampler" and k2["inputs"]["denoise"] == 0.3 and k2["inputs"]["seed"] == 6
    assert g[k2["inputs"]["latent_image"][0]]["class_type"] == "VAEEncode"
    f = flux2_graph.build("flux-2-klein-base-4b-fp8.safetensors", "p", "", 1, 1344, 768)
    go.add_upscale(f, "RealESRGAN_x4plus.pth", 1920, 1080)
    go.add_refine(f, 0.35)
    refs_ok(f)
    sched = [v for v in f.values() if v["class_type"] == "Flux2Scheduler"]
    assert len(sched) == 2 and {(s["inputs"]["width"], s["inputs"]["height"]) for s in sched} == {(1344, 768), (1920, 1080)}


def test_freeu_sdxl_only():
    g = sdxl()
    go.add_freeu(g)
    refs_ok(g)
    assert g[g["6"]["inputs"]["model"][0]]["class_type"] == "FreeU_V2"
    f = flux1_graph.build("flux1-schnell-fp8.safetensors", "p", 1, 1024, 1024)
    try:
        go.add_freeu(f)
        assert False, "FreeU must refuse FLUX"
    except go.GraphError:
        pass


FAKE_INFO = {
    "UltralyticsDetectorProvider": {"input": {"required": {"model_name": [["bbox/face_yolov8m.pt", "bbox/hand_yolov8s.pt"]]}}},
    "FaceDetailer": {"input": {"required": {
        "image": ["IMAGE"], "model": ["MODEL"], "clip": ["CLIP"], "vae": ["VAE"], "guide_size": ["FLOAT", {"default": 512}],
        "guide_size_for": ["BOOLEAN", {"default": True}], "max_size": ["FLOAT", {"default": 1024}], "seed": ["INT", {"default": 0}],
        "steps": ["INT", {"default": 20}], "cfg": ["FLOAT", {"default": 8}], "sampler_name": [["euler", "dpmpp_2m"]],
        "scheduler": [["normal", "karras"]], "positive": ["CONDITIONING"], "negative": ["CONDITIONING"],
        "denoise": ["FLOAT", {"default": 0.5}], "feather": ["INT", {"default": 5}], "noise_mask": ["BOOLEAN", {"default": True}],
        "force_inpaint": ["BOOLEAN", {"default": True}], "bbox_threshold": ["FLOAT", {"default": 0.5}],
        "bbox_dilation": ["INT", {"default": 10}], "bbox_crop_factor": ["FLOAT", {"default": 3.0}],
        "sam_detection_hint": [["center-1", "horizontal-2"]], "sam_dilation": ["INT", {"default": 0}],
        "drop_size": ["INT", {"default": 10}], "bbox_detector": ["BBOX_DETECTOR"], "wildcard": ["STRING", {"multiline": True}],
        "cycle": ["INT", {"default": 1}]}, "optional": {"sam_model_opt": ["SAM_MODEL"]}}},
}


def test_face_detailer_fills_from_object_info():
    g = sdxl()
    go.add_upscale(g, None, 1920, 1080)
    go.add_face_detailer(g, FAKE_INFO, denoise=0.4)
    refs_ok(g)
    fd = g[g[go.save_node(g)]["inputs"]["images"][0]]
    assert fd["class_type"] == "FaceDetailer"
    i = fd["inputs"]
    assert i["model"] == ["1", 0] and i["clip"] == ["1", 1] and i["positive"] == ["2", 0] and i["denoise"] == 0.4
    assert i["sam_detection_hint"] == "center-1" and i["bbox_dilation"] == 10 and i["guide_size"] == 1024
    assert "sam_model_opt" not in i
    try:
        go.add_face_detailer(sdxl(), FAKE_INFO, detector="bbox/nope.pt")
        assert False
    except go.GraphError as e:
        assert "not installed" in str(e)
    try:
        go.add_face_detailer(sdxl(), {})
        assert False
    except go.GraphError as e:
        assert "install" in str(e)


def test_node_from_info_new_combo_shape():
    info = {"X": {"input": {"required": {"mode": ["COMBO", {"options": ["a", "b"]}], "n": ["INT", {"default": 3}]}}}}
    assert go.node_from_info(info, "X", {}) == {"mode": "a", "n": 3}


def test_fit_render_size():
    assert go.fit_render_size(2304, 1536) == (1216, 832)
    w, h = go.fit_render_size(1920, 1080)
    assert w % 64 == 0 and h % 64 == 0 and 0.85e6 < w * h < 1.15e6


# ------------------------------------------------------------------ CPU ops
def greybox(w=240, h=160):
    im = Image.new("RGB", (w, h), (120, 100, 80))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, w - 1, 15], fill=(90, 70, 60))
    d.rectangle([110, 0, 125, 100], fill=(90, 70, 60))
    d.rectangle([30, 40, 60, 70], fill=(34, 38, 46))
    return im


def test_canny_finds_walls_and_overlay():
    im = greybox()
    e = ed.canny(im)
    a = np.asarray(e) > 127
    assert a.shape == (160, 240) and a.any()
    assert a[50:60, 108:112].any() and a[50:60, 124:128].any()      # both sides of the vertical wall
    assert not a[120:150, 150:230].any()                              # flat floor: no edges
    ov = ed.overlay(im, e)
    assert ov.size == im.size and np.asarray(ov)[a].tolist()[0] == [255, 40, 40]
    assert ed.edge_agreement(im, e) > 0.9
    assert ed.edge_agreement(Image.new("RGB", im.size, (120, 100, 80)), e) < 0.1


def test_normal_map_and_emissive():
    im = Image.new("RGB", (64, 64), (40, 40, 40))
    ImageDraw.Draw(im).ellipse([16, 16, 48, 48], fill=(220, 220, 220))
    n = np.asarray(lt.normal_map(im)).astype(int)
    assert abs(n[5, 5, 0] - 128) <= 2 and abs(n[5, 5, 1] - 128) <= 2 and n[5, 5, 2] == 255   # flat → (0,0,1)
    assert n[32, 15, 0] < 120 and n[32, 49, 0] > 136      # bump's left edge faces left, right edge faces right
    assert n[15, 32, 1] > 136 and n[49, 32, 1] < 120      # top edge faces up (OpenGL green up)
    neon = Image.new("RGB", (32, 32), (30, 30, 30))
    ImageDraw.Draw(neon).rectangle([4, 4, 10, 10], fill=(255, 40, 200))
    ImageDraw.Draw(neon).rectangle([20, 20, 26, 26], fill=(250, 250, 250))  # bright but grey: not a glow
    e, lit = lt.emissive_mask(neon, feather=0)
    a = np.asarray(e)
    assert a[7, 7].tolist() == [255, 40, 200] and a[23, 23].tolist() == [0, 0, 0] and 0 < lit < 0.1


# ------------------------------------------------------------------ handlers against a fake ComfyUI
class FakeComfy:
    url, timeout, poll = "http://fake", 10, 0.1

    def __init__(self, info=None):
        self.graphs, self.uploads, self.info = [], [], info or FAKE_INFO

    def is_up(self):
        return True

    def object_info(self):
        return self.info

    def upload_image(self, path, subfolder="forge", name=None):
        self.uploads.append(Path(path))
        return f"forge/{name or Path(path).name}"

    def _png(self, w, h, color):
        b = io.BytesIO()
        Image.new("RGB", (w, h), color).save(b, "PNG")
        return b.getvalue()

    def _size(self, g, ref):
        """Follow the picture upstream to the nearest ImageScale (what ComfyUI would output); 64×48 if none."""
        n = g[ref[0]]
        if n["class_type"] == "ImageScale":
            return n["inputs"]["width"], n["inputs"]["height"]
        for key in ("image", "pixels", "samples", "latent_image", "images"):
            v = n["inputs"].get(key)
            if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str):
                return self._size(g, v)
        return 64, 48

    def run_by_node(self, g):
        self.graphs.append(g)
        out = {}
        for k, n in g.items():
            if n["class_type"] != "SaveImage":
                continue
            w, h = self._size(g, n["inputs"]["images"])
            out[k] = [self._png(w, h, (200, 120, 60) if n["inputs"]["filename_prefix"] != go.RAW_PREFIX else (10, 10, 10))]
        return out

    def run(self, g):
        self.graphs.append(g)
        return [self._png(512, 512, (255, 0, 255))]


def ctx_with(tmp_path, fake):
    from forge.jobs.common import Context
    cfg = cfgmod.load()
    return Context(cfg=cfg, comfy=fake, palettes_dir=cfgmod.ROOT / "palettes", root=cfgmod.ROOT)


def test_scene_paint_end_to_end(tmp_path):
    from forge.jobs import paint
    fake = FakeComfy()
    ctx = ctx_with(tmp_path, fake)
    job = {"id": "t1", "type": "scene_paint", "name": "gas_station", "prompt": "a gas station at dusk",
           "checkpoint": "sd_xl_base_1.0.safetensors", "face_fix": True, "variants": 2, "seed": 100}
    res = paint.scene_paint(job, ctx, tmp_path)
    assert res["outputs"] == ["scene_1.png", "scene_2.png"]
    assert Image.open(tmp_path / "scene_1.png").size == (1920, 1080)
    assert (tmp_path / "raw_1.png").exists() and (tmp_path / "contact.png").exists()
    g = fake.graphs[0]
    kinds = go.required_nodes(g)
    assert {"UpscaleModelLoader", "ImageUpscaleWithModel", "FaceDetailer", "UltralyticsDetectorProvider"} <= kinds
    assert len([n for n in g.values() if n["class_type"] == "KSampler"]) == 2        # base + refine
    assert g["4"]["inputs"]["width"] == 1344
    prov = json.loads((tmp_path / "prov.json").read_text(encoding="utf-8"))
    assert prov["seeds"] == [100, 101] and prov["target"] == [1920, 1080]
    roles = {l["role"] for l in prov["licences"]}
    assert {"checkpoint", "upscaler", "face_detector"} <= roles
    assert prov["commercial_ok"] is True        # SDXL base + RealESRGAN + face_yolov8m are registered commercial-OK


def test_repaint_sweep_keeps_init_size_and_canny_control(tmp_path):
    from forge.jobs import paint
    init = tmp_path / "greybox.png"
    greybox(230, 154).save(init)
    fake = FakeComfy()
    ctx = ctx_with(tmp_path, fake)
    out = tmp_path / "out"
    out.mkdir()
    job = {"id": "t2", "type": "repaint", "name": "bills_house", "prompt": "a cosy living room", "init": str(init),
           "denoise": [0.45, 0.55, 0.65], "control": {"type": "canny", "strength": 0.5}, "refine": False,
           "checkpoint": "sd_xl_base_1.0.safetensors"}
    res = paint.repaint(job, ctx, out)
    assert res["outputs"] == ["scene_d045.png", "scene_d055.png", "scene_d065.png"]
    assert all(Image.open(out / n).size == (230, 154) for n in res["outputs"])
    assert (out / "control.png").exists() and (out / "control_overlay_d055.png").exists() and (out / "contact.png").exists()
    g = fake.graphs[1]
    assert {n["class_type"] for n in g.values()} >= {"VAEEncode", "ControlNetApplyAdvanced", "SetUnionControlNetType"}
    scales = [n for n in g.values() if n["class_type"] == "ImageScale"]
    assert all(s["inputs"]["crop"] == "disabled" for s in scales)
    assert [n for n in g.values() if n["class_type"] == "KSampler"][0]["inputs"]["denoise"] == 0.55
    prov = json.loads((out / "prov.json").read_text(encoding="utf-8"))
    assert prov["denoise"] == [0.45, 0.55, 0.65] and "layout_agreement" in prov


def test_depth_control_skips_cleanly_without_aux_nodes(tmp_path):
    from forge.jobs import paint
    init = tmp_path / "g.png"
    greybox().save(init)
    fake = FakeComfy(info={})
    ctx = ctx_with(tmp_path, fake)
    out = tmp_path / "o"
    out.mkdir()
    job = {"id": "t3", "type": "scene_paint", "prompt": "x", "init": str(init), "control": {"type": "depth"},
           "checkpoint": "sd_xl_base_1.0.safetensors", "refine": False}
    paint.scene_paint(job, ctx, out)
    prov = json.loads((out / "prov.json").read_text(encoding="utf-8"))
    assert any("depth SKIPPED" in n for n in prov["notes"])
    assert "ControlNetApplyAdvanced" not in go.required_nodes(fake.graphs[0])


def test_icon_and_sleeve(tmp_path):
    from forge.jobs import assets
    fake = FakeComfy()
    ctx = ctx_with(tmp_path, fake)
    # icon: the fake renders flat magenta → after background removal nothing is left but the canvas must still be right
    res = assets.icon({"id": "i1", "type": "icon", "prompt": "a coolant canister", "canvas": 256, "seed": 3,
                       "checkpoint": "sd_xl_base_1.0.safetensors"}, ctx, tmp_path)
    assert Image.open(tmp_path / "icon.png").size == (256, 256) and res["outputs"] == ["icon.png"]
    cut = Image.new("RGBA", (100, 40), (255, 0, 0, 255))
    ic = assets.fit_on_canvas(cut, 256, 0.1)
    bbox = ic.getbbox()
    assert bbox[2] - bbox[0] == 205 and (bbox[1] + bbox[3]) // 2 == 128
    art = Image.new("RGB", (512, 512), (40, 80, 160))
    for layout in ("band", "corner"):
        s = assets.compose_sleeve(art, "The Choice Before the War", "Narrator / the DARPA briefing", "Album 2", layout, 512)
        a = np.asarray(s)
        assert s.size == (512, 512) and (a > 200).all(axis=-1).sum() > 200     # white type got drawn
    out2 = tmp_path / "s"
    out2.mkdir()
    assets.sleeve({"id": "s1", "type": "sleeve", "prompt": "a sunrise over a lab", "title": "Sarah: Activation Sequence",
                   "artist": "Sarah", "checkpoint": "sd_xl_base_1.0.safetensors", "out_size": 384}, ctx, out2)
    assert Image.open(out2 / "sleeve.png").size == (384, 384)


def test_pipeline_cpu_chain(tmp_path):
    from forge import pipeline, schema
    from forge.jobs import get_handlers
    src = tmp_path / "a.png"
    greybox().save(src)
    job = {"id": "p1", "type": "pipeline", "name": "chain", "steps": [
        {"type": "canny", "inputs": [str(src)]},
        {"type": "normal_map", "inputs": ["$prev.outputs"]},
        {"type": "contact_sheet", "inputs": ["$steps[1].outputs[0]", "$prev.outputs[0]"]}]}
    assert schema.validate(job) == [] and not schema.needs_gpu(job)
    from forge.jobs.common import Context
    ctx = Context(cfg=cfgmod.load(), root=cfgmod.ROOT, palettes_dir=cfgmod.ROOT / "palettes")
    get_handlers()
    res = pipeline.handler(job, ctx, tmp_path / "out")
    assert res["steps"] == 3 and res["step_dirs"] == ["01_canny", "02_normal_map", "03_contact_sheet"]
    assert (tmp_path / "out" / "02_normal_map" / "a_n.png").exists() and (tmp_path / "out" / "contact.png").exists()
    prov = json.loads((tmp_path / "out" / "prov.json").read_text(encoding="utf-8"))
    assert prov["steps"][1]["outputs"] == ["02_normal_map/a_n.png"]


def test_pipeline_errors_name_the_step(tmp_path):
    from forge import pipeline, schema
    from forge.jobs import get_handlers
    from forge.jobs.common import Context
    bad = {"type": "pipeline", "steps": [{"type": "canny", "inputs": ["$prev.outputs[0]"]}]}
    ctx = Context(cfg=cfgmod.load(), root=cfgmod.ROOT, palettes_dir=cfgmod.ROOT / "palettes")
    try:
        pipeline.run(bad, ctx, tmp_path, get_handlers())
        assert False
    except pipeline.PipelineError as e:
        assert "step 1 (canny)" in str(e) and "first step" in str(e)
    assert schema.validate({"type": "pipeline", "steps": []})
    assert schema.needs_gpu({"type": "pipeline", "steps": [{"type": "canny", "inputs": ["x"]}, {"type": "upscale", "inputs": ["y"]}]})
    nested = {"type": "pipeline", "steps": [{"type": "pipeline", "steps": [{"type": "canny", "inputs": ["x"]}]}]}
    assert any("do not nest" in p for p in schema.validate(nested))


def test_big_scrolling_target_refines_at_capped_size(tmp_path):
    from forge.jobs import paint
    fake = FakeComfy()
    ctx = ctx_with(tmp_path, fake)
    job = {"id": "t9", "type": "scene_paint", "prompt": "a long main street", "target": [6144, 3072],
           "checkpoint": "sd_xl_base_1.0.safetensors"}
    paint.scene_paint(job, ctx, tmp_path)
    g = fake.graphs[0]
    scales = sorted((n["inputs"]["width"], n["inputs"]["height"]) for n in g.values() if n["class_type"] == "ImageScale")
    assert (6144, 3072) in scales and any(w * h <= 4_000_000 for w, h in scales)
    refine = [n for n in g.values() if n["class_type"] == "KSampler"][1]
    enc = g[refine["inputs"]["latent_image"][0]]
    src = g[enc["inputs"]["pixels"][0]]
    assert src["class_type"] == "ImageScale" and src["inputs"]["width"] * src["inputs"]["height"] <= 4_000_000
    assert Image.open(tmp_path / "scene.png").size == (6144, 3072)


def test_depth_control_uses_only_the_commercial_depth_model(tmp_path):
    from forge.jobs import paint
    init = tmp_path / "g.png"
    greybox().save(init)
    info = dict(FAKE_INFO)
    info["DepthAnythingV2Preprocessor"] = {"input": {"required": {"image": ["IMAGE"],
        "ckpt_name": [["depth_anything_v2_vitl.pth", "depth_anything_v2_vits.pth"]], "resolution": ["INT", {"default": 512}]}}}
    fake = FakeComfy(info=info)
    ctx = ctx_with(tmp_path, fake)
    out = tmp_path / "o"
    out.mkdir()
    paint.scene_paint({"id": "t4", "type": "scene_paint", "prompt": "x", "init": str(init), "control": {"type": "depth"},
                       "checkpoint": "sd_xl_base_1.0.safetensors", "refine": False}, ctx, out)
    node = [n for n in fake.graphs[0].values() if n["class_type"] == "DepthAnythingV2Preprocessor"][0]
    assert node["inputs"]["ckpt_name"] == "depth_anything_v2_vits.pth" and node["inputs"]["resolution"] == 1024
    prov = json.loads((out / "prov.json").read_text(encoding="utf-8"))
    assert {"role": "depth_model", "file": "depth_anything_v2_vits.pth", "model": "depth-anything-v2-small",
            "license": "Apache-2.0", "commercial_ok": True} in prov["licences"] and prov["commercial_ok"] is True


def test_every_new_gpu_type_survives_the_workers_defaults(tmp_path):
    """The worker runs schema.with_defaults first (unset optional fields → None); every handler must cope."""
    from forge import schema
    from forge.jobs import get_handlers
    init = tmp_path / "g.png"
    greybox().save(init)
    fake = FakeComfy()
    ctx = ctx_with(tmp_path, fake)
    jobs = [{"type": "scene_paint", "prompt": "x"}, {"type": "scene_paint", "prompt": "x", "init": str(init)},
            {"type": "repaint", "prompt": "x", "init": str(init)}, {"type": "upscale", "inputs": [str(init)]},
            {"type": "icon", "prompt": "a cup"}, {"type": "sleeve", "prompt": "x", "title": "T"},
            {"type": "render", "prompt": "x"}]
    h = get_handlers()
    for i, j in enumerate(jobs):
        j = dict(j, id=f"d{i}", name=f"d{i}", checkpoint="sd_xl_base_1.0.safetensors")
        assert schema.validate(j) == [], j
        full = schema.with_defaults(j)
        out = tmp_path / f"o{i}"
        out.mkdir()
        if j["type"] == "render":
            fake.run = lambda g: (fake.graphs.append(g), [fake._png(64, 64, (1, 2, 3))])[1]
        h[j["type"]](full, ctx, out)
    for g in fake.graphs:
        for n in g.values():
            if n["class_type"] == "KSampler":
                assert n["inputs"]["sampler_name"] != "None" and isinstance(n["inputs"]["steps"], int)
