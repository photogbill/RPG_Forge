"""A stand-in for Blender's Python in the tests: run as  <python> fake_blender.py <forge blender script> <its arguments>.
It writes what the real script would write (a small .glb, the motion sheet, the TIDY line), so the line can be tested
without Blender. A word in the arguments plants a failure: PLANT_BLENDER_FAIL."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from forge.threed import glb  # noqa: E402

script, args = Path(sys.argv[1]).name, sys.argv[2:]
if any("PLANT_BLENDER_FAIL" in a for a in args):
    print("Traceback (most recent call last):\nRuntimeError: a planted failure", flush=True)
    sys.exit(1)


def opt(flag, default=None):
    return args[args.index(flag) + 1] if flag in args else default


if script == "fit_motions.py":
    lib, body, out = args[0], args[1], args[2]
    skip = [s for s in (opt("--skip", "") or "").split(",") if s]
    names = [m for m in ["Idle_Loop", "Walk_Loop", "Jog_Fwd_Loop", "Sprint_Loop", "Dance_Loop", "Jump_Start"] if m not in skip]
    glb.box(out, (0.5, float(opt("--height", 1.72)), 0.3), motions=names, joints=4)
    sheet = {"body": Path(body).name, "library": Path(lib).name, "height_m": float(opt("--height", 1.72)), "stride_scale": 1.0,
             "left_out": skip, "motions": {n: {"seconds": 1.0, "loop": n.endswith("_Loop"),
                                               **({"speed": {"Walk_Loop": 0.98, "Jog_Fwd_Loop": 5.37, "Sprint_Loop": 8.27}[n]}
                                                  if n in ("Walk_Loop", "Jog_Fwd_Loop", "Sprint_Loop") and opt("--travel") else {})}
                                           for n in names}}
    Path(out).with_suffix(".json").write_text(json.dumps(sheet), encoding="utf-8")
    print(f"FITTED {len(names)} motions in 0 s", flush=True)
    print(f"STANDS feet at 0.000 m, top at {float(opt('--height', 1.72)):.3f} m", flush=True)
elif script == "tidy_model.py":
    src, dst = args[0], args[1]
    i = glb.info(src)["size_m"]
    size = (i["width"], i["height"], i["depth"])
    for flag, axis in (("--height", 1), ("--width", 0), ("--depth", 2)):
        if opt(flag):
            k = float(opt(flag)) / max(size[axis], 1e-9)
            size = tuple(v * k for v in size)
            break
    glb.box(dst, size)
    print("TIDY " + json.dumps({"in": src, "out": dst, "pieces_before": 3, "pieces_after": 1, "removed_vertices": 12,
                                "welded": 100, "size_after_m": {"width": size[0], "height": size[1], "depth": size[2]}}), flush=True)
elif script == "grow_tree.py":
    out = Path(args[0])
    out.mkdir(parents=True, exist_ok=True)
    name = opt("--name", "linden")
    tag = f"{name}_seed{int(opt('--seed', 11))}" + ("_bare" if "--bare" in args else "")
    glb.box(out / f"{tag}.glb", (6, 12, 6))
    from forge.threed.standin import png
    for k in range(int(opt("--views", 1))):
        (out / f"{tag}_{k}.png").write_bytes(png())
    print("TREE", tag, {"nodes": 1}, flush=True)
    print("DONE", tag, flush=True)
elif script == "build_stage.py":                     # BUILD 34: a place's plan-built solids
    plan = json.loads(Path(opt("--plan")).read_text(encoding="utf-8"))
    sx, sy = (plan.get("size") or [10, 10])
    glb.box(opt("--out"), (float(sx), 3.0, float(sy)))
    print("STAGE " + json.dumps({"faces": 12 * len(plan.get("solids") or []), "meshes": 1, "solids": len(plan.get("solids") or []),
                                 "out": opt("--out")}), flush=True)
elif script == "join_head.py":                       # BUILD 39: a head joined onto a shared body
    body, head, out = args[0], args[1], args[2]
    h = glb.info(body)["size_m"]["height"] or 1.75
    glb.box(out, (0.5, h * 0.98, 0.3))
    print("JOINED " + json.dumps({"collar_m": round(h * 0.86, 4), "collar_share": 0.86, "body_neck_m": 0.12, "head_neck_m": 0.14,
                                  "head_scale": 0.857, "height_before_m": h, "height_after_m": round(h * 0.98, 4), "materials": 2,
                                  "vertices": 8}), flush=True)
elif script == "cloth_pin.py":          # BUILD 73: the cape pinned to a body
    body, cloth, out = args[0], args[1], args[2]
    if "NOSKELETON" in body:
        print('CLOTH {"error": "RuntimeError: the body has no skeleton"}', flush=True)
        sys.exit(0)
    import shutil
    shutil.copyfile(body, out)
    print("CLOTH " + json.dumps({"mesh": opt("--name", "cloth"), "pinned": 120, "free": 880,
                                 "pin_bones": ["clavicle_l", "clavicle_r", "neck_01"], "spine": "spine_03",
                                 "size_m": {"width": 0.6, "height": 0.9}}), flush=True)
else:
    print(f"fake_blender: no stand-in for {script}", flush=True)
    sys.exit(2)
