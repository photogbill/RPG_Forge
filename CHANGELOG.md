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


