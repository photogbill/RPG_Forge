"""Bake a looping flipbook (a sheet of frames) of chimney smoke, hot-tub steam or a fire, in Blender's own fluid
simulation (Mantaflow, built in: no add-on, so blender.run with no profile, --factory-startup).

BUILD 98 Part 6 (life): the court's chimney smoke, William's working fireplace and the hot tub's steam. Godot plays the
sheet on a camera-facing quad (a particle billboard); the game is a fixed camera, so a billboard reads as real smoke.

    blender --background --factory-startup --python flipbook_bake.py -- --out <folder> --kind smoke|steam|fire
            [--frames 64] [--grid 8] [--size 128] [--samples 24] [--res 56]

Writes into --out: <kind>_frames/0001.png …, <kind>_flipbook.png (grid × grid frames, transparent), <kind>_flipbook.json
(frames, grid, fps, frame size, how it was made, the licence: made by the forge, ours).
Claude Opus, 2026-11-21. Data and words are ours; Blender is GPL, what it renders is ours.
"""
import json
import math
import os
import sys
import time
from pathlib import Path

import bpy

KINDS = {
    # style for quick_smoke, density, colour, how fast it rises and thins, the domain's shape (x, y, z in metres)
    "smoke": {"style": "SMOKE", "density": 4.0, "colour": (0.42, 0.42, 0.44), "vort": 0.3, "dissolve": 40,
              "domain": (2.2, 1.6, 4.0), "emit_r": 0.12, "temp": 2.5, "fps": 15, "wind": 0.08,
              "why": "chimney smoke on a still, cool evening: a thin grey column that leans and thins"},
    "steam": {"style": "SMOKE", "density": 0.9, "colour": (0.92, 0.93, 0.95), "vort": 0.5, "dissolve": 10, "inflow": 0.45,
              "domain": (2.0, 2.0, 2.4), "emit_r": 0.6, "temp": 1.5, "fps": 15, "wind": 0.02,
              "why": "steam off a hot tub at night: low, white, quick to vanish"},
    "fire": {"style": "FIRE", "density": 1.5, "colour": (0.25, 0.22, 0.2), "vort": 0.25, "dissolve": 20,
             "domain": (1.2, 1.2, 1.8), "emit_r": 0.22, "temp": 3.0, "fps": 20, "wind": 0.0,
             "why": "a small wood fire (a firepit, the fireplace's flames): low flames and a little smoke"},
}


def args():
    # straight from Blender the script's own arguments follow "--"; through the forge's boot (blender.run) they are
    # sys.argv[1:] and the run folder is FORGE_RUN_DIR
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    o = {"out": os.environ.get("FORGE_RUN_DIR", "."), "kind": "smoke", "frames": 64, "grid": 8, "size": 128,
         "samples": 24, "res": 56}
    i = 0
    while i < len(a):
        k = a[i].lstrip("-")
        if k in o and i + 1 < len(a):
            o[k] = type(o[k])(a[i + 1]) if not isinstance(o[k], str) else a[i + 1]
            i += 2
        else:
            i += 1
    return o


def log(*m):
    print("[flipbook]", *m, flush=True)


def main():
    o = args()
    kind = o["kind"]
    K = KINDS[kind]
    out = Path(o["out"])
    out.mkdir(parents=True, exist_ok=True)
    frames, grid, size = int(o["frames"]), int(o["grid"]), int(o["size"])
    warm = 70                                      # frames before the loop starts: the column has risen
    t0 = time.time()

    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, warm + frames
    sc.render.fps = K["fps"]

    # the emitter
    ex = -K["domain"][0] * 0.2 if K["wind"] > 0.05 else 0.0     # upwind of centre, so a leaning column stays in frame
    bpy.ops.mesh.primitive_cylinder_add(radius=K["emit_r"], depth=0.1, location=(ex, 0, 0.15))
    em = bpy.context.active_object
    em.name = "emitter"
    em.hide_render = True                          # the flow object is not seen: only what it breathes out
    bpy.ops.object.select_all(action="DESELECT")
    em.select_set(True)
    bpy.context.view_layer.objects.active = em
    bpy.ops.object.quick_smoke(style=K["style"], show_flows=False)
    dom = next(ob for ob in bpy.data.objects if ob.name.startswith("Smoke Domain"))
    dx, dy, dz = K["domain"]
    dom.location = (0, 0, dz / 2)
    dom.dimensions = (dx, dy, dz)
    bpy.context.view_layer.update()
    ds = dom.modifiers["Fluid"].domain_settings
    ds.resolution_max = int(o["res"])
    ds.cache_directory = str(out / f"{kind}_cache")
    ds.cache_type = "ALL"
    ds.cache_frame_start, ds.cache_frame_end = 1, warm + frames
    ds.vorticity = K["vort"]
    if kind != "fire":                              # wisps: the noise pass adds detail finer than the grid
        ds.use_noise = True
        ds.noise_scale = 2
        ds.noise_strength = 1.2
    ds.use_dissolve_smoke = True
    ds.use_dissolve_smoke_log = True               # thins slowly then goes, as real smoke does
    ds.dissolve_speed = int(K["dissolve"])
    ds.alpha = 1.0
    ds.beta = 1.5
    # open borders: what rises leaves, it does not pile up at the lid
    for attr in ("use_collision_border_top", "use_collision_border_front", "use_collision_border_back",
                 "use_collision_border_left", "use_collision_border_right"):
        if hasattr(ds, attr):
            setattr(ds, attr, False)
    fs = em.modifiers["Fluid"].flow_settings
    fs.density = K.get("inflow", 1.0)
    fs.temperature = K["temp"]
    fs.smoke_color = K["colour"]
    if kind == "fire":
        fs.flow_type = "BOTH"
        fs.fuel_amount = 1.2
    # a little wind so it leans and wavers, not a perfect pillar
    bpy.ops.object.effector_add(type="TURBULENCE", location=(0, 0, dz * 0.6))
    tb = bpy.context.active_object
    tb.field.strength = {"smoke": 0.45, "steam": 0.3}.get(kind, 0.15)
    tb.field.size = 0.5
    bpy.ops.object.effector_add(type="WIND", location=(-dx, 0, dz * 0.5), rotation=(0, math.radians(90), 0))
    wd = bpy.context.active_object
    wd.field.strength = K["wind"]

    # the volume's look
    mat = dom.active_material
    nt = mat.node_tree
    pv = next((n for n in nt.nodes if n.type == "PRINCIPLED_VOLUME"), None)
    if pv:
        pv.inputs["Density"].default_value = K["density"]
        if kind != "fire":
            pv.inputs["Color"].default_value = (*K["colour"], 1.0)
            pv.inputs["Blackbody Intensity"].default_value = 0.0

    # bake
    log("baking", kind, "res", ds.resolution_max, "frames", sc.frame_end)
    bpy.ops.object.select_all(action="DESELECT")
    dom.select_set(True)
    bpy.context.view_layer.objects.active = dom
    with bpy.context.temp_override(active_object=dom, object=dom, scene=sc):
        bpy.ops.fluid.bake_all()
    log("baked in", round(time.time() - t0), "s")

    # camera: orthographic, side on, framing the domain
    cam_d = bpy.data.cameras.new("cam")
    cam_d.type = "ORTHO"
    cam_d.ortho_scale = max(dz, dx) * 1.02
    cam = bpy.data.objects.new("cam", cam_d)
    sc.collection.objects.link(cam)
    cam.location = (0, -10, dz / 2)
    cam.rotation_euler = (math.radians(90), 0, 0)
    sc.camera = cam
    # light: a soft evening key from the west and the sky
    ld = bpy.data.lights.new("sun", "SUN")
    ld.energy = 2.5
    ld.angle = math.radians(20)
    lo = bpy.data.objects.new("sun", ld)
    sc.collection.objects.link(lo)
    lo.rotation_euler = (math.radians(55), math.radians(-35), 0)
    world = bpy.data.worlds.new("w")
    if hasattr(world, "use_nodes") and not world.node_tree:
        world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.35, 0.38, 0.45, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.6
    sc.world = world

    r = sc.render
    r.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = int(o["samples"])
    sc.cycles.use_denoising = True
    r.film_transparent = True
    aspect = dx / dz
    r.resolution_y = size * 2 if dz > dx * 1.3 else size
    r.resolution_x = max(16, int(round(r.resolution_y * aspect / 2) * 2))
    r.resolution_percentage = 100
    r.image_settings.file_format = "PNG"
    r.image_settings.color_mode = "RGBA"
    fdir = out / f"{kind}_frames"
    fdir.mkdir(exist_ok=True)
    fw, fh = r.resolution_x, r.resolution_y
    paths = []
    for i in range(frames):
        sc.frame_set(warm + 1 + i)
        p = fdir / f"{i + 1:04d}.png"
        r.filepath = str(p)
        bpy.ops.render.render(write_still=True)
        paths.append(p)
        if i % 8 == 0:
            log("frame", i + 1, "of", frames, round(time.time() - t0), "s")

    # the sheet: grid × grid, first frame top-left; the last frames cross-fade into the first so it loops
    import numpy as np
    sheet = np.zeros((fh * grid, fw * grid, 4), np.float32)
    imgs = []
    for p in paths:
        im = bpy.data.images.load(str(p))
        a = np.array(im.pixels[:], np.float32).reshape(fh, fw, 4)[::-1]
        imgs.append(a)
        bpy.data.images.remove(im)
    # the domain's lid and floor are never seen: the top third fades out (the column thins into the evening) and the
    # emitter's lip at the bottom fades in, so a sheet has no hard edges for the billboard to show
    yy = np.linspace(0.0, 1.0, fh, dtype=np.float32)[:, None]          # 0 at the top row, 1 at the bottom
    top = np.clip(yy / 0.35, 0, 1) ** 1.5
    bot = np.clip((1.0 - yy) / 0.04, 0, 1)
    ramp = (top * bot)[..., None]
    imgs = [np.concatenate([a[..., :3], a[..., 3:4] * ramp], -1) for a in imgs]
    blend_n = max(1, frames // 6)
    for i in range(frames - blend_n, frames):                  # loop: fade the tail into the head
        w = (i - (frames - blend_n) + 1) / (blend_n + 1)
        imgs[i] = imgs[i] * (1 - w) + imgs[i - (frames - blend_n)] * w
    for i, a in enumerate(imgs[: grid * grid]):
        gy, gx = divmod(i, grid)
        sheet[gy * fh:(gy + 1) * fh, gx * fw:(gx + 1) * fw] = a
    out_img = bpy.data.images.new(f"{kind}_flipbook", fw * grid, fh * grid, alpha=True)
    out_img.pixels[:] = sheet[::-1].ravel()
    sp = out / f"{kind}_flipbook.png"
    out_img.filepath_raw = str(sp)
    out_img.file_format = "PNG"
    out_img.save()
    meta = {"kind": kind, "frames": min(frames, grid * grid), "grid": grid, "frame_px": [fw, fh], "fps": K["fps"],
            "loops": True, "what": K["why"], "domain_m": list(K["domain"]),
            "made": f"Blender {bpy.app.version_string} Mantaflow, res {ds.resolution_max}, Cycles {sc.cycles.samples} "
                    f"samples, transparent; forge/threed/blender/flipbook_bake.py",
            "licence": "made by the forge (ours): no outside asset", "seconds": round(time.time() - t0)}
    (out / f"{kind}_flipbook.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    log("done", sp, meta["seconds"], "s")


if __name__ == "__main__":
    main()
