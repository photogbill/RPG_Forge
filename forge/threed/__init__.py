"""The 3D workshop's methods: picture -> 3D body -> skeleton -> motions, and trees grown by rule (BUILD 36).

Game-neutral. A game's job lists, looks and characters stay in `games/<id>/`; nothing in this package names a game.

    env.py       the rigging ComfyUI (a second ComfyUI with its own Python, Blender inside) and every path it uses
    comfyapi.py  talking to a ComfyUI: send a request, wait, read its own words when it says no, find what it saved
    template.py  ComfyUI's own image-to-3D template (TRELLIS.2 / Pixal3D, MIT) turned into a request for the running ComfyUI
    cardlock.py  one lock on the graphics card that every 3D step honours, so two ComfyUIs never hold the card at once
    bodies.py    a list of things -> one picture each (FLUX.2 klein) -> one 3D model each; resumable, goes on past a failure
    rig.py       3D bodies -> skeletons with the rigging ComfyUI (people: Make-It-Animatable with fingers; animals: UniRig)
    motions.py   a motion library fitted to a rigged body, with a sheet of each motion's length, loop and ground speed
    trees.py     a tree grown from a species sheet and a seed (Blender), never guessed from a picture
    tidy.py      a model's loose scraps removed, welded, set to its real size in metres, stood on the floor (Blender)
    line.py      the whole line for a list, unattended, with one report (what cast_overnight.py did)
    rules.py     what was learned the hard way, as checks and plain warnings (A-pose, height in metres, long coats ...)
    glb.py       read a .glb without Blender: size, bounds, motions, skins - for the screens, the checks and the tests
    standin.py   a stand-in ComfyUI that answers like the real one and writes the files a real run would (tests, no card)
    install.py   install and check the rigging ComfyUI and its model files, everything on the forge's own drive

Where it writes: `out/3d/<batch>/` (pictures/, models/, rig/, moves/, trees/, REPORT.txt, run.log) — never into the
folders the per-game test scripts of 2026-11-12/13 used (`out/trellis`, `out/rig_test`, `out/cast`), which it reads.
"""
from __future__ import annotations

VERSION = "1"
