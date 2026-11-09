# RPG_Forge — what it does, what it should do, and the build order for the next Opus session

*Fable, 2026-11-09, at William's request ("what all does it do and what should it do that it doesn't yet… let's have Opus code them"). Read with `docs/CLAUDE.md` (how an assistant drives the forge), `docs/PROTOCOL.md` (the job files), `docs/BAKEOFF_1_VERDICT.md` and `docs/NEXT_MODELS.md` (the models). The game it serves is `D:\Turing Accords Game`; its art direction is `10_Art_Direction_and_Production.md §10.1b` — **1920×1080, painted scene backgrounds with walk polygons, characters at 144×216, vivid, composed.***

## 1. What the forge does today (v0.1 + 2026-11-09)

| Area | What exists |
|---|---|
| **Queue** | A disk job queue (`jobs/pending → running → done|failed`, atomic renames, receipts in `out/<id>/job.json`), CLI `submit · worker · status · requeue · retry · validate · doctor`, daily logs, a config that refuses to write outside the repo, Windows `.bat`s for everything. Claude writes jobs; the worker on William's PC runs them; nothing is lost if either side is away. |
| **GPU job types** (ComfyUI) | `scene_card` (16:9 card → palette), `concept`, `portrait` (seed-locked expression sets), `prop` (key-colour isolation → bg removed → trimmed), `tile_texture` (→ seamless → downscaled), `render` (the raw unit: any checkpoint + LoRA chain, any graph). |
| **Engines** | Code-built graphs: **SDXL** (checkpoint + LoRA chain + clip-skip), **FLUX.2 klein** (4B/9B, base/distilled, fp8 cast), **FLUX.1** (dev/schnell/fine-tunes; split files, all-in-one checkpoints, GGUF via the GGUF node; real CFG for de-distilled). `{{placeholder}}` JSON workflows for exotic graphs. ComfyUI driver over the local API; `comfy-paths` writes `extra_model_paths.yaml` from `forge.json`. |
| **CPU ops** (tested) | OKLab palette snap with animation hysteresis; pixel-grid detection + mode/median downscale; flood-fill background removal, trim, pad; contact sheets and sprite sheets; seamless tiles, seam score, jitter variants; Godot 4 TileSet writer. CPU job types `palette_snap · pixelize · remove_bg · contact_sheet · pack_sheet · godot_tileset`. |
| **Models** | Header-only scan of every model folder (kind, architecture, triggers → `models/INVENTORY.md`), a registry with licences and `pull` (HF download, flattens repackaged paths), `commercial_ok` flags carried into every `prov.json`. |
| **Bake-off** | `plan · submit · report · rate`; suites per game; checkpoints × compatible LoRAs × prompts with incompatible pairs skipped; discovery by folder / architecture / name; grids + `by_model` / `by_category` trees + `index.html`. |
| **Game glue** | `games/turing_accords/forge.game.json` (palette, sizes, style prefix, model picks per job type), batches, the Gate Law cards as the first real batch. |

## Status after the Night 2 forge session (Opus, 2026-11-09)

**Built and tested:** F1–F11, F18, F19, plus the quality stages (refine / FaceDetailer / FreeU) — see
`docs/HANDOFF_FORGE_2026-11-09.md`. **Not started:** F12–F17. GPU paths are proven only against a fake ComfyUI until
the first real run (`docs/FOR_FABLE_FORGE_2026-11-09.md` is the test checklist).

## 2. What it should do and does not yet — in build order

Each item: why, what, done-when. The order follows what unblocks the game soonest under `10.1b`. **P0 is a night's work; P1 a second; P2 as time allows.**

### P0 — the painted-background pipeline (unblocks every room in the game)

**F1 · Upscale stage + `scene_paint` job.** *Why:* the game is 1920×1080 and SDXL paints at ~1 MP. *What:* an `upscale_models` registry entry (`4x-UltraSharp` or `RealESRGAN_x4plus`, both free) + `pull`; an `UpscaleModelLoader → ImageUpscaleWithModel → ImageScale` tail that any graph can take (`upscale: {"model": …, "factor": 2, "fit": [1920,1080]}`); `scene_paint` = render at 1344×768 (or the size the job gives) → ×2 → cover-fit to the target (default 1920×1080; `2560×1080` for scrolling streets) → `scene.png` + `raw.png` + prov. *Done when:* `forge submit` of one `scene_paint` job yields a 1920×1080 painting from ArtUniverse with prov, and `tests/` has a unit check of the graph tail.

**F2 · `repaint` (image-to-image) — the greybox→painting bridge.** *Why:* the game already has every map as a greybox render (`project/tools/greybox_to_painted.py` from the game's Night 2); a painting that *keeps that layout* means the walk polygons, doors and spawns stay valid. *What:* `LoadImage → VAEEncode → KSampler(denoise 0.45–0.7)` on the SDXL graph (and the FLUX graphs' equivalents), `denoise`, `strength`, `init` fields; the handler copies the init into ComfyUI's input folder (`out/_comfy_in/`) first. *Done when:* a greybox PNG of `bills_house` repainted at denoise 0.55 keeps its room layout and reads as a painting (contact sheet of 3 denoise values).

**F3 · ControlNet for SDXL (depth + canny, the "union" model).** *Why:* when F2's denoise is high enough to look good, layouts drift; ControlNet pins them. *What:* registry entry for an SDXL ControlNet union (`xinsir/controlnet-union-sdxl-1.0` — check licence; Apache-2.0 at last look), `ControlNetLoader → ControlNetApplyAdvanced` in the graph builder behind `control: {"type": "depth|canny", "image": …, "strength": 0.6}`; a CPU `canny` op (PIL/numpy) so no preprocessor node is needed for edges; depth via the ComfyUI aux node if installed, else skipped with a clear log. *Done when:* the greybox's edges drive a painting whose walls are where the greybox's were (overlay check image written beside it).

**F4 · The asset manifest — what the game wants vs. what the forge has made.** *Why:* the game's `make_placeholders.py` is the complete list of files to replace; today nobody can see the gap. *What:* `games/turing_accords/wanted.json` generated from the game (a small script in the game repo exports: path, kind, size, notes — Opus can write the exporter on the game side as part of the forge night, read-only), `forge wanted` lists missing/approved/stale, `forge approve <job-id> --as <wanted-name>` copies `card|scene|…png` + `prov.json` to the game path from the manifest (by path, no code changes), refuses non-`commercial_ok` provenance, and records the approval in the batch. *Done when:* `forge wanted` shows the Night 1 placeholder list with 0 approved, and approving one Gate Law card lands it in `project/assets/vignettes/` with provenance.

**F5 · Pipelines (job chains).** *Why:* "render → upscale → palette → approve-candidate" is one intention, today four files. *What:* `type: pipeline`, `steps: [ {type, …}, … ]`, each step's output feeding the next (`$prev.outputs[0]`), one `out/<id>/` with step sub-folders, one receipt; the queue runs steps in order and fails the chain at the first error with the step named. *Done when:* a pipeline of `render → upscale → palette_snap` runs end to end and the contact sheet shows all three stages.

### P1 — breadth for the game's content

**F6 · `icon` job type.** `prop` with a square canvas (256/512), padding, optional palette snap, game_icon LoRA default; batch of 20 from `items.json` names. *Done when:* 20 inventory icons on one contact sheet.

**F7 · `sleeve` job type (159 record sleeves).** Art by SDXL at 1024² + **typography by PIL** (title, artist, a small "record" mark) from `records.json`, fonts from `assets/fonts` (OFL), two layouts; deterministic text beats asking a model to spell. *Done when:* 10 sleeves render with legible titles and the batch generator writes all 159 from the game's `records.json`.

**F8 · Review sheets as a command.** `forge review <suite|batch> [--by category|model] [--thumb 256]` produces the readable labelled grids Fable built by hand today (`out/bakeoff/sdxl_v1/review/`), plus a one-page `index.html` with radio buttons that *export* a `ratings.json` (no server) → `rate` import. *Done when:* `forge review style_v1` reproduces today's sheets for the new suite.

**F9 · `doctor` checks the graphs before a 7-hour run.** Query ComfyUI `/object_info` and list which node types each graph needs that the install lacks (`Flux2Scheduler`, `UnetLoaderGGUF`, `ControlNetApplyAdvanced`…); check every model file the queued jobs name exists; estimate VRAM by file size and warn. *Done when:* `doctor.bat` says "flux2_klein: OK · flux1 gguf: UnetLoaderGGUF missing → install_comfy_gguf.bat".

**F10 · Batches from the bible.** `forge brief games/turing_accords/maps` reads `project/data/maps/*.json` `notes` + `15.2` and writes a `scene_paint` batch draft per map (camera, time of day, idiom words), for Claude to edit rather than write from zero. *Done when:* a draft batch exists for every Act I map.

**F11 · Lighting helpers.** CPU `normal_map` (height-from-luminance → tangent-space normals, strength parameter) and `emissive_mask` (colour-threshold masks for cores, screens, neon) for the game's painted maps (`_n.png`, `_e.png` slots). *Done when:* both run on a scene painting and Godot shows the light responding (William's eyes).

### P2 — characters and the rest

**F12 · Turnaround → parts (the cut-out rig prep).** From a 3-view/8-view turnaround sheet (SpriteGen2 or hand-drawn): detect columns, remove bg, normalise heights, split into `front/back/side` PNGs, and write a Godot `Skeleton2D` scene template with `Polygon2D` placeholders named for the parts. *Done when:* Sarah's turnaround becomes a rig William can open.

**F13 · `render_text` via MOSS-Image** (`docs/NEXT_MODELS.md`): the graph, the registry entries, a job type for signs/screens/title cards. *Done when:* "NO ROBOTS" renders legibly on a bar sign.

**F14 · Reference-image consistency** (IP-Adapter for SDXL, or FLUX.2 klein's reference-image editing graph) for portraits and props across sessions. *Done when:* one face holds across 7 expressions without a per-character LoRA.

**F15 · Depth → layers** (ComfyUI aux depth node): split a painting into back/mid/fore bands for parallax and the walk-behind overlay. *Done when:* a street painting yields an overlay PNG of its foreground.

**F16 · A local dashboard** — `forge ui` (stdlib `http.server`, no new deps): queue state, recent outputs with contact sheets, Approve/Reject that call `approve`; colour-coded by job type and model licence. William's rule: the better a tool looks, the more it is used. *Done when:* he approves a card from the browser and it lands in the game.

**F17 · Krea 2 graph** when the file list is confirmed; **F18 · priority/pause/resume** in the queue (`priority`, `jobs/paused/`); **F19 · `licences` report** for every approved asset.

## 3. Rules for the forge session (read before touching code)
1. **The GPU worker is probably running** (`doctor.bat` / `status`). While `jobs/pending` is not empty, **do not edit** `forge/queue.py`, `forge/jobs/*.py`, `forge/engines/comfy.py`, `forge/engines/*_graph.py` or `forge/bakeoff.py` — the worker hot-reloads handler code before each job and a half-written edit fails a 7-hour run. Build new features as **new modules** (`forge/ops/…`, `forge/engines/upscale.py`, `forge/manifest.py`, `forge/pipeline.py`) with their own tests, and wire them into the handlers/CLI as the **last step, only when the queue is empty**; otherwise leave the wiring as a documented stub and say so in the hand-off.
2. **Tests first and after**: `python -m pytest` in William's venv (`pytest.ini` is set); every new op gets a unit test; graph builders are pure dicts and are tested as dicts.
3. **Never write outside the repo** or the game's asset folders named in `forge.game.json`; never put a non-`commercial_ok` model in a shipped-asset path (`approve` must refuse).
4. **Windows first**: a `.bat` for every new command; `chcp 65001`; no nested-quote blocks.
5. **Docs**: `docs/JOB_TYPES.md` is generated (`forge docs`); update `docs/CLAUDE.md`, `README.md`, `CHANGELOG` via `COMMIT_MESSAGE.txt` (append if one exists).
6. **No art decisions**: the forge makes pictures when asked; which pictures, which style, is William's and Fable's. Test renders go in `out/_tests/`, never into the game.
7. **Hand-off**: `docs/HANDOFF_FORGE_<date>.md` — built · tests · how to try each new command (one line each) · what is stubbed and why.
