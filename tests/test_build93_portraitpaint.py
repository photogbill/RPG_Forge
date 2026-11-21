"""BUILD 93 — portraits painted over the bodies: the words, the graph (one reference and two), what a result kept, which
one is proposed, the job and the command against a stand-in for ComfyUI (it keeps what was uploaded, reads the graph it
is given and paints by rule), and the card lock taken once for a whole batch. Nothing here touches a graphics card."""
import io
import json
import os
import re
import time
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from forge import config as cfgmod
from forge.jobs.common import Context
from forge.threed import portraitpaint as pp
from forge.threed import same_person as sp


def body_portrait(size=256, hair=(120, 40, 160), shirt=(40, 60, 150)) -> Image.Image:
    """A head and shoulders on a clear background, lit from the right: a face, hair, a shirt."""
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    s = size / 256
    d.ellipse([70 * s, 30 * s, 186 * s, 170 * s], fill=hair + (255,))
    d.ellipse([88 * s, 52 * s, 168 * s, 160 * s], fill=(215, 160, 130, 255))
    d.rectangle([128 * s, 52 * s, 168 * s, 160 * s], fill=(235, 185, 150, 255))          # the lit side
    d.ellipse([100 * s, 92 * s, 116 * s, 102 * s], fill=(30, 30, 40, 255))
    d.ellipse([140 * s, 92 * s, 156 * s, 102 * s], fill=(30, 30, 40, 255))
    d.polygon([(30 * s, 256 * s), (60 * s, 180 * s), (196 * s, 180 * s), (226 * s, 256 * s)], fill=shirt + (255,))
    return im


def body_picture(size=256) -> Image.Image:
    """The picture a body was made from: the whole figure, small, on a light ground."""
    im = Image.new("RGB", (size, size), (205, 205, 208))
    d = ImageDraw.Draw(im)
    d.ellipse([116, 20, 140, 48], fill=(215, 160, 130))
    d.rectangle([108, 50, 148, 150], fill=(40, 60, 150))
    d.rectangle([112, 150, 126, 240], fill=(20, 20, 24))
    d.rectangle([130, 150, 144, 240], fill=(20, 20, 24))
    return im


class StandIn:
    """Stands in for ComfyUI. A graph whose last reference is the body portrait comes back as that portrait (it was
    painted over: layout and colours hold); one whose only reference is the body's picture comes back as that picture
    (the whole figure on a light ground: reframed). 'PLANT_FAIL' anywhere in the words fails that request."""
    def __init__(self):
        self.uploads, self.graphs, self.up, self.during = {}, [], True, None

    def is_up(self):
        return self.up

    def upload_image(self, path, subfolder="forge", name=None):
        n = name or Path(path).name
        self.uploads[n] = Path(path).read_bytes()
        return n

    def run(self, g):
        self.graphs.append(g)
        if self.during:
            self.during()
        if "PLANT_FAIL" in g["4"]["inputs"]["text"]:
            raise RuntimeError("the card ran out of memory")
        refs = [g[k]["inputs"]["image"] for k in sorted(g, key=int) if g[k]["class_type"] == "LoadImage"]
        w, h = g["6"]["inputs"]["width"], g["6"]["inputs"]["height"]
        img = Image.open(io.BytesIO(self.uploads[refs[-1]])).convert("RGB").resize((w, h), Image.LANCZOS)
        b = io.BytesIO()
        img.save(b, "PNG")
        return [b.getvalue()]


def ctx_of(cfg, tmp):
    return Context(cfg=cfg, palettes_dir=cfgmod.ROOT / "palettes", root=tmp)


@pytest.fixture()
def forge(tmp_path, monkeypatch):
    """A forge in a folder: a game with three names — one with a made body and its picture, one with a body portrait
    and no picture, one whose body is not made — and one more the game leaves as it is."""
    base = cfgmod.load()
    cfg = {**base, "paths": {**base["paths"], "jobs": str(tmp_path / "jobs"), "out": str(tmp_path / "out"), "logs": str(tmp_path / "logs"),
                             "games": str(tmp_path / "games")}, "allow_external_paths": True}
    monkeypatch.setattr(cfgmod, "ROOT", tmp_path)
    g = tmp_path / "games" / "g"
    (g / "wanted_3d" / "_state").mkdir(parents=True)
    (g / "pictures").mkdir()
    (g / "wanted_3d" / "list.json").write_text(json.dumps({"entries": [
        {"id": i, "kind": "body", "tier": "named", "words": "A person.", "real_size_m": {"height": 1.7}} for i in ("hero_body", "later_body")]}))
    pics = tmp_path / "out" / "3d" / "world" / "g" / "hero_body" / "pictures"
    pics.mkdir(parents=True)
    body_picture().save(pics / "hero_body.png")
    (g / "wanted_3d" / "_state" / "hero_body.json").write_text(json.dumps({
        "state": "made", "model": "out/3d/world/g/hero_body/hero_body.glb", "picture": "out/3d/world/g/hero_body/pictures/hero_body.png",
        "engine": "trellis2", "try": "t1"}))
    (g / "pictures" / "portraits.json").write_text(json.dumps({"size": 768, "portraits": {
        "hero": {"world": "hero_body", "rim": [0.25, 0.9, 1.0]}, "glow": {"model": "somewhere/glow.glb"}, "later": {"world": "later_body"},
        "shade": {"model": "somewhere/shade.glb"}}}))
    (g / "pictures" / "portraits_painted.json").write_text(json.dumps({
        "skip": {"shade": "a figure of light: nothing to paint"}, "names": {"hero": {"who": "a woman of thirty"}}}))
    src = tmp_path / "out" / "pictures" / "g" / "portraits"
    src.mkdir(parents=True)
    for n in ("hero", "glow", "shade"):
        body_portrait().save(src / f"{n}.png")
    return cfg, tmp_path


class Args:
    only = None
    again = False
    ways = None
    seeds = None


# ------------------------------------------------------------------ the words and the graph
def test_every_way_starts_with_the_style_start_and_says_its_own_thing():
    over, pic, both = (pp.words_for(w) for w in pp.WAYS)
    assert all(t.startswith(sp.STYLE_START) and t.startswith("Fantastic Realism, Hyperrealistic, ") for t in (over, pic, both))
    assert "changed from a rough 3D model into a real photograph" in over and "Keep the pose, the" in over
    assert "the body turned a little to one side" in pic
    assert "the person in image 1" in both and "as in image 2" in both               # each picture's part is named, in reference order
    assert all("one warm candle close to the face" in t and "near-black background" in t and "mouth closed" in t for t in (over, pic, both))
    # the rim has a colour's name only where a character owns one
    assert "a faint cool rim" in over and "cyan" not in over
    assert "a faint cyan rim" in pp.words_for("over", rim=[0.25, 0.9, 1.0]) and "a faint red rim" in pp.words_for("both", rim=[200, 12, 20])
    assert "the same person (a boy of ten)" in pp.words_for("picture", who="a boy of ten")
    assert pp.words_for("over", also="Freckles.").endswith(" Freckles.")
    with pytest.raises(pp.PaintError, match="no way called"):
        pp.words_for("sideways")


def test_one_reference_is_the_same_person_graph_and_two_are_two_nodes_in_a_line():
    one = pp.graph(["a.png"], "words", 7, 1024, 1024)
    theirs = sp.graph_instructed("a.png", "words", 7, 1024, 1024)
    for g in (one, theirs):
        g["13"]["inputs"]["filename_prefix"] = "x"
    assert one == theirs                                                     # the proven graph, not a cousin of it
    two = pp.graph(["picture.png", "portrait.png"], "words", 7, 1024, 1024)
    refs = [k for k in sorted(two, key=int) if two[k]["class_type"] == "ReferenceLatent"]
    assert refs == ["43", "53"] and two["40"]["inputs"]["image"] == "picture.png" and two["50"]["inputs"]["image"] == "portrait.png"
    assert two["43"]["inputs"]["conditioning"] == ["4", 0] and two["53"]["inputs"]["conditioning"] == ["43", 0]      # each on the one before
    assert two["10"]["inputs"]["positive"] == ["53", 0] and two["5"]["inputs"]["conditioning"] == ["53", 0]
    assert two["1"]["inputs"]["unet_name"] == "flux-2-klein-4b.safetensors" and two["9"]["inputs"]["steps"] == 4       # distilled: 4 steps
    assert pp.refs_for("over", "p", "q") == ["p"] and pp.refs_for("picture", "p", "q") == ["q"] and pp.refs_for("both", "p", "q") == ["q", "p"]
    with pytest.raises(pp.PaintError, match="needs the picture the body was made from"):
        pp.refs_for("both", "p", None)
    with pytest.raises(pp.PaintError, match="at least one reference"):
        pp.graph([], "w", 1)


# ------------------------------------------------------------------ what a result kept, and which is proposed
def test_the_two_tripwires_tell_a_reframed_picture_and_a_recoloured_one():
    body, fig = pp.flatten(body_portrait(512))
    same = pp.kept(body, fig, body)
    assert same["ok"] and same["layout"] > 0.95 and same["colour"] > 0.95 and same["patches"] >= 6
    moved = Image.new("RGB", body.size, pp.GROUND)
    moved.paste(body.resize((256, 256)), (240, 250))                         # the same person, small, in a corner
    r = pp.kept(body, fig, moved)
    assert not r["ok"] and r["layout"] < 0.5 and "reframed, re-posed or lit from another side" in r["says"]
    green, _ = pp.flatten(body_portrait(512, hair=(40, 95, 40), shirt=(120, 45, 20)))        # other colours, the same light and dark
    c = pp.kept(body, fig, green)
    assert not c["ok"] and c["layout"] > 0.8 and c["colour"] < 0.6 and "the colours moved" in c["says"]
    # brighter or darker is not a change of colour: light is the painting's to set
    dark = Image.fromarray((np.asarray(body, dtype=np.float32) * 0.6).astype(np.uint8))
    d = pp.kept(body, fig, dark)
    assert d["colour"] > 0.9 and d["layout"] > 0.95
    # lit from the other side: the same person, the same place, and the layout says so
    r2 = pp.kept(body, fig, body.transpose(Image.FLIP_LEFT_RIGHT))
    whole = pp.kept(body, fig, body_picture(512))
    assert whole["layout"] < 0.3 and not whole["ok"]                           # a whole figure on a light ground is nothing like it
    assert r2["layout"] < same["layout"]


def test_which_one_is_proposed():
    k = lambda lay, col, ok=True: {"layout": lay, "colour": col, "ok": ok}                       # noqa: E731
    c = [{"key": "over__1", "way": "over", "file": "a", "kept": k(0.80, 0.90)}, {"key": "picture__1", "way": "picture", "file": "b", "kept": k(0.2, 0.9, False)},
         {"key": "both__1", "way": "both", "file": "c", "kept": k(0.79, 0.90)}, {"key": "both__2", "way": "both", "kept": {}, "error": "boom"}]
    best, why = pp.choose(c)
    assert best["key"] == "both__1" and "held layout and colours" in why           # a near tie goes to the way that used most
    c[2]["kept"] = k(0.60, 0.90)
    assert pp.choose(c)[0]["key"] == "over__1"                                     # a real difference wins
    assert pp.choose(c, pick="picture__1") == (c[1], "named in the table")
    none, why = pp.choose(c, pick="both__2")
    assert none is None and "was not painted" in why and "over__1" in why
    for x in c:
        if x.get("file"):
            x["kept"]["ok"] = False
    best, why = pp.choose(c)
    assert best["key"] == "over__1" and "NONE held both" in why and "look before using" in why
    assert pp.choose([{"key": "over__1", "way": "over", "error": "x"}]) == (None, "nothing was painted")


# ------------------------------------------------------------------ the job
class Beats:
    n = 0

    def beat(self):
        self.n += 1


def job_of(tmp, **more):
    body_portrait().save(tmp / "hero.png")
    body_picture().save(tmp / "hero_picture.png")
    return {"id": "J1", "type": "portrait_paint", "name": "painted_hero", "slot_name": "hero", "portrait": str(tmp / "hero.png"),
            "picture": str(tmp / "hero_picture.png"), "size": 512, "rim": [0.25, 0.9, 1.0], **more}


def test_the_job_paints_three_ways_two_seeds_and_proposes_one(tmp_path):
    out = tmp_path / "out" / "J1"
    out.mkdir(parents=True)
    st, lock = StandIn(), Beats()
    res = pp.paint_job(job_of(tmp_path), ctx_of({}, tmp_path), out, client=st, lock=lock)
    assert len(st.graphs) == 6 and lock.n == 6                                     # the caller's lock is kept alive, none taken
    assert res["proposed"] == "both__1001" and "held layout and colours" in res["why"]
    assert Image.open(out / "hero.png").size == (768, 768) and Image.open(out / "hero_384.png").size == (384, 384)
    assert sorted(p.name for p in out.glob("hero__*.png")) == [f"hero__{w}__{s}.png" for w in ("both", "over", "picture") for s in (1001, 2002)]
    assert Image.open(out / "hero__over__1001.png").size == (512, 512) and (out / "contact.png").is_file()
    by = {c["key"]: c for c in res["candidates"]}
    assert by["over__1001"]["kept"]["ok"] and by["both__2002"]["kept"]["ok"] and not by["picture__1001"]["kept"]["ok"]     # the whole figure: reframed
    # what was sent: the body portrait on the near-black ground, the body's picture as it is; 'both' = picture then portrait
    assert sorted(st.uploads) == ["J1__picture.png", "J1__portrait.png"]
    sent = Image.open(io.BytesIO(st.uploads["J1__portrait.png"]))
    assert sent.mode == "RGB" and sent.getpixel((2, 2)) == pp.GROUND
    last = st.graphs[-1]
    assert [last[k]["inputs"]["image"] for k in ("40", "50")] == ["J1__picture.png", "J1__portrait.png"]
    assert "a faint cyan rim" in last["4"]["inputs"]["text"] and last["7"]["inputs"]["noise_seed"] == 2002 and last["6"]["inputs"]["width"] == 512
    prov = json.loads((out / "prov.json").read_text())
    assert prov["proposed"] == "both__1001" and any("FLUX.2 [klein] 4B" in ln and "Apache-2.0" in ln for ln in prov["licences_lines"])
    assert prov["commercial_ok"] is True and "cannot say it is the same face" in prov["measures"] and len(prov["candidates"]) == 6


def test_without_the_bodys_picture_only_over_is_painted_and_a_named_pick_wins(tmp_path):
    out = tmp_path / "o"
    out.mkdir()
    j = job_of(tmp_path, pick="over__2002")
    del j["picture"]
    st = StandIn()
    res = pp.paint_job(j, ctx_of({}, tmp_path), out, client=st, lock=Beats())
    assert len(st.graphs) == 2 and res["proposed"] == "over__2002" and res["why"] == "named in the table"
    assert [c["key"] for c in res["candidates"]] == ["over__1001", "over__2002"]
    res2 = pp.paint_job({**j, "ways": ["over", "both"], "pick": None}, ctx_of({}, tmp_path), out, client=StandIn(), lock=Beats())
    assert "only 'over' was painted" in res2["notes"][0]
    with pytest.raises(pp.PaintError, match="need the picture the body was made from"):
        pp.paint_job({**j, "ways": ["both"]}, ctx_of({}, tmp_path), out, client=StandIn(), lock=Beats())


def test_failures_are_written_down_and_said_plainly(tmp_path):
    out = tmp_path / "o"
    out.mkdir()
    st = StandIn()
    with pytest.raises(pp.PaintError, match="nothing was painted - over__1001: RuntimeError: the card ran out of memory"):
        pp.paint_job(job_of(tmp_path, also="PLANT_FAIL"), ctx_of({}, tmp_path), out, client=st, lock=Beats())
    assert len(st.graphs) == 6                                                     # every one was tried; none hid the others
    with pytest.raises(pp.PaintError, match="the body portrait is not there"):
        pp.paint_job({**job_of(tmp_path), "portrait": str(tmp_path / "gone.png")}, ctx_of({}, tmp_path), out, client=st)
    with pytest.raises(pp.PaintError, match="the picture the body was made from is not there"):
        pp.paint_job({**job_of(tmp_path), "picture": str(tmp_path / "gone.png")}, ctx_of({}, tmp_path), out, client=st)
    with pytest.raises(pp.PaintError, match="the table names sideways__1"):
        pp.paint_job(job_of(tmp_path, pick="sideways__1"), ctx_of({}, tmp_path), out, client=StandIn(), lock=Beats())


# ------------------------------------------------------------------ the command
def test_the_command_paints_what_has_a_body_portrait_and_says_the_rest(forge):
    cfg, tmp = forge
    st = StandIn()
    states, bad = pp.cmd_paint(cfg, "g", Args(), client=st, use_lock=False)
    assert bad == 0 and states["hero"]["state"] == "painted" and states["hero"]["proposed"] == "both__1001"
    assert states["glow"]["state"] == "painted" and states["glow"]["proposed"] == "over__1001"          # no picture of its own: 'over' only
    assert states["later"]["state"].startswith("no body portrait yet") and states["shade"]["state"] == "left as it is: a figure of light: nothing to paint"
    assert len(st.graphs) == 6 + 2
    assert any("the same person (a woman of thirty)" in g["4"]["inputs"]["text"] for g in st.graphs)     # the game's own words went in
    dest = tmp / "out" / "pictures" / "g" / "portraits_painted"
    assert Image.open(dest / "hero.png").size == (768, 768) and Image.open(dest / "384" / "hero.png").size == (384, 384)
    assert len(list((dest / "candidates").glob("hero__*.png"))) == 6 and len(list((dest / "candidates").glob("glow__*.png"))) == 2
    note = json.loads((dest / "hero.json").read_text())
    assert note["proposed"] == "both__1001" and note["picture"].endswith("hero_body.png") and len(note["candidates"]) == 6
    sheet = pp.write_sheet(cfg, "g", states)
    im = Image.open(sheet)
    assert sheet.name == "portraits_painted_sheet.png" and im.width == 8 + 7 * (256 + 8)             # the body portrait and six, one line a name
    # the jobs were the forge's own, GPU jobs with receipts, and they are done
    done = [json.loads(p.read_text()) for p in (tmp / "jobs" / "done").glob("*.json")]
    assert len(done) == 2 and all(d["batch"] == "pictures/portraits_painted" and d["type"] == "portrait_paint" for d in done)
    # a second run paints nothing; a body portrait taken again is painted again; --again paints all; --only one
    st2 = StandIn()
    assert pp.cmd_paint(cfg, "g", Args(), client=st2, use_lock=False)[0]["hero"]["proposed"] == "both__1001" and not st2.graphs
    t = time.time() + 5
    os.utime(tmp / "out" / "pictures" / "g" / "portraits" / "glow.png", (t, t))
    pp.cmd_paint(cfg, "g", Args(), client=st2, use_lock=False)
    assert len(st2.graphs) == 2
    again = Args()
    again.again, again.only, again.ways, again.seeds = True, ["hero"], ["over"], [5]
    pp.cmd_paint(cfg, "g", again, client=st2, use_lock=False)
    assert len(st2.graphs) == 3 and st2.graphs[-1]["7"]["inputs"]["noise_seed"] == 5


def test_another_candidate_is_picked_without_the_card(forge):
    cfg, tmp = forge
    pp.cmd_paint(cfg, "g", Args(), client=StandIn(), use_lock=False)
    dest = tmp / "out" / "pictures" / "g" / "portraits_painted"
    before = (dest / "hero.png").read_bytes()
    assert pp.set_pick(cfg, "g", "hero", "picture__2002") == dest / "hero.png"
    assert (dest / "hero.png").read_bytes() != before and json.loads((dest / "hero.json").read_text())["proposed"] == "picture__2002"
    assert Image.open(dest / "384" / "hero.png").size == (384, 384)
    with pytest.raises(pp.PaintError, match="hero has no painted candidate called sideways__1: it has both__1001"):
        pp.set_pick(cfg, "g", "hero", "sideways__1")
    with pytest.raises(pp.PaintError, match="nothing is painted for that name yet"):
        pp.set_pick(cfg, "g", "later", "over__1001")


def test_the_command_line_says_things_plainly(forge, monkeypatch, capsys):
    cfg, tmp = forge
    monkeypatch.setattr(pp.cfgmod, "load", lambda: cfg)
    monkeypatch.setattr(pp.cfgmod, "ensure_dirs", lambda c: None)
    pp.cmd_paint(cfg, "g", Args(), client=StandIn(), use_lock=False)
    assert pp.main(["pick", "hero", "over", "1001", "--game", "g"]) == 0                # three words or two: over 1001 / over__1001
    assert json.loads((tmp / "out" / "pictures" / "g" / "portraits_painted" / "hero.json").read_text())["proposed"] == "over__1001"
    assert pp.main(["pick", "hero", "--game", "g"]) == 2 and "pick <name> <way> <seed>" in capsys.readouterr().out
    assert pp.main(["sheet", "--game", "g"]) == 0 and "portraits_painted_sheet.png" in capsys.readouterr().out
    (tmp / "games" / "g" / "pictures" / "portraits.json").unlink()
    assert pp.main(["sheet", "--game", "g"]) == 2 and "this game has no" in capsys.readouterr().out


def test_comfyui_down_queues_nothing_and_says_so(forge):
    cfg, tmp = forge
    st = StandIn()
    st.up = False
    with pytest.raises(pp.PaintError, match="ComfyUI is not answering .* Nothing was queued"):
        pp.cmd_paint(cfg, "g", Args(), client=st, use_lock=False)
    assert not list((tmp / "jobs").rglob("*.json")) and not st.graphs


def test_a_batch_takes_the_card_once_and_gives_it_back(forge, monkeypatch):
    from forge.threed import cardlock, comfyapi
    cfg, tmp = forge
    monkeypatch.setattr(comfyapi, "is_up", lambda *a, **k: False)                  # no rigging ComfyUI on a test machine
    st, seen = StandIn(), []
    st.during = lambda: seen.append(cardlock.state(cfg))
    states, bad = pp.cmd_paint(cfg, "g", Args(), client=st, use_lock=True)
    assert bad == 0 and len(seen) == 8 and all(s["held"] and s["holder"] == "painted portraits" for s in seen)
    assert len({s["since"] for s in seen}) == 1                                    # one hold for the whole batch, not one a picture
    assert cardlock.state(cfg)["held"] is False


# ------------------------------------------------------------------ the plug-in, the docs, no game named
def test_the_job_type_is_a_plug_in_and_a_gpu_job():
    from forge import schema
    from forge.plugins import portraitpaint as plug
    assert sorted(plug.HANDLERS) == sorted(plug.JOB_TYPES) == ["portrait_paint"]
    assert schema.validate({"type": "portrait_paint", "portrait": "a.png"}) == [] and schema.validate({"type": "portrait_paint"}) != []
    assert schema.needs_gpu({"type": "portrait_paint", "portrait": "a.png"})        # the world queue steps aside for it
    doc = (cfgmod.ROOT / "docs" / "JOB_TYPES.md").read_text(encoding="utf-8")
    assert "## `portrait_paint`  (GPU)" in doc


def test_the_painting_code_names_no_game():
    words = re.compile(r"turing|linden|sarah|valkyrie|chloe|minerva|\bbill(_|\b)", re.I)
    root = Path(pp.__file__).resolve().parent
    for p in (root / "portraitpaint.py", root / "portraitpaint_specs.py", root.parent / "plugins" / "portraitpaint.py",
              cfgmod.ROOT / "docs" / "PAINTED_PORTRAITS.md", cfgmod.ROOT / "portraits_painted.bat"):
        assert p.is_file(), p
        assert not words.search(p.read_text(encoding="utf-8")), p.name
