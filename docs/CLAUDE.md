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

