"""BUILD 04 — Sprite intake and Characters in the suite: a sheet goes in by dropping it, its figures are clicked
into facings (the mapping file is written for the person, checked, kept, signed), the game sheet comes out through the
same sprite_intake job the .bat runs; the registry as pages, its few edits, the face sheet, make the set.

Everything on a throwaway copy of games/_example with synthetic sheets (tests/n4_fixtures.py) — no real art."""
from __future__ import annotations
import base64, io, json, shutil, threading, urllib.error, urllib.request
from pathlib import Path

import pytest
from PIL import Image

from forge import config as cfgmod
from forge.suite import cast, games, journal, settings, sprites
import n4_fixtures as fx

REPO = Path(__file__).resolve().parents[1]
CW, CH = 144, 216


@pytest.fixture
def world(tmp_path, monkeypatch):
    gdir = tmp_path / "games"
    shutil.copytree(REPO / "games" / "_example", gdir / "_example",
                    ignore=shutil.ignore_patterns("journal", "proposals", "_workbench_*", "WORKBENCH_LOG.md", "__pycache__",
                                                  "intake", "batches"))
    cfg = cfgmod.load()
    cfg["allow_external_paths"] = True
    cfg["paths"] = dict(cfg["paths"], games=str(gdir), jobs=str(tmp_path / "jobs"), out=str(tmp_path / "out"),
                        logs=str(tmp_path / "logs"))
    cfg["incoming_dir"] = str(tmp_path / "_incoming")
    for s in ("pending", "running", "done", "failed", "paused"):
        (tmp_path / "jobs" / s).mkdir(parents=True)
    (tmp_path / "out").mkdir()
    (tmp_path / "logs").mkdir()
    monkeypatch.setattr(settings, "PATH", tmp_path / "local" / "suite.json")
    monkeypatch.setattr(sprites, "REGISTER_ROOT", tmp_path / "reg")
    (tmp_path / "reg" / "models").mkdir(parents=True)
    monkeypatch.delenv("FORGE_IDENTITY", raising=False)
    monkeypatch.delenv("FORGE_GAME_ROOTS", raising=False)
    games._loaded.clear()
    cast._done_cache.clear()
    # a character with two variants, asymmetric, look blocks placeholders — like a real cast member
    chdir = gdir / "_example" / "characters"
    (chdir / "miller.json").write_text(json.dumps({
        "id": "miller", "name": "The Miller", "asymmetric": True, "_asymmetric_why": "a satchel on one hip",
        "default_variant": "work",
        "variants": {
            "work": {"describe": "apron on", "prompt": "{{char.miller.base}}, {{char.miller.work}}", "negative": "{{neg.miller}}",
                     "checkpoint": "ArtUniverseSDXL_v8.safetensors", "sampler": "dpmpp_2m", "steps": 28, "seed": 77,
                     "references": [], "wanted": {"field_sheet": "placeholder/npc_miller", "portrait_moods": ["neutral"]}},
            "feast": {"describe": "best coat", "prompt": "{{char.miller.base}}, {{char.miller.feast}}", "negative": None,
                      "checkpoint": "ArtUniverseSDXL_v8.safetensors", "seed": None, "references": [], "wanted": {}}}},
        indent=1), encoding="utf-8")
    (gdir / "_example" / "prompts" / "library.json").write_text(json.dumps({"blocks": {
        "style.house": "TODO your house style words", "char.miller.base": "TODO Fable's words",
        "char.miller.work": "an apron dusted with flour"}}, indent=1), encoding="utf-8")
    return cfg, tmp_path


def _png(img: Image.Image) -> bytes:
    b = io.BytesIO()
    img.save(b, "PNG")
    return b.getvalue()


def _sign_in():
    settings.set_identity("Bill")


def _click_all(view: dict, facings: list[str | None]) -> list[dict]:
    """What the page sends after the person has clicked each figure: n → facing (None = leave it out)."""
    return [{"n": f["n"], "facing": fc, "skip": fc is None} for f, fc in zip(view["figures"], facings)]


# ---------------------------------------------------------------- taking a sheet in
def test_a_dropped_sheet_is_kept_never_overwritten_and_only_pictures_pass(world):
    cfg, tmp = world
    data = _png(fx.clean_grid())
    p1 = sprites.save_upload(cfg, "_example", "miller", "work", "My Sheet (final).png", data)
    assert p1.parent == tmp / "games" / "_example" / "intake" / "miller__work" and p1.name == "My_Sheet_final.png"
    assert sprites.save_upload(cfg, "_example", "miller", "work", "My Sheet (final).png", data) == p1      # same bytes
    p2 = sprites.save_upload(cfg, "_example", "miller", "work", "My Sheet (final).png", _png(fx.labelled()))
    assert p2.name == "My_Sheet_final_2.png" and p1.read_bytes() == data
    with pytest.raises(sprites.IntakeRefused, match="not a picture"):
        sprites.save_upload(cfg, "_example", "miller", "work", "notes.png", b"hello there")
    with pytest.raises(sprites.IntakeRefused, match="whose sheet"):
        sprites.save_upload(cfg, "_example", "", None, "x.png", data)
    outside = tmp / "elsewhere.png"
    outside.write_bytes(data)
    with pytest.raises(sprites.IntakeRefused, match="outside"):
        sprites.allowed_picture(cfg, "_example", outside)
    names = {c["name"] for c in sprites.candidates(cfg, "_example")}
    assert {"My_Sheet_final.png", "My_Sheet_final_2.png"} <= names


def test_opening_a_sheet_writes_the_forges_guess_unchecked(world):
    cfg, tmp = world
    p = sprites.save_upload(cfg, "_example", "miller", "work", "turn.png", _png(fx.labelled()))
    v = sprites.open_sheet(cfg, "_example", "miller", "work", p)
    assert v["ok"] and v["first"] and not v["checked"] and v["found"] == 4
    assert v["labels"], "the printed words are found and drawn as labels, not figures"
    mp = Path(v["mapping"])
    assert mp == tmp / "games" / "_example" / "intake" / "miller__work" / "turn.intake.json"
    m = json.loads(mp.read_text(encoding="utf-8"))
    assert m["checked_by_person"] is False and m["made_by"].startswith("the forge's first guess")
    assert v["char"]["asymmetric"] is True and "satchel" in v["char"]["why"]
    again = sprites.open_sheet(cfg, "_example", "miller", "work", p)
    assert not again["first"] and again["rev"] == v["rev"]                   # opening again changes nothing


def test_clicks_become_the_mapping_checked_kept_and_signed(world):
    cfg, tmp = world
    _sign_in()
    p = sprites.save_upload(cfg, "_example", "miller", "work", "grid.png", _png(fx.clean_grid()))
    v = sprites.open_sheet(cfg, "_example", "miller", "work", p)
    with pytest.raises(sprites.IntakeRefused, match="who you are"):
        sprites.save_mapping(cfg, "_example", v["mapping"], v["rev"], [], [], None)
    clicks = _click_all(v, ["S", "SW", "W", "NW", "N", "N", None, "SE"])     # two figures face N, one left out
    r = sprites.save_mapping(cfg, "_example", v["mapping"], v["rev"], clicks, [], "Bill")
    assert r["ok"], r
    m = json.loads(Path(v["mapping"]).read_text(encoding="utf-8"))
    f = {e["n"]: e for e in m["figures"]}
    assert (f[5]["facing"], f[5]["frame"]) == ("N", 0) and (f[6]["facing"], f[6]["frame"]) == ("N", 1)
    assert f[7].get("skip") is True and f[7]["facing"] is None
    assert m["checked_by_person"] is True and m["checked_by"] == "Bill" and m["checked_at"]
    # a stale page is refused, not written over
    stale = sprites.save_mapping(cfg, "_example", v["mapping"], v["rev"], clicks, [], "Bill")
    assert stale["ok"] is False and stale["conflict"]
    r2 = sprites.save_mapping(cfg, "_example", v["mapping"], r["rev"], _click_all(v, ["S", "SW", "W", "NW", "N", "NE", "E", "SE"]), [], "Bill")
    assert r2["ok"]
    hist = list((Path(v["mapping"]).parent / "_history").glob("grid.*.intake.json"))
    assert len(hist) == 2, "every earlier version is kept"
    root = games.game_root(cfg, "_example")
    lines = [e for e in journal.read(root) if e["kind"] == "art"]
    assert lines and lines[-1]["who"] == "Bill" and "6 NE" in lines[-1]["after"] and "6 N·1" in lines[-1]["before"]
    with pytest.raises(sprites.IntakeRefused, match="not a facing"):
        sprites.save_mapping(cfg, "_example", v["mapping"], None, [{"n": 1, "facing": "UP"}], [], "Bill")
    with pytest.raises(sprites.IntakeRefused, match="no figure 99"):
        sprites.save_mapping(cfg, "_example", v["mapping"], None, [{"n": 99, "facing": "S"}], [], "Bill")
    with pytest.raises(sprites.IntakeRefused, match="not a mapping file"):
        sprites.save_mapping(cfg, "_example", tmp / "x.json", None, [], [], "Bill")


def test_an_asymmetric_character_is_not_flipped_without_a_second_yes(world):
    cfg, _ = world
    _sign_in()
    p = sprites.save_upload(cfg, "_example", "miller", "work", "three.png", _png(fx.white_backdrop()))
    v = sprites.open_sheet(cfg, "_example", "miller", "work", p)
    clicks = _click_all(v, ["S", "W", "N"])
    r = sprites.save_mapping(cfg, "_example", v["mapping"], v["rev"], clicks, ["W→E"], "Bill")
    assert r["ok"] is False and r["asymmetric"] and "satchel" in r["message"]
    assert json.loads(Path(v["mapping"]).read_text(encoding="utf-8"))["checked_by_person"] is False
    r = sprites.save_mapping(cfg, "_example", v["mapping"], v["rev"], clicks, ["W→E"], "Bill", mirror_anyway=True)
    assert r["ok"] and r["mirror"] == ["W→E"]
    r = sprites.save_mapping(cfg, "_example", v["mapping"], r["rev"], _click_all(v, ["S", "W", "E"]), ["W→E"], "Bill")
    assert r["ok"] and r["mirror"] == []                     # E has its own figure now: nothing to fill, nothing to warn
    with pytest.raises(sprites.IntakeRefused, match="opposite"):
        sprites.save_mapping(cfg, "_example", v["mapping"], None, clicks, ["W→N"], "Bill")
    with pytest.raises(sprites.IntakeRefused, match="no figure faces"):
        sprites.save_mapping(cfg, "_example", v["mapping"], None, clicks, ["NW→NE"], "Bill")


def test_the_game_sheet_comes_out_of_the_clicks(world):
    cfg, tmp = world
    _sign_in()
    p = sprites.save_upload(cfg, "_example", "miller", "work", "grid.png", _png(fx.clean_grid()))
    v = sprites.open_sheet(cfg, "_example", "miller", "work", p)
    with pytest.raises(sprites.IntakeRefused, match="still the forge's guess"):
        sprites.make_sheet(cfg, "_example", v["mapping"], "Bill")
    order = ["S", "SW", "W", "NW", "N", "NE", "E", "SE"]
    assert sprites.save_mapping(cfg, "_example", v["mapping"], v["rev"], _click_all(v, order), [], "Bill")["ok"]
    r = sprites.make_sheet(cfg, "_example", v["mapping"], "Bill")
    assert r["ok"], r
    res = r["result"]
    o = tmp / "out" / res["job"]
    sheet = Image.open(o / "sheet.png")
    assert sheet.size == (8 * CW, CH) and sheet.mode == "RGBA"
    assert (o / "turntable.gif").exists() and (o / "edges.md").exists() and res["missing"] == []
    assert (tmp / "jobs" / "done" / f"{res['job']}.json").exists()
    job = json.loads((tmp / "jobs" / "done" / f"{res['job']}.json").read_text(encoding="utf-8"))
    assert job["mapping"] == v["mapping"] and job["ran"] == "inline" and job["character"] == "miller"
    # every cell holds a figure standing on the same baseline
    a = sheet.getchannel("A")
    for i in range(8):
        cell = a.crop((i * CW, 0, (i + 1) * CW, CH))
        assert cell.getbbox() is not None and abs(cell.getbbox()[3] - (CH - 6)) <= 1
    again = sprites.open_sheet(cfg, "_example", "miller", "work", p)
    assert again["results"] and again["results"][0]["job"] == res["job"]
    notes = [e.get("note", "") for e in journal.read(games.game_root(cfg, "_example")) if e["kind"] == "art"]
    assert any("made the game sheet — 8 of 8 facings" in n for n in notes)


@pytest.mark.parametrize("make,facings", [
    (fx.clean_grid, ["S", "SW", "W", "NW", "N", "NE", "E", "SE"]),
    (fx.ragged_grid, ["S"] * 3 + ["W"] * 3 + ["E"] * 3 + ["N"] * 3),
    (fx.labelled, ["S", "W", "N", "E"]),
    (fx.white_backdrop, ["S", "W", "N"]),
    (fx.painted_checker, ["S", "SW", "W", "NW", "N"]),
])
def test_five_synthetic_sheets_go_through_the_screen(world, make, facings):
    """The five F1 sheets (clean grid, ragged grid, labels, white backdrop, painted checkerboard) — dropped, clicked,
    made — each ends in the game's contract."""
    cfg, tmp = world
    _sign_in()
    p = sprites.save_upload(cfg, "_example", "hero", None, f"{make.__name__}.png", _png(make()))
    v = sprites.open_sheet(cfg, "_example", "hero", None, p)
    assert v["found"] == len(facings), (make.__name__, v["found"])
    r = sprites.save_mapping(cfg, "_example", v["mapping"], v["rev"], _click_all(v, facings), [], "Bill")
    assert r["ok"], r
    out = sprites.make_sheet(cfg, "_example", v["mapping"], "Bill")
    assert out["ok"], out
    res = out["result"]
    sheet = Image.open(tmp / "out" / res["job"] / "sheet.png")
    assert sheet.size == (8 * CW, CH)
    assert sorted(set(facings)) == sorted(set("S SW W NW N NE E SE".split()) - set(res["missing"]))
    if len(facings) > len(set(facings)):
        assert res["anim"] and res["anims"], "more than one frame per facing → anim.png and a GIF per facing"


def test_the_program_that_made_the_sheet_goes_through_the_tool_register(world):
    cfg, tmp = world
    _sign_in()
    with pytest.raises(sprites.IntakeRefused, match="yes or no"):
        sprites.add_tool(cfg, "_example", "Paintbox", "2", "maybe", "", "", "Bill")
    r = sprites.add_tool(cfg, "_example", "Paintbox", "2", "yes", "under a revenue cap", "its terms page, today", "Bill")
    assert r["ok"] and r["key"] == "Paintbox 2"
    t = sprites.tools(cfg, "_example")
    assert t["last"] == "Paintbox 2" and t["tools"][0]["commercial_ok"] is True
    reg = json.loads((tmp / "reg" / "models" / "licences.json").read_text(encoding="utf-8"))
    assert reg["Paintbox 2"]["kind"] == "outside tool" and reg["Paintbox 2"]["licence_condition"] == "under a revenue cap"
    p = sprites.save_upload(cfg, "_example", "hero", None, "s.png", _png(fx.labelled()))
    v = sprites.open_sheet(cfg, "_example", "hero", None, p, tool="Paintbox 2")
    assert v["tool"] == "Paintbox 2"
    sprites.save_mapping(cfg, "_example", v["mapping"], v["rev"], _click_all(v, ["S", "W", "N", "E"]), [], "Bill")
    res = sprites.make_sheet(cfg, "_example", v["mapping"], "Bill")["result"]
    job = json.loads((tmp / "jobs" / "done" / f"{res['job']}.json").read_text(encoding="utf-8"))
    assert job["tool"] == "Paintbox 2"


def test_a_sheet_that_changed_is_flagged_and_can_start_again(world):
    cfg, _ = world
    _sign_in()
    p = sprites.save_upload(cfg, "_example", "hero", None, "s.png", _png(fx.labelled()))
    v = sprites.open_sheet(cfg, "_example", "hero", None, p)
    p.write_bytes(_png(fx.white_backdrop()))                                   # the artist re-exported it
    again = sprites.open_sheet(cfg, "_example", "hero", None, p)
    assert again["sheet_changed"] and again["found"] == 3
    fresh = sprites.open_sheet(cfg, "_example", "hero", None, p, fresh=True, who="Bill")
    assert not fresh["sheet_changed"] and len(fresh["figures"]) == 3
    assert list((Path(v["mapping"]).parent / "_history").glob("s.*.intake.json"))


def _jpeg_sheet() -> bytes:
    """Three figures with an arm bent back to the hip (a gap of backdrop between arm and body) on white, saved as a
    JPEG — the gap's white is noisy, as on a real sheet from an image generator."""
    import numpy as np
    bg = Image.new("RGB", (900, 420), (255, 255, 255))
    im = fx.paste_all(bg, [fx.figure(360, fx.COLOURS[i], pocket=True, eye=False) for i in range(3)], [(60 + i * 280, 30) for i in range(3)])
    arr = np.asarray(im.convert("RGB")).astype(np.int32)
    arr = arr + np.random.default_rng(5).integers(-5, 6, arr.shape)                  # sensor-ish noise
    b = io.BytesIO()
    Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).save(b, "JPEG", quality=80)
    return b.getvalue()


def _white_inside(png: Path) -> int:
    """Opaque, near-white pixels in the packed sheet — a gap the cut kept."""
    import numpy as np
    a = np.asarray(Image.open(png).convert("RGBA")).astype(np.int32)
    return int(((a[..., 3] > 200) & (a[..., :3].min(axis=2) > 225)).sum())


def test_see_through_gaps_are_found_marked_and_cleared_on_a_jpeg_sheet(world):
    cfg, tmp = world
    _sign_in()
    data = _jpeg_sheet()
    p = sprites.save_upload(cfg, "_example", "hero", None, "gaps.jpg", data)
    v = sprites.open_sheet(cfg, "_example", "hero", None, p)
    assert v["found"] == 3 and len(v["pockets"]) == 3 and all(pk["hole"] for pk in v["pockets"]), v["pockets"]
    m = json.loads(Path(v["mapping"]).read_text(encoding="utf-8"))
    assert len(m["holes"]) == 3, "the forge's first guess marks them; the person keeps or clears each"
    # the person says: keep none of them (all cleared) — the sheet comes out with no white patch
    clicks = _click_all(v, ["S", "W", "N"])
    assert sprites.save_mapping(cfg, "_example", v["mapping"], v["rev"], clicks, [], "Bill",
                                holes=[pk["pt"] for pk in v["pockets"]])["ok"]
    res = sprites.make_sheet(cfg, "_example", v["mapping"], "Bill")["result"]
    assert res["holes"] == 3 and _white_inside(tmp / "out" / res["job"] / "sheet.png") < 40
    job = json.loads((tmp / "jobs" / "done" / f"{res['job']}.json").read_text(encoding="utf-8"))
    # wiring day W10: the intake clears the person's holes itself — the original sheet goes in, no _cut/ copy
    assert job["input"] == str(p.resolve()) and job["mapping"] == v["mapping"] and job["holes"] == 3
    assert not (Path(v["mapping"]).parent / "_cut").exists()
    assert p.read_bytes() == data, "the original sheet is never changed"
    assert not any("sheet changed" in w for w in res["warnings"])
    # the same sheet with every gap kept as figure: the white stays — what the intake alone would make
    r = sprites.open_sheet(cfg, "_example", "hero", None, p)
    assert sprites.save_mapping(cfg, "_example", v["mapping"], r["rev"], clicks, [], "Bill", holes=[])["ok"]
    res2 = sprites.make_sheet(cfg, "_example", v["mapping"], "Bill")["result"]
    assert res2["holes"] == 0 and _white_inside(tmp / "out" / res2["job"] / "sheet.png") > 400
    assert [x["job"] for x in sprites.open_sheet(cfg, "_example", "hero", None, p)["results"][:2]] == [res2["job"], res["job"]]
    with pytest.raises(sprites.IntakeRefused, match="outside the sheet"):
        sprites.save_mapping(cfg, "_example", v["mapping"], None, clicks, [], "Bill", holes=[[5000, 5]])


def test_an_eye_and_a_glow_are_not_taken_for_gaps(world):
    """The white of an eye inside a head is small and the intake keeps it; it is not offered as a gap."""
    cfg, _ = world
    p = sprites.save_upload(cfg, "_example", "hero", None, "eyes.png", _png(fx.white_backdrop()))
    v = sprites.open_sheet(cfg, "_example", "hero", None, p)
    for pk in v["pockets"]:
        x0, y0, x1, y1 = pk["bbox"]
        assert (y1 - y0) > 20, f"a pocket the size of an eye was offered: {pk}"


# ---------------------------------------------------------------- the registry as pages
def test_the_registry_pages_show_variants_seeds_and_block_states(world):
    cfg, _ = world
    rows = {r["id"]: r for r in cast.listing(cfg, "_example")}
    assert set(rows) >= {"hero", "miller"} and rows["miller"]["variants"] == ["work", "feast"]
    pg = cast.page(cfg, "_example", "miller")
    work = next(v for v in pg["variants"] if v["name"] == "work")
    states = {b["ref"]: b["state"] for b in work["blocks"] + work["neg_blocks"]}
    assert states == {"char.miller.base": "placeholder", "char.miller.work": "written", "neg.miller": "missing"}
    assert work["seed"] == 77 and work["asymmetric"] is True and work["default"]
    assert any("no locked seed" in p for p in pg["problems"])                  # feast has none
    assert any("placeholder" in p for p in pg["problems"])
    with pytest.raises(cast.CastRefused, match="no character"):
        cast.page(cfg, "_example", "nobody")


def test_registry_edits_keep_the_file_and_are_signed(world):
    cfg, tmp = world
    _sign_in()
    p = tmp / "games" / "_example" / "characters" / "miller.json"
    raw = p.read_text(encoding="utf-8")
    pg = cast.page(cfg, "_example", "miller")
    r = cast.edit(cfg, "_example", "miller", "feast", "seed", "4242", pg["rev"], "Bill")
    assert r["ok"] and r["changed"]
    new = p.read_text(encoding="utf-8")
    assert json.loads(new)["variants"]["feast"]["seed"] == 4242
    assert new.replace('"seed": 4242', '"seed": null') == raw, "only the seed's own bytes changed"
    assert cast.edit(cfg, "_example", "miller", "feast", "seed", "4242", None, "Bill")["changed"] is False
    stale = cast.edit(cfg, "_example", "miller", "feast", "seed", "1", pg["rev"], "Bill")
    assert stale["ok"] is False and stale["conflict"]
    with pytest.raises(cast.CastRefused, match="whole number"):
        cast.edit(cfg, "_example", "miller", "feast", "seed", "abc", None, "Bill")
    with pytest.raises(cast.CastRefused, match="prompt library"):
        cast.edit(cfg, "_example", "miller", "feast", "prompt", "pretty words", None, "Bill")
    with pytest.raises(cast.CastRefused, match="who you are"):
        cast.edit(cfg, "_example", "miller", "feast", "seed", "5", None, None)
    assert cast.edit(cfg, "_example", "miller", "feast", "asymmetric", False, None, "Bill")["ok"]
    ref = str(tmp / "ref.jpg")
    assert cast.edit(cfg, "_example", "miller", "work", "references", {"op": "add", "path": ref}, None, "Bill")["changed"]
    pg = cast.page(cfg, "_example", "miller")
    work = next(v for v in pg["variants"] if v["name"] == "work")
    assert work["references"][0]["path"] == ref and work["references"][0]["exists"] is False
    assert cast.edit(cfg, "_example", "miller", "work", "references", {"op": "remove", "path": ref}, None, "Bill")["changed"]
    assert len(list((p.parent / "_history").glob("miller.*.json"))) >= 1
    edits = [e for e in journal.read(games.game_root(cfg, "_example")) if e["kind"] == "edit"]
    assert edits[0]["obj"] == "character · miller/feast · seed" and edits[0].get("before") is None and edits[0]["after"] == 4242


def test_make_the_set_says_why_not_in_submits_own_words_then_queues(world):
    cfg, tmp = world
    _sign_in()
    plan = cast.plan_set(cfg, "_example", "miller", "work")
    assert plan["can_queue"] is False and "placeholder" in plan["message"]
    assert {b["ref"] for b in plan["blocks"]} == {"char.miller.base", "neg.miller"}
    assert cast.queue_set(cfg, "_example", "miller", "work", "Bill")["can_queue"] is False
    assert not list((tmp / "jobs" / "pending").glob("*.json"))
    # once the words are written (Fable's, in the library) the same button plans and queues
    lib = tmp / "games" / "_example" / "prompts" / "library.json"
    lib.write_text(json.dumps({"blocks": {"char.miller.base": "a broad-shouldered miller", "char.miller.work": "an apron",
                                          "neg.miller": "blurry", "pose.portrait": "head and shoulders",
                                          "pose.battle": "braced", "pose.turnaround": "turnaround sheet",
                                          "mood.neutral": "calm"}}), encoding="utf-8")
    plan = cast.plan_set(cfg, "_example", "miller", "work")
    assert plan["can_queue"], plan
    assert [r["part"] for r in plan["renders"]] == ["mood:neutral", "battle", "turnaround"] and plan["renders"][0]["seed"] == 77
    r = cast.queue_set(cfg, "_example", "miller", "work", "Bill")
    assert r["ok"], r["printed"]
    assert (tmp / "games" / "_example" / "batches" / "charset_miller_work.json").exists()
    pend = list((tmp / "jobs" / "pending").glob("*.json"))
    assert len(pend) == 1 and json.loads(pend[0].read_text(encoding="utf-8"))["renders"]
    assert "character job(s) resolved from the registry" in r["printed"]


def test_the_face_sheet_from_the_page(world):
    cfg, tmp = world
    _sign_in()
    r = cast.make_face_sheet(cfg, "_example", "miller", "Bill")
    assert r["ok"] is False and "Nothing to put on it yet" in r["message"]
    p = sprites.save_upload(cfg, "_example", "miller", "work", "grid.png", _png(fx.clean_grid()))
    v = sprites.open_sheet(cfg, "_example", "miller", "work", p)
    sprites.save_mapping(cfg, "_example", v["mapping"], v["rev"], _click_all(v, ["S", "SW", "W", "NW", "N", "NE", "E", "SE"]), [], "Bill")
    sprites.make_sheet(cfg, "_example", v["mapping"], "Bill")
    cast._done_cache.clear()
    r = cast.make_face_sheet(cfg, "_example", "miller", "Bill")
    assert r["ok"] and r["sheets"] and (tmp / "out" / "review" / "character_miller" / "sheet_01.jpg").exists()
    pg = cast.page(cfg, "_example", "miller")
    assert pg["face_sheets"] and pg["pictures"][0]["file"] == "sheet.png"


# ---------------------------------------------------------------- the app
@pytest.fixture
def app(world):
    from forge.suite import server
    cfg, tmp = world
    srv = server.make_server(cfg, 0)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield cfg, tmp, f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def _get(url):
    with urllib.request.urlopen(url, timeout=20) as r:
        return r.status, r.read(), r.headers.get("Content-Type")


def _post(url, body, header=True):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **({"X-Forge": "1"} if header else {})})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def test_the_screens_work_over_http_drop_click_make(app):
    cfg, tmp, base = app
    st, body, _ = _get(base + "/")
    assert b"Sprite intake" in body and b"Characters" in body
    up = {"game": "_example", "character": "miller", "variant": "work", "filename": "drop.png",
          "data": "data:image/png;base64," + base64.b64encode(_png(fx.clean_grid())).decode()}
    assert _post(base + "/api/suite/act/intake_upload", up)["ok"] is False          # nobody signed in yet
    _post(base + "/api/suite/act/identity", {"name": "Bill"})
    v = _post(base + "/api/suite/act/intake_upload", up)
    assert v["ok"] and v["found"] == 8, v
    lst = json.loads(_get(base + "/api/suite/intake?id=_example")[1])
    assert any(c["name"] == "drop.png" for c in lst["candidates"]) and {"hero", "miller"} <= {c["id"] for c in lst["characters"]}
    st, img, ctype = _get(base + "/suite/picture?id=_example&w=300&path=" + urllib.request.quote(v["sheet"]))
    assert st == 200 and ctype == "image/jpeg" and Image.open(io.BytesIO(img)).width == 300
    with pytest.raises(urllib.error.HTTPError) as e:
        _get(base + "/suite/picture?id=_example&path=" + urllib.request.quote(str(REPO / "README.md")))
    assert e.value.code == 404
    with pytest.raises(urllib.error.HTTPError) as e:
        _post(base + "/api/suite/act/intake_save", {"mapping": v["mapping"]}, header=False)
    assert e.value.code == 403
    s = _post(base + "/api/suite/act/intake_save", {"game": "_example", "mapping": v["mapping"], "rev": v["rev"],
              "figures": _click_all(v, ["S", "SW", "W", "NW", "N", "NE", "E", "SE"])})
    assert s["ok"], s
    m = _post(base + "/api/suite/act/intake_make", {"game": "_example", "mapping": v["mapping"]})
    assert m["ok"], m
    st, png, ctype = _get(base + m["result"]["sheet"])
    assert ctype == "image/png" and Image.open(io.BytesIO(png)).size == (8 * CW, CH)
    pg = json.loads(_get(base + "/api/suite/character?id=_example&cid=miller")[1])
    assert pg["name"] == "The Miller" and len(pg["variants"]) == 2
    plan = _post(base + "/api/suite/act/char_plan", {"game": "_example", "cid": "miller", "variant": "work"})
    assert plan["can_queue"] is False and "placeholder" in plan["message"]
    ed = _post(base + "/api/suite/act/char_edit", {"game": "_example", "cid": "miller", "variant": "feast", "field": "seed",
                                                   "value": "9", "rev": pg["rev"]})
    assert ed["ok"] and ed["changed"]


# ---------------------------------------------------------------- the real registry (William's PC only)
def test_sarahs_two_variants_are_in_the_registry():
    """Done-when: Sarah's Guardian and Warrior exist in the registry, holster (asymmetric) in both, each variant's look
    block a placeholder (the shared prefix is William's own words). Only where the game's art settings are present (git-ignored; a public clone skips this)."""
    cfg = cfgmod.load()
    gids = [g for g in games.game_ids(cfg) if (REPO / "games" / g / "characters" / "sarah.json").exists()]
    if not gids:
        pytest.skip("no game with that registry on this PC")
    pg = cast.page(cfg, gids[0], "sarah")
    vs = {v["name"]: v for v in pg["variants"]}
    assert {"guardian", "warrior"} <= set(vs)
    for n in ("guardian", "warrior"):
        v = vs[n]
        assert v["asymmetric"] is True and v["seed"] not in (None, -1)
        own = [b for b in v["blocks"] if b["ref"].endswith("." + n)]
        assert own and all(b["state"] == "placeholder" for b in own), "look words are Fable's to write"
    assert "loose" in vs["guardian"]["describe"] and "braid" in vs["warrior"]["describe"]
