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


## 2026-11-10

Krea 2 cut from the forge; depth normals ignore the floor ramp

William: the Stable Yogi Krea 2 checkpoint said "commercial use by permission only" - deleted at his request -
and then "if Krea 2 has that license, we won't use it period". Removed: forge/engines/krea2_graph.py, its
build_graph branch and hot-reload entry, the doctor krea2 check, the four Krea 2 registry entries, forge.json
comfy.krea2, the krea2_v1 suite, the Krea tests; docs and the hand-off say so. Kept: generic licence_condition
printing in approve/licences, and the scanner's Krea 2 detection so `models unusable` lists Krea files
(cinematicFantasy_v1 is now a delete candidate).

Depth normals (seen on the real GPU output): ComfyUI saves depth as 8-bit, so floors arrived as terraces that
printed as contour lines/stripes in the normals - a resolution-scaled de-banding blur now runs first; and a receding
floor read as one big slope - new `flatten` (default 0.85) removes the depth's trend up the screen, only where a
pixel is ground, so upright objects keep their shape and nothing gets a halo. Comparison: out/_tests/flatten_compare_v5.png.

Real-GPU proof of N1-N3 (batch night3_checks): depth map, normals from depth, layers on the street, and a full
scene_kit with all six slot files and a commercial-OK licence chain including the depth model.

Night 3 plan: docs/ROADMAP_NIGHT_3.md (G1-G9: morning report, compact review sheets, tiled big scenes,
inpaint + scene states, kit check, prompt library, sprite-sheet tools, credits, dashboard) and
KICKOFF_PROMPT_FOR_OPUS_FORGE_NIGHT_3.md.

Plug-in job types (forge/plugins/): a file exposing JOB_TYPES + HANDLERS (+ DEPENDS) is picked up by a running
worker before its next job - no restart to add a job type. Re-imported only when it changes on disk; a broken or
half-saved plug-in keeps its last good version; a plug-in can never replace a built-in type. schema.validate /
with_defaults / needs_gpu / docs learn plug-in types on demand. forge/plugins/ping.py is the example and the
health check. 10 tests (tests/test_plugins.py); 106 green.

William: deleted the three non-commercial FLUX files from flux_models (FLUX.1 dev x2, klein 9B). Ruling:
artist-named LoRAs may be used; the artist's name and the LoRA's trigger keywords never go in a prompt.

Fixes found on the first real run: models.json named FLUX files that do not exist on Hugging Face (klein 4B has
no -fp8 files; schnell fp8 is flux1-schnell-fp8-e4m3fn) - corrected against the repos' file lists. pull_flux.bat had
mixed line endings and non-ASCII characters, so cmd ran its comments as commands - rewritten (ASCII, CRLF), pulls only
the commercial models, one model per line so one failure does not stop the rest. bakeoff_tonight.bat now requeues,
pulls FLUX, queues every suite and starts the worker.

Worker idle-gap fix (forge/queue.py run_worker): accept() called the reloading handler factory once per pending
file on every claim, so with 3,250 jobs queued the worker sat ~16 s between renders reloading plug-ins. The handler
map is now loaded once per claim cycle (code fixes still picked up before every claim). SPRITE_1_START.bat requeues
an interrupted job before starting the worker, so it doubles as the restart.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>


---

Night 3 (Opus): plug-in job types for big scenes, room states, sprite and UI tools; morning report, review sheets a model can read, kit check, prompt library, brief missing, credits

Every new job type is a plug-in (forge/plugins/) - nothing the running worker reloads was edited. G0: the worker ran the
ping at 22:54 (plug-in support confirmed).

- G1 report night (night_report.bat): per batch done/failed (causes folded)/queued/skipped, wall time, s/render by
  checkpoint, slowest, models with licence colour, thumbnails, what to run next. Checked on the 1,280-render 11-08 run.
- G2 review --compact / --pairs A,B (review_compact.bat): <=12 labelled cells, <=2000 px, <=1.5 MB, review_index.json.
- G3 scene_big: small whole scene -> climb <=2x per step (William: "6X disappoints usually") -> tiled img2img with
  ControlNet tile (+ canny from the greybox) -> feathered merge -> seam scores. op tiles-demo.
- G4 inpaint + scene_state: SetLatentNoiseMask with the job's own checkpoint (no new model/licence); mask from two
  greyboxes (refused over 35 %); bit-identical outside the mask (tested); kit companions rebuilt only inside it.
- G5 kit check (kit_check.bat); approve --set (CLI + dashboard) refuses on a fail.
- G6 prompt library (games/<game>/prompts, placeholders only) expanded by submit and bakeoff submit; never.json with
  the artist-named LoRA's two words (William's ruling: the LoRA may be used, the name and triggers never prompted).
- G10/G11 brief missing (paint_missing.bat): one draft per missing painting, type by the facts; room families.
- G7 facings_pack / anim_preview / turnaround_split; G8 credits; G9 dashboard Report link, kit colours, A/B, up next;
  G12 nine_slice / button_states. op.bat runs every CPU tool directly.

GPU proofs of G3/G4 are queued for William in night3_tests/run_night3_tests.bat (worker was stopped at 23:09).
Wiring left for an empty queue: docs/WIRE_NIGHT_3.md. Hand-off: docs/HANDOFF_FORGE_NIGHT_3.md. Tests 106 -> 139.

Night 3B: a hand-off folder for outside tools (G13) and a Filter Forge driver (G14)

- G13 handoff out/in/tool (handoff_out.bat, handoff_in.bat, handoff_tool_add.bat): raw renders out to a folder with
  a README, results matched back by job id (missing / extra / wrong-size named), filed as handoff_file or handoff_kit
  jobs (the kit's companions rebuilt from the returned picture). Tool licences live in models/licences.json; approve
  names every outside tool and asks for a missing licence; a tool's condition prints like a model's.
- G14 filter_forge job type (filter_forge.bat, filter_forge_proof.bat): task XML from the renderer's own documented
  vocabulary (a channel is a saved preset; seamless checked against the preset and measured; normals OpenGL, measured
  against the height channel when there is one); filters used by path, never copied. Proven on the worker: Wet Stone
  at 1024 in 6 s. Finding: its "seamless" output has a wrap seam.
- .gitignore: /*.exe and *.ffxml (the Filter Forge installers were in the repo root; push.bat runs git add -A).
- Plug-ins only while the bake-off ran; nothing the worker reloads was edited. Hand-off: docs/HANDOFF_FORGE_NIGHT_3B.md.
  Tests 139 -> 155.

Worker idle-gap fix (forge/queue.py run_worker): accept() called the reloading handler factory once per pending
file on every claim, so with 3,250 jobs queued the worker sat ~16 s between renders reloading plug-ins. The handler
map is now loaded once per claim cycle (code fixes still picked up before every claim). SPRITE_1_START.bat requeues
an interrupted job before starting the worker, so it doubles as the restart.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

---

Sprite-only sampler bake-off (SPRITE_1/2/3 .bat)

William, 2026-11-10: sprites are the biggest art risk (faces and eyes go wrong on ~90%-good renders); samplers matter,
so sweep them. New: a `samplers` axis for bake-off suites — every category runs once per sampler entry with that
sampler's OWN steps/cfg/scheduler (and `evals` for the time estimate); filed as "<category>-<label>" so the across
grids become checkpoint x sampler per LoRA and seed. sdxl_graph now accepts every sampler/scheduler ComfyUI 0.44
offers. Model scan now also covers model_dirs.diffusion_models (klein 4B and schnell were invisible to it).
Suites: sprite_samplers_v1 (SDXL, 14 samplers, ~3,220 renders), sprite_samplers_klein_v1, sprite_samplers_schnell_v1
(commercial-OK FLUX only). Queued directly (old bake-off parked in jobs/paused/); William runs SPRITE_1_START.bat (worker), SPRITE_2_LOOK.bat
(reports + eta, any time), SPRITE_3_FINISHED.bat (resume the old bake-off).

Worker idle-gap fix (forge/queue.py run_worker): accept() called the reloading handler factory once per pending
file on every claim, so with 3,250 jobs queued the worker sat ~16 s between renders reloading plug-ins. The handler
map is now loaded once per claim cycle (code fixes still picked up before every claim). SPRITE_1_START.bat requeues
an interrupted job before starting the worker, so it doubles as the restart.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

Sprite run v2 (William 02:25-02:30): his prompt prefix "8k, High definition highly detailed, Perfect violet eyes, Violet
Purple and cobalt Blue Balayage" (v1's "solar panel" wording drew literal panels); canon nuclear core + trefoil and
holster. Suites: sprite_samplers_v2 (SDXL minus tile/map/icon/level LoRAs, the icon checkpoint, mislabelled FLUX/MOSS
LoRAs and banned Krea 2), sprite_samplers_klein_v2, sprite_flux1_v2 (every FLUX.1 model incl. non-commercial dev ones -
bake-off only - with the FLUX.1 LoRAs that apply), and an extra Pre-Raphaelite Guardian set (guardian_prerap_v1 /
_flux_v1 / _klein_v1). v1's unrun jobs moved to jobs/_cancelled_sprite_v1/; its 53 renders kept as the before-picture.


