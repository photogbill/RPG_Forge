# RPG_Forge

**A local, file-driven art foundry for 2D games.** Drop a JSON job into a folder; a worker on your own
GPU paints it, cleans it, snaps it to your palette and leaves the result — with a contact sheet and a
provenance record — in another folder. Nothing leaves your machine, nothing needs an API key, and
anyone who can write a text file can drive it: you, a script, or an AI assistant working through the
same folders. Built for [*The Turing Accords*](https://github.com/photogbill) JRPG; made for any game.

```
jobs/pending/*.json  ──►  worker (GPU: ComfyUI · CPU: Pillow/numpy)  ──►  out/<job-id>/
      ▲                                                                      │
      └──────────── you / a script / Claude write the next job ◄─────────────┘
```

## Why a folder queue

- **Overnight batches.** Queue two hundred cards before bed; the worker chews through them and the
  contact sheets are waiting in the morning. Slow models are fine.
- **Compatible with assistants.** The queue is just files, so an AI that can read and write your disk
  can submit jobs, look at the contact sheets, grade them against a brief and queue corrections —
  no plug-in, no cloud, no network hop. `docs/CLAUDE.md` is the hand-off document for that.
- **Honest provenance.** Every output carries `prov.json`: model, licence, seed, prompt, every post step.
  That file is your Steam AI-disclosure inventory and your licence audit, written for free.
- **Nothing outside the folder.** No AppData, no `C:\Users\…`: jobs, outputs, models, logs all live
  beside the code (`forge.json` refuses external paths unless you say so).

## What it makes

| Job type | What you get | Needs |
|---|---|---|
| `scene_card` | a painted cutscene/location card at your card size, palette-snapped | GPU |
| `concept` | a large location concept painting (the image a tileset kit is derived from) | GPU |
| `portrait` | a **seed-locked** expression set: one face, N expressions, contact sheet | GPU |
| `prop` | a prop sprite on alpha (key colour flooded away, trimmed, scaled, snapped) | GPU |
| `tile_texture` | a seamless tile at your tile size + jittered variants + a 4×4 repeat preview | GPU |
| `palette_snap` | any image snapped to your master palette in OKLab (perceptual nearest) | CPU |
| `pixelize` | big "pixel-art" renders collapsed to true pixels (grid detection + mode per cell) | CPU |
| `remove_bg` · `contact_sheet` · `pack_sheet` · `godot_tileset` | the finishing and packing tools | CPU |
| `overworld` | *planned*: public-domain map layers → a compressed game overworld | CPU |

| `render` | a raw render (SDXL, FLUX.1 or FLUX.2 klein) with any checkpoint + LoRA chain — the bake-off's unit | GPU |
| `scene_paint` | a **painted background at game resolution**: render → RealESRGAN → cover-fit 1920×1080 (or any size) → refine (hires fix) → optional FaceDetailer; optional img2img start and ControlNet layout lock | GPU |
| `repaint` | **greybox → painting**: img2img from the map's greybox at its exact pixel size so walk polygons stay valid; a denoise sweep on one contact sheet; canny ControlNet | GPU |
| `upscale` | any images through an upscale model to an exact size | GPU |
| `icon` · `sleeve` | inventory icons on a transparent square canvas; record sleeves with PIL typography (no model spelling) | GPU |
| `pipeline` | a chain of jobs as one (`$prev.outputs[0]` feeds the next step) | GPU or CPU |
| `canny` · `normal_map` · `emissive_mask` | ControlNet edges; `_n.png` normal maps and `_e.png` glow layers for painted maps | CPU |

Full field reference: `docs/JOB_TYPES.md` (generated from the code).

## Your own model collection

`forge.json → model_dirs` lists every folder of weights per kind — the forge's own `models\…` plus your
collections (`sdmodels\`, `lora models\` by default). `scan_models.bat` reads every file's header (no
weights loaded) and writes `models\INVENTORY.md`: checkpoint or LoRA, **SD1.5 / SDXL / FLUX**, and the
trigger words the trainer left behind. `install_comfy.bat` points ComfyUI at all of them.

## The bake-off — which model for which kind of picture?

Fine-tunes and LoRAs are unpredictable and sometimes perfect, so instead of guessing: `bakeoff.bat` queues
**every checkpoint × every compatible LoRA (+ none) × a suite of test prompts** — portraits, scene cards,
sprite sheets, tiles, maps, icons, props, concepts (`games/turing_accords/bakeoff/sdxl_v1.json`) — with one
seed and identical sampler settings, grouped by checkpoint so ComfyUI reloads less. Incompatible pairs (an
SD1.5 or FLUX LoRA on an SDXL checkpoint, which ComfyUI would silently ignore) are skipped and listed; a
render that fails is a red cell, and the run moves on. Every render is also filed twice — `out\bakeoff\<suite>\by_model\<checkpoint>\<lora>\` and
`by_category\<kind>\<prompt>\` (one folder per picture, one file per model) — so comparing is a matter of
opening a folder. `bakeoff_report.bat` builds one grid per prompt
(rows = checkpoints, columns = LoRAs) and an `index.html`; `python -m forge bakeoff rate <suite> <job-id> <1-5>`
records verdicts that show up as badges. `bakeoff.bat --quick` is a ten-minute smoke run first.

## Quick start (Windows)

1. `install.bat` — Python venv + the CPU tools. Run `run_cpu_worker.bat` and you can already snap,
   pixelize and pack.
2. `install_comfy.bat` — clones ComfyUI into `engines\ComfyUI` with CUDA PyTorch (one big download).
3. `pull_model.bat` — downloads the default checkpoint (SDXL base, ~6.9 GB) into `models\checkpoints\`; or drop any checkpoint there yourself.
4. `run_worker.bat` — starts ComfyUI minimised and the GPU worker.
5. `submit.bat jobs\templates\scene_card.json` — or drag a job/batch file onto `submit.bat`.
6. Look in `out\<job-id>\` — `card.png`, `raw.png`, `contact.png`, `prov.json`, `job.json`.
7. `push.bat` commits and pushes. It reads the commit message from `COMMIT_MESSAGE.txt` when that file exists — whoever changed the files (a person, a script, Claude) writes what changed there — and otherwise asks for one line. Pushed messages are kept in `CHANGELOG.md`.

Linux/macOS: `python -m venv venv && . venv/bin/activate && pip install -r requirements.txt && python -m forge worker`.

## A job

```json
{"type": "scene_card", "name": "gate_law_01_ribbon", "game": "turing_accords",
 "prompt": "a kitchen at breakfast; a synthetic housekeeper with a ribbon in her apron pours coffee; a child reaches for her hand; warm morning light"}
```

A batch is `{"batch": "name", "defaults": {...}, "jobs": [...]}` — see `games/turing_accords/batches/`.
A game's palette, style prefix and sizes live in `games/<game>/forge.game.json`, so jobs stay short.

## Repository map

```
forge/            the package: queue, schema, cli, bakeoff, ops/ (image maths, safetensors headers), engines/ (ComfyUI, SDXL graph), jobs/
forge.json        configuration (paths, ComfyUI url, defaults)
jobs/             pending/ running/ done/ failed/ — the queue; templates/ — one example per job type
out/              results, one folder per job id
models/           weights (ignored) + models.json registry with licences
palettes/         master palettes (.hex, Lospec format)
games/            per-game config and job batches (turing_accords is the first)
docs/             PROTOCOL.md · JOB_TYPES.md · CLAUDE.md · LICENSING.md · ROADMAP.md
tests/            pytest (CPU side; 24 tests)
```

## Status

v0.2 (2026-11-09) — painted-background pipeline, game manifest + approve, pipelines, review pages, pre-flight
doctor (see `docs/HANDOFF_FORGE_2026-11-09.md`). v0.1 — the queue, the CLI, the CPU tools and the ComfyUI driver are real and tested; the GPU handlers
run against an SDXL workflow out of the box. FLUX.2 klein and Qwen-Image-Edit workflows are added by
exporting from ComfyUI (`forge/engines/workflows/README.md`). The sprite pipeline (image → 3D proxy →
8 facings → pixelize) and the overworld job are designed in `docs/ROADMAP.md` and not built yet.

## Painted backgrounds and the game manifest (added 2026-11-09, Night 2)

- **Setup once:** `pull_quality.bat` (RealESRGAN upscaler, face finder, SDXL union ControlNet — all commercial-OK),
  `install_comfy_faces.bat` (FaceDetailer add-on), optional `install_comfy_aux.bat` (depth control). Then `doctor.bat`
  lists which graphs and stages this ComfyUI can run and whether every model the queue names is on disk.
- **What the game still needs:** `wanted.bat --refresh` then `wanted.bat --missing`.
- **Put a finished picture in the game:** `approve.bat <job-id> <wanted-name> [pick]` — copies it to the game path with a
  provenance record, after checking every model behind it is commercial-OK (refuses otherwise). `licence.bat` records a
  licence you checked yourself (e.g. a Civitai checkpoint's page); `licences.bat` prints the licence record of everything approved.
- **Judge a batch:** `review.bat <batch-or-suite>` → a page with 1–5 buttons → "Export ratings.json" → `rate.bat <same name>`.
- **Drafts from the game data:** `brief.bat maps|sleeves|icons` (drafts cannot be submitted until their prompts are written).
- **Queue control:** `"priority": 10` in a job runs it first; `pause.bat` / `resume.bat` park and restore waiting jobs.

## Scene sets, the dashboard and Krea 2 (added 2026-11-09, session 2)

- **A painted scene is a set of six files** (the game's HD-2D-feel pass): `scene.png` + `_n` (normals from a depth map) +
  `_e` (glow) + `_back` (far parallax plane) + `_over` (walk-behind plane) + `_depth` (16-bit, white = near). One
  `scene_kit` job makes all six (`jobs/templates/scene_kit.json`); `approve.bat <job-id> scenes/<map> --set` copies them
  into the game together, with one licence check, all or nothing. The pieces also run alone: `depth_map`,
  `normal_map` with `"source": "depth"`, `scene_layers`.
- **Dashboard:** `ui.bat` opens http://127.0.0.1:8765 — the queue with an ETA, what is rendering, batch progress,
  the newest pictures, failed jobs with Retry, Pause/Resume, and Approve (dry run first). Only this PC can see it.
- **No double runs:** `bakeoff submit` skips cells already queued or finished (`--force` to redo); `submit --skip-done`
  does the same for a plain batch. `eta.bat` says how long the queue will take.
- **Krea 2:** `graph: "krea2"` (core ComfyUI, no custom node; INT8-ConvRot files load natively). Needs
  `pull_model.bat qwen-image-vae`. Suite `krea2_v1` (not submitted). Krea 2 base models are commercial-OK under
  US$1M/year revenue — `approve` and `licences` print that condition.
- **Models:** `python -m forge models unusable` → `out/unusable_models.md` (what no graph can run, what is
  non-commercial, what still needs a licence check — report only). `licence.bat` with no arguments asks its questions.
- **Bake-off detail crops:** `bakeoff report <suite> --detail-at <prompt>=x,y[,size]` or `--detail-auto` (largest face).

## Licence

MIT (code). Models and palettes carry their own licences — `docs/LICENSING.md` and `models/models.json`.

## Bake-off scripts added 2026-11-09
- `bakeoff_tonight.bat` — queues the whole evening in order: the tools test → the finishing bake-off → new SDXL LoRAs → house styles → FLUX.2 klein → FLUX.1 + LoRAs; then `run_worker.bat`.
- `test_tools.bat` — 13 small jobs, one per paint tool (about 20 minutes); run it before any long run. `bakeoff_finish.bat` — the finishing bake-off (refine, FreeU, face repair per checkpoint, with 1:1 detail sheets).
- `bakeoff_new_models.bat` / `bakeoff_styles.bat` / `bakeoff_flux.bat` — the same runs one at a time.
- `pull_flux.bat [dev]` — fetches FLUX.2 klein 4B + FLUX.1 schnell and their encoders/VAEs into `models\` (dev is non-commercial; opt in).
- Verdicts and what each model is for: `docs/BAKEOFF_1_VERDICT.md`, `docs/NEXT_MODELS.md`.

