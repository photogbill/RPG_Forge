# Hand-off — RPG_Forge, 2026-11-09 (Opus, the Night 2 forge build)

Plan: `docs/ROADMAP_NIGHT_2.md`. William turned the bake-off off at the start of the session and the queue was empty,
so features were wired straight into the live handlers (rule 1's stub path was not needed). **Tests: 33 → 61, all green**
(`python -m pytest`, Linux VM; the GPU paths are tested against a fake ComfyUI that records the graph each handler sends).

## Built

| Item | What | Status |
|---|---|---|
| **F1** upscale + `scene_paint` | `forge/engines/graph_ops.py` (graph surgery on any builder's graph), RealESRGAN tail (`UpscaleModelLoader → ImageUpscaleWithModel → ImageScale`, cover-fit or stretch), `scene_paint` in `forge/jobs/paint.py`, `upscale` job, raw + final saves told apart by node (`ComfyClient.run_by_node`) | code + tests ✓ · first real render: pending William's run |
| **F2** `repaint` | img2img for SDXL / FLUX.1 (KSampler denoise) and FLUX.2 (SplitSigmasDenoise); init uploaded through ComfyUI's `/upload/image`; output at the init's exact pixel size; `denoise` list → sweep contact sheet | code + tests ✓ · greybox of bills_house does not exist yet (the game's `greybox_to_painted.py` makes it) |
| **F3** ControlNet | `add_controlnet` with SetUnionControlNetType; canny computed in numpy (`forge/ops/edges.py`); depth via comfyui_controlnet_aux if installed, else skipped with a note in prov; `control_overlay.png` + a `layout_agreement` number | code + tests ✓ · real run pending |
| **Quality** (William's ask) | `refine` = hires fix (default on, denoise 0.3, ≤4 MP then upscale), `face_fix` = Impact Pack FaceDetailer (fills every input from `/object_info`, so pack updates don't break it), `freeu` (SDXL) | code + tests ✓ · needs `install_comfy_faces.bat` |
| **F4** manifest + approve | `games/turing_accords/export_wanted.py` (read-only on the game; **275 wanted files** today), `forge/manifest.py`: `wanted`, `approve`, `models licence`, `licences` | ✓ — dry-run against the real game: an `sd_xl_base` render is accepted, an ArtUniverse render is **refused (licence unknown)** — see below |
| **F5** pipelines | `forge/pipeline.py`, `type: pipeline`, `$prev.outputs[0]` / `$prev.outputs` / `$steps[N].outputs[K]`, step folders, step-named errors | ✓ CPU chain tested end to end |
| **F6** `icon` | key colour → cut → centred on a transparent square canvas | ✓ |
| **F7** `sleeve` | model art + PIL typography, layouts `band` / `corner` (checked by eye: legible) | ✓ · the game has no `assets/fonts` yet — falls back to Pillow's built-in font; drop OFL fonts there for the real look |
| **F8** review | `forge/review.py`: labelled sheets + `index.html` (1–5 radios, notes, licence-coloured borders, Export → `rate --import`) | ✓ checked on `sdxl_v1_quick` |
| **F9** doctor | `forge/doctor.py`: nodes per graph/stage from the real builders, remedies (`install_comfy_gguf.bat`, `install_comfy_faces.bat`), every model the queue names, biggest model vs VRAM | ✓ (node check needs ComfyUI running) |
| **F10** brief | `forge/brief.py`: `brief maps|sleeves|icons` → `_draft` batches (submit refuses drafts) | ✓ |
| **F11** lighting | `normal_map` (OpenGL/Godot convention) and `emissive_mask` CPU jobs | ✓ · Godot check is William's eyes |
| **F18** priority/pause | `"priority"` in a job; `pause.bat` / `resume.bat` (`jobs/paused/`) | ✓ |
| **F19** licences | `licences.bat` → `out/licences_<game>.md` | ✓ |

Not started: **F12** (turnaround → rig parts), **F13** (MOSS-Image text), **F14** (IP-Adapter / reference consistency),
**F15** (depth → layers), **F16** (dashboard), **F17** (Krea 2 graph).

## Try each one (one line each)

- `pull_quality.bat` → `install_comfy_faces.bat` → restart `run_worker.bat` → `doctor.bat` (says what is still missing)
- `submit.bat jobs\templates\scene_paint.json` — a 1920×1080 painting with raw.png, prov.json and two variants
- `submit.bat jobs\templates\repaint.json` — needs `bills_house_greybox.png` from the game first
- `submit.bat jobs\templates\pipeline.json` — render → upscale → palette snap, one folder, one contact sheet
- `submit.bat jobs\templates\icon.json` · `jobs\templates\sleeve.json` · `jobs\templates\upscale.json` (edit the input path)
- `wanted.bat --refresh` then `wanted.bat --missing` (or `--kind scene`)
- `approve.bat <job-id> <wanted-name> [pick]` — add `--dry-run` as the third argument to look first
- `licence.bat "<file>" "<licence>" yes "<where you checked>"` · `licences.bat`
- `review.bat <batch-or-suite>` → rate on the page → Export → `rate.bat <same name>`
- `brief.bat maps` (or `sleeves`, `icons`) → `games\turing_accords\batches\draft_*.json`
- `pause.bat` / `resume.bat`; `"priority": 10` in a job file to jump the queue

## What William needs to know

1. **ArtUniverseSDXL_v8 has no licence on record**, so nothing painted with it can be approved yet, and it is the
   game's default checkpoint for scenes. Open its Civitai page, look at the permission icons (whether generated images may be sold
   or used commercially), then: `licence.bat "ArtUniverseSDXL_v8.safetensors" "<licence name>" yes "<what the page said>"`
   (or `no`). Same for any LoRA used in a shipped picture. The forge will not guess.
2. **No non-commercial model anywhere in the paint path** (your rule): RealESRGAN (BSD-3) instead of 4x-UltraSharp
   (CC BY-NC-SA); Depth Anything V2 **Small** (Apache-2.0) only; no CodeFormer/GFPGAN: FaceDetailer repaints faces with
   the job's own checkpoint and uses face_yolov8m (Apache-2.0) only to find them.
3. **The game's `make_placeholders.py` overwrites approved art** if it is run again (it rewrites every placeholder PNG).
   `wanted` shows such files as **stale**; re-approve them. The lasting fix is game-side: skip any file that has a
   `_provenance/<name>.json`. That's a note for the game session, since this session did not touch the game.
4. Approved files are copied at the size they were made; `approve` notes when that differs from the ×3 target (the game
   scales). The Gate Law cards were never rendered (only the placeholder sheet), so `approve` was proven by tests and a
   dry run, not a real card.
5. Live modules changed tonight (fine with the queue empty; the worker hot-reloads them, and an already-running worker
   upgrades its ComfyUI client by itself): `forge/jobs/gpu.py` (`render` now shares `build_graph`), `jobs/common.py`
   (licence lookup: registry `save_as`, `models/licences.json`, `licence_chain`), `jobs/cpu.py`, `jobs/__init__.py`,
   `engines/comfy.py` (+`object_info`, `upload_image`, `run_by_node`), `queue.py` (priority, pause), `schema.py`, `cli.py`,
   `config.py`. `bakeoff.py` and the bake-off suites / `out/bakeoff/` were not touched.

6. **`.gitignore` fixed before your next push:** `sdmodels/`, `lora models/`, `flux_models/`, `flux_lora/`,
   `flux_workflow/` and `Bills Actual Art/` were untracked but not ignored, and `push.bat` runs `git add -A`, so the next
   push would have tried to upload ~100 GB of model weights and your photographs to the public repo. Nothing had been
   committed; they are now ignored.

## Not proven until the GPU runs

Every ComfyUI node name and input was checked against the installed ComfyUI's source (`ImageScale`, `ControlNetApplyAdvanced`,
`SetUnionControlNetType`'s types, `UpscaleModelLoader`, `SplitSigmasDenoise`, `FreeU_V2`, `/upload/image`). FaceDetailer and the
depth preprocessors are custom nodes not installed yet; their inputs are filled from `/object_info` at run time. `doctor.bat`
will name anything still missing. Fable's test run (`docs/FOR_FABLE_FORGE_2026-11-09.md`) is the proof.
