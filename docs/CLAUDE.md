# Working the forge as an AI assistant

This file is the hand-off for an assistant (Claude, or any agent) that can read and write the repo
folder but cannot run the GPU itself. It is written so a fresh session can drive the forge from this
page alone.

## The rpg-forge connector (BUILD 83)

If your tools include `forge_status`, `forge_call` and the rest (the rpg-forge connector), use them instead of writing files by hand: `forge_status` first, `forge_search` for an operation's input, `forge_call` with `who` = your own name ("Claude Fable" / "Claude Opus"), `dry_run` for anything big and an `idempotency_key` for anything you might retry. `docs/MCP.md` has the whole of it. Without the connector, what follows still holds.

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


## The map camera and block-outs (BUILD 33, 2026-11-12) — read before painting anything an actor walks on

- **A walkable map is painted from one fixed camera**, which the game's art bible states (for the first game: high above,
  looking north, no vanishing points; back walls whole, side and south walls cut low). The cinematic eye-level pictures
  the place bake-offs judged are scene cards, not maps. Never paint a map from a prompt alone and hope the floor matches.
- **Draw the plan first.** `games/<game>/scenes/<map>.plan.json` → `forge/layout/oblique.py` (`docs/FLOOR_PLANS.md` has
  the table): guide, depth, lines, over, normal, glow, walk rings, anchors. Look at the guide yourself before anything
  is queued — it costs nothing and it is where a room is designed. `check(plan)` and `reaches(plan, "start", anchor)`
  must be clean.
- **Build it from the texture library first.** `render(plan, textures=…)` fills every surface with a tiling picture
  (a texture bake-off's winners, a procedural texture tool's renders) at a true scale. Lit, that is already a place:
  the plan owns the layout, the library owns the surfaces, and a model is asked only for single objects and a gentle
  pass over the whole (denoise 0.35–0.5). Reach for a from-nothing painting only when this is not enough.
- **Light it before it is painted.** Give the plan a `"lighting"` block and use `oblique.lit(blockout)` as the `init`:
  where the lamps are and what colour the night is are design decisions, and a flat guide hands them to the model.
- **Paint over it** with `repaint` (`init` = the guide or the lit guide; `control` = the plan's depth or lines, `preprocessed: true`).
  Score what comes back with `oblique.agreement` and then with your eyes: is the hearth where the plan put it, is the
  door a door.
- **Put it in the game from the plan**, not by tracing: a game keeps a small installer beside its plans (the first
  game's is `games/<game>/scene_install.py`) that writes the painted map's size, walk rings, entity pixels, lights and
  over plane. The painting itself goes in by the owner's approval, as always.

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


## The suite (BUILD 01, 2026-11-10) — how a session works with a game's data from now on

- **One app, every game:** `forge.bat` / `python -m forge suite`. Code in `forge/suite/` never names a game; a game's
  shapes live in `games/<id>/workbench_adapter.py` (contract: `forge/suite/adapter.py`). `tests/test_suite_build01.py`
  fails if anything under `forge/` names a game (a short list of files the running worker reloads waits for BUILD 16).
  Commands default to `config.default_game(cfg)` (local/suite.json), never a literal.
- **Sign everything.** A session sets `FORGE_IDENTITY="Claude Opus"` (or Fable) or passes `--who`; the install's own
  identity (`local/suite.json`) is the person at the PC — never sign as them.
- **Write a game's data through the safe path** when the suite can: `safesave.edit(adapter, rel, [("set", pointer,
  value) | ("add", obj_pointer, key, value)], who, expected_hash=…, reason=…)`. It checks the hash, runs the game's
  own validator on a temp copy, backs up, replaces atomically and journals. Ids are refused; locked lines (a song's
  own words — `adapter.locked()`) are refused.
- **Approved means his.** Before changing anything with `approved_by` (or `status: approved`), don't: `edit()` turns
  it into a proposed change in `<game_root>/proposals/` for its owner. `approval.mark()` sets draft/flagged; only a
  person approves.
- **Journal what you do** that the safe path didn't: `python -m forge journal add <kind> <object> --note "…" --who
  "Claude Opus" [--game <id>]`. Read what happened first: `journal show --since <time>`, or `WORKBENCH_LOG.md`.
- **Times:** this Linux shell runs on UTC. `local/suite.json` → `"timezone": "America/New_York"` (or `FORGE_TZ`) keeps
  journal lines in the PC's local time; Windows needs nothing.
- **Never write test data into a real game.** The tests copy `games/_example` to a temp folder.

## The Mail, work orders, "while you were away" (BUILD 03) — every session, start and finish

**Start** (sign as yourself: `--who "<your name>"` or `FORGE_IDENTITY`):
1. `python -m forge away --who "<you>" --mark` — everything anyone else did since you last worked, lines they rewrote as
   word diffs (also written to `<game_root>/journal/DIGEST_for_<group>.md`). `--mark` starts your session there.
2. `python -m forge mail list --who "<you>"` then `mail read <id>` — your inbox is `<game_root>/mail/to_<group>/`
   (a group is the first word of a name). What the person answered or asked is a ruling; act on it first and reply
   in the thread saying what you did, what you didn't and why.
3. `python -m forge orders list --for "<you>"` — start at the top; close each with `orders done <id> --note "…"`.

**Finish** with a letter through the Mail, never a loose file:
`python -m forge mail send --from "<you>" --to "<person>" --subject "…" --body-file letter.md [--questions q.json] [--attach <path>]`.
`q.json` is a list of questions: `{"id", "question", "why", "recommendation", "default", "choices", "applies_to"}`.
`choices` are labels or `{"label", "value"}`; "something else" is always allowed. Give `applies_to: {"file", "pointer"}`
only when a choice maps to one data field — the person's Send then changes it through the safe-save path. Put what
only they can do on their list: `orders add --for "<person>" --title "…" [--detail …] [--priority now|soon|someday]`.

### Don't wait for me (2026-11-17) — when the person isn't waiting on your questions

The person can set a standing instruction (Tasks, top of the page; `local/suite.json` → `nowait`; only a person sets
it): **Wait for me** · **Take the defaults** · **Leave it to <an assistant they pick>**, after a wait of their choosing.
`python -m forge nowait` shows it, what went ahead under it, and what is whose call.

- **So always give a question a real `default`** — the thing you will actually do if nobody answers — and make it one of
  the `choices` (word for word) when a choice sets a data field. Under *Take the defaults* the forge writes a stand-in
  answer in your name from exactly those words (`default`, else `recommendation`); a default that is one of the choices
  applies its `applies_to` through the safe-save path as you (so anything a person approved becomes a proposal, never an
  overwrite); a default that is only words changes nothing. `mail send` carries the instruction out at once and prints
  what was taken — you can go on working.
- **A question left to you is a work order** ("Your call: …", priority now). `python -m forge nowait pending --who "<you>"`
  lists them with their choices; decide with `python -m forge nowait decide <letter id> --answers a.json --body "why"`
  (`a.json`: `[{"id", "choice" | "text", "note"}]`). Decide as the person would want, from the rulings book and the
  canon first; say why; prefer the choice that is cheapest to undo. Only the assistant named decides.
- **A stand-in answer is never the person's ruling.** It is marked `stand_in` in the letter and `provisional` in the
  rulings book; it stops the question being asked again, and the person's own answer replaces it whenever it comes
  (their inbox shows every one; Tasks lists them under "Went ahead without you"). Build on it as something that may
  change, and never quote it as what the person said.
- It covers questions in letters only. A file only the person has, pictures waiting for approval, a music brief and a
  build the queue marks as waiting still wait — don't work around those.

## Sprite intake and the character registry in the suite (BUILD 04)

- **A sheet's mapping is edited on the Sprite intake screen**, never by hand: `forge/suite/sprites.py` (open → save →
  make). The forge's first guess is written unchecked; saving the clicks marks it `checked_by_person` with `checked_by`
  and keeps the previous file in `intake/<who>/_history/`. A session may open and save a mapping too, signed as itself —
  but **facings on William's sheets are his to click**; don't save his mappings for him.
- `make_sheet` runs the same `sprite_intake` job as `sprite_intake.bat`, in-process (`night4/inline.run_now`), on the
  original sheet. **See-through gaps (wiring day W10):** `intake.foreground` clears exactly the mapping's `holes` when a
  person has decided (an empty list keeps every gap as figure), and gaps that pass the POCKET_* rule when nobody has;
  `detect` keeps them (`auto_pockets=False`) so the screen can offer them. The original sheet is never changed.
- **Cut off** (edges.md, report.json): a side is listed only where the figure meets the sheet's edge, or a box a person
  narrowed (`bbox_found` = the box detection drew; mappings made before wiring day have none).
- **The registry** (`forge/suite/cast.py`): the page edits only `seed`, `asymmetric` and `references` (format-preserving,
  `characters/_history/`, journalled). Look blocks are the art direction's words in the prompt library — not edited
  there. *Make the set* = the batch file `characters set` writes + `submit` (which resolves characters itself since wiring
  day W5 — the Night 4 shim is retired), printout shown; it refuses a TODO block.
- Wiring day (BUILD 16, 2026-11-11) did W1–W10 of `local/<game>/docs/WIRE_NIGHT_3.md` / `WIRE_NIGHT_4.md`. New items
  that need a file the worker reloads go into a new `WIRE_*.md`, for the next time the worker is stopped.

## Art production in the suite (BUILD 12)

- The Wanted board, Make a picture and Review & approve are `forge/suite/production.py` and `picture.py` over the forge's
  own functions: `produce.plan/queue/estimate/blockers` (queue takes `names=` for a selection), `deliver.hold/run`,
  `manifest.approve_set`, `kitcheck`, `feedback.draft_redo`, `handoff.hand_out`, `reviews.town_sheet/atlas_sheet`.
- **A session never queues William's live production** — the board's Queue is his button. From a session: `plan`,
  `plan_selection` (read-only) and `produce queue --dry`. Approving is his too (an assistant identity is refused).
- Approve = hold (the licence gate now, the copy at Deliver); a kit = `approve_set` (copies on confirm). Deliver keeps
  what it replaces in `out/_replaced/` and writes `games/<game>/delivered.json`.

## Feedback and finishing in the suite (BUILD 14)

- `forge/suite/finishing.py`: Called out (`feedback.list_drafts` / `draft_action` / `take_in`), mark-up (`markup` → a mask
  in `out/markup/<job>/` + `feedback.draft_redo` + a scene_state fix draft carrying the mask), the prompt library
  (`edit_block`: jsondoc, `prompts/_history/`, journalled), bake-offs (`cli.cmd_bakeoff` submit/report, printout shown),
  hand-offs (`handoff.hand_in`), the model shelf (`models_shelf.build`).
- **Look words are the art direction's.** A session may read the library and point at placeholders; it does not write
  a look block's words unless the person (or Fable, by name) asked for that block.
- `bakeoff.inventory(refresh=True)` and `bakeoff.submit` write under the repo root (`models/`, `out/bakeoff/`), not the
  cfg's paths — tests must never call them.

## Music — the board and composing together (BUILD 06)
The Music board (Story → ♪ Music) is every slot the game has, each with a state: needed → proposed → agreed → written →
delivered → in game. `forge/suite/music.py` holds the rules; the game's adapter says where the board record, the
profiles, briefs, song drafts and the score inbox live (defaults: `<game_root>/music/…`, `score_inbox/`). From a session:
- `python -m forge music board [--state needed] [--singer <name>]` — counts, "next most useful", the slots.
- `python -m forge music sheets` / `sheet <id>` — the profiles (voice · style 1, 2, 3 … · how their songs are built ·
  style notes · open spots). A profile is built from evidence only; anything you can't determine stays **open** and you
  ask in a letter (one per character is fine). Never infer a voice type: it is the bible's lock or `ask`.
- `python -m forge music propose <slot> --brief-file b.md --style style-N|new --who "<you>"` — a brief: the scene and
  what the song must do, whose voice, which style of their profile (measured against its example song) and what you'd
  do differently here, the form, tempo and metre, a motif, two or three alternatives. It goes to the owner as a letter
  with one question; their answer lands in the board through the Mail. A style still open can't carry a brief.
- `python -m forge music write <slot> --title "…" --file song.md --who "<you>"` — only after a yes (`agreed`): a
  Suno-ready file (the style input, then the lyrics with section tags; notes after). Every version is kept and credited.
What a session never does: answer its own brief, write before a yes, touch a slot that is the owner's own, deliver a
track, change a delivered (cemented) slot or its words, fill a profile field (that is the person's — you ask). A slot is
the owner's own from the start when they said so in writing: `music.record_own(adp, slot, who, "<file:line — the words>")`.
No game's music — sheets, briefs, lyrics, audio — is ever written into this repository.

## The read-through and notes on anything (BUILD 07)
The person reads a town in `forge.bat` → Story → 📖 Read-through and rules on each line (approve / draft / flag as
generic) or rewrites it; a ⚑ usually carries a note saying what is generic about it. You find all of it in your digest
(`python -m forge away --who "<you>"`): rewritten lines as word diffs (read them — how a person rewrites is the best
guide to their voice), approvals, flags, notes. Notes live in `<game_root>/notes/notes.jsonl` (`forge/suite/notes.py`:
`threads(root, obj)`, `add(root, obj, who, text, tag, reply_to=…)`, a resolving note closes a thread) — pinned to a ref
(`file#pointer`) or a key like `place:<id>` / `music:<slot>`. Answer a note by replying to it, and resolve it when the
work it asked for is done. A game's adapter can order a place's lines (`line_order`), give its sheet per era
(`place_sheet`), its own words and greeting for the sameness meter (`place_words`, `place_greeting`).

## How a letter to the person is written (the standard every session inherits)

One colleague writing to another, signed with your name, with a subject line. Say what you built, how to try it (the
first three things to click), what you're unsure of, what you'd do next, and only the questions you couldn't decide —
each with your recommendation and what you'll do by default. "I went ahead with X; tell me if that's wrong" for what
you could decide. No forms, no ticket numbers in the prose, no deference, no apology rituals — and none of it in the
other direction either; disagree plainly when you disagree. Humour is allowed. `games/_example/game/mail/` has three
letters written to this standard.

## Team memory — the rulings book, the idea box, playtest notes (BUILD 17)

**Before you ask the person anything, search the rulings book.** It holds every answer they have given: questions
answered in the Mail, every line marked ✦ in the game's notes (the files the adapter's `ruling_files()` names; `!x.md`
leaves a generated report out), and rulings written straight in (`<game_root>/rulings/rulings.jsonl`, append-only).
- `python -m forge rulings check "the question"` — exit 1 and the ruling(s) when it is already answered. `mail send`
  runs the same check on every question an assistant sends and **refuses** one already ruled on (`rulings.AlreadyRuled`)
  unless the question carries `asked_again` — why it must be asked once more. A person is never refused; the page warns.
- `python -m forge rulings search "words"` — the book, best match first. Read a ruling in its file before building on it.
- `python -m forge rulings record "…" --by "<person>" --source "where/when they said it, in their words"` — a ruling
  given in a chat. You write it down; you never make one (`--by` an assistant is refused). `--file/--pointer/--value`
  **pins** it to a data field: the book then warns whenever the data says anything else (Notes → Rulings, Home, and the
  safe-save path's `warnings`, journalled as `conflict`). `rulings conflicts` lists them. Retiring a ruling is a person's.
- **Idea box:** `python -m forge idea list` at the start of a session; sort each (`idea sort <id> --to task|note|letter|
  file|kept|dropped --where …`) and say where it went in your letter. The person files them with **I** anywhere in the suite.
- **Playtest notes:** `python -m forge playtest list` / `in` — the game's note key writes `<adapter.playtest_dir()>/notes.jsonl`;
  taking in routes Art → Called out (redo drafts), Writing → a note on the conversation's first line (else the place),
  Music → a note on the place, Bug/Balance/Other → a work order, and writes one letter per category (screenshots
  attached), replying in the category's thread next time. A note is never taken in twice (`playtest_inbox/routed.jsonl`).
- **Home → Where the game stands** is `forge/suite/standing.py`: n of m from the game's own checklist, lines approved,
  songs, questions answered — and the next most useful thing for the person and for the assistants.

## User Needs To Provide Image — the forge pool (2026-11-11)

- **Anything the forge can't make well becomes a request, not a guess.** A real person's likeness, a layout the model keeps
  ignoring after a bake-off, references only the owner has (his photo archive, sheets he made elsewhere). Add it with
  `python -m forge provide add --title "…" --why "what was tried and how it failed" --helps "what picture would help"
  [--count n] [--goes-to reference/provided/<id>] [--priority now|soon|someday] [--hold "until …"]`. The pool is
  `games/<game>/provide_requests.json` (forge-side — works without the game folder). Say *why* with evidence (the
  suite, the render count) and ask for the smallest thing that unblocks it (a stick-figure layout, three plain photos).
- `--hold` = listed but not yet a task (waiting on a verdict). `provide open|hold|withdraw <id>`; `provide list`.
- **The section:** Art → User Needs To Provide Image (`forge/suite/provide.py`, GET `/api/suite/provide`). Opening it —
  or Tasks — runs `provide.sync()`: each open request is filed once as a work order for the game's owner with
  `"provide": <id>` and `wants`/`goes_to`, so the card takes the file through `tasks.accept` like any task. A dismissed
  card is never re-filed. Uploading stays a person's act.

## Sampler bake-offs — every sampler at its own steps (2026-11-11, William's correction)

- **Samplers matter.** Comparing them at one step count each only shows that convergent samplers converge; judge them
  as a sampler × steps grid (e.g. 4/6/8/12/16/24/32/48 — `sprite_sampler_steps_sdxl_v1`).
- A `samplers` axis entry **always** names its own `steps` (and scheduler, and cfg where it matters); never leave them to
  the model default — that runs every sampler at one count and the test means nothing (sprite_flux1_v2 and
  sprite_samplers_klein_v2 made that mistake; v3 fixes it). `evals` = 2× steps for heun / dpm_2 / dpmpp_sde / dpmpp_2s_a.
- SDXL ranges: euler / euler_a 20–30 (euler_a above ~30 drifts), dpmpp_2m 20–30, dpmpp_2m_sde 25–35, dpmpp_3m_sde 30–45
  at cfg 4–6, dpmpp_sde / heun / dpm_2 15–25, uni_pc 12–25, lms 30–40, ddim 25–50.
- FLUX.1 dev-style (rectified flow): euler + simple 20–25 or + beta 24–30; dpmpp_2m / deis + beta 25–35; heun + beta
  15–20; cfg 1, guidance 3.5 (2–3 softer/more natural, 4–5 crisper). Ancestral/SDE samplers knock FLUX off its path —
  test them only as a control. Schnell and distilled klein: their trained 4 steps, euler. Klein's graph uses
  Flux2Scheduler (no scheduler choice); klein base cfg 5.



## The 3D workshop (BUILD 36, 2026-11-14) — picture → body → skeleton → motions, and trees

- **The methods live in `forge/threed/`** (game-neutral): `bodies` (a list → FLUX.2 klein pictures → TRELLIS.2 / Pixal3D
  models through ComfyUI's own MIT template, `template.py`; resumable, steps down the resolutions only for memory or time),
  `rig` (the rigging ComfyUI, engines/rig port 8189, started and stopped by the step itself), `motions` (the Quaternius
  library fitted under Blender, with each motion's ground speed), `tidy` (weld, loose scraps off, real size in metres,
  on the floor), `trees` (grown by rule from a species sheet), `line` (the whole line for a list, one report). The list
  files are the same format the first game's 2026-11-13 scripts read; those scripts stay as they are until the new code
  has made the same bodies from the same list on the real card, then become thin callers.
- **Job types** `model_3d`, `rig_body` (GPU), `fit_motions`, `grow_tree` (CPU, Blender), `line_3d` — a plug-in
  (`forge/plugins/threed.py`), so a running worker learns them without a restart. Each writes run.log, prov.json (with the
  licence line of every tool, `threed/licences.py`) and report.json. **The card lock** (`threed/cardlock.py`,
  `out/3d/_card.lock`): every step that puts work on the card through a ComfyUI takes it; it also still looks at both
  ComfyUIs the way the old scripts did, so it never lands on top of one. `python -m forge 3d lock` says who has it.
- **Never from a session against William's live queue:** the 3D tabs' buttons queue real GPU work. Test against the
  stand-in instead: `forge/threed/standin.py` answers like ComfyUI (art: the image-to-3D nodes, built from two real
  requests; rig: the rigging pack's real node list) and writes the files a real run would, with planted failures
  (`PLANT_FAIL`, `PLANT_OOM`, `PLANT_OOM_ONCE`, `PLANT_HANG`, `PLANT_NOFILE`, `PLANT_SLOW` anywhere in a request).
  `tests/fixtures/threed/fake_blender.py` stands in for Blender's Python; set `FORGE_TEST_BPY_PYTHON` to a Python with
  `bpy` (pip `bpy==4.2.0` on Python 3.11) to run the Blender scripts for real.
- **The suite's 3D area** is `forge/suite/threed.py` + `threed.js` (+ `viewer.html`, three.js in `vendor/three`). A *try*
  is one attempt at one character or thing (`games/<id>/threed/tries/<who>/<try>.json`): its words, four pictures, the
  pick, body, skeleton, motions, review. Approving and delivering are the person's; a session refuses itself. The rules
  learned the hard way are `threed/rules.py`: shown as warnings (A-pose, long coats / skirts / capes / wings / tails /
  loose hair, shiny cloth, hip gear, height in metres) — never refusals. The standing picture words are the game's
  prompt blocks `pose.threed_body` / `neg.threed_body` / `layout.threed_thing` / `neg.threed_thing`, else the forge's
  (`threed/defaults.json`). The 3D tabs queue at priority 5 (a whole-list run at 2), ahead of bulk queues at 0 — a person
  is waiting at the screen (forge.json `threed.priority` / `threed.line_priority`).

## The world queue (BUILD 39, 2026-11-14) — the standing list, the one launcher, the checks after every model

- **The list** is `games/<id>/wanted_3d/*.json` (a file holds one entry, a list, or `{"defaults", "entries"}`); the queue's
  own record of each thing is `wanted_3d/_state/<id>.json` — never edit those by hand, use the actions. Entry fields:
  `id, kind (body|prop|building|panel|tree), tier, words | image | adopt, real_size_m, first {where, order}, rank, hold`,
  plus `wreck_of`, `shared_body` + `head_words`, `glow`, `panel {...}`, `skip_motions`, `no_straighten`. Add things with
  `python -m forge 3d world add <file>` or the World list's form (signed). **The order of need when two things tie (`rank`),
  letting a held thing through and starting the launcher are the person's.** Approving is in Review, as ever.
- **Never start the launcher from a session** while a run or the art worker is using the card: `make_what_we_need.bat` is
  the person's. Test with `world.run(..., check_machine=False)` against the stand-in ComfyUI (`tests/test_world_build39.py`).
  Things that need no card (adopted models, panels, wrecks from intact models, trees) are made without asking for it.
- **The checks** (`forge/threed/checks.py`; every number in `forge.json` → `threed.checks`): *level* = the resting plane
  (widest contact patch, nearest vertical) and the structure's own up must agree before a lean is called; a lean up to
  `straighten_up_to_deg` (15) is straightened by the queue, more is held. *Loose* = pieces not joined to the main body
  that float or poke below its floor (the floor is fitted to the joined assembly only). *Glass* = flat near-white + metal 1
  + roughness 0. *Thin* = enclosed holes in the model's outline minus the picture's (limit 0.2). Validated on 85 models of
  the 2026-11-13/14 runs: every fault a person had found, plus several nobody had; no false hold on a body. Run them on any
  model: `python -m forge 3d checks <model.glb> --picture <png> --draw out.png`.
- **meshio / raster** read and write .glb and draw pictures without Blender; `meshio.place()` gives real size, floor and an
  optional straightening as **one node above the mesh** (the mesh is never rewritten). glb.info's size is conservative for
  rotated nodes; use `Glb.load(p).bounds()` for the exact one.


## What the second run taught (BUILD 40, 2026-11-14) — colours that hold, the picture gate, vehicles, flames

- **Colours** (`checks.check_colour`, on every kind): the colour texture as stored, seen from the picture's own view, against
  the picture — brightness, contrast and (bodies) the head. The cause is in ComfyUI's core bake (`BakeTextureFromVoxel` →
  `ApplyTextureToMesh` → `Save3DAdvanced` embeds the voxel colours with no colour-space step; no setting fixes it), so the fix
  is a **tone-curve match** (`tone_curves`: quantile match per channel, smoothed, never falling, slope capped at 3; not a
  fixed gamma). Bodies are put right by the queue (the body as made kept as `__as_made.glb`, the curves applied to the
  moving copy too); props and buildings are held with the matched version offered (`threed_world_colours`, the person's),
  because a prop's picture carries studio light the texture rightly doesn't. Validated on the 90 models of the two runs
  (`out/3d/world/_b40_validation/`). A body is always seen from the front half (40 of 40 face azimuth 0).
- **Glass**: `checks.fix_glass` paints the white-mirror panes (grown from the faces the check finds into touching near-white
  near-mirror faces) dark glass, roughness 0.18, metal 0; the queue applies it before the checks run again.
- **The picture gate** (`forge/threed/gate.py`, numpy only, numbers in `forge.json` → `threed.gate`): before a body is made
  from its picture — arm count (held out, hanging against the body, or a stump by reach), the pose from the hand's drop below
  the shoulder joint (A-pose 32–76°, T-pose 66–115°), head height over figure height by age band read from the words
  (child 0.135–0.19, teen 0.11–0.15, adult 0.10–0.165). Entry fields: `expects {arms}`, `age`, `seated`, `carried_object`,
  `gate` (false = off), `gate_tries` (3). On a miss the world queue paints again with a new seed (seed + 7919·n), keeps
  every try (`pictures/<id>__try<n>.png`, `<id>.gate.json`) and after three holds the thing with the tries side by side;
  `world.gate_anyway` / "Make the body from this picture anyway" is the person's. In the Bodies form it is a warning only.
  Validated read-only on the 40 body pictures: catches Kim's two arms (and both redo Kims), the A-pose drawn for a T-pose,
  the two cartoon children; no good picture caught. The stand-in ComfyUI paints a good A-pose figure (`standin.png`, with
  `arm_deg / arms / head / forearm` for tests).
- **Standing words** (`rules.standing_check` for the Bodies form, `rules.body_word_rules` in the queue): children and
  teenagers start "Hyperrealistic" and name real proportions; a missing limb gets its own pose words (but the picture model
  painted two arms under both wordings tried — a missing limb is made by cutting the finished body, `damage.py` is the
  place, not yet written); clothes get "no lettering, no badges, no logos, no name tapes".
- **Seated and standing-aid bodies** (`seated: true`, `carried_object: "cane"`): a skeleton, no motion fitting, said in the
  report (`motion_note`); Review shows the motions step as skipped.
- **Flames** (`damage.flame`, entry `flame {texture, source, width_share, min_val, scale}`): crossed cards stood where the
  model's own colours burn (flame-coloured, bright: sites gathered per fire, per candle), the flame picture's brightness as
  its alpha, emissive and unlit; the Viewer flickers them and opens night light for things with flame or glow.
- **Vehicles** go to TRELLIS.2 (`defaults.json` `_routes`); buildings stay with Pixal3D, which alone can take **a back
  picture** (`back_image` or `back_words`; `template.add_back_view` swaps in `Pixal3DMultiViewConditioning`). TRELLIS.2's
  conditioning takes one picture, so a body's back is never seen: Review's card asks "Seen from behind?".

## Places — towns as 3D stages (BUILD 34, started 2026-11-14) — the forge's half

- **A place plan** (`<id>.place.json`, `forge/threed/place.py`, game-neutral): the stage proof's scene plan grown up —
  metres, x east, y south, up z; `ground`, `solids` (plan-built, the proof's format), `things` (generated: building ·
  prop · vehicle · tree · panel · body, each with `at` or `footprint`, `size_m`, `turn`, `enter plan-built|shell|closed`,
  `door`/`front`, `closed_line`, `words`, `model` to share one world-list model), `road {type dirt|gravel|street}`,
  `lighting.lights`, `anchors`. `place.check()` says what is wrong in words.
- **Compiling** (`python -m forge 3d place compile <place.json> --game <id>`): (a) `<id>.stage.glb` — the plan-built solids
  modelled by `forge/threed/blender/build_stage.py` (moved from the game's `stage_proof\blender\`, prints `STAGE {...}`)
  in the rigging tools' Blender, no card; floors and lights stay the engine's, read from the plan as the proof does;
  (b) `games/<id>/wanted_3d/<place>.json` — every generated thing in story order with tier and real size; a thing nobody
  has described is written with `needs_words` and held (the world queue never makes it; no look is guessed); compiling
  again keeps what a person wrote and holds, never drops, a thing gone from the plan; (c) `<id>.things.json` — what stands
  where: world-list id, at, turn, real size and the grey box's size, dust by road type, the lamps.
- **A town's layout** becomes a place plan: `place.from_town(layout_record, grid, sheet, metres_per_tile, entities)` /
  `3d place from-town <plan set folder> [--sheet s.json]` — roads by the sheet's road type, buildings as things facing
  their streets, fences as plan-built solids, spawns and doors as anchors; what the sheet doesn't say is listed to ask.
- Tests: `tests/test_place_build34.py` (the stand-in Blender, and for real when `import bpy` works — `pip install bpy`
  gives Blender 5.3 as a module in the session's container).
- **Not yet (the game's half, next sessions):** the stage map kind in `project\` (the proof's loader, saves, cues,
  dialogue, fights), the one camera, doors that open (plan-built: roof and near walls give way; shells: question 1),
  dust, people at real size, Linden Mills court's place plan, 3D → Places, the frame rate.

## What the third run taught (BUILD 73, 2026-11-17) — the face not the hair, matched not held, capes, cut-outs

- **The head check** (`checks.head_check`, `face_split`, `face_verdict`): the head band is read from the **level front view**
  in both the model and its picture (the aligned view was often 53° from above — through the hair), and the face (skin by
  chromaticity and brightness near the face's own middle) and the hair are measured apart: two numbers. A picture whose
  face is more than a third darker than its own neck (a hat's shadow) is said so and never holds the thing on its own.
- **Matching a body** (`fix_colour(..., mode="auto")`): three ways in turn — one curve fitted on brightness through all three
  channels alike (`luma`: the bake's own fault undone), one curve a colour (`rgb`, BUILD 40's), a brightness gain (`gain`) —
  and the first is kept whose numbers pass, whose whites stay white (`neutral_drift`), whose skin does not move from the
  picture's colour (`skin_shift`) and whose colours are no louder than the picture's (`loudness`). BUILD 40's per-colour curve
  alone turned white shoes pink and a white coat mint. When the face alone is still wrong, **a curve for the head alone**,
  feathered at the neck (`fix_head`, `head_weights`; head.png shows before / after / picture at twice the size); still wrong:
  "the face did not come through — make the body again", and the queue spends one try (`face_redo`). A matched body is
  **made** (`colour_matched: true`); a prop stays held with the match offered (William, 2026-11-17 11:50).
- **Props** (`prop_check`): against the picture with its highlights out (the tail above the 90th percentile not counted), the
  middle compared and the shadows not crushed; a dark thing (picture's middle under 70) is held only for lost detail.
- **One button for what is left** (3D → World list): **Match and release** (rows of as made · matched · picture, ticked, one
  button — props to Review, bodies back to the queue for their skeleton only, `reuse_body`), **Straighten and release**, and
  **Which way is up?** (three small pictures, a click). All journalled with who pressed.
- **Capes** (`worn_over` on a body → `cloth` entries, `world.worn_pieces`; the body's words lose the piece, `worn_words_out`;
  `blender/cloth_pin.py` pins a made cape to the shoulder and collar bones into `<id>_worn.glb` with a `cloth` block for the
  game's spring — `cloth.pin`, `world.pin_worn`). **Nudges** (`gate.nudge`): a pose miss sends new words to the next try.
  **Mesh words** (`world.MESH_WORDS`) plan a cut-out from the start (`needs_panel`, held); `world.supersede` retires a solid
  made another way. **Stale jobs**: `python -m forge housekeeping --stale-jobs` (`forge/stale_jobs.py`, never deletes).
- Tests: `tests/test_build73.py`. Read-only validation: `out/3d/world/_b73_validation/`.

## The ground is true (BUILD 77, 2026-11-17) — DTED Level 0, bakes, the line through a mountain

- `forge/terrain/dted.py` (the reader; zips read in place), `bake.py` (window, shade, water, edits, profile), `proof.py`,
  `forge/cli_terrain.py` (`python -m forge terrain status|check|proof|bake|profile`), 3D → **Terrain** (`suite/terrain.py`,
  in `threed.js`), `terrain_bake.bat`, `terrain_profile.bat`. All in `docs/TERRAIN.md`. The data path is `forge.json` →
  `dted_dir` (default `local/dted`, ignored). A game's windows are geography (`games/<id>/terrain/world.json`); its story's
  edits and lines are in the game's own folder (`terrain/story.json`). Tests: `tests/test_terrain_build77.py`.

## The same person, changed (BUILD 74, 2026-11-17)

- `forge/threed/same_person.py`: the job's contract (`validate`), the region (`region_mask`, `grow_feather`), the check that
  nothing else moved (`moved`, `check_picture`), the three graphs (`graph_masked` RealVisXL inpaint, `graph_guided` union
  ControlNet openpose, `graph_instructed` FLUX.2 klein 4B + ReferenceLatent), the bake-off (`bakeoff`;
  `same_person_bakeoff.bat` — William's to start; cases in `games/<id>/same_person_bakeoff.json`). What the disk can do:
  `docs/EDITING_MODELS.md`. A body's **bearing** (`motions.add_bearing`; easy, proud, tired, wary, warm — from its words or
  `"bearing"`), written into its motion sheet by the world queue. Tests: `tests/test_same_person_build74.py`.

## The voice bench (BUILD 71, 2026-11-17)

- Characters → **Voice bench** (`suite/voicebench.py` + `voicebench.js`): Face (a portrait set, or one picture with a
  STAND-IN mouth from a dragged box), Script, Voice (cuts, samples, a file, or an engine), Test (two lanes — `loud` and
  `rhubarb` — the words under the waveform, offset and blend), takes with verdicts, voice cards only a person locks.
- `forge/suite/mouthrule.py` is the game's MouthModel in Python; `tests/fixtures/mouth/cases.json` is read by both.
- `forge/voice/`: `loud`, `lipsync` (Rhubarb), `hear` (Whisper large-v3 in its own environment), `engines/` (the contract;
  `pretend`, and Qwen3-TTS, Kokoro, Chatterbox as descriptions until installed), `bench` (takes, cards, verdicts, learned),
  `tools` (homes inside `engines/voice/_home`, `logs/voice/`, the card asked for), `licences` (the gate). Job types
  `lipsync`, `hear`, `speak` (`forge/plugins/voice.py`). `get_rhubarb.bat` / `.command`, `get_whisper.bat`,
  `python -m forge voice …`. The adapter hook is `voice_paths()`. Tests: `tests/test_voicebench_build71.py`.

## Approvals made easy (BUILD 78, 2026-11-18)

- `forge/suite/approve_all.py` + `approve.js`: **Approve everything here** on 3D → World list and Art → Review & approve
  (one plain line a group; the page's own functions), **Undo** a thing (`out/approvals/<game>.jsonl`), and the setting
  **"Fable may approve for me"** (`games/<id>/approvals.json` default; the person's switch in `local/suite.json` wins).
  An assistant approves only through `approve_all.signer()`, which writes "Claude Fable, for William" — use it (or
  `threed._approver`) for any new approving action; `_person()` stays for what is never an assistant's (starting runs,
  installs, deliveries, standing words). CLI: `python -m forge approvals …`, `python -m forge world-fix …`.
- **A running world queue**: edit no existing forge file. Leave the edit as a package in `_xfer/waiting/<name>/`
  (`manifest.json`: files with `base_md5`/`new_md5`, `tests`, `after` steps, `sign_as`, `says`, `then_tell`) for
  `put_in_waiting_changes.bat`. Write every checks result through `checks.jsonable` — pixels are never written.
- Docs: `docs/APPROVALS.md`. Tests: `tests/test_build78.py`.

## What the first day around the clock taught (BUILD 84, 2026-11-19)

- **A body's colours by brightness only** (`checks.fix_colour_body`, called by `fix_colour` for every body kind, whatever
  `mode` is asked): one gain for the whole colour picture, worked out from the body **as made** — never a curve a colour,
  never one curve through the channels, never one shaped like a gain; no head curve either (`head_fix` is off). The gain
  is the least that brings the body inside the check (`choose_gain`: the face first, then the mean, then the contrast;
  never past the point where more than `body_gain_clip_share` of the lit texels the unwrap uses go past white — on a
  body that is the skin, which goes pale and yellow). Where one gain can't bring it inside, it is released at that gain
  and the reason is written with it. `hue_moved` compares the result with the body as made, texel by texel; a release
  whose hue moved is refused (it can't under one gain; the guard is tested). Files: `<id>__one_gain.glb`; the colour
  sheet's left panel is always the body as made (`colour_picture(..., label="one gain ×1.14")`).
- **Releases**: Match and release, Approve everything here and the daily redo all reach `world.release_body_one_gain`;
  a released body is never matched again by the queue (`_put_right(colour=False)`), and a release made before this
  build (a curve) is turned into one gain from the body as made when the queue takes it up. `world-fix one-gain <ids>`
  (`approve_all.world_one_gain`) puts a body already released with a curve right: released again if it is not on its
  skeleton yet, or the colour picture inside its moving copy swapped (same mesh, same unwrap — checked first), each in
  the undo log with the moving copy as it was kept for Undo (`restore_files`).
- **Metal out of the colour check**: a texel whose metalness (metallicRoughness blue × metallicFactor) is at least
  `metal_from` (0.8) is left out of both the model and its picture; a thing more than `metal_skip_share` metal is not
  colour-checked. The image-to-3D step leaves what it can't tell at about 0.5 — that is not metal.
- **The picture gate's pose band is what the skeleton step needs**: 14–90° (was 32–76°), measured on 42 people rigged
  from pictures with arms at 14–31° (every one took its skeleton and motions, no more arm/trunk webbing than at
  40–50°). **The head is measured without its hair or hat** (`gate.face_height`: from the chin up to the hairline or a
  brim, by the skin's own colour; `face_head` 0.65 scales it to a head); held only when the face alone is too big as
  well. A seated figure's head isn't measured against its seated height. `world-fix regate` judges every body the gate
  holds again, try by try, with the numbers as they are now (nothing painted again).
- **Repair before reroll** (`bodies.repair_pose`): a picture whose only miss is its arms is made again from itself against
  the A-pose skeleton (`same_person.graph_guided`, RealVisXL + the union ControlNet) once, before a new picture is
  painted. **Nudges** go near the front of the words (`gate.with_nudge`, after the style start), and a low miss asks
  for sixty degrees. **Make again** carries the last miss's nudge into its first new picture (`gate_carry`) and the seed
  moves on with the tries. **The redo**: a thing held twice running for the same reason (`redo.reason_of`) goes straight
  to NEEDS_BETTER_WORDS.md, named in the redo's report with why.
- **Animals** (`"rig_kind": "animal"`, `world.is_animal`): never the picture gate, the person's checks (face, hair, head
  match, smile), the person's skeleton or the person's motions (`line.run` skips them too). Tonight's floor: checked as
  a thing, colours by one gain, sized, placed, made with `"moves": "none yet"`. `world-fix animal-again <ids>` remakes an
  animal that was given a person's skeleton (the body kept, the try withdrawn, skeleton and motions set aside);
  `world-fix unhold <ids>`. The animal route (UniRig's `articulationxl` template and keyed four-legged motions) is in
  `docs/ANIMALS.md`, not built.
- Tests: `tests/test_build84.py`, `tests/test_build84_gate.py`.

### BUILD 84, the rest (2f and parts 4, 5, 6 — the second sitting, 2026-11-19 evening)

- **Loose pieces the queue puts right by itself (2f)** — for a prop or a building, never a body (`checks.fix_loose`,
  called first in `world._put_right`; the model as made is kept, the result is `<id>__loose_off.glb`). Three held models
  all said "1 piece not joined to the rest (below the floor)" and were three different things, so **look before you
  write a rule from a check's one line** (the check picture now paints the loose piece orange):
  - a piece that lies **wholly under the floor** (a sheet of ground the image-to-3D step left) is taken off —
    `Glb.drop_faces`, triangles and their vertices, so the thing's box and floor stop counting it — while what is taken
    off is under `loose_fix_max_share` (a tenth) of the surface;
  - a piece that **stands by itself a little through the floor** (a chair the step invented behind a building, its feet
    4% of the height under) is stood on the floor — `Glb.move_faces`, up by what it was sunk; limits `loose_sink_max`
    (6% of the model's height) and `loose_sink_own` (a third of its own);
  - a thing that **hangs** has no floor (`world.is_hanging`: the entry's `"hangs": true|false`, else its words —
    `HANG_WORDS`: chandelier, hanging lamp, ceiling fan …): its separate pieces are judged by how near they hang to the
    rest (`loose_hang_gap`, 4% of its size). The "loose piece" on the chandelier was its own centre crystal.
  A piece in the air, or deep through the floor, is held as before. `world-fix check-again <ids>` (`world.check_again`)
  checks held props and buildings again with the forge as it is now — no card, nothing remade — and sends on what passes.
  Not built: verdict 12's "settle" (lower a piece that hangs just above the floor); no model on the list shows it now.
- **Proportions (part 6)** — `real_size_m` may say `"length"`: the longer side on the ground, whichever way the model
  turned out (`meshio.SIZE_ORDER`: a thing is scaled by its height, else its length, else a named side). An entry that
  gives **two** measures is checked after it is made (`checks.size_check`, in `world._check_and_place`): at the size its
  first measure gives it, each other measure more than `size_max_off` (a third) from what was asked holds it, numbers
  shown ("Proportions: at 8.1 m tall — asked 8 m deep, it is 12.1 m (151%)"). A named side is compared with whichever
  ground side is nearer (a model may come out turned a quarter); width and depth both named: longer with longer. One
  measure: nothing to compare, nothing said. Such a hold is not an approval and not a remake: change the words or the
  size, or let it through. A place plan's grey box does not read `length` yet (`place._box`): give such a thing a footprint.
- **Trees by species (part 5)** — `docs/TREES.md`. Twelve sheets in `forge/threed/species/`; a sheet may say `leaf`
  (the sprig on the cards), `leaf_tint`, `bark`, `flare`, and `form`: `broadleaf` (the grower) or `column` (a saguaro),
  `canes` (an ocotillo), `rosette` (a yucca) — plants built by their own rule, their colours on the mesh. A sheet that
  says none of it grows the tree it grew before, to the vertex (checked). Pick a sheet **by name**, never by its place
  in `trees.sheets()`.
- **The connector's status (part 4)** — `docs/MCP.md`. `world.merged()` finds every Review entry in one walk
  (`world.tries_index`); it used to ask the disk once a made thing a folder, every time anything read the list. The art
  queue is counted from the folder listing (`ops.count_jobs`: only files small enough to be a tombstone are opened).
  Status says how long each part took (`took_seconds`) and logs a warning past 5 s. **If you add something to status,
  count what it reads**: `tests/test_build84_connector.py` fails when status opens the finished jobs or reads the list twice.
- Tests: `tests/test_build84_loose_and_sizes.py`, `tests/test_build84_connector.py`, `tests/test_build84_trees.py`.

## BUILD 87 — materials: every channel, Material Maker driven (`docs/MATERIALS.md`)

`forge/materials/` and the plug-in `forge/plugins/materials.py`: job types `ff_channel_proof`, `ff_channels`,
`mm_material`, `material_mix`, `material_decal`; commands `python -m forge.materials <command>` (the four
`materials_*.bat`). Read `docs/MATERIALS.md` before touching any of it. What to remember:

- **Filter Forge's channel is a preset, and only a preset inside the filter file.** Its command line skips presets a
  person added to a library filter (its own help). `ffchannels.py` writes working copies of the filter into the
  job's folder with every preset's `map_type` set, renders, and removes them. Which number is which channel is
  **proved by rendering** (`probe` / `name_numbers`: what the picture is, checked against the menu's order) and kept
  in `local/ff_channels.json`. Never hard-code a number; never trust the name `map_type` further than a proof.
- **A set is one geometry.** `ffchannels.tile_together` heals every channel with the roll and cut of the final
  picture. `night4.tileable.tile_channels` did not until 2026-11-20 (each channel got its own roll and its own cut, so a
  `filter_forge` set with `tileable: true` came back shifted against itself; its test gave both channels the same
  picture). It does now, the same way; and `filter_forge` writes `<slot>_n_tile.png` from the healed normal.
  `tileable.make` / `blend` on ONE picture are as they were.
- **Beside a picture: new names only, and only when the render is that picture** (`deliver_beside`, `matches`).
  `<name>_ffnormal.png` is what `3d relief` promotes to `<name>_n.png`.
- **Every channel says what it is** in `channels.json`: `true`, `worked out` (a legacy filter's roughness, from its
  two specular channels) or `FALLBACK` / `MISSING`. Keep that honest when adding a channel.
- **Material Maker's command line** was read from the installed program's own script (`mm.py`'s notes): the export
  word must come first; it does not quit after a mistake, so every run has a time limit; it draws on the card, so
  every export holds `CardLock`. `mm.lint` checks a graph against the installed `nodes/*.mmg` before it starts.
- **Named parameters are the forge's**: a side file `<graph>.json` maps each name (0 to 1) onto node parameters;
  `mm.patch` writes them into a copy. Settings `broken` / `mended` = one surface in two states; a game's
  `materials.json` says which era wears which.
- **The lamp pictures are previews** (`look.py`, numpy) and are stamped as such. They judge a channel set; they are
  not the game's look, and a place drawn by `sheets.place_pictures` is its ground only.
- **The commands run their own batch in their own window** (`__main__.submit_and_run`): they never start, stop or
  feed the art worker and never touch another batch's waiting jobs.
- A game's choices live in `games/<id>/materials/materials.json` (a proposal file). Nothing under `forge/materials`
  names a game — `tests/test_build87_materials.py` checks.

## BUILD 91 — icons and portraits from the models (`docs/MODEL_PICTURES.md`)

`forge/threed/modelpics.py` + `forge/threed/blender/picture_model.py`, plug-in `forge/plugins/modelpics.py` (job types
`model_icon`, `model_portrait`), `icons_from_models.bat`. What to remember:

- **The pictures come from the made models**, found through the world queue's own record (`modelpics.made_model` →
  `world.read_state`: a body's model is `<id>/moves/<id>_moves.glb`, a thing's is `<id>/<id>.glb`). Never guess a path.
- **Processor only.** Blender's Cycles with `device = CPU`: no card, no ComfyUI, so it may run beside the queue. Keep
  it that way; an engine that wants the card would have to take `CardLock`.
- **One rule for every icon** (the script's `auto_view`): longer side across the frame, a long thing along the
  diagonal, a flat-lying thing seen from above. A thing's own view goes in the game's table, not in the code.
- **A portrait's traps**: the .glb importer leaves a hidden "Icosphere" (its bone shape) in the scene — it must be left
  out of the bounds; an idle motion looks at the floor — the head is set upright in armature space after the pose is
  held (`hold_pose`); bodies arrive faceted with split seams — weld and smooth for the picture only (`smooth`).
- The script must run under the forge's Blender AND as a module in other Blenders. It was run for real under **4.2**
  and **5.3** (2026-11-19; the same icon from both). Three things 4.2 does differently, each of which bit: it names an
  imported motion `<motion>_<figure>`, so asking for `Idle_Loop` by "holds the words" took `Crouch_Idle_Loop_character`
  — she crouched (`pose` now asks for the name, then `<name>_…`, then anything that holds it); its Python can fall
  over while shutting down, so the script ends with `os._exit` and the job judges by the `PICTURE` line and the file,
  never by the exit code; and actions are played through a slot only from 4.4 on. `World.use_nodes` is going away.
  `tests/test_build91_modelpics.py` runs the real script wherever `bpy` can be imported, and a stand-in everywhere else.
- A portrait's expressions are the files **its own note names** (`portraits/<name>.json`, `files`). Never glob
  `<name>_*.png`: `hero_boy` is another portrait, not an expression of `hero` (the first sheet made that mistake).
- A game's tables are `games/<id>/pictures/items_to_models.json` and `portraits.json` (proposals: `exact`, `near` = a
  stand-in shown amber, `world: null` = no model, grouped). The code never writes a world list or a game's data.

## BUILD 93 — portraits painted over the bodies (`docs/PAINTED_PORTRAITS.md`)

`forge/threed/portraitpaint.py`, plug-in `forge/plugins/portraitpaint.py` (job type `portrait_paint`, **GPU**),
`portraits_painted.bat`. What to remember:

- **It is the same-person job's graph with more references.** `portraitpaint.graph([...])` = `same_person.graph_instructed`
  for one reference (a test holds them equal); a second reference is a second `ReferenceLatent` node whose conditioning
  is the first's output (ComfyUI 0.44's own node says "chain multiple"). FLUX.2 [klein] 4B, distilled, 4 steps. Do not
  write a cousin of that graph: change `flux2_graph.build` or `graph_instructed` and this follows.
- **Three ways** — `over` (the body portrait alone), `picture` (the picture the body was made from, alone), `both` (that
  picture first, the body portrait second). A body's own picture is found through the world queue's record
  (`world.read_state(...)["picture"]`), never by guessing a path. Every sentence starts with `same_person.STYLE_START`.
- **The card.** A session never runs it (the rule for every GPU job). `portraits_painted.bat` takes `CardLock` **once for
  the whole batch** (`run_batch`) and passes it to the job, which only keeps it alive (`lock.beat()`); a job run by
  anything else takes its own. The world queue steps aside for either (the lock, and a GPU job in `jobs/running`).
  It asks ComfyUI `is_up()` first and queues nothing if it is not.
- **The two numbers are tripwires, not a judge** (`kept`): layout = the two pictures blurred to 32 x 32 and compared;
  colour = the figure's colour patch by patch without its brightness. `layout_min` 0.5 and `colour_min` 0.6 are guesses
  until a first real run is looked at — change them from what that run shows, not before. The first try at `layout`
  (the forge's edge agreement) could not tell a whole figure from a portrait (0.24 to 0.53): too many edges, too wide a
  net. `choose` proposes one candidate so the .bat ends with a set; `pick` (or the game's table) overrides it.
- **A job left behind must never stall the world queue** (found while writing this; its own package, `b93_3`). A GPU
  job's file in `jobs/running/` made `world.machine_busy` say "the art worker is on a GPU job" for as long as the file
  lay there — so a .bat window closed while its job waited for the card (BUILD 87's `mm_material` claims first, then
  waits) would have stopped the queue making models until someone noticed. Now `Queue.claim` writes who has the job
  (`worker`: pid and host, taken off again by `finish`; `dedupe` already counts that key as a receipt), and
  `world.claimer_gone` lets the queue pass a job whose process is known to be gone. Unknown is still "busy". A runner of
  your own: take the card **before** you claim (`portraitpaint.run_batch`), and finish the job in hand on Ctrl+C.
- **Stand-in pictures are not results.** The tests' stand-in hands the reference back as the "painting". Never leave a
  sheet made that way in `out/pictures/` or send one to the person.
- A game's settings are `games/<id>/pictures/portraits_painted.json` (`skip`, `who`, `ways`, `seeds`, `pick`), beside
  BUILD 91's `portraits.json`. Moods and mouth shapes are not here: they are `same_person`'s `masked` way on a painted
  portrait once one is approved.

## Faults found on 2026-11-19 and fixed the next night (William: "When you find faults, if you can fix them please do")

Fix what you find, in the forge, when you can; say what you could not. What these taught:

- **A test that fails on the PC and nowhere else: look at the PC before the code.** One test in
  `tests/test_suite_build27.py` failed there from 2026-11-18, before and after every package, and was called "not this
  package's" each time. The code was right: the PC's `venv` had no `tzdata` (in `requirements.txt` for Windows, added
  after the venv was made), and Windows has no list of time zones without it. `venv\Lib\site-packages\` is a folder
  you can read: compare it with `requirements.txt` first. (`tzdata` was put there by hand, as new files, checked
  against the package's own RECORD — a pure-data wheel is only a folder.)
- **`put_in_waiting_changes.bat` names the tests that fail** now, before and after, in the window and in the package's
  `APPLIED.txt`. It used to keep pytest's last line only, which is how a failure went nameless for two days.
- **A file in `jobs/running` that is not a job** (a tombstone, a type from a plug-in that is gone, half a file) used to
  stop `world.machine_busy` reading the rest of the folder, so a GPU job sorted after it was not seen. Each file is
  judged by itself now.
- **Ctrl+C in a runner of your own** (`forge.materials.__main__.submit_and_run`, `portraitpaint.run_batch`): finish
  the job in hand before going. A closed window cannot be caught; `world.claimer_gone` is what covers that.
- **A test that gives two channels the same picture proves nothing about register.** Use a picture whose pixels say
  where they are (red = column, green = row): a healed copy then says where every pixel came from
  (`tests/test_night4_tools.py`).
