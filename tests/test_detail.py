"""N6: detail crops moved without re-rendering, the face search (fake ComfyUI), and N9d's review detail thumbnails."""
import io, json

import numpy as np
import pytest
from PIL import Image, ImageDraw

from forge import detail, config as cfgmod


@pytest.fixture
def suite(tmp_path, monkeypatch):
    monkeypatch.setattr(detail, "path", lambda s: tmp_path / s / "detail_at.json")
    return "t_suite"


def rows():
    return [{"id": "a", "image": None, "meta": {"prompt_id": "juke", "detail": {"size": 512, "at": [0.5, 0.5]}}},
            {"id": "b", "image": None, "meta": {"prompt_id": "juke", "detail": {"size": 512, "at": [0.5, 0.5]}}},
            {"id": "c", "image": None, "meta": {"prompt_id": "street"}}]


def test_parse_and_apply(suite):
    assert detail.parse_at("juke=0.42,0.35,640") == ("juke", {"at": [0.42, 0.35], "source": "manual", "size": 640})
    for bad in ("juke", "juke=1.5,0.2", "juke=0.1"):
        with pytest.raises(ValueError):
            detail.parse_at(bad)
    detail.set_at(suite, "juke=0.3,0.4")
    rs = rows()
    assert detail.apply(suite, rs) == 2
    assert rs[0]["meta"]["detail"] == {"size": 512, "at": [0.3, 0.4]} and "detail" not in rs[2]["meta"]


def test_largest_blob():
    m = Image.new("L", (1000, 500), 0)
    d = ImageDraw.Draw(m)
    d.rectangle([100, 100, 140, 140], fill=255)          # small face
    d.rectangle([700, 200, 820, 330], fill=255)          # big face
    x, y, area = detail.largest_blob_centre(m)
    assert abs(x - 0.76) < 0.02 and abs(y - 0.53) < 0.03 and area > 0
    assert detail.largest_blob_centre(Image.new("L", (64, 64), 0)) is None


class FaceComfy:
    def __init__(self, info):
        self.info, self.graphs = info, []

    def is_up(self):
        return True

    def object_info(self):
        return self.info

    def upload_image(self, p, name=None):
        return f"forge/{name}"

    def run_by_node(self, g):
        self.graphs.append(g)
        m = Image.new("RGB", (400, 200), 0)
        ImageDraw.Draw(m).rectangle([40, 20, 80, 60], fill=(255, 255, 255))
        b = io.BytesIO(); m.save(b, "PNG")
        return {"6": [b.getvalue()]}


def test_auto_centres_on_face_and_keeps_manual(suite, tmp_path):
    img = tmp_path / "x.png"; Image.new("RGB", (400, 200)).save(img)
    rs = rows()
    for r in rs:
        r["image"] = str(img)
    info = {n: {} for n in detail.FACE_NODES}
    fake = FaceComfy(info)
    lines = detail.auto(suite, rs, fake)
    assert any("largest face" in l for l in lines) and len(fake.graphs) == 1      # one search per prompt
    at = detail.load(suite)["juke"]["at"]
    assert abs(at[0] - 0.15) < 0.03 and abs(at[1] - 0.2) < 0.04
    detail.set_at(suite, "juke=0.9,0.9")
    assert any("kept the manual" in l for l in detail.auto(suite, rs, fake))
    assert "not installed" in detail.auto(suite, rs, FaceComfy({}))[0]
    assert "not running" in detail.auto(suite, rs, None)[0]


def test_review_shows_detail_crop(tmp_path, monkeypatch):
    from forge import review
    from test_manifest import make_world
    cfg, root, assets = make_world(tmp_path)
    monkeypatch.setattr(detail, "path", lambda s: tmp_path / "d" / s / "detail_at.json")
    out = tmp_path / "out" / "R1"; out.mkdir(parents=True)
    Image.new("RGB", (1920, 1080), (120, 80, 40)).save(out / "scene.png")
    (out / "prov.json").write_text("{}", encoding="utf-8")
    (tmp_path / "jobs" / "done" / "R1.json").write_text(json.dumps({"id": "R1", "type": "scene_paint", "batch": "bakeoff/fin",
        "result": {"outputs": ["scene.png"]}, "meta": {"suite": "fin", "category": "refine", "prompt_id": "juke",
        "checkpoint": "a.safetensors", "detail": {"size": 512, "at": [0.5, 0.5]}}}), encoding="utf-8")
    d = review.build(cfg, "fin")
    assert (d / "thumbs" / "R1_detail.jpg").exists() and "1:1 detail" in (d / "index.html").read_text(encoding="utf-8")
