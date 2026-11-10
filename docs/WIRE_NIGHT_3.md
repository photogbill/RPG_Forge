# Wiring left from Night 3 — do these with an EMPTY queue (worker stopped, `jobs/pending` empty)

Night 3 built every new job type as a **plug-in** (`forge/plugins/*.py`) so nothing the running worker reloads was
touched. Three things cannot be plug-ins, because they change built-in types or a shared live helper. Each is small;
each has its test named. Run `python -m pytest` before and after (Night 3 ended at **139 green**).

## W1 · `scene_kit` accepts `big: true` (→ paints with `scene_big`, then the companions)

*Why:* the street (6144 × 3072), the lab and the compound are bigger than one pass; `brief missing` drafts them as
`scene_big`, which makes only the painting. With this, one `scene_kit` job makes the six-file set at any size.

- **File:** `forge/jobs/scene.py`, `kit_steps()` (≈ line 191) and `scene_kit()` (≈ line 218).
- **Edit:** in `kit_steps`, when `job.get("big")` is true, the first step becomes
  `{"type": "scene_big", **{k: job[k] for k in PAINT_KEYS + ("tile", "overlap", "max_step", "source", "init_denoise",
  "tile_strength", "canny_strength") if job.get(k) is not None}}` (scene_big reads `init` as the greybox; drop `denoise`
  and `control`, which scene_big does not take). In `scene_kit`, the handler table must include the plug-in types:
  `handlers = {**get_handlers(), **SCENE_HANDLERS}` (today it prefers the cached `HANDLERS`; `get_handlers()` merges
  plug-ins). `steps[0]["outputs"][0]` is `scene.png` for scene_big too, so the rest of the chain is unchanged.
- **Depth at size:** Depth Anything runs at `resolution` (default 1024) and is resampled to the painting — at 6144 wide
  that is soft. Pass `depth_resolution: 2048` in big kits (the field exists).
- **Test:** add to `tests/test_scene.py`: `kit_steps({"prompt": "p", "big": True, "target": [6144, 3072]})[0]["type"] ==
  "scene_big"`, and a fake-ComfyUI `scene_kit` with `big: true, target: [960, 540], tile: [512, 384]` producing all six
  slot files (copy `test_scene_kit_end_to_end_six_files`).
- **Then:** in `forge/brief_missing.py`, draft maps larger than one frame as `{"type": "scene_kit", "big": true, …}`
  instead of `scene_big` (one line, in `draft()`), and update `test_brief_missing.py` (`by["street"]["type"]`).

## W2 · `scene_layers` `fill: "inpaint"` → the Night 3 inpaint graph

*Why:* a stub since Night 2 — the back plane's holes (where the mid plane was lifted off) are filled by push-pull
smearing; an inpaint paints real background there.

- **File 1:** `forge/ops/layers.py` `split_layers()` (≈ line 147): instead of the note, keep `known` and return it:
  `out["back_known"] = Image.fromarray((known * 255).astype(np.uint8), "L")` (before overscan padding); set
  `out["info"]["fill"]` to the fill actually used.
- **File 2:** `forge/jobs/scene.py` `scene_layers()` (≈ line 155): after `split_layers`, if `fill == "inpaint"`:
  require `ctx.comfy` (raise "fill: inpaint needs the GPU worker" otherwise); build the mask as
  `state_mask.grow_feather(ImageOps.invert(L["back_known"]), 12, 8)`; take the un-padded back
  (`L["back"].crop((overscan, 0, overscan + w, h))`); call
  `forge.night3.inpaint.repaint_masked(ctx, {**job, "prompt": job.get("prompt") or "the far background of the scene,
  continuing what is around it", "denoise": 0.95}, back, mask, out, seed, tag="backfill")`; re-pad the result by
  reflection exactly as `split_layers` does; add the checkpoint to the job's prov (`licence_chain`).
- **Schema:** `scene_layers` stays `needs: cpu`, so a CPU-only worker could claim an inpaint-fill job and fail with the
  message above — acceptable (the GPU worker also takes CPU jobs). Document `fill: "inpaint"` in its doc string.
- **Test:** in `tests/test_scene.py`, a `scene_layers` job with `fill: "inpaint"` against `SceneComfy` → one graph with
  `SetLatentNoiseMask`, the back plane's known pixels unchanged (compare to a `fill: "extend"` run where the mask is 0).

## W3 · `prov.json` carries the prompt library (G6)

*Why:* `submit` records `prompt_blocks`, `prompt_library` and `prompt_template` on the job (they are in
`jobs/done/<id>.json` and `out/<id>/job.json` today), but `prov.json` — the file `approve` copies into the game — does
not have them yet.

- **File:** `forge/jobs/common.py` `write_prov()` (≈ line 64): add to `rec`:
  `**{k: job[k] for k in ("prompt_blocks", "prompt_library", "prompt_template") if job.get(k)}`.
- **Test:** `tests/test_paint.py::test_scene_paint_end_to_end` — give the job `prompt_blocks: ["style.house"]` and
  assert it is in `prov.json`.

## Not wiring, just a note

- The worker that is running picked up the Night 3 plug-ins without a restart (that is the point of them). A restart
  changes nothing either way.
- The map fields `brief missing` and `kit check` read (`template`, `skin`, `era`, `state_of`; walk rings as `walk` /
  `walk_rings`, `doors`, `spawns`, or `D` / `S` tiles in `rows`) were chosen without the game folder connected — the
  game session should confirm or rename them (one place each: `forge/brief_missing.py facts()`,
  `forge/kitcheck.py map_points()`).
