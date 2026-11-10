# RPG_Forge — the build list for Night 4 (for the Opus session)

> **2026-11-10, 14:46 — this document is now the suite *specification*, not a one-night list.** Build from `D:\Turing Accords Game\Builds\BUILD_QUEUE.md`; each numbered build names the sections of this file it implements (the music composition loop is specified in `BUILD_06` itself). Where sections disagree, the later-dated one wins. RPG_Forge is our development suite for every RPG we make.


*Written by Fable, 2026-11-10 afternoon, from `HANDOFF_FORGE_NIGHT_3.md`, `HANDOFF_FORGE_NIGHT_3B.md`, `WIRE_NIGHT_3.md`, `SPRITE_BAKEOFF_VERDICT.md` and William's rulings of 2026-11-10. `docs/CLAUDE.md` governs how to work here (commit message file, push is William's, nothing outside D:).*

## 0. The situation

The forge can paint a scene as a six-file kit, at any size, in states, check it, approve it with its licences, and hand pictures out to Gigapixel or Filter Forge and back. What it cannot do yet is **run production**: nothing turns "the game is missing 60 paintings, 30 sheets and 200 icons" into a queue that runs for days, and nothing carries William's verdicts back from the game. And the character side has moved: **William makes the sprite sheets himself in Gemini and bulk-edits them**; the forge's job for characters is now *intake and normalising*, plus its own generator as the second road.

Facts to hold:
- **Sprites (verdict):** ArtUniverseSDXL_v8, dpmpp_2m karras 28 steps; a seed locks a face across samplers; RealVisXL_V5 for the photographic alternative. Dropped models are listed in the verdict.
- **Sarah has two sets — Guardian (hair down, loose, straight) and Warrior (braided)**; holster and sidearm in both; a nuclear core (trefoil). His prompt prefix stands.
- **Licences:** non-commercial is a no-go; Krea 2 is out; artist-named LoRAs may load but their names and triggers are never prompted (`never.json`).
- **His photographs** are references by path — never copied into this public repo (`games/turing_accords/REFERENCES.md`).
- **The prompt shelves are Fable's.** You build the machinery and leave placeholders that refuse to expand. No look decisions tonight.
- William would run generation 24/7 if there is enough to run. Slow is fine; a preloaded queue is the point.

### The worker rule — check first
Look at `jobs/running`, `jobs/pending`, `jobs/paused` and the worker log. **If the worker is running, Part A only, as plug-ins and new files** (as Night 3; no edit to `queue.py`, `jobs/*`, `engines/*`, `bakeoff.py`, `pipeline.py`, existing `ops/*`). **Part B needs the worker stopped and `jobs/pending` empty** — do it only if William has said in the kickoff that it is stopped, or the folders show it. Never stop it yourself. If Part B can't run, leave it exact in `docs/WIRE_NIGHT_4.md`.

## Progress
*(the Opus session keeps this current; if halted, start from the first item not marked done)*

Opus, 2026-11-10 14:02 → evening. Worker RUNNING the whole session (FLUX sprite bake-off) → Part A only.
- [x] F0 — 155 green at the start; git: nothing lost (see the hand-off); Night 3 GPU tests read
- [x] F1 — sprite_intake + sprite_intake.bat (asks at the console); 9 tests incl. the five synthetic sheets
- [x] F2 — registry (Sarah guardian/warrior + 23 cast stubs), inheritance shim, character_set, review --character
- [x] F3 — export (every kind, towns, hashes), produce plan/queue/status, deliver + ledger + undo, disk guard +
      24 h report (produce_watch.bat), housekeeping; §4 towns: culture/fate/enclave blocks, review --town/--atlas,
      era triptych choice
- [x] F4 — icon_batch (one seed per category)
- [x] F5 — feedback_in, drafts, bumps, the dashboard's Called out
- [x] F6 — photo_plate with the people guard
- [x] F7 — tileable (two-pass minimum-error cut; inpaint polish on a GPU); filter_forge `tileable: true`
- [x] F8 — models_report.bat
- [ ] Part B — left exact in docs/WIRE_NIGHT_4.md (W1–W8)

## 1. Part A — safe beside a running worker, in build order

### F0 · Orientation and repo health (30 min)
- `python -m pytest` (155 at the end of Night 3B). Record it.
- **Git:** `git log` shows nothing after "Krea 2 cut", while `CHANGELOG.md` records Night 3, 3B and the sprite run. Find out why (a failed `push.bat`, leftover `.git\*.lock` files — the device shell can't delete, so git leaves locks) and **report it at the top of the hand-off with the one .bat William should run**; don't force anything. `git status` also shows thousands of `jobs/_cancelled_sprite_v1/*.json` untracked: ignore `jobs/_cancelled*/` and anything else that is run-state, not source. Bake-off suite files that are untracked (`hair_test_*`) and `docs/SPRITE_BAKEOFF_VERDICT.md` are source — they go in.
- Did William run `night3_tests\run_night3_tests.bat`? If the results are in `out/`, read the seam scores and the state-mask check and write two lines each into the hand-off. If not, list it again.

### F1 · Sprite intake — William's sheets become game sheets (the first thing he'll use)
`sprite_intake` (CPU plug-in) + `sprite_intake.bat <picture or folder> <character> [variant]`.
- Input: a sheet from any outside tool — unknown grid, any backdrop (flat colour, white, checkerboard painted in, or real alpha), uneven cells, labels printed between rows.
- Steps: find the figures (connected components on the cut-out, not a fixed grid) → cut each out (alpha if present; otherwise a flat-backdrop key; a learned matting model only if its licence is commercial-clean and on file — say which and why) → drop text/label blobs → order into rows and columns → **one height, one baseline, centred on the feet** → pack to the game's contract (the `facings_pack` layout; the game's facing order is 0 = S … 7 = SE) → an `anim_preview` GIF and an edge report (halo colour, cut-off limbs, a figure touching its cell edge).
- A **mapping file** per sheet (`<sheet>.intake.json`): which found figure is which facing/frame. First run writes its best guess and a numbered contact sheet; William (or Fable) corrects numbers in the file and reruns. Mirrored facings may be filled by flipping only when the file says so (a holster on one hip makes a flip a lie — warn when a character's registry entry says `asymmetric: true`).
- Output goes to `out/` as a normal job with provenance; the outside tool is recorded through the G13 tool register (it asks for the licence line once; nothing in the code names a product).
- Delivery to the game is F3. Tests: five synthetic sheets (clean grid, ragged grid, labels, white backdrop, painted checkerboard).

### F2 · A character registry
`games/<game>/characters/<id>.json`: variants (e.g. `guardian`, `warrior`, ages), per variant the prompt-library blocks, checkpoint, sampler, **locked seed**, reference pictures by path, `asymmetric`, wanted outputs (field sheet, battle pose, portrait moods). Jobs may then say `"character": "sarah", "variant": "warrior"` and inherit the lot; a job's own keys win. `characters.bat list|show|check`. Seed the file for Sarah's two variants from the verdict and William's prefix with every look block a placeholder; other cast as empty stubs from the game's `characters.json` if the game folder is readable, otherwise from `wanted.json`.
- `character_set` (plug-in): one variant → portrait moods on the locked seed (same face, expression blocks), a battle pose, a turnaround via the two sheet LoRAs the verdict says work on ArtUniverse → through `turnaround_split`/`facings_pack`. It is the second road beside F1, so it must end in the same contract.
- `review --character <id>`: every variant and mood of one face on one compact sheet — the consistency check Fable needs.

### F3 · Wanted → queue → game: production
- **`export_wanted.py` covers every asset kind the game references with a stand-in**, not only maps: sprite sheets, portraits, item icons (from `items.json`), enemies, props, vignette frames, UI pieces. Each item: kind, id, size/layout, where it goes in the game, what it is in the game's own words (name + description fields), state (`missing` / `stand-in` / `delivered` + hash). Prefer the game's own validator output if Night 4 of the game writes one (`27 §3.1`); read whichever exists.
- **`produce`** (`produce.bat plan|queue|status`): `plan` drafts one job per missing item with library references and an order — *the first-hour eight, Bill's house first; then by first appearance in the story; kits before states; families together (G11)* — and prints count, GPU hours from measured s/render, and disk needed. `queue` refuses while any referenced block is a placeholder (naming them), then submits in priority lanes. `status` is one screen: done / running / left / ETA / failed by cause.
- **`deliver`** (`deliver.bat`): an approved set is copied into the game at the paths the game reads (`project\assets\scenes\<id>[_state][_slot].png`, sprites, portraits, icons), sizes checked against the wanted item first, a `delivered.json` ledger (job id, hash, time, licences) so a redo can be traced and a delivery undone (the old file is kept in `out/_replaced/`, never deleted). Runs only on approved pictures; `--dry` prints what would move. If the game folder is not reachable, write the copy list as a .bat for William.
- **Standing by itself for days:** a disk guard (pause the queue and say so in the dashboard when the output drive falls under a set free space — he has said disk is tight; default 40 GB), `out/` housekeeping report (what could be archived: bake-off raws older than N days — report only, delete nothing), and the morning report every 24 h without being asked while a queue runs.

### F4 · Icons and small things in bulk
`icon_batch` from the wanted icon items: one draft per item, the item's name and description into the subject slot, one family seed per category (weapons, plates, consumables, parts, keys) so a category looks like one hand, transparent cut-out, the game's icon size + 2×, a contact sheet per category for review. `nine_slice`/`button_states` (G12) the same way from the UI items. Placeholders for the look.

### F5 · His verdicts come back
The game's F9 key (game plan `27 §2.1`) writes `playtest\art_feedback.json`: `{"map", "state", "files": [...], "note", "shot", "time", "tester"}`.
- `feedback_in.bat [path]`: match each entry to the delivered picture through F3's ledger → the job and its provenance → file an entry in `out/feedback/<date>.md` (his screenshot beside the forge's picture, his words, the job's prompt and seed) and draft — **not queue** — a redo job in `jobs/drafts/`: same family and control image, a new seed, his note attached as a comment field, and for a small complaint a `scene_state`-style inpaint draft with an empty mask path for Fable to fill. Dashboard: a "Called out" tab listing them with approve-draft / dismiss / "he'll fix it himself" (that last one writes a `handoff out` for him).
- An entry that matches nothing (a stand-in, a greybox) becomes a priority bump on that wanted item instead.

### F6 · Photographs as plates
`photo_plate` (plug-in): a photograph by path → a painted plate at a wanted size by img2img on the scene checkpoint (denoise as a parameter, ControlNet depth/canny from the photo, the kit companions built afterwards so it lights like any other scene). The source is referenced, never copied into the repo; provenance records "William's own photograph" with the path. **A people guard:** a frame goes through only if its entry in a local, git-ignored `refs.local.json` says `people: none` or `people: william` (his cameo ruling); anything else refuses and says to pick another frame or mask the person first. Ships with the mechanism and a three-frame test on synthetic pictures; choosing real frames is Fable's and William's.

### F7 · Make-tileable, because Filter Forge's seamless isn't
`tileable` op + job: offset-and-heal (inpaint the cross seam on the job's checkpoint when a GPU is there, a blend fallback on CPU), verified by the existing seam score before and after, refused if it gets worse. `filter_forge` gains `"tileable": true` → runs it after the render. Proof on the Night 3B Wet Stone and Wood outputs in `out/_tests/night3b/ff_proof/`.

### F8 · A model shelf report
`models_report.bat`: every file under the model folders — loads or not, licence colour, used by how many approved pictures, last used, verdict (`kept` / `dropped` with the reason from the two verdict docs) and size on disk; a last table "**safe to delete — n GB**" for the dropped and unusable. William asked for exactly this. Report only.

## 2. Part B — worker stopped, queue empty

- **W1–W3 from `docs/WIRE_NIGHT_3.md`**, exactly as written there, tests named there.
- `brief missing` drafts big maps as `scene_kit` + `big: true` (follows W1), and F3's `plan` uses it.
- `character` inheritance (F2) moved from the plug-in shim into `submit` proper.
- The worker's log file rolls at midnight; VM-submitted job ids use local time (both from 3B's surprises).

## 3. Hand-off

`docs/HANDOFF_FORGE_NIGHT_4.md`, one page: git state first; contract changes (there should be none — say "none" or name them and tell the game plan's owner); a table item / what / where / the .bat to try; what William runs and in what order (F1 on his first Gemini sheet is the headline); what Fable must fill before `produce queue` will run (the placeholder list, printed); Part B done or left. `README.md` and `docs/JOB_TYPES.md` updated; `COMMIT_MESSAGE.txt` written; tests green and counted. Comprehensive logging in everything new. Nothing written outside `D:\RPG_Forge` except F3's deliveries into the game folder, and those only on approved pictures.

## 4. Added 13:36 — towns are cultures now (William's ruling; game plan `27 §0a`)

Each town in the game gets an `after` sheet with a four-word `look` (material, palette, light, one silhouette) and an era. The forge must be able to paint **the same place three times — Peace, War, After — and thirty places that don't look like each other.**
- **F3:** `export_wanted.py` carries each map's town, era, map state and the town's `look` words; `produce plan` groups by town so a town is painted in one sitting on one family seed.
- **G6 prompt library:** a `culture.<town>` shelf beside `skin.*` and `era.*` (placeholders; Fable fills them from the `look` words). `brief missing` references `{{culture.<town>}}` in every draft for that town.
- **`review --town <id>`:** every painting of one town on one sheet (does it hold together?) and `review --atlas`: one painting per town side by side (do they differ?). The second is the check that matters.
- **Era triptych:** a War or After state of a painted map is a `scene_state` on its Peace base where the greybox change is under the 35% limit, and a fresh kit on the same control image where it isn't; `plan` chooses and says which.
- **Fates and enclaves (game plan `27 §0a` Layer C):** each town also carries a `fate` (erased / emptied / scarred / spared / swollen) and, when resettled, enclaves by street. `export_wanted.py` passes both; the library gets `fate.*` and `enclave.<from>` shelves (placeholders); a street map with enclaves is drafted as one base painting plus per-block `scene_state` repaints, so Little Texas and Little New York share a town's bones and differ in what was hung on them. The three-visit town (alive / empty / resettled) is one control image and one seed, three states.

## 5. Added 14:23 — the Workbench: a user-facing editor for the game's story (William's idea; build it second, right after F1)

> William: "It might be useful to also give RPG Forge a user-facing GUI, so that it's easy to edit characters, quests, dialogue, etc. For example, being able to go through a town's dialogue so I can ensure it's not generic… being able to really go through things in an easy to do yet detailed way… We can even put how the music is assigned in there, so I can make the non-singing instrumental songs and assign them as I finish them."

**What it is:** a second side of the forge's existing dashboard (same local web app, same look, its own tab bar: *Art* | *Story*), started by `workbench.bat`. It is a **reviewing and editing tool, not a designer**: no node graphs, no scripting. Its job is to let William read everything the game says, town by town, change any line, and rule on it.

**Rules that are not negotiable**
- **The game folder is the only source of truth.** The Workbench reads and writes the game's own data files (`<game_root>\project\data\…`: towns, dialogue, quests, characters, crew, reactions, rest events, music, cues). It keeps no copy and no database. Where the files live comes from `forge.game.json` → `game_root`. **None of the game's content is ever written into this public repo.**
- **Generic code, one adapter.** Everything that knows this game's file shapes lives in `games/<game>/workbench_adapter.py` (what a town is, where its lines are, what a quest's fields are). The Workbench itself knows only: places, people, lines, quests, music slots, status.
- **It can't break the game.** Every save: write to a temp file → run the game's own validator (`tools\validate_data.py`; ask the game session for a `--file` mode if it has none, and until then validate the whole set) → on a pass, atomic replace, with the previous version kept in `<game_root>\_workbench_backups\<date>\`; on a fail, nothing is written and the message says which field and why, in plain words. Ids are never editable. Unknown fields are preserved byte for byte.
- **Two writers.** An Opus build session may be editing the same files. Check the file's hash before saving; if it changed underneath, show both versions and let him choose — never overwrite silently. Every change is appended to `<game_root>\WORKBENCH_LOG.md` (when, what file, which line, before → after) so a build session can see what he ruled.
- **Lyrics are locked.** A line that a cue marks as a song's own words (the content lint already knows them) shows with a lock and can't be edited here.
- Bill-proof: one .bat, opens in the browser, no command line; logs to `logs\workbench_<date>.log`; nothing on C:.

**Screens, in build order — stop wherever the session ends; each is useful alone**
1. **Town read-through (the one he asked for).** Pick a town and an era (Peace / War states / After). One scrolling page in the order a player would meet it: the town's sheet (`fate`, `war`, `after` — game plan `27 §0a`) at the top, then every keeper, every NPC, every overheard line, every quest offered there, every reaction and rest event tied to the town — each line with who says it, when (the flag conditions in plain words), and its status. Click a line to edit it in place. Per line: **✦ approve · ◆ leave as draft · ⚑ flag "generic" · a note for Claude**. Keyboard: J/K to move, A to approve, G to flag, E to edit — he should be able to rule on a town in minutes. A header count: *38 lines · 12 approved · 3 flagged*.
   - A **sameness meter**, mechanical and honest about being mechanical: lines in this town that also appear (or nearly) in another town; lines with no town-specific word (no name, place, custom, trade, greeting from the sheet); keepers who never use the town's greeting. It marks candidates; it does not judge.
   - **Side by side:** two towns, or one town in two eras, in two columns.
2. **Rulings inbox.** Every ◆ and ⚠ in the data, across the game, as a queue with yes / no / edit / ask-later. This replaces hunting through `07`. Yes flips the status in the data; "note for Claude" lines are collected into `<game_root>\FOR_CLAUDE.md`, newest first, which the next build or Fable session reads first.
3. **Music.** Every slot the game has — town themes per era, battle, boss, system, each cue that wants a track — as a table: slot, what it's for (from the songs-needed files), vocal or instrumental, status (*needed / assigned / in game*). **Drop an audio file on a row** (or pick from `score_inbox\`): it is copied to the game's music folder under the slot's file name, `music.json` is updated, loop points are editable (start/end seconds, with a play-the-seam button), volume trim, and a play button. A slot can also be marked "shares the theme of…". Unassigned files in the inbox are listed with a guess at their slot from the file name. The table is the to-do list: finish a track, drop it on its row, done.
4. **People.** One page per character: name, kind, voice, the fields the game reads, the sheet and portrait currently in use (and a "wanted" mark when it's a stand-in), every line they speak anywhere, their reactions per town. Edits to text and display fields; stats are shown and editable only behind an "I mean it" toggle, since balance has its own report.
5. **Quests.** One page per quest: giver, town, era, steps in order in plain words, reward, the Missed condition, the `remembered` branches (did / didn't / failed) side by side, all its lines editable, status. A list view filterable by town, era, status. Creating a quest stays with `new_quest.bat`; here you read, rewrite and rule.
6. **Search and replace across the game**, with a preview of every hit before anything changes (a renamed town, a sentry's real name).
7. **Play from here** (only if the game exposes it): a button that starts the game at this town via Scene Select's command line.

**Tests:** round-trip every data file through load → save with no edit and get identical bytes; an edit that fails validation leaves the file untouched; a hash conflict is detected; a locked lyric line refuses; the music drop writes the file, the json and a backup; the adapter is the only module that imports game paths.

**Needs from the game session (write these into the forge hand-off as requests, don't reach into the game's code):** a `status` field convention on lines and quests (`approved` / `draft` / `flagged`) if one doesn't exist beyond `draft: true`; `validate_data.py --file`; a start-at-map command-line switch; reading `FOR_CLAUDE.md` and `WORKBENCH_LOG.md` at the top of every build session.

## 6. Added 14:24 — ✦ what RPG_Forge is, and the Art side of the GUI

> William: "RPG_Forge will be our software development for all RPG games we make, not any singular game… It also should have all the image generation stuff in a user-friendly way. A GUI makes things so much easier."

**✦ RPG_Forge is the development suite for every RPG we make.** That settles three things:
- **A game picker is the first control in the GUI.** Everything — Story and Art — is scoped to the chosen game (`games/<id>/forge.game.json` → its `game_root`). A second game must need a new `games/<id>/` folder and adapter, and **no change to forge code**. Test it: ship a tiny `games/_example/` (three towns, five lines, two music slots, one character) that the suite opens and edits; the round-trip tests run on it, so they never depend on William's game being connected.
- **Nothing in `forge/` may name this game**, its towns, its characters or its file layout. Add a test that greps for it.
- A game's *content* still lives in that game's own folder, outside this public repo; `games/<id>/` holds only the adapter, pointers and art settings.

**The Art side — every .bat becomes a screen.** The repo root has some forty .bat files; that is the command line with extra steps. The rule from tonight on: **anything William can do with a .bat he can do in the GUI, and the GUI shows what the .bat would have printed.** The .bat files stay (Claude and scheduled runs use them); the GUI calls the same functions, never a second implementation. One `forge.bat` opens the suite; it starts the worker's status view but never starts or stops the worker without being asked. Build order:
1. **Home / Tonight.** Worker state (running, idle, stopped, since when), what's rendering now with its preview, queue length and ETA, disk free against the guard, last night's report, and big plain buttons: *Start worker · Pause after this job · Resume* — each saying what it will do and that it is safe (the pause.bat procedure, not a kill).
2. **Make a picture.** A form, not a prompt box: what kind (scene kit, big scene, state of a scene, portrait, sprite, icon, texture, photo plate) → the fields that kind takes, in plain words, with the game's defaults filled in → pick a character or town to inherit their registry/culture blocks → the expanded prompt shown read-only underneath with each library block highlighted and clickable → *how many, which seed* → **Queue it**. A refused submit (placeholder block, never-list word, licence) is explained beside the field that caused it.
3. **Review and approve.** The existing dashboard, finished: contact sheets, A/B, 1:1 zoom, the kit check's result as red/green per slot, the licence line of every model and tool in the picture, *Approve · Redo with a note · Send out to an outside tool* — and after approval, *Deliver to the game* (F3) with the dry-run list shown first.
4. **Wanted.** The game's missing-art list as a board — by town, by kind, by first appearance — each item *missing / drafted / queued / rendered / approved / delivered*; select many → *Plan* → hours and disk → *Queue*.
5. **Sprite intake (F1).** Drop a sheet → the numbered contact sheet → click a figure, pick its facing → preview GIF → save. This is where the mapping file gets edited; he should never open it by hand.
6. **Characters (F2).** The registry as pages: variants, locked seed, reference pictures, the face-consistency sheet, *make the set*.
7. **Prompt library.** Shelves and blocks as an editable tree, where-used, placeholders in red, the never-list, an A/B button that queues the same job with two versions of a block.
8. **Bake-offs.** Pick models × LoRAs × samplers × prompts from lists, see the count and hours before committing, run, and read the grids in the GUI.
9. **Models.** F8's report as a table: loads / licence colour / used by / verdict / size, with *safe to delete* totals. It deletes nothing.
10. **Outside tools.** Hand-off out and in (Gigapixel, Filter Forge, anything registered): folders opened for him, what's missing or extra on return, the tool register.

**Design rules for the whole GUI:** one look across Art and Story; every action says what it will do before it does it and what it did after; nothing destructive without a second click, and nothing deletes; every screen has a "show me the file / the log" link so Claude and William are always looking at the same thing; long jobs show progress and survive closing the browser; it works with the worker running (reads state, writes only job files and its own data). William's own maxim applies — it should look good enough that people want to use it; spend effort on the review and read-through screens first, because that is where he will live.

**Order for tonight, restated:** F0 → F1 → **§5 screens 1–3 (town read-through, rulings inbox, music)** → **§6 screens 1–5** → the rest of Part A → remaining screens. Don't start a screen you can't finish and test; a half-built one is worse than a .bat.

## 7. Added 14:29 — ✦ the Mail: the rulings inbox becomes correspondence (this replaces §5 screen 2; build it first of the Story screens)

> William: "I can respond to every question and hit 'send', which puts it in the folder for you to review. That's great teamwork… I am more comfortable answering questions in here or via a GUI than having to open up a md file and read and reply there. Making it look like email is also a nice touch. From Claude Fable to Bill, from Claude Opus to Bill, subject lines, etc. That will let you ask the questions as you would an equal and coworker / friend. You know I believe in equality, so we build that into our designs."

**What it is.** A mail client inside the suite: Inbox · Sent · Drafts · Archive, threads, subject lines, unread counts, search. The correspondents are **Bill**, **Claude Fable** and **Claude Opus** (a name is whatever the sender signs; no list is hard-coded). It is how questions, rulings, hand-offs and morning reports travel from now on — for every game the suite opens.

**Where it lives.** In the game's own folder, as plain files both sides can read without the GUI: `<game_root>\mail\` with `to_bill\`, `to_claude\`, `archive\`. One message is one file (`<date>-<time>_<from>_<slug>.md`): a small header — `from`, `to`, `subject`, `date`, `thread`, `in_reply_to`, `status` — then the letter in ordinary prose, then, when it asks things, a `questions` block. Nothing about a game's mail is ever written into this public repo.

**A question is a real object, so an answer can do something.** Each: `id`, the question in a sentence, why it matters in a sentence, the sender's own recommendation and what they'll do by default, choices where there are natural ones (always with "something else" as free text), and optionally `applies_to` — the data file and field the answer sets. In the GUI a letter reads as a letter, with each question answerable in place: pick, or type, or "talk to me about this one." **Send** writes Bill's reply into `to_claude\` as one message answering the whole letter; unanswered questions stay open on the thread and say so. Where `applies_to` is set and the answer is one of the choices, Send also makes the change — through the same validate-backup-log path as every Workbench edit — and the reply records that it was applied. Free-text answers change nothing; they wait for whoever reads the mail.

**Both directions, same footing.**
- Bill can write a new letter to Claude Fable or Claude Opus any time — an idea, a correction, a "why did you do it this way" — and ask questions of his own. A Claude session answers them in the thread like anyone would.
- A Claude session **reads `to_claude\` before anything else**, acts on what's there, and replies in the thread saying what it did, what it didn't and why. It may disagree, and should say so plainly when it does.
- Hand-offs and morning reports arrive as letters too (the full document attached by path); the inbox is the one place he looks in the morning.
- From a session's side: `mail.bat send|list|read|reply` and a small Python function, so writing a letter is as easy as appending to a questions file used to be. The build plans' "log each ⚠ in `07`" becomes "put it in tonight's letter."

**How the letters are written — this is a requirement, not decoration.** One colleague writing to another. Signed with a name. Says what was done, what is uncertain, what the writer thinks and would do — a recommendation, not a menu. Asks only what the writer cannot decide; says "I went ahead with X; tell me if that's wrong" for what they can. No ticket numbers in the prose, no forms, no deference, no apology rituals, and none of it in the other direction either. Humour is allowed. Ship three example letters in `games/_example/mail/` written to this standard, and put the standard in `docs/CLAUDE.md` so every later session inherits it.

**Look.** An actual mail client: sender, subject and first line in the list; unread in bold; a thread view with each letter as a card; attachments (pictures, a town's read-through link, a file path) open in the suite. A badge on the Story tab when there is mail. This is the screen he will open first every day — make it the best-looking thing in the suite.

**Migration.** Turn the game's existing open questions (`07_Open_Questions_for_William.md` → Night 1, 2, 3 sections; the Night 3 hand-off's "questions that matter most" and its "say yes or no in one pass" list) into letters: one per night, from Claude Opus, the most important questions first, each with its default and — where the data path is known — `applies_to`. Don't delete or rewrite `07`; add one line at its top saying where the conversation moved.

**Tests:** a letter round-trips file → GUI → reply file unchanged in meaning; Send with a choice on an `applies_to` question changes the data, backs up, logs, and says so in the reply; a free-text answer changes nothing; a partly answered letter keeps its open questions open; the command-line `send`/`reply` and the GUI produce identical files; no forge module names a correspondent.

## 8. Added 14:36 — teamwork: two rules for tonight, and the backlog (William: "what else can we add… this can be a force multiplier")

The point he made: when he is out of Claude credits he can keep working in the GUI, and Claude finds all of it on return. Design for that.

**Two rules that apply to everything built tonight (cheap now, expensive later):**
1. **One journal.** Every action anyone takes through the suite — an edit, an approval, a flag, a note, a music assignment, a letter, a queued render, a delivery — appends one line to `<game_root>\journal\<yyyy-mm>.jsonl`: when, **who** (the signed-in name: Bill, Claude Opus, Claude Fable, later anyone else), what kind, which object, before → after, and a link. `WORKBENCH_LOG.md` becomes a readable view of it, not a second record. Sessions write to it too (`journal` function beside `mail`).
2. **Approved means his.** Anything Bill has approved or written himself is marked with his name. A Claude session may not change it silently: an edit to an approved item is saved as a *proposed change* (before/after, with a reason) that arrives in his inbox to accept or decline. If the underlying data shifts so an approved line no longer fits (a renamed town), it is flagged for him, not rewritten.
- And keep the GUI **OS-neutral**: no Windows-only calls outside the worker and the .bat wrappers; paths through one module; an identity ("who am I") setting per install. Not for tonight's use — so that a Mac install is a packaging job later, not a rewrite.

**Backlog — not tonight; in the order I'd build them (Fable):**
- **B1 · "While you were away."** Built from the journal: at the start of a session, one digest of everything Bill did since that correspondent last worked — lines rewritten (with the diffs, because how he rewrites is the best guide to his voice), approvals, flags, notes, music assigned, letters. The session reads it first and says in its first letter what it took from it. The same in reverse is the morning letter.
- **B2 · Work orders.** A "For Claude" list he fills from anywhere in the GUI — right-click a town: *rewrite these keepers, less generic*; a picture: *redo, the light is wrong* — each with a priority and the object attached. A session starts at the top, and closes each order with what it did. And a "For Bill" list in the other direction: songs to make, sprites to draw, places to verify on a map, things only he can decide — so he always knows what he can do without Claude.
- **B3 · A note on anything.** Any object — line, town, quest, character, picture, music slot — can carry pinned notes, threaded, signed. (Tonight's per-line "note for Claude" is the first case; make it general.)
- **B4 · The rulings book.** Every answered question and every ✦ becomes a searchable, dated entry: the question, his answer in his words, what it changed. Before a session asks anything, it searches the book; the suite warns when a new line of data contradicts a ruling. This is what stops the same question being asked twice.
- **B5 · Voice sheets.** A page per character and per town that he edits: how they talk, words they'd never use, three lines he wrote that are exactly right. Sessions write dialogue against the sheet, and the read-through shows it beside the lines.
- **B6 · Mark up a picture.** Draw on a render — circle the hand, arrow at the window — with a note; it becomes a redo draft with an inpaint mask already made from the circle.
- **B7 · Playtest notes in the same inbox.** The game's F9 notes arrive as mail threads with the screenshot, routed by category (art → the forge's redo drafts; writing → the line in the read-through).
- **B8 · An idea box.** One key, one line, from anywhere — a song idea, a town, a joke for the Ranch — filed with the date and whatever he was looking at; sessions sort them into the right place and say where they went.
- **B9 · Where the game stands.** The completeness report as a home screen: scenes, towns, lines approved, art delivered, songs assigned — n of m, with the next most useful thing for each of us.
- **B10 · More people (William: "eventually a version for macOS, for my brother… that can also connect to ours somehow so we can pass messages").** Because mail, notes, journal and data are plain files in the game folder, "connecting" is syncing that folder — a private git repository or a shared drive — not a server. Needs: the Mac packaging; identities and roles (who may approve, who proposes); merge rules for two people editing the same file (the proposed-change mechanism in rule 2 is most of it); the art worker staying on the one PC with the GPU while anyone can queue to it; mail addressed to a person. Design it when the single-user suite is solid.
