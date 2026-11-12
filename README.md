# RPG_Forge

**A local, file-driven art foundry for 2D games.** Drop a JSON job into a folder; a worker on your own
GPU paints it, cleans it, snaps it to your palette and leaves the result — with a contact sheet and a
provenance record — in another folder. Nothing leaves your machine, nothing needs an API key, and
anyone who can write a text file can drive it: you, a script, or an AI assistant working through the
same folders. A game-agnostic engine: each game's own data stays in `games/<game>/` on your PC (never pushed).

```
jobs/pending/*.json  ──►  worker (GPU: ComfyUI · CPU: Pillow/numpy)  ──►  out/<job-id>/
      ▲                                                                      │
      └──────────── you / a script / Claude write the next job ◄─────────────┘
```

## The suite — `forge.bat` (BUILD 01, 2026-11-10)

RPG_Forge is a development suite for every RPG you make, not one game's tool. **`forge.bat`** opens it in your browser
(http://127.0.0.1:8770 — only this PC can see it):

- **A game picker** first. Each game is a folder `games/<id>/` (git-ignored) with `forge.game.json` → `game_root` (where
  the game's own folder is) and, for its Story side, a `workbench_adapter.py`. `games/_example/` is a tiny made-up game
  the suite always opens; every test runs on it.
- **One sidebar of areas** (BUILD 26, the way ATK is organised): Home · Status · Messages · Tasks · Story · Music · Art ·
  Characters · Workshop · Notes · Settings, each a row with its own count badge, and a strip of **tabs** across the top of
  each area. Every area and tab has an address (`#music/needed`, `#messages/inbox/<letter>`) — reload keeps your place,
  Back works, a letter can link straight to a tab — and one quiet line under the tabs says **what that tab needs** and
  whether it has it (a tab that isn't built yet says which build brings it). The art worker's button sits under the game
  picker in every area (▶ Start / ■ Stop, which pauses the queue safely). **Home** is the day at a glance: what needs
  you, what's waiting in each area, what changed since you last looked, the worker, the queue and the disk.
  **Tasks** is a checklist, not an inbox: every thing in the game waiting on you (work orders, letters with open
  questions, music briefs, songs waiting for their track, profiles with open spots, pictures to review, builds waiting on
  you, notes addressed to you), one card each, the ones that unblock work first; a card leaves only when it's done or
  you dismiss it with a reason. A task that wants a file takes it **on the card** — drop it or *Choose a file…* — and the
  file goes through its area's own delivery (a track is delivered and cemented, a sheet goes into Sprite intake). A work
  order asks for one with `wants` (audio · image · sheet · text · any, and how many) and `goes_to` (a folder in the game,
  `music:<slot>`, `sprite:<character>`). **Status** shows every requirement and task as met / partly / not met in big
  colour-coded tiles, plus the game's build queue and its own completeness checklist (the adapter's optional `builds()`
  and `completeness()` hooks). **Queue & pictures** (Art) is the dashboard `ui.bat` has always shown.
- **Team memory** (Notes, BUILD 17) — **Rulings**: every answer you've given, in one searchable book (questions answered in the Mail, every ✦ line in the game's notes, rulings written straight in); a session's letter is turned back when the book already answers one of its questions, and data that contradicts a pinned ruling shows red. **Idea box**: press **I** anywhere — one line, filed with the date and what you were looking at, sorted later into a task, a note, a letter or a file. **Playtest notes**: the game's note key, taken in — art to Called out, writing to the lines, the rest to work orders — and a letter per category. **Home** opens with *where the game stands*: n of m, and the next most useful thing for you and for Claude.
- **Floor plans** (BUILD 29) — a town's own sheet
  (fate, culture, era, what it sells) + an **archetype** + a seed → a map the game loads, its greybox, and a **paint guide**
  (flat colour regions, the story element in magenta) for the scene kit to repaint over, so a painting keeps the one
  thing the scene is about. Districts first, then lots and buildings (doors on streets, every door joined to the street),
  then interiors from a kit library (ruined or underground as the archetype says), then WFC texture on the empty ground.
  **Art → Floor plans** (BUILD 29b): four candidates side by side, paint on the grid with the checks live, approve into
  the game (the paint guide becomes what the scene kit paints over), reroll, or send one to the owner by mail.
  Fifteen archetypes, each with a War and an After version — the Buried Town, the Purity Town, the Congregation of the
  Machine, the Ledger Town, the Wall of Names, the Swollen City, the Toll Kingdom, the Moving Town, the Pretend Town, the
  Quarantine, the Salvage Republic, the Sanctuary, the Fortress Farm, the Ghost Town That Isn't, the Glass Field — and
  every plan reserves its upgrade places (weapon/armor, accessory) at the tier the town sells. Same sheet and seed, same
  bytes; nothing goes into the game until a person approves it, and an approved or hand-edited plan is never written
  over. `floor_plans.bat` · `python -m forge layout sheets|generate|show|check|approve` · docs/FLOOR_PLANS.md.
- **Tiles** (BUILD 30, first part) — the materials bake-off (`bakeoff_materials.bat`: SDXL ArtUniverse vs FLUX.2 Klein
  4B vs Filter Forge, one flat seamless tile per material per source; contact sheets, scores and a verdict draft, the
  pick is yours) and the autotile builder (`python -m forge tiles build`): the 47-tile blob set or the 16 corner set of
  one material on another, wall faces, variants that keep their borders, decals, normals for every tile, and world
  textures at the material's full resolution with mask-only tiles for the sharpest result. docs/TILES.md.
- **Who you are.** The first time it opens it asks your name; every change made through the suite is signed with it.
- **The Mail** (Messages, BUILD 03) — the screen to open first each day. Letters between you and the assistants working on
  the game: Inbox · Sent · Drafts · Archive, threads, search. A letter's questions are answered in place — pick, type, or
  "talk to me about this one" — and **Send** puts your reply in the game's `mail\` folder for the next session. Where a
  question says which data field it sets, picking an answer changes it through the safe path (checked, backed up,
  logged) and the reply says so. **While you were away** sits at the top: what everyone else did since you last worked.
- **Work orders** — two lists, "for" each side: what you want done (add one from any letter, question or picture, or a
  blank box, with a priority), and what only you can do. Plain files in the game's `work_orders\` folder.
- **Read-through** (Story, BUILD 07) — pick a town and an era and read everything it says, top to bottom, in the order
  a player meets it: the town's sheet on top, then every line with who says it, when (the conditions in words) and its
  status, then the quests offered there. Click ✎ or press **E** to rewrite a line in place; **A** approves, **D** leaves
  it a draft, **G** flags it as generic (with a note), **N** pins a note for Claude, **J/K** move. Song words show locked.
  A **sameness meter** marks candidates — a line that also appears in another town, a line with no word that belongs to
  this town, a speaker who never uses its greeting — and says it is mechanical. **Side by side** puts another town (or
  this one in another era) next to it. If a session changed the file while you were reading, nothing is overwritten:
  you see both versions and choose. Everything lands in the journal, so the next session's digest has it.
- **Music** (its own area, BUILD 06; Needed · Singers · Score inbox · Briefs & songs since BUILD 26) — every music slot the game has as one board, each with a coloured state (needed →
  proposed → agreed → written → delivered → in game), filterable by town, era, voice and state, with the gaps counted on
  top and the next most useful piece of work. **Drop a finished track on its row** (or deliver one from the score inbox,
  which guesses the slot): it is copied into the game under the slot's file name, the game's music data points at it,
  and the slot is cemented — delivered, by you, on that date; loop points (with a play-the-seam button) and volume trim
  are editable. Briefs from a session arrive as letters you answer yes / yes, but… / no / I'll write this one / not yet;
  no lyric is drafted before a yes. **Profiles** — what each voice sounds like, from the songs: the voice, each style with
  its example song, how their songs are built, your style notes, and the open spots you fill in place.
- **Called out and Mark up** (Art → Review & approve, BUILD 14) — redo drafts from your playtest notes (*Take in playtest
  notes* reads the game's F9 file), from review notes and from mark-ups: circle or draw over what's wrong on any
  picture — waiting, approved or already in the game — and say what; the marks become the inpaint mask of a repaint
  draft beside a full redo with a new seed. Nothing is queued until you press *Queue it*; *Dismiss* keeps it in
  `jobs\drafts\_dismissed\`; *I'll fix it myself* hands the picture out to you.
- **Prompt library · Bake-offs · Models · Outside tools** (Art, BUILD 14) — the look-word shelves (red = still a
  placeholder; words saved format-preserving, every save kept and signed; where used; an A/B draft with and without a
  block); the game's bake-off suites with renders, hours, grids, Queue and the report; the model shelf with what is
  **safe to delete** and why (it deletes nothing); hand-offs to outside programs and back, and the tool register.
  Photographs as plates show the people guard beside the photo field; *Make a texture tile seamlessly* is a kind in
  Make a picture.
- **Sprite intake** (Art, BUILD 04) — drop a character sheet from any program (or open one from the game's folder).
  The forge finds and numbers the figures *on the sheet itself*; click a figure, pick its facing on the compass (or the
  number pad), leave out repeats, mirror a figure drawn the wrong way round; **Make the game sheet** → the packed sheet
  (eight facings, one height, one baseline), the turntable and walk GIFs, warnings and the edge report. The mapping file
  is written for you and kept with every earlier version; you never open it. Backdrop showing through between an arm and
  the body on a JPEG sheet is found and marked (violet) — keep or clear each. A character the registry marks asymmetric
  is never flipped without a second yes. The program that made the sheet goes through the tool register (the licence is
  your answer; the forge never guesses one).
- **Wanted** (Art, BUILD 12) — everything the game still needs, from its own files, as a board: by town, by kind or by
  first appearance; each item *missing · stand-in · drafted · queued · rendered · approved · delivered*. **Plan** reads
  the game and drafts one job per missing item (`produce plan`; nothing queued). Select a town (or anything) → *What
  would it take?* → jobs, GPU hours, disk against free space and the guard, and every look block that still has no
  words → **Queue** only when nothing refuses (`produce queue`, now with `names=`). A town sheet per town and the atlas
  (does each town hold together? do they differ?).
- **Make a picture** (Art, BUILD 12) — a form by kind (scene kit, big scene, state, portrait set, character set, icon,
  prop, texture, photo plate, plain render): the fields in plain words with the game's defaults, *for* a wanted item
  (takes its size; the board follows it), a character to inherit from, a town (its culture and fate blocks, its family
  seed), how many takes. The prompt the worker will get is shown expanded with every block marked; each refusal sits
  beside its field. **Queue it** goes through submit like any batch.
- **Review & approve** (Art, BUILD 12) — pictures waiting for a verdict (made for a wanted item, not yet approved): 1:1
  zoom, every output, A/B against another take, the licence line, the kit check. **Approve** holds it for delivery (the
  licence check runs now; a kit is approved as a set); **Redo with a note** writes a draft (never queued); **Send out**
  makes a hand-off folder. **Deliver to the game** shows the list first, then copies — whatever it replaces is kept in
  `out/_replaced/`, the ledger records it, nothing is deleted. An assistant can check an approval but not make one.
- **Characters** (Art, BUILD 04) — the registry as pages: variants, the locked seed (the face lock — change it here),
  `asymmetric`, reference pictures by path, the look blocks (green written · red not written yet · grey not in the
  library), what each variant is wanted for; **Make the face sheet** (every variant and mood of one face on one sheet);
  **Make the set** says what it would queue — or, in submit's own words, why it can't yet — and queues only on a second click.

Under it, the pieces every later screen uses (`forge/suite/`):

| Piece | What it guarantees |
|---|---|
| **Adapter contract** (`adapter.py`) | The suite knows places, lines, quests, music slots, people and status — nothing about any one game. A game's adapter says where those are in its files; a second game needs a folder and an adapter, no forge change. |
| **Safe save** (`safesave.py`) | A data file is changed only through: hash check (someone else saved it? show both, write nothing) → a temp copy checked by the *game's own validator* → backup in `<game_root>/_workbench_backups/<date>/` → atomic replace → journal. Ids never editable; a song's own words locked; unknown fields and formatting kept byte for byte (`jsondoc.py`). |
| **Journal** (`journal.py`) | Every action, by anyone, is one line in `<game_root>/journal/<yyyy-mm>.jsonl` (who, what, before → after). `WORKBENCH_LOG.md` is its readable view. |
| **Approved means his** (`approval.py`) | An item someone approved carries `approved_by`. Anyone else's edit to it becomes a *proposed change* for its owner to accept or decline; an assistant can't approve. |

Commands: `python -m forge suite | identity [name] | journal add|show | mail list|read|send|reply | orders add|list|done | away | suite-check` (`mail.bat` for the Mail) (`suite-check` loads and saves every
data file of every game with no edit and confirms the bytes are identical). `run_tests.bat` runs the forge's tests (safe while the worker renders).

## On a Mac (BUILD 27)

The suite (everything but making pictures) runs on a Mac too. On the Mac:

1. Python 3.11 or newer from <https://www.python.org/downloads/macos/> (the official installer).
2. This repository (GitHub → Code → Download ZIP, or `git clone`), and a copy of the game's folder.
3. Double-click **`install_mac.command`** once, then **`forge.command`** to start the suite. If Finder says it can't open
   them, open Terminal in this folder and run `chmod +x *.command` once.
4. The first time, the suite asks who you are and where the game's folder is on this Mac (Settings → This computer →
   *Check*, *Save*). That answer stays on this Mac (`local/suite.json`, never pushed).

Making pictures needs the art worker, which runs on the Windows PC with the NVIDIA card; on a Mac its button says so.
Messages, Tasks, Story, Music, Characters, Notes and Review & approve all work. Keeping two copies of a game folder in
step, and mail between two installs, come with BUILD 23. From Terminal, `./forge.command <words>` runs any forge command
(`./forge.command handoff in <name>` is `handoff_in.bat <name>` on Windows).

The suite's tests run on Windows, macOS and Linux at every push (`.github/workflows/suite.yml`):
![suite tests](https://github.com/photogbill/RPG_Forge/actions/workflows/suite.yml/badge.svg)

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
sprite sheets, tiles, maps, icons, props, concepts (`games/<game>/bakeoff/*.json`) — with one
seed and identical sampler settings, grouped by checkpoint so ComfyUI reloads less. Incompatible pairs (an
SD1.5 or FLUX LoRA on an SDXL checkpoint, which ComfyUI would silently ignore) are skipped and listed; a
render that fails is a red cell, and the run moves on. Every render is also filed twice — `out\bakeoff\<suite>\by_model\<checkpoint>\<lora>\` and
`by_category\<kind>\<prompt>\` (one folder per picture, one file per model) — so comparing is a matter of
opening a folder. `bakeoff_report.bat` builds one grid per prompt
(rows = checkpoints, columns = LoRAs) and an `index.html`; `python -m forge bakeoff rate <suite> <job-id> <1-5>`
records verdicts that show up as badges. `bakeoff.bat --quick` is a ten-minute smoke run first.

## Quick start (Windows)

**Everything below also has a place in the suite: double-click `forge.bat`.**

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
{"type": "scene_card", "name": "intro_01_kitchen", "game": "mygame",
 "prompt": "a farmhouse kitchen at breakfast, window light from the left, steam rising from a coffee pot"}
```

A batch is `{"batch": "name", "defaults": {...}, "jobs": [...]}` — see `games/_example/`.
A game's palette, style prefix and sizes live in `games/<game>/forge.game.json`, so jobs stay short.

## Repository map

```
forge/            the package: queue, schema, cli, bakeoff, ops/ (image maths, safetensors headers), engines/ (ComfyUI, SDXL graph), jobs/
forge.json        configuration (paths, ComfyUI url, defaults)
jobs/             pending/ running/ done/ failed/ — the queue; templates/ — one example per job type
out/              results, one folder per job id
models/           weights (ignored) + models.json registry with licences
palettes/         master palettes (.hex, Lospec format)
games/            per-game config and batches — git-ignored, one folder per game; games/_example is the template
docs/             PROTOCOL.md · JOB_TYPES.md · CLAUDE.md · LICENSING.md · ROADMAP.md · FLOOR_PLANS.md · TILES.md
tests/            pytest (CPU side; 24 tests)
```

## Status

v0.2 (2026-11-09) — painted-background pipeline, game manifest + approve, pipelines, review pages, pre-flight
doctor (session hand-offs are kept per game, locally). v0.1 — the queue, the CLI, the CPU tools and the ComfyUI driver are real and tested; the GPU handlers
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

## Scene sets and the dashboard (added 2026-11-09, session 2)

- **A painted scene is a set of six files** (the game's HD-2D-feel pass): `scene.png` + `_n` (normals from a depth map) +
  `_e` (glow) + `_back` (far parallax plane) + `_over` (walk-behind plane) + `_depth` (16-bit, white = near). One
  `scene_kit` job makes all six (`jobs/templates/scene_kit.json`); `approve.bat <job-id> scenes/<map> --set` copies them
  into the game together, with one licence check, all or nothing. The pieces also run alone: `depth_map`,
  `normal_map` with `"source": "depth"`, `scene_layers`.
- **Dashboard:** `ui.bat` opens http://127.0.0.1:8765 — the queue with an ETA, what is rendering, batch progress,
  the newest pictures, failed jobs with Retry, Pause/Resume, and Approve (dry run first). Only this PC can see it.
- **No double runs:** `bakeoff submit` skips cells already queued or finished (`--force` to redo); `submit --skip-done`
  does the same for a plain batch. `eta.bat` says how long the queue will take.
- **Krea 2 is not used** (William, 2026-11-09: its licence) — no graph, no registry entry.
- **Models:** `python -m forge models unusable` → `out/unusable_models.md` (what no graph can run, what is
  non-commercial, what still needs a licence check — report only). `licence.bat` with no arguments asks its questions.
- **Bake-off detail crops:** `bakeoff report <suite> --detail-at <prompt>=x,y[,size]` or `--detail-auto` (largest face).

## Night 3 (2026-11-09) — big scenes, room states, review for a model, the prompt library

New job types are **plug-ins** (`forge/plugins/`): a running worker picks them up before its next job, no restart.

| What | Command / .bat | Job type |
|---|---|---|
| The morning report — what ran, what failed and why, seconds per render by model | `night_report.bat` (`report night`) | — |
| Review sheets a model can read: ≤ 12 labelled cells, ≤ 2,000 px, ≤ 1.5 MB, `review_index.json`; side-by-side pairs with a 1:1 crop | `review_compact.bat <suite>` (`review --compact` / `--pairs A,B`) | — |
| Paint past one frame: small whole scene → climb ≤ 2× per step → tiled repaint (ControlNet tile + canny) → feathered merge → seam scores | `op.bat tiles-demo` | `scene_big` · `scene_kit` with `big: true` (the six-file set at any size) |
| Inpaint; a *state* of a room (the same room years on) — bit-identical to the base outside what changed | `op.bat state-mask …` | `inpaint`, `scene_state` |
| Is this kit safe to approve? (slots, sizes, normals, depth, glow, planes, walk rings) — `approve --set` refuses on a fail | `kit_check.bat <job>` (`kit check`) | — |
| Prompt library: `{{style.house}}` blocks expanded by `submit`; the never-list | `prompts.bat` (`prompts …`) | — |
| One draft for every missing painting, type chosen by the facts; room families | `paint_missing.bat` (`brief missing`) | — |
| Sprite sheets: eight poses → one 1152×216 facings sheet; GIF previews; turnaround split | `op.bat facings-pack …` | `facings_pack`, `anim_preview`, `turnaround_split` |
| Every model in shipped art | `credits.bat` | — |
| Nine-slice UI panels; button states | `op.bat nine-slice …` | `nine_slice`, `button_states` |

Dashboard: a **Report** link, kit-check colours on kit cards, an **A/B** view, and what runs next. Session notes are kept per game, locally.

## Night 4 (2026-11-10) — production: your sheets in, a queue that runs for days, verdicts back

| What | .bat | Job type |
|---|---|---|
| **Your character sheets → the game's sprite sheet.** Any grid, any backdrop (flat, white, painted checkerboard, real alpha), labels dropped. The forge numbers the figures, guesses the facings and *asks you* if the guess is right; one height, feet on one baseline, centred on the feet; packed to 8 facings S…SE at 144×216 (+ frames). Nothing of yours is copied or changed | `sprite_intake.bat "<sheet or folder>" hero default` | `sprite_intake` |
| The character registry: one file per character, each variant's recipe (checkpoint, sampler, **locked seed**, prompt blocks, `asymmetric`). A job with `"character": "hero", "variant": "armoured"` inherits it | `characters.bat list / show / check / stubs / set` | `character_set` (moods on one face + battle pose + a generated sheet) |
| What the game is missing → one ordered plan (first hour first, a town in one sitting on one seed) → a queue that refuses until every look block is written | `produce.bat plan` · `produce.bat queue` · `produce.bat status` | — |
| Approved pictures → the game, with a ledger (undo-able; replaced files kept in `out\_replaced`). If the game folder isn't reachable, it writes a copy .bat for you | `deliver.bat [--dry]` · `deliver.bat undo <name>` | — |
| Leave running beside a long queue: parks the queue under 40 GB free, brings it back by itself, writes the 24-hour report | `produce_watch.bat` (the worker also checks the disk guard itself every 5 minutes) | — |
| Item icons in bulk, one hand per category | (planned by produce) | `icon_batch` |
| The notes you make in the game with F9 → redo drafts (never queued); the dashboard's **Called out** section approves / dismisses / hands one to you | `feedback_in.bat` | — |
| One of your photographs → a painted plate (only frames listed with no people, or only you) | — | `photo_plate` |
| Make a texture tile (Filter Forge's own seamless doesn't survive its command line); `filter_forge` takes `"tileable": true` | — | `tileable` |
| Every model file: loads? licence, used by, verdict, size — and what is safe to delete | `models_report.bat` | — |
| What in out\ could be archived (report only) | `housekeeping.bat` | — |

Session hand-offs and plans are per game, in `local/<game>/` (never pushed).

## Licence

MIT (code). Models and palettes carry their own licences — `docs/LICENSING.md` and `models/models.json`.

## Bake-off scripts added 2026-11-09
- `bakeoff_tonight.bat` — queues the whole evening in order: the tools test → the finishing bake-off → new SDXL LoRAs → house styles → FLUX.2 klein → FLUX.1 + LoRAs; then `run_worker.bat`.
- `test_tools.bat` — 13 small jobs, one per paint tool (about 20 minutes); run it before any long run. `bakeoff_finish.bat` — the finishing bake-off (refine, FreeU, face repair per checkpoint, with 1:1 detail sheets).
- `bakeoff_new_models.bat` / `bakeoff_styles.bat` / `bakeoff_flux.bat` — the same runs one at a time.
- `pull_flux.bat [dev]` — fetches FLUX.2 klein 4B + FLUX.1 schnell and their encoders/VAEs into `models\` (dev is non-commercial; opt in).
- Verdicts and what each model is for: `docs/BAKEOFF_1_VERDICT.md`, `docs/NEXT_MODELS.md`.

