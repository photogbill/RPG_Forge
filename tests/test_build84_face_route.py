"""BUILD 84 (2i) — the face route: ComfyUI's ImageScaleToTotalPixels (the version on William's PC) has a required
`resolution_steps` input; a graph without it is refused with "400 Bad Request" before anything runs. Both graphs that use
the node send it."""
from __future__ import annotations

import io

from PIL import Image

from forge.threed import bodies, same_person


def test_the_instructed_graph_sends_resolution_steps():
    g = same_person.graph_instructed("s.png", "the same man", 1, 768, 1024)
    node = next(n for n in g.values() if n["class_type"] == "ImageScaleToTotalPixels")
    assert node["inputs"]["resolution_steps"] == 1


def test_a_picture_with_a_face_to_start_from_sends_resolution_steps(tmp_path, monkeypatch):
    sent = {}

    class Client:
        def __init__(self, url):
            self.timeout = 0

        def upload_image(self, p, subfolder="", name=""):
            return name

        def run(self, g):
            sent.update(g)
            buf = io.BytesIO()
            Image.new("RGB", (8, 8)).save(buf, "PNG")
            return [buf.getvalue()]
    import forge.engines.comfy as comfy
    monkeypatch.setattr(comfy, "ComfyClient", Client)
    face = tmp_path / "face.png"
    Image.new("RGB", (8, 8)).save(face)
    bodies.paint("http://x", {"seed": 1}, {"id": "gen", "prompt": "An old general.", "face_ref": str(face)},
                 tmp_path / "p.png", "b", None)
    node = next(n for n in sent.values() if n["class_type"] == "ImageScaleToTotalPixels")
    assert node["inputs"]["resolution_steps"] == 1
