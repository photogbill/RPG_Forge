# Working the forge as an AI assistant

This file is the hand-off for an assistant (Claude, or any agent) that can read and write the repo
folder but cannot run the GPU itself. It is written so a fresh session can drive the forge from this
page alone.

## What you can and cannot do

- You **can**: write job and batch files into `jobs/pending/`; read `jobs/done/`, `jobs/failed/` and
  `out/<id>/`; look at `out/<id>/contact.png` (that is how you grade a batch); run the CPU side yourself
  (`python -m forge worker --once` with no GPU) if you have Python where the files are; edit
  `games/<game>/forge.game.json` and batches; add palettes; regenerate docs.
- You **cannot**: run diffusion. GPU jobs wait until the person starts `run_worker.bat`. Say so when you
  queue them ("queued 21 cards; they'll render when the worker is up").
- You **must**: keep every output's `prov.json` with it when you copy approved assets into a game; put
  only `commercial_ok` models in shipped-asset jobs (`models/models.json`); never write outside the repo
  folder or the game's own asset folder.

## The loop, concretely

1. **Brief → batch.** Turn a design sheet into a batch file under `games/<game>/batches/`. One job per
   asset, `name` = the asset's slug, `prompt` = the picture in plain words (subject, action, light,
   mood); do not restate the style — `style_prefix` in the game config carries it. Set `variants` 2–4
   when you want a choice; 1 when the brief is exact.
2. **Submit.** `python -m forge submit games/<game>/batches/<batch>.json` — or, with no Python at hand,
   write the job files straight into `jobs/pending/` following `docs/PROTOCOL.md` (ids optional).
3. **Wait for the worker.** Check `jobs/done/` and `jobs/failed/`. A failed job's `error` tells you why
   (missing model, ComfyUI down, bad input path); fix and resubmit — never silently drop it.
4. **Grade.** Open `out/<id>/contact.png`. Judge against the brief: subject right? read at target size?
   palette holding? composition clear at 288×162? Write the verdict in one line per card.
5. **Correct.** Re-queue only what missed, with a changed prompt phrase or a fixed `seed` from the
   variant that was close (seeds are in `prov.json`). Same `name`, new job → a new id; the old stays.
6. **Approve.** Copy the approved file + its `prov.json` into the game's asset folder (for a Godot
   game: `project/assets/<kind>/…` plus `project/assets/_provenance/<name>.json`). Record what
   was approved in the batch file's `approved` list so the next session knows.

## Committing

You cannot push (git credentials live on the person's machine). Whenever you change files in the repo,
write **`COMMIT_MESSAGE.txt`** at the repo root — a one-line title, a blank line, then what changed and
why, ending with your `Co-Authored-By` line — and tell the person to run `push.bat`. The script commits
with that file as the message, pushes, appends it to `CHANGELOG.md` and keeps it as
`COMMIT_MESSAGE.last.txt`, so the next session can read what the last push said. If a
`COMMIT_MESSAGE.txt` already exists when you start, the last change has not been pushed yet: append to
it rather than overwrite it — **and rewrite its first line so the title covers everything in the file** (push.bat
uses the first line as the commit title; on 2026-11-10 Night 3, 3B and the sprite run were all pushed under the old
title "Krea 2 cut…", which made `git log --oneline` look as if they had never been committed).

## Running a bake-off (choosing models)

The person's model collection is in the folders listed by `forge.json → model_dirs`. Before proposing a
checkpoint or LoRA for anything, read `models/INVENTORY.md` (regenerate with `python -m forge models scan`):
it says which files are SDXL, which are SD1.5 or FLUX (unusable on SDXL), and the trigger words.
To compare them, edit or copy `games/<game>/bakeoff/*.json` (test prompts per asset kind; keep the house
`style_prefix` *out* — a bake-off tests the model, not the style), run `python -m forge bakeoff plan` to see
the counts and skips, `submit` to queue, and after the GPU worker has run, `report` and look at
`out/bakeoff/<suite>/grid_*.png` — rows are checkpoints, columns LoRAs — or open `by_category/<kind>/<prompt>/` (every model's take on one picture, side by side) and `by_model/<checkpoint>/<lora>/` (everything one model made). Rate what you see with
`bakeoff rate` (or `review <suite>` → the page → `rate --import`) and write the conclusions into the game config (`checkpoint`, per-job-type `loras`) so later
jobs inherit the winners. Prompt in your own words; never prompt a named artist's style.

A category can queue one of the forge's **tools** instead of a raw render — `"type": "scene_paint"` (or icon, sleeve,
repaint …) plus `"job": {…extra fields…}` — so a suite compares *treatments* on the same picture and seed. The report
then also builds `across_<picture>_…png` (rows checkpoints, columns categories — this works for style suites too) and,
with `"detail_crop": N`, `detail_<picture>_…png`: the same grid as a 1:1 crop. Judge refine, face repair and upscalers
on the detail sheets; they are invisible on thumbnails. `games/<game>/bakeoff/finish_v1.json` (in your game folder) is the model
(`bakeoff_finish.bat`). Keep the model bake-offs raw — a finishing chain on every cell multiplies the hours and hides
what the model itself did; finish only the survivors.

**Before any long run, run the tools test** (a small batch of one job per tool — `games/<game>/batches/tools_v1.json`, 13 jobs,
priority 10): one small job per tool, so a missing node or model fails in minutes, not at 3 a.m.

## Writing prompts that work

- Say what is *in* the picture and where the light comes from; one sentence, concrete nouns. The
  game's `style_prefix` adds the medium ("painterly, muted palette, soft edges, 16:9 scene card").
- For a card series, keep the camera consistent across the set ("medium-wide, eye level") and vary only
  the scene — the set then reads as one artist's work.
- Portraits: one base description (the character brief) and short expression phrases ("listening,
  slight smile", "eyes down, grief") — the handler keeps the seed, so the face holds.
- Props: name the object, its era and material, and say "single object" — the handler adds the key
  background and the isolation words.
- Tiles: name the surface and the scale ("cracked asphalt, top-down, one square metre") — the handler
  adds the seamless/top-down words.

## Reading results

`out/<id>/` — `card.png` (final), `raw.png` (the render before downscale/snap — keep for a re-snap
with a new palette), `contact.png` (variants), `prov.json`, `report.json` (palette/colour counts for
CPU jobs), `job.json` (receipt with timings). `jobs/failed/<id>.json` — `error`, `traceback`.

## A game's own pieces are not in this repo

RPG_Forge is a public, game-agnostic engine (William, 2026-11-10): **nothing specific to one game is pushed.** A game's
forge data is `games/<game>/` (git-ignored; start from `games/_example/`); its plans, hand-offs, kickoff prompts and
verdicts are `local/<game>/` (git-ignored). Read `local/<game>/CLAUDE_<game>.md` and the newest hand-off in
`local/<game>/docs/` before working on that game. Commit messages are public too: describe the forge change, not the
game's characters or story.

## Engines beyond SDXL (2026-11-09)

A `render` job (and therefore a bake-off suite) carries `"graph"`: `sdxl` (default), `flux2_klein` (FLUX.2 [klein] 4B — `forge/engines/flux2_graph.py`) or `flux1` (FLUX.1 dev/schnell and fine-tunes — `forge/engines/flux1_graph.py`). For FLUX the job's `checkpoint` is the diffusion-model file; text encoder and VAE default from `forge.json → comfy.flux2 / comfy.flux1`. A FLUX suite may **discover** its checkpoints instead of listing them: `checkpoint_dirs` (folders), `base_filter` (`flux1`), `checkpoint_include` / `checkpoint_exclude` (regexes on the name), `base_override` (pin the architecture when the header scan cannot tell). LoRA compatibility is checked by detected base (SDXL LoRAs never go on FLUX, FLUX.1 LoRAs never on klein); `lora_base_override` pins a LoRA with no metadata. Model folders: `forge.json → model_dirs` (William's collections: `sdmodels`, `lora models`, `flux_models`, `flux_lora`); after adding a folder run `python -m forge comfy-paths` and restart ComfyUI. Licences: klein 4B and FLUX.1 schnell are Apache-2.0; FLUX.1 dev and most Civitai FLUX fine-tunes are **non-commercial** — `models/models.json` flags them and `prov.json` records the flag; never put one in a shipped-asset job. Reading: `docs/NEXT_MODELS.md`, the bake-off verdicts in `local/<game>/docs/`.


## Painted backgrounds, the manifest and approval (2026-11-09, Night 2)

- **Paint:** `scene_paint` (prompt → 1344×768 render → RealESRGAN → cover-fit to `target`, default 1920×1080 → `refine`
  hires-fix at the final size → optional `face_fix`) and `repaint` (img2img from a greybox at its exact pixel size, `denoise`
  list for a sweep, `control: {"type": "canny"}` to lock the walls). Both take any `graph`. Checkpoint/LoRAs default from
  the game's `checkpoints_by_job` / `loras_by_job` for that type. Big targets (a scrolling street) refine at ≤4 MP and are
  upscaled after (`refine_max_mp`). Templates: `jobs/templates/scene_paint.json`, `repaint.json`, `pipeline.json`.
- **Know what the game wants:** `python -m forge wanted --refresh` reads the game folder (read-only) into
  `games/<game>/wanted.json`: every placeholder, vignette, per-map scene background (×3 size), every sleeve and icon.
  Names are paths under `project/assets/` without the extension (`scenes/town_square`, `vignettes/intro/01_title`).
- **Approve by path:** `python -m forge approve <job-id> --as <wanted-name> [--pick N] [--dry-run]`. This replaces the manual
  copy in step 6 above: it checks the licence of **every** model that touched the pixels (the job, its pipeline steps, and
  any forge job it was made from), refuses unknown or non-commercial ones, backs up what it replaces to
  `out/_approved_backup/`, writes `_provenance/<name>.json` in the game and records the approval. A Civitai model is
  "unknown" until a person checks its page and runs `python -m forge models licence <file> "<licence>" yes|no "<where>"` —
  never record one on their behalf.
- **Non-commercial models are a no-go for shipped art (William, 2026-11-09)** — none is registered as a default anywhere in
  the paint path (the upscaler is RealESRGAN BSD-3, not 4x-UltraSharp; depth is Depth Anything V2 *Small*; there is no
  CodeFormer/GFPGAN). Face repair is FaceDetailer only: it repaints faces with the job's own checkpoint.
- **Judge:** `python -m forge review <batch|suite> --by category|model` → `out/review/<name>/index.html`; ratings come
  back with `rate <name> --import ratings.json`. Drafts: `brief maps|sleeves|icons` writes a `_draft` batch from the game
  data — the prompts are the game's notes, not art direction; write them properly before submitting (submit refuses drafts).
- **Before a long run:** `doctor` checks ComfyUI's nodes per graph/stage and every model file the pending queue names.

## Scene sets, the dashboard (2026-11-09, session 2)

- **A scene is six files.** `scene_kit` (one job) = paint (`scene_paint`, or `repaint` when `init` is given) →
  `depth_map` → `normal_map` (`source: "depth"`, `detail` blends brush texture back in) → `emissive_mask` →
  `scene_layers`. The six slot files land at the top of `out/<id>/`: `scene.png`, `scene_n.png`, `scene_e.png`,
  `scene_back.png`, `scene_over.png`, `scene_depth.png` (+ `scene_mid_alpha.png`, an extra outside the contract),
  `layers.json`, `contact.png`. Contract: OpenGL normals; depth 16-bit, white = near; all at the painting's size except
  `_back` (wider by `overscan` px per side). The painting itself is never altered after painting.
- **Depth is Depth Anything V2 Small only** (Apache-2.0). The aux node's own default is Large (CC-BY-NC):
  `forge/jobs/scene.py depth_graph` always names Small and refuses to build without it. Never change that.
- **Approve a set:** `approve <id> --as scenes/<map> --set [--dry-run]` — one licence check over every model in the
  chain (the depth model included), all-or-nothing, one provenance file per slot. `wanted.json` lists the five
  companions as `scenes/<map>_n` … with `optional: true` (`wanted --missing` hides them; `--all` shows them).
- **Do not queue twice:** `bakeoff submit` skips cells already done/pending/running/paused (failed ones re-queue);
  `--force` overrides. `submit <batch> --skip-done` for plain batches (by batch + name + type).
- **Krea 2 is cut — do not propose it** (William, 2026-11-09: "if Krea 2 has that license, we won't use it
  period"). The scanner still recognises Krea 2 files so `models unusable` lists them for deletion. `approve` /
  `licences` print any `licence_condition` a registry model carries (none today).
- **Dashboard** `python -m forge ui` (`ui.bat`), `forge/ui.py`: read-only except Retry / Pause / Resume / Approve
  (POSTs need the `X-Forge: 1` header). **ETA**: `forge/eta.py`, `eta.bat`.
- **Detail crops:** `bakeoff report <suite> --detail-at <prompt>=x,y[,size]` / `--detail-auto` → saved in
  `out/bakeoff/<suite>/detail_at.json`; `report` and `review` both read it (`forge/detail.py`).
- **Models:** `models unusable` (report only, never delete); the scanner now tells flux2 / flux3 (and krea2) apart from
  FLUX.1 (ComfyUI's own detection keys). `licence.bat` with no arguments asks one question at a time.
- **Writing files into D:\RPG_Forge from a cloud session:** a commit over an existing file sometimes does not land.
  Commit to a new path (`_incoming/`, git-ignored) and `mv` it into place from `device_bash`, then check `md5sum`.


## Night 3 (2026-11-09) — read this for anything added that night

- **Plug-in job types** (`forge/plugins/<name>.py`: `JOB_TYPES`, `HANDLERS`, `DEPENDS`). Night 3's: `scene_big`,
  `inpaint`, `scene_state` (GPU); `facings_pack`, `anim_preview`, `turnaround_split`, `nine_slice`, `button_states` (CPU).
  Their specs live in `forge/night3/specs.py` (no imports — a plug-in must not import `forge.jobs` at load time, because
  `forge.jobs` loads the plug-ins; handlers import lazily). `tests/test_night3_plugins.py` guards that they all load.
- **Reading results as a model:** `review <suite> --compact` (≤ 12 cells, labels in the picture, `review_index.json`
  maps cell numbers to job ids) and `--pairs A,B` (two treatments side by side with the 1:1 crop). Stage a sheet, read
  it, turn "cell 7" into `bakeoff rate <suite> <id> <1-5>` from the index.
- **Mornings:** `report night` first (`out/reports/night_<date>.html/.md`).
- **Big maps:** `scene_big` never climbs more than `max_step` (2×) per step (William: "6X disappoints usually").
  `scene_kit big: true` is not wired yet (see the per-game wiring notes in `local/<game>/docs/`).
- **States of a room:** `scene_state` with `greybox_base` + `greybox_state` (the mask is what changed; refused over 35 %).
  Outside the mask the picture — and, for a kit, every companion — is bit-identical to the base.
- **Before approving a kit:** `kit check <id> --map <map>`; `approve --set` runs it and refuses on a *fail*.
- **Prompts:** write style words once as blocks in `games/<game>/prompts/*.json` and reference them as `{{style.house}}`.
  The shipped blocks are placeholders (`TODO …`) and refuse to expand until someone writes them. Never put a name from
  `never.json` in a prompt — `submit` refuses it (William's artist-LoRA ruling).
- **What to paint next:** `brief missing` → `games/<game>/batches/draft_missing.json` (a draft; every `{{block}}` must
  exist before it submits).
- **Credits:** `credits` → `out/reports/CREDITS_MODELS.md`.


## Night 4 (2026-11-10) — production

- **Sprites are William's** (he draws sheets in an outside tool and bulk-edits them). `sprite_intake` cuts, aligns and
  packs them: `python -m forge intake <sheet|folder> <character> [variant] [--tool "<name version>"]` runs inline (not
  queued) and, at a console, asks him whether the facing guess is right. The mapping file
  (`games/<game>/intake/<character>[__<variant>]/<sheet>.intake.json`) is the record; numbers are on `numbers.png`.
  Contract: `sheet.png`, one row, S,SW,W,NW,N,NE,E,SE, cell 144×216, feet at y = 210. Never mirror an `asymmetric`
  character without saying so (a holster on one hip ends up on the wrong side).
- **Characters:** `games/<game>/characters/<id>.json`. Inheritance runs in a submit shim (`forge/cli_night4.py`) until
  WIRE_NIGHT_4 moves it. `character_set` is expanded at SUBMIT (registry + blocks → plain-text renders).
- **Production:** `produce plan` writes `games/<game>/batches/produce_plan.json` (+ .md); it adds TODO placeholder blocks
  (`place.<map>`, `culture.<town>`, `fate.*`, `enclave.*`, `sleeve.*`, `icon.*`) to `prompts/night4.json` with the
  game's own words inside — **those words are Fable's to write**. `produce queue` refuses while any is TODO.
  **Never run `produce queue` without `--dry` from an assistant session against William's live queue** (it submits).
- **Delivery:** approve (and `deliver`) record every copy into the game in `games/<game>/delivered.json`; `deliver undo`
  puts back what was replaced. `deliver hold` approves without copying (for sessions that can't reach the game).
- **Feedback:** `feedback-in` turns `playtest/art_feedback.json` into drafts in `jobs/drafts/` — never queued.
- **Photographs:** `photo_plate` refuses any frame not listed in the git-ignored `games/<game>/refs.local.json` with
  `people: none` or `people: william`.
- `models-report`, `housekeeping`: report only. Nothing in the forge deletes a file.
