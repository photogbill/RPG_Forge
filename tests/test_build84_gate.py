"""BUILD 84 part 2 (first step) — the picture gate's pose band is what the skeleton step needs, measured: arms from 14 to
90 degrees out of the body's line, not 32 to 76. And the bodies the old band held go back in line with the try that
passes now — nothing painted again. No graphics card: the stand-in paints the figures.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

from PIL import Image

from forge.threed import gate, standin, world


def fig(**kw) -> Image.Image:
    im = Image.open(io.BytesIO(standin.png(**kw)))
    im.load()
    return im


def _cfg(tmp_path, entries, gid="g1"):
    d = tmp_path / "games" / gid / "wanted_3d"
    d.mkdir(parents=True, exist_ok=True)
    (d / "list.json").write_text(json.dumps({"entries": entries}), encoding="utf-8")
    return {"_root": str(tmp_path), "threed": {"out_root": str(tmp_path / "out3d")},
            "paths": {"games": str(tmp_path / "games"), "out": str(tmp_path / "out"), "jobs": str(tmp_path / "jobs")},
            "allow_external_paths": True}


def test_the_pose_band_is_what_the_rig_needs():
    assert gate.settings(None)["a_pose_deg"] == [14.0, 90.0]
    words = {"prompt": "A woman of forty, a cardigan and slacks"}
    for d in (10, 17, 25, 45, 78):                       # measured 19-86 degrees: every one of them rigs (BUILD 84's count)
        assert gate.judge(fig(arm_deg=d), words)["ok"], d
    held = gate.judge(fig(arm_deg=5), words)              # arms against the body: still held
    assert not held["ok"] and any("no arm stands clear" in ln for ln in held["lines"])
    over = gate.judge(fig(arm_deg=88), words)             # above level is not an A-pose
    assert not over["ok"] and any("(14–90°)" in ln for ln in over["lines"])
    # a T-pose asked is still a T-pose: an A-pose drawn for one is held, as BUILD 40 had it
    assert not gate.judge(fig(arm_deg=45), {"prompt": "A soldier of thirty in a T-pose"})["ok"]


def _held_by_gate(tmp_path, cfg, eid, degs):
    out = world.item_dir(cfg, "g1", eid)
    (out / "pictures").mkdir(parents=True, exist_ok=True)
    tries = []
    for n, d in enumerate(degs, 1):
        p = out / "pictures" / f"{eid}__try{n}.png"
        fig(arm_deg=d).save(p)
        tries.append({"try": n, "seed": 1000 + n, "ok": False, "picture": p.name,
                      "lines": ["Picture gate — pose: the arms are at 20° (from the body's line); an A-pose (about 45°) was asked "
                                "(32–76°). Made again."]})
    fig(arm_deg=degs[-1]).save(out / "pictures" / f"{eid}.png")
    (out / "pictures" / f"{eid}.gate.json").write_text(json.dumps({"tries": tries, "ok": False, "held": True}), encoding="utf-8")
    world.write_state(cfg, "g1", eid, {"state": "held", "kind": "body", "tier": "crowd", "held_by": "picture gate", "tries": 1,
                                       "why": ["Picture gate: pose: the arms are at 20°"], "gate": {"tries": tries}})
    return out


def test_regate_sends_back_the_bodies_the_old_band_held_with_the_try_that_passes_now(tmp_path):
    cfg = _cfg(tmp_path, [{"id": "gun_clerk", "kind": "body", "words": "A man of fifty, a polo shirt.", "real_size_m": {"height": 1.8}},
                          {"id": "stiff", "kind": "body", "words": "A man of sixty.", "real_size_m": {"height": 1.8}},
                          {"id": "fine", "kind": "body", "words": "A woman of thirty.", "real_size_m": {"height": 1.7}}])
    out = _held_by_gate(tmp_path, cfg, "gun_clerk", [12, 14, 13])
    _held_by_gate(tmp_path, cfg, "stiff", [4, 5, 3])                 # arms against the body on every try
    world.write_state(cfg, "g1", "fine", {"state": "made", "kind": "body"})
    jobs_before = list((tmp_path / "jobs").rglob("*.json")) if (tmp_path / "jobs").exists() else []
    r = world.regate(cfg, "g1", None, "the forge")
    assert [d["id"] for d in r["passed"]] == ["gun_clerk"] and r["passed"][0]["try"] == 1, r
    st = world.read_state(cfg, "g1", "gun_clerk")
    assert st["state"] == "wanted" and not st.get("gate_override")            # the gate's own verdict, not an overrule
    rec = json.loads((out / "pictures" / "gun_clerk.gate.json").read_text())
    assert rec["held"] is False and rec["rejudged"]["try"] == 1
    assert (out / "pictures" / "gun_clerk.png").read_bytes() == (out / "pictures" / "gun_clerk__try1.png").read_bytes()
    assert world.read_state(cfg, "g1", "stiff")["state"] == "held"
    assert world.read_state(cfg, "g1", "fine")["state"] == "made"
    assert (list((tmp_path / "jobs").rglob("*.json")) if (tmp_path / "jobs").exists() else []) == jobs_before   # no job


def test_the_body_step_makes_a_regated_body_from_its_picture_without_painting_again(tmp_path):
    """bodies.run's gate step (1b) runs again only for a picture just painted or a record still held: a regated record is
    neither, so the picture that passed is the one the body is made from."""
    cfg = _cfg(tmp_path, [{"id": "rep", "kind": "body", "words": "A man of thirty-five.", "real_size_m": {"height": 1.8}}])
    out = _held_by_gate(tmp_path, cfg, "rep", [12])
    world.regate(cfg, "g1", ["rep"], "the forge")
    rec = json.loads((out / "pictures" / "rep.gate.json").read_text())
    target = out / "pictures" / "rep.png"
    made_pics: dict = {}
    again = target.exists() and ("rep" in made_pics or not (out / "pictures" / "rep.gate.json").exists() or rec.get("held"))
    assert not again


def test_world_fix_regate_is_on_the_command_line(tmp_path, monkeypatch, capsys):
    from forge import cli_approve
    cfg = _cfg(tmp_path, [{"id": "rep", "kind": "body", "words": "A man of thirty-five.", "real_size_m": {"height": 1.8}}])
    _held_by_gate(tmp_path, cfg, "rep", [12])
    assert cli_approve.cmd_world_fix(cfg, ["regate", "--game", "g1"]) == 0
    assert "1 pass the picture gate" in capsys.readouterr().out
    assert world.read_state(cfg, "g1", "rep")["state"] == "wanted"
    assert "world-fix regate" in (Path(cli_approve.__file__)).read_text(encoding="utf-8")


# ------------------------------------------------------------------------------------------------ 2e: hair and hats are not head
def _figure(kind="plain", head=0.125, size=512):
    """A drawn figure: clothes, a skin-coloured face and neck, short dark hair — or an afro, a high bun, a wide-brimmed hat
    of a straw colour close to the skin's — with `head` the skull's height (chin to crown) over the figure's."""
    import math
    from PIL import ImageDraw
    skin, cloth, hair, bg = (206, 160, 134), (70, 90, 120), (40, 30, 26), (226, 226, 230)
    im = Image.new("RGB", (size, size), bg)
    d = ImageDraw.Draw(im)
    top, H, cx = 26, 460, size // 2
    hh = head * H
    crown = top + {"bun": 0.06, "hat": 0.05, "afro": 0.06}.get(kind, 0.0) * H
    chin = crown + hh
    sh = chin + 0.045 * H
    hip = sh + 0.33 * H
    if kind == "afro":
        r = 0.11 * H
        cy = crown - 0.06 * H + r
        d.ellipse([cx - r, cy - r, cx + r, cy + r * 0.85], fill=hair)
    if kind == "bun":
        d.ellipse([cx - 0.035 * H, crown - 0.06 * H, cx + 0.035 * H, crown + 0.01 * H], fill=hair)
    hw = 0.38 * hh
    d.ellipse([cx - hw, crown, cx + hw, chin], fill=hair)
    hairline = crown + 0.3 * hh
    d.ellipse([cx - hw * 0.92, hairline - 0.25 * hh, cx + hw * 0.92, chin], fill=skin)
    d.rectangle([cx - hw, crown, cx + hw, hairline - 0.05 * hh], fill=hair)
    d.rectangle([cx - 0.024 * H, chin - 0.05 * hh, cx + 0.024 * H, sh + 3], fill=skin)
    if kind == "hat":
        d.ellipse([cx - 0.13 * H, hairline - 0.03 * H, cx + 0.13 * H, hairline + 0.01 * H], fill=(200, 170, 138))
        d.rectangle([cx - hw * 0.9, crown - 0.05 * H, cx + hw * 0.9, hairline - 0.01 * H], fill=(200, 170, 138))
    d.polygon([(cx - 0.105 * H, sh), (cx + 0.105 * H, sh), (cx + 0.08 * H, hip + 0.03 * H), (cx - 0.08 * H, hip + 0.03 * H)], fill=cloth)
    a = math.radians(45)
    for s in (-1, 1):
        p0 = (cx + s * 0.10 * H, sh + 0.02 * H)
        p1 = (p0[0] + s * 0.31 * H * math.sin(a), p0[1] + 0.31 * H * math.cos(a))
        d.line([p0, p1], fill=cloth, width=int(0.05 * H))
        d.ellipse([p1[0] - 0.025 * H, p1[1] - 0.025 * H, p1[0] + 0.025 * H, p1[1] + 0.025 * H], fill=skin)
        d.line([(cx + s * 0.05 * H, hip), (cx + s * 0.065 * H, top + H - 0.02 * H)], fill=cloth, width=int(0.08 * H))
    return im


def test_hair_and_hats_are_not_counted_as_head_but_a_cartoon_head_is_still_held():
    words = {"prompt": "A woman of thirty"}
    for kind in ("afro", "hat", "bun"):
        j = gate.judge(_figure(kind), words)
        assert j["ok"], (kind, j["lines"])
        assert j["measures"]["head_ratio"] > 0.165                                    # the outline alone would have held it
        assert any("hair and hats are not counted" in ln for ln in j["lines"]), kind
    plain = gate.judge(_figure("plain"), words)
    assert plain["ok"] and any("right for an adult" in ln for ln in plain["lines"])
    cartoon = gate.judge(_figure("plain", head=0.22), words)                         # all face: held, as it should be
    assert not cartoon["ok"] and any("cartoon proportions" in ln for ln in cartoon["lines"])
    assert gate.settings(None)["face_head"] == 0.65


def test_a_seated_figure_is_not_measured_against_its_seated_height():
    j = gate.judge(_figure("plain", head=0.2), {"prompt": "A woman of thirty-four. She sits upright on a plain wooden chair."})
    assert any("seated" in ln and "proportions" in ln for ln in j["lines"])
    assert not any("cartoon" in ln for ln in j["lines"])
