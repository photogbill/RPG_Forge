# Changelog

Each entry is the commit message push.bat was given. Newest at the bottom.

## 2026-11-08

RPG_Forge v0.1 — the skeleton

A local, file-driven art foundry for 2D games: a disk job queue (jobs/pending →
running → done|failed, atomic renames, receipts in out/<id>/job.json), a CLI
(submit · worker · status · requeue · validate · palette · models · docs · doctor),
daily logs, and a config that refuses to write outside the repo folder.

CPU ops (tested): OKLab palette snap with animation hysteresis; pixel-grid
detection + mode/median cell downscale; flood-fill background removal, trim, pad;
contact sheets and sprite sheets; seamless tiles, seam score, jitter variants;
Godot 4 TileSet writer.

Engines: ComfyUI driver over the local HTTP API with {{placeholder}} API-format
workflows (SDXL shipped; FLUX.2 klein / Qwen-Image-Edit by export).
GPU job types: scene_card, concept, portrait (seed-locked sets), prop, tile_texture.
CPU job types: palette_snap, pixelize, remove_bg, contact_sheet, pack_sheet,
godot_tileset; overworld planned.

Model registry with licences (shipped assets only from commercial-OK models),
Lospec palettes Resurrect 64 and Endesga 64, Windows .bat install/run/submit/
doctor/push, docs (PROTOCOL, CLAUDE hand-off, LICENSING, ROADMAP, JOB_TYPES),
and the first game config: games/turing_accords with the 21 Gate Law cards batch.

20 pytest checks pass (Linux container and Windows-side Python 3.10 VM).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>


## 2026-11-09

RPG_Forge v0.1 — the skeleton

A local, file-driven art foundry for 2D games: a disk job queue (jobs/pending →
running → done|failed, atomic renames, receipts in out/<id>/job.json), a CLI
(submit · worker · status · requeue · validate · palette · models · docs · doctor),
daily logs, and a config that refuses to write outside the repo folder.

CPU ops (tested): OKLab palette snap with animation hysteresis; pixel-grid
detection + mode/median cell downscale; flood-fill background removal, trim, pad;
contact sheets and sprite sheets; seamless tiles, seam score, jitter variants;
Godot 4 TileSet writer.

Engines: ComfyUI driver over the local HTTP API with {{placeholder}} API-format
workflows (SDXL shipped; FLUX.2 klein / Qwen-Image-Edit by export).
GPU job types: scene_card, concept, portrait (seed-locked sets), prop, tile_texture.
CPU job types: palette_snap, pixelize, remove_bg, contact_sheet, pack_sheet,
godot_tileset; overworld planned.

Model registry with licences (shipped assets only from commercial-OK models),
Lospec palettes Resurrect 64 and Endesga 64, Windows .bat install/run/submit/
doctor/push, docs (PROTOCOL, CLAUDE hand-off, LICENSING, ROADMAP, JOB_TYPES),
and the first game config: games/turing_accords with the 21 Gate Law cards batch.

20 pytest checks pass (Linux container and Windows-side Python 3.10 VM).

Also: push.bat (commit message from COMMIT_MESSAGE.txt, appended to CHANGELOG.md),
pull_model.bat, and the queue moves job files by rename so it works on folders
where deletion is blocked.

Bake-off: `render` job type (raw SDXL with any checkpoint + LoRA chain via a
code-built ComfyUI graph), safetensors header inspection (checkpoint/LoRA,
SD1.5/SDXL/FLUX, trigger words) → models/INVENTORY.md, forge.json model_dirs
(your own sdmodels/ and lora models/ folders; install_comfy.bat points ComfyUI
at all of them), and `python -m forge bakeoff plan|submit|report|rate`: every
checkpoint × every compatible LoRA × a suite of test prompts, grouped by
checkpoint, incompatible pairs skipped, failures as red cells, grids + index.html
+ ratings. bakeoff.bat / bakeoff_report.bat / scan_models.bat. 24 tests.

games/turing_accords/REFERENCES.md: William's own photography as lighting/place references
(paths only — nothing copied into the repo), with a shot list.

Bake-off renders are filed by_model/<checkpoint>/<lora>/ and by_category/<kind>/<prompt>/
as they finish, so the comparison is a folder, not a search.

Fixes from the first live run: the render job's batch-size field collided with the
queue's batch tag (renamed to `count`); consoles on cp1252 no longer crash on → × ·
(chcp 65001 in every .bat + errors=replace); cmd-safe .bats without nested-quote
blocks (start_comfy.bat split out); run_worker.bat reuses a ComfyUI that is already
up; the worker hot-reloads handler code before each job; `retry` / retry_failed.bat.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>

---

Bake-off 1 judged; FLUX engines; the second night's bake-offs (2026-11-09)

Bake-off 1 (sdxl_v1, 1,280 renders, no failures): report built; verdicts per
asset kind in docs/BAKEOFF_1_VERDICT.md — paint the world with SDXL
(ArtUniverse scenes, base+rpg_portrait portraits, RealVis for the horrific
register, game_icon_v1 icons), characters another way; two SpriteSheet LoRAs
are broken (noise), the named-artist LoRA is out by our own rule. Review
sheets under out/bakeoff/sdxl_v1/review/.

Engines: two code-built graphs beside sdxl_graph — flux2_graph.py (FLUX.2
klein 4B, base/distilled, Apache-2.0) and flux1_graph.py (FLUX.1 dev/schnell
and fine-tunes; split files or all-in-one). render jobs take "graph"; the
bake-off planner takes graph, base_override, checkpoint_kinds/dirs/
include/exclude, base_filter and lora_base_override so FLUX suites can
discover their checkpoints. models pull flattens split_files/. Header scan
now labels FLUX.1 unets and VAEs. 7 new unit checks (tests/test_flux_graphs).

Model registry: klein 4B base+distilled fp8, Qwen3-4B encoder, FLUX.2 VAE,
FLUX.1 schnell fp8 (+ dev, non-commercial, opt-in), CLIP-L/T5 fp8, FLUX.1
VAE. forge.json: William's flux_models / flux_lora folders registered;
comfy.flux1 / comfy.flux2 defaults.

Suites: sdxl_v1_newmodels (the new SDXL LoRAs as new columns of sdxl_v1),
style_v1 (five house styles in our own words x five checkpoints x ten Game I
pictures), flux2_klein_v1, flux1_v1. Scripts: bakeoff_tonight.bat,
bakeoff_new_models.bat, bakeoff_styles.bat, bakeoff_flux.bat, pull_flux.bat.
Docs: NEXT_MODELS.md (Krea 2, MOSS-Image, the FLUX wiring), CLAUDE.md,
README. Game config moved to the 1080p sizes with bake-off picks per job.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>

---

FLUX for William's own files; the forge roadmap (2026-11-09, later)

flux1_graph: real CFG for de-distilled fine-tunes, GGUF models via UnetLoaderGGUF,
weight_dtype (bf16 unets cast to fp8 on load when over comfy.fp8_cast_over_gb);
flux2_graph: weight_dtype; the klein-9B text encoder picked by name. Header scan
lists .gguf files and labels FLUX.1 unets/VAEs. Bake-off planner: checkpoint
discovery by folder/name/architecture (checkpoint_dirs, _include, _exclude,
base_filter, lora_base_filter, lora_checkpoint_filter), per-model overrides by
name (cfg_by_name, steps_by_name), all-in-one checkpoints detected. forge.json:
flux_models / flux_lora folders registered. install_comfy_gguf.bat; pull_flux.bat
9b. Suites: flux1_v1 discovers every FLUX.1 file (LoRA columns on the all-in-one
dev checkpoint), flux2_klein_v1 every *klein* file (the unidentified 'flux3'
files excluded). docs/NEXT_MODELS.md: what each downloaded file needs.
docs/ROADMAP_NIGHT_2.md + KICKOFF_PROMPT_FOR_OPUS_FORGE.md: what the forge does
and the build order for the next Opus session. 29 tests green.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>

---

Night 2 forge build: painted backgrounds, game manifest + approve, pipelines (2026-11-09, Opus)

The roadmap's P0 and P1 (F1-F11), plus F18 (priority/pause) and F19 (licence report), and the
quality stages William asked for.
Paint: forge/engines/graph_ops.py splices stages into any builder's graph (img2img incl. FLUX.2
SplitSigmasDenoise, SDXL union ControlNet, RealESRGAN upscale + cover-fit, hires-fix refine with
a 4 MP cap for scrolling streets, FreeU, Impact Pack FaceDetailer filled from /object_info).
New job types scene_paint, repaint (exact init size, denoise sweeps, layout-agreement score),
upscale, icon, sleeve (PIL typography), pipeline ($prev.outputs[0]), canny, normal_map,
emissive_mask. ComfyClient gains object_info, upload_image, run_by_node; render shares
build_graph with the paint jobs.
Manifest: games/turing_accords/export_wanted.py (read-only on the game: 275 wanted files),
forge wanted / approve / licences / models licence. approve checks every model that touched the
pixels (pipeline steps and upstream forge jobs included), refuses unknown or non-commercial,
backs up, writes _provenance in the game, records the approval. No non-commercial model is a
default anywhere (RealESRGAN, not UltraSharp; Depth Anything V2 Small only; FaceDetailer, no
CodeFormer/GFPGAN). New registry entries: realesrgan-x4plus, controlnet-union-sdxl-promax,
face-yolov8m, depth-anything-v2-small, midas-dpt-hybrid.
Also: review pages with ratings export + rate --import, brief maps|sleeves|icons drafts (submit
refuses drafts), doctor checks graph nodes and every model the queue names, job priority and
pause/resume. Bats: wanted, approve, licence, licences, review, rate, brief, pause, resume,
pull_quality, install_comfy_faces, install_comfy_aux. Templates for every new type.
Docs: HANDOFF_FORGE_2026-11-09.md, FOR_FABLE_FORGE_2026-11-09.md, CLAUDE.md, README,
JOB_TYPES (regenerated). Tests 33 -> 61, all green. Not started: F12-F17.
.gitignore: sdmodels/, lora models/, flux_models/, flux_lora/, flux_workflow/ and Bills Actual Art/ are now
ignored — push.bat's `git add -A` would otherwise have tried to push ~100 GB of weights and William's photos.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>


## 2026-11-09

Bake-off: tool categories, a finishing suite, and a tools test

The bake-off could only queue raw renders. A category can now queue any of the forge's tools
("type": "scene_paint" + "job": {...}), so a suite compares treatments on the same picture and seed.

- forge/bakeoff.py: category/suite `type` / `job_type`, `job`, `detail_crop`, `detail_at`, per-category
  `seconds_per_render`; the report takes each job's first picture (scene.png, icon.png ...) instead of
  only render.png; new across_<picture> grids (rows checkpoints, columns categories - also useful for
  the style suite) and detail_<picture> grids (the same as a 1:1 crop, because refine and face repair
  cannot be judged on a thumbnail).
- games/turing_accords/bakeoff/finish_v1.json: 4 pictures x 4 SDXL checkpoints x 6 finishes at
  1920x1080 (upscale only, refine 0.30, refine 0.45, FreeU, face_fix 0.30 / 0.50) = 88 paintings.
- games/turing_accords/batches/tools_v1.json: 13 jobs, one per Night 2 tool, priority 10, so a missing
  node or model shows up in minutes. Uses ref/bills_house_greybox_test.png, drawn from the game's real
  bills_house map at x3.
- test_tools.bat, bakeoff_finish.bat; bakeoff_tonight.bat now queues those two first and skips them
  with a message if pull_quality.bat / install_comfy_faces.bat have not been run.
- `models licence` refuses a placeholder such as "<licence name>" as the licence name.
- docs/CLAUDE.md, docs/FOR_FABLE_FORGE_2026-11-09.md, README.md updated. Tests: 61 -> 64, all green.
- docs/model_licences/: the licence texts William supplied (CreativeML Open RAIL++-M for SDXL 1.0; Krea 2
  Community License v1), kept out of the repo root so they are not mistaken for the forge's own MIT licence.
  models/licences.json: ArtUniverseSDXL_v8 recorded as CreativeML Open RAIL++-M (replaces the placeholder).

The model bake-offs (sdxl_v1, style_v1, FLUX) are unchanged and stay raw on purpose.

Co-Authored-By: Claude <noreply@anthropic.com>


## 2026-11-09

Roadmap: the next forge session (N1-N9) - painted scenes become six-file sets

Decision behind it (William, 2026-11-09): no true HD-2D. The game keeps painted 2D scenes and gets the
look on top - lights on normal maps, glow, parallax layers, a focus shader (game plan 21, section 3b).

- docs/ROADMAP_NIGHT_2.md section 2b: N1 depth maps and normals from depth, N2 scene_layers, N3 scene_kit
  (painting, normals, glow, layers and depth as one job), N4 approve --set, N5 bake-off skips finished
  cells, N6 re-crop detail sheets, N7 the dashboard, N8 the Krea 2 graph, N9 small fixes.
- KICKOFF_PROMPT_FOR_OPUS_FORGE.md rewritten for that session.
- models/licences.json: ArtUniverseSDXL_v8 note - William checked the Civitai v8 page, no additional
  restrictions.

Co-Authored-By: Claude <noreply@anthropic.com>


## 2026-11-09

Forge session 2: painted scenes as six-file sets (N1-N9), dashboard, Krea 2

Tools test (tools_v1) ran first on the real GPU: 13/13 done, 0 failed. Tests 64 -> 98, all green.

- N1 depth_map job (Depth Anything V2 Small only - the node's default is the non-commercial Large; the graph
  refuses to run without naming Small), 16-bit depth, white = near; normal_map source luminance|depth with a
  detail blend and a lit-from-the-left preview (forge/ops/depth.py, forge/jobs/scene.py)
- N2 scene_layers: auto depth cuts, soft walk-behind plane, push-pull hole fill, overscan, layers.json, slide
  preview (forge/ops/layers.py)
- N3 scene_kit: one job -> scene.png, _n, _e, _back, _over, _depth + contact sheet + one licence chain;
  brief maps drafts scene_kit jobs
- N4 approve --set: one licence check for the whole set, all-or-nothing, provenance per file; wanted.json lists
  the five optional companions per map
- N5 bakeoff submit skips finished/queued cells (--force), submit --skip-done, eta (forge/dedupe.py, eta.py)
- N6 bakeoff report --detail-at / --detail-auto (largest face) without re-rendering (forge/detail.py)
- N7 the dashboard: ui.bat -> http://127.0.0.1:8765 (queue, ETA, progress, newest pictures, Retry, Pause/Resume,
  Approve with dry run) (forge/ui.py)
- N8 Krea 2 graph from ComfyUI 0.44's own source (forge/engines/krea2_graph.py); registry entries with the
  Krea 2 Community License revenue condition, printed by approve/licences; doctor krea2 check; krea2_v1 suite
  (not submitted). The Stable Yogi fine-tune says "commercial use by permission only" - not recorded.
- N9 licence.bat asks its questions; doctor lists unknown-licence models jobs used; models unusable report;
  review shows detail crops; bakeoff_tonight prints an ETA
- .gitignore: "engines/" (meant for the ComfyUI install) also matched forge/engines/, so the ComfyUI driver and
  every graph builder (comfy.py, graph_ops.py, sdxl/flux1/flux2/krea2 graphs, workflows) were never in the public
  repo - a fresh clone could not render. Now "/engines/"; this push adds them.
- Fixes: a doctor test used the real model folders; the scanner now tells FLUX.2/FLUX.3/Krea 2 apart from FLUX.1

Hand-off: docs/HANDOFF_FORGE_2026-11-09b.md

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>


