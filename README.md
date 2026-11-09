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

Full field reference: `docs/JOB_TYPES.md` (generated from the code).

## Quick start (Windows)

1. `install.bat` — Python venv + the CPU tools. Run `run_cpu_worker.bat` and you can already snap,
   pixelize and pack.
2. `install_comfy.bat` — clones ComfyUI into `engines\ComfyUI` with CUDA PyTorch (one big download).
3. `python -m forge models pull sdxl-base-1.0` (inside the venv) or drop any checkpoint into `models\checkpoints\`.
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
forge/            the package: queue, schema, cli, ops/ (image maths), engines/ (ComfyUI), jobs/ (handlers)
forge.json        configuration (paths, ComfyUI url, defaults)
jobs/             pending/ running/ done/ failed/ — the queue; templates/ — one example per job type
out/              results, one folder per job id
models/           weights (ignored) + models.json registry with licences
palettes/         master palettes (.hex, Lospec format)
games/            per-game config and job batches (turing_accords is the first)
docs/             PROTOCOL.md · JOB_TYPES.md · CLAUDE.md · LICENSING.md · ROADMAP.md
tests/            pytest (CPU side; 20 tests)
```

## Status

v0.1 — the queue, the CLI, the CPU tools and the ComfyUI driver are real and tested; the GPU handlers
run against an SDXL workflow out of the box. FLUX.2 klein and Qwen-Image-Edit workflows are added by
exporting from ComfyUI (`forge/engines/workflows/README.md`). The sprite pipeline (image → 3D proxy →
8 facings → pixelize) and the overworld job are designed in `docs/ROADMAP.md` and not built yet.

## Licence

MIT (code). Models and palettes carry their own licences — `docs/LICENSING.md` and `models/models.json`.
