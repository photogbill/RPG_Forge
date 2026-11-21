# RPG_Forge

**A one-stop development suite for making RPGs on your own PC — art, 3D, story, music and teamwork with Claude.**

RPG_Forge started as an art foundry (drop a JSON job in a folder, a worker on your graphics card paints it) and grew into
the whole workshop: a browser-based suite where you write and check dialogue, track music, review and approve art, turn
town plans into 3D stages, and leave letters and tasks for the AI assistants working beside you. It is **game-agnostic**:
each game is its own folder and its own small adapter, and nothing about any one game is built into the forge.

- **Everything runs locally.** No API keys, no cloud generation. Jobs, outputs, models and logs live beside the code.
- **Anyone can drive it** — you through the suite, a script through the folders, or Claude through its MCP connector.
- **Every output is accountable.** Each picture or model carries `prov.json` (model, licence, seed, prompt, every step),
  and nothing reaches a game until a person (or an assistant the person allowed) approves it.

```
 you (the suite, forge.bat) ─┐
 a script (jobs/*.json) ─────┼──►  queues  ──►  workers (ComfyUI on the GPU · Pillow/numpy · Blender)  ──►  out/
 Claude (the MCP connector) ─┘                                                                              │
          ▲                                                                                                 │
          └────────────── review & approve ◄──── checks, contact sheets, provenance ◄───────────────────────┘
                                   │
                                   └──► deliver into the game's own folder (with a ledger and undo)
```

---

## Contents

1. [What you need](#what-you-need)
2. [Install (Windows)](#install-windows)
3. [Run it](#run-it)
4. [Start a new game from scratch](#start-a-new-game-from-scratch) ← start here if you are new
5. [What the suite can do](#what-the-suite-can-do)
6. [Making art](#making-art)
7. [3D: bodies, props, buildings, places](#3d-bodies-props-buildings-places)
8. [The MCP connector for Claude](#the-mcp-connector-for-claude): setting up Claude, the tools, companion connectors
9. [Connecting other tools](#connecting-other-tools): Blender, Godot, Filter Forge, Photoshop, libraries, adding your own
10. [Everyday .bat files](#everyday-bat-files)
11. [On a Mac](#on-a-mac)
12. [Pushing changes (git)](#pushing-changes-git)
13. [Troubleshooting](#troubleshooting)
14. [Repository map](#repository-map) · [Further reading](#further-reading) · [Licence](#licence)

---

## What you need

| | Minimum | Notes |
|---|---|---|
| **OS** | Windows 10/11 | The suite (everything except making pictures/3D) also runs on macOS and Linux. |
| **Python** | 3.10 or newer | From python.org — tick **"Add python.exe to PATH"** when installing. |
| **Graphics card** | NVIDIA, CUDA-capable | Needed for pictures and 3D. 12 GB+ VRAM is comfortable; image-to-3D can spill to system RAM. |
| **Disk** | 100 GB+ free | Models are large (SDXL ~7 GB each, FLUX and 3D models more). The worker parks the queue under 40 GB free. |
| **Optional** | Blender, Godot, Filter Forge, Material Maker, Photoshop, Gigapixel | Each is used only if present. See [Connecting other tools](#connecting-other-tools). |

Everything installs **inside the RPG_Forge folder**. Nothing is written to `C:\Users\…` or AppData (`forge.json` refuses
outside paths unless you say so).

---

## Install (Windows)

Run these once, in order, by double-clicking them in the RPG_Forge folder:

1. **`install.bat`** — makes the Python environment (`venv\`), installs the CPU tools, writes the docs and runs the
   doctor. After this the suite and the CPU tools (palette snap, pixelize, pack sheets) already work.
2. **`install_comfy.bat`** — installs ComfyUI into `engines\ComfyUI` with CUDA PyTorch (a large one-time download).
   It points ComfyUI at every model folder listed in `forge.json → model_dirs`.
3. **Models** — get at least one picture model:
   - `pull_model.bat` — the SDXL base checkpoint (~6.9 GB) into `models\checkpoints\`, **or**
   - `pull_flux.bat` — FLUX.2 klein 4B (Apache-2.0) and its encoders/VAE, **or**
   - drop any checkpoint you own into `models\checkpoints\` (or a folder listed in `model_dirs`).
4. **`pull_quality.bat`** — the finishing models (RealESRGAN upscaler, face finder, SDXL ControlNet; all commercial-OK).
   Optional add-ons: `install_comfy_faces.bat` (FaceDetailer), `install_comfy_aux.bat` (depth maps),
   `install_comfy_gguf.bat` (GGUF model support).
5. **3D tools (optional)** — in the suite: **Settings → This computer → 3D tools → Install** (or
   `python -m forge 3d check | install`). TRELLIS.2, Pixal3D and the rigger install into this drive.
6. **`doctor.bat`** — the pre-flight check: what ComfyUI can run, which models are on disk, which tools are found.
   Run it whenever something seems missing.
7. **`scan_models.bat`** — reads every model file's header (no weights loaded) and writes `models\INVENTORY.md`:
   checkpoint or LoRA, SD1.5 / SDXL / FLUX, and trigger words.

> **Licences matter.** The forge refuses to deliver art made with a model it can't confirm is commercial-OK.
> `licence.bat` records a licence you checked yourself (e.g. a Civitai model page); `models_report.bat` says what each
> model file is, whether it loads, and what is safe to delete. See `docs/LICENSING.md`.

---

## Run it

| To… | Double-click | What happens |
|---|---|---|
| Open the suite | **`forge.bat`** | Opens http://127.0.0.1:8770 in your browser (only this PC can see it). Close the window to stop it. |
| Make pictures | **`run_worker.bat`** | Starts ComfyUI (minimised) and the GPU worker, which works through `jobs\pending\`. Also: ▶ Start / ■ Stop under the game picker in the suite. |
| CPU jobs only | `run_cpu_worker.bat` | Palette snap, pixelize, pack, normal maps — no graphics card needed. |
| Make the world's 3D things | `make_what_we_need.bat` | The world queue: takes the next thing on the world list, makes it, checks it, goes on until stopped. |
| Keep everything going day and night | **`art_around_the_clock.bat`** | Keeps ComfyUI and the world queue alive, restarts what stops, runs the daily redo at 05:00, keeps Windows awake. `art_around_the_clock_at_logon.bat` starts it at log-on. |
| The older art dashboard | `ui.bat` | http://127.0.0.1:8765 — queue, ETA, newest pictures, Retry/Pause/Approve. (Also in the suite: Art → Queue & pictures.) |

To **stop safely**: ■ Stop in the suite (pauses the queue after the job in hand), *Stop after this one* in 3D → World
list, or close the window — at most the job in hand is lost, and it is put back in line.

---

## Start a new game from scratch

*Written for anyone starting their own game with RPG_Forge.* A game is two things: a **config folder** inside the forge
(`games\<your_game>\`) and the **game's own folder** wherever you keep it (your Godot project, say). The forge never
pushes your game's data — `games\` is git-ignored except for the example.

### 1. Install and look at the example

Do the [Install](#install-windows) steps, run `forge.bat`, and pick **Example game (made up)**. It is a tiny invented
game (three places, five lines, one quest, two music slots, one person) that shows every screen working. Click around:
that is what your game will look like once it is connected.

### 2. Copy the example

Copy the folder `games\_example\` to `games\<your_game>\` — a short id with no spaces, e.g. `games\iron_coast\`.
You now have:

```
games\iron_coast\
  forge.game.json        ← your game's settings (step 3)
  workbench_adapter.py   ← tells the suite where things are in your game's files (step 4)
  characters\            ← one file per character: look, locked face seed, variants
  prompts\               ← your prompt library (library.json) and never-list (never.json)
  export_wanted.py       ← optional: lists what art your game still needs
  game\                  ← the example's made-up game folder — delete it once yours is connected
```

Add these as you need them: `bakeoff\` (test suites to compare models), `wanted_3d\` (the world list of 3D things),
`places\` (place plans that become 3D stages).

### 3. Fill in `forge.game.json`

```json
{
  "owner": "Alex",
  "game_root": "D:\\Games\\IronCoast",
  "asset_root": "D:\\Games\\IronCoast\\assets",
  "provenance_dir": "D:\\Games\\IronCoast\\assets\\_provenance",
  "palette": "resurrect-64",
  "scene_size": [1920, 1080],
  "card_size": [864, 486],
  "tile_size": 96,
  "hero_cell": [144, 216],
  "style_prefix": "",
  "negative": "text, watermark, signature, logo, blurry, deformed, extra limbs, extra fingers, low quality",
  "checkpoint": "sd_xl_base_1.0.safetensors"
}
```

| Field | What it is |
|---|---|
| `owner` | **Your name.** Letters from assistants are addressed to you; approvals are yours. |
| `game_root` | Your game's own folder (absolute, or relative to `games\<your_game>\`). On another computer you can override it in Settings → This computer. |
| `asset_root` / `provenance_dir` | Where delivered art goes in your game, and where its provenance records go. |
| `palette` | A palette in `palettes\` (Lospec `.hex` format) for palette-snapped jobs — add your own. |
| sizes | Your scene, card, tile and sprite-cell sizes, so jobs stay short. |
| `style_prefix` | Words put in front of every prompt — your house style. Leave empty and use the prompt library instead. |
| `checkpoint` | The default picture model — **must be a file you actually have** (see `models\INVENTORY.md`). `checkpoints_by_job` / `loras_by_job` set per-job-type choices. |

### 4. Point the adapter at your game's files

`workbench_adapter.py` is the one piece of code per game. It **only reads**: it tells the suite where your places,
dialogue lines, quests, music slots and people are. All writing goes through the suite's safe-save path (hash check →
your validator → backup → atomic replace → journal), so the adapter can't damage your files.

Open it and change:

- `name` — your game's display name.
- `data_globs` — which files hold your data, e.g. `("data/**/*.json",)`.
- `validator` — your game's own checker, run on a temp copy before any save (e.g. `("tools/validate.py", "--file")`).
  If you don't have one yet, copy the example's `game\tools\validate.py` and grow it.
- `places()`, `lines()`, `quests()`, `music_slots()`, `people()` — return your data in the suite's shapes
  (`Place`, `Line`, `Quest`, `MusicSlot`, `Person` from `forge/suite/adapter.py`). Each item carries a **ref**
  (file + JSON pointer) so the suite knows exactly where to save an edit.
- Optional hooks light up more screens: `builds()` and `completeness()` (Status), `town_sheets()` (floor plans),
  `play_command()` (open the game at a place), `profiles_dir()` (Characters → Profiles), `stage_maps()` /
  `stage_install()` (3D places). Leave out any you don't need — the tab just says what it is waiting for.

**Easiest path:** if your game's data is still blank, lay your folders out the way the example game does
(`data/places/*.json`, `data/dialogue/*.json`, `data/quests.json`, `data/music.json`, `data/characters.json`) and the
example adapter works almost unchanged. Or ask Claude to write the adapter for your layout — that is what the file is
designed for.

### 5. Check it

```
python -m forge suite-check
```

(from a command prompt in the RPG_Forge folder, after `venv\Scripts\activate`). It loads and saves every data file of
every game with no edit and confirms the bytes come back identical. Then run `forge.bat`, pick your game, and the first
time it asks **who you are** — every change you make is signed with that name.

### 6. Set your look

1. **Prompt library** (Workshop → Prompt library): write your look blocks — `{{style.house}}`, per-town culture and fate
   blocks. A red block is still a placeholder; the queue refuses to run jobs that use unwritten blocks.
2. **Characters**: one file per character in `characters\` (start from `hero.json`). A character's **locked seed** keeps
   its face the same across every picture. `characters.bat list | show | check | stubs`.
3. **Bake-off** (optional, recommended): put test prompts for the kinds of pictures your game needs in
   `games\<your_game>\bakeoff\*.json` and run `bakeoff.bat --quick`, then `bakeoff.bat`. It renders every model × LoRA
   on the same seed and builds comparison grids (`bakeoff_report.bat`) so you can pick the best model for each kind.

### 7. Make what the game needs

- **Art → Wanted** reads your game and lists every missing picture. *Plan* drafts one job per item; *What would it
  take?* shows jobs, GPU hours and disk; *Queue* runs them.
- **Art → Make a picture** for one-offs. **Art → Review & approve** to judge them; **Deliver to the game** copies the
  approved ones in (anything replaced is kept in `out\_replaced\`).
- For 3D: add things to `wanted_3d\*.json` (or 3D → World list) and start `make_what_we_need.bat`.

### 8. (Optional) Bring in Claude

Follow [Setting up Claude, start to finish](#setting-up-claude-start-to-finish). Claude can then queue jobs, review
results, add to the world list, write your adapter and write to you through the Mail. Put a short brief about your
story and rules in your game's folder. From then on the Mail and the Rulings book keep the conversation organised. To
hook up Blender, Godot or your other programs, see [Connecting other tools](#connecting-other-tools).

---

## What the suite can do

`forge.bat` opens one window with a **game picker** and a **sidebar of areas**, each with tabs across the top. Every tab
has an address (`#music/needed`) so reload keeps your place, and a line under the tabs says what the tab needs and
whether it has it.

| Area | Tabs | What it's for |
|---|---|---|
| **Home** | Today | What needs you, what changed since you last looked, the worker, the queue, the disk. |
| **Status** | At a glance · Builds · The game | Every requirement as big colour-coded tiles (met / partly / not met); the game's build queue and completeness checklist. |
| **Messages** | Inbox · Sent · Drafts · Archive | **The Mail**: letters between you and the assistants. Answer questions in place and press Send; the reply goes in the game's `mail\` folder for the next session. |
| **Tasks** | For you · For Claude · Done | A checklist (not an inbox) of everything waiting on someone. A task that wants a file takes it on the card. **Don't wait for me** switch: wait, take the defaults, or leave it to an assistant. |
| **Story** | Read-through · People · Quests · Voice sheets · Find & replace | Read a town top to bottom as a player meets it; edit lines in place (E), approve (A), flag generic (G). A sameness meter catches lines that could belong to any town. |
| **Music** | Overview · Needed · Singers · Score inbox · Briefs & songs | Every music slot with its state (needed → delivered → in game). Drop a finished track on its row to deliver it. Song review checks Suno sheets. |
| **Art** | Wanted · Make a picture · Review & approve · Queue & pictures · Floor plans · User Needs To Provide Image | Everything 2D: what's missing, making it, judging it, delivering it; town floor plans; requests for pictures only a person can supply. |
| **Characters** | Profiles · Characters · Behaviours · Sprite intake · Voice bench | Editable character profiles; the character registry (locked seeds, variants); turning any sprite sheet into the game's sheet; testing voices against mouth movement. |
| **3D** | Bodies · Skeleton & motions · Props & buildings · Trees · World list · Places · Terrain · Viewer · Runs | Words → picture → 3D model → skeleton → motions; the world list; place plans compiled into stages. |
| **Motion capture** | Takes to film · How to film | Planned motion-capture work. |
| **Workshop** | Prompt library · Bake-offs · Models · Outside tools | Look-word blocks; model comparisons; the model shelf (and what's safe to delete); hand-offs to outside programs. |
| **Notes** | Open notes · Rulings · Idea box · Playtest notes | **Rulings**: every answer you've given, searchable. **Idea box**: press **I** anywhere. Playtest notes taken in from the game. |
| **Settings** | This computer · About | Who you are, where the game folder is on this PC, 3D tools, approvals. |

**Safety built in:** a data file changes only through safe save (hash check, your game's validator, a backup in
`<game_root>\_workbench_backups\`, atomic replace). Every action by anyone is a line in `<game_root>\journal\`. An item a
person approved stays theirs — anyone else's edit becomes a *proposed change*.

---

## Making art

The art queue is a folder: `jobs\pending\*.json` → worker → `out\<job-id>\` (the picture, a contact sheet, `prov.json`,
the job). Drag a job or batch file onto `submit.bat`, use Art → Make a picture, or let Claude queue it.

```json
{"type": "scene_card", "name": "intro_01_kitchen", "game": "iron_coast",
 "prompt": "a farmhouse kitchen at breakfast, window light from the left, steam rising from a coffee pot"}
```

A batch: `{"batch": "name", "defaults": {...}, "jobs": [...]}`. `"priority": 10` runs a job first.

| Job type | Makes | Needs |
|---|---|---|
| `render` | A raw render with any checkpoint + LoRA chain (SDXL, FLUX.1, FLUX.2 klein) | GPU |
| `scene_paint` · `scene_kit` · `scene_big` | A painted background at game resolution; the six-file scene set (picture, normals, glow, back plane, over plane, depth); scenes larger than one frame | GPU |
| `repaint` · `inpaint` · `scene_state` | Greybox → painting at the exact pixel size; fixing part of a picture; the same room years later | GPU |
| `concept` · `scene_card` | Large concept paintings; cutscene / location cards | GPU |
| `portrait` · `character_set` | Seed-locked expression sets (one face, many moods) | GPU |
| `prop` · `icon` · `sleeve` | Props on alpha; inventory icons; record sleeves with real typography | GPU |
| `tile_texture` · `tileable` · `filter_forge` · `material_maker` | Seamless tiles and full material channel sets | GPU / CPU |
| `upscale` · `depth_map` | Upscaling to an exact size; depth maps | GPU |
| `palette_snap` · `pixelize` · `remove_bg` · `contact_sheet` · `pack_sheet` · `godot_tileset` · `canny` · `normal_map` · `emissive_mask` · `scene_layers` | Finishing and packing tools | CPU |
| `pipeline` | A chain of jobs as one (`$prev.outputs[0]` feeds the next step) | either |
| `model_3d` · `rig_body` · `fit_motions` · `grow_tree` · `compile_place` | 3D (see below) | GPU / CPU |

Every field: `docs/JOB_TYPES.md` (generated from the code). Templates for each type: `jobs\templates\`.

**Useful tools around the queue:** `eta.bat` (how long the queue will take) · `pause.bat` / `resume.bat` ·
`retry_failed.bat` · `night_report.bat` (what ran overnight, what failed and why) · `review.bat <batch>` and
`rate.bat` (score a batch 1–5) · `review_compact.bat` (small labelled sheets an AI can read) · `credits.bat` (every model
in shipped art) · `housekeeping.bat` (what in `out\` could be archived; deletes nothing).

---

## 3D: bodies, props, buildings, places

- **Bodies:** describe someone → four pictures → pick one → a 3D body (TRELLIS.2) → a skeleton (Make-It-Animatable for
  people, UniRig for animals) → motions fitted (walk, run, idle and more). A **picture gate** checks arms and head size
  before minutes go into a body.
- **Props and buildings:** at a real size in metres. TRELLIS.2 for things and vehicles, Pixal3D for buildings (it takes
  a back picture too). See-through things (fences, grilles) become flat cut-out panels.
- **Trees:** grown from species sheets (sliders, seed, bare or in leaf) — not image-to-3D.
- **The world list** (`games\<id>\wanted_3d\*.json`): one entry per thing — kind, size tier, real size, where it first
  appears. `make_what_we_need.bat` works through it; after every model come **checks** (sits level, loose pieces, blank
  glass, thin parts, colours hold). A leaning model is straightened, not thrown away. What passes goes to Review & approve.
- **Places:** a place plan (`<id>.place.json` — ground, roads, walls, furniture, every generated thing with its footprint)
  compiles in Blender into a stage the game loads, with terrain (including DTED heights) and a look (windows, trim,
  dressing). Compiling never starts generation; new world-list entries arrive held.
- **Approving:** *Approve everything here* on 3D → World list and Art → Review & approve, with an **Undo** for each
  thing. *Deliver* copies the .glb, its motion sheet and provenance into the game and records it in `delivered.json`.
- **Focus:** `python -m forge.focus <place>` (or the connector's `focus.set`) holds everything except one place, so
  the art finishes one area first. `resume_all_art.bat` releases exactly what the focus held.

Details: `docs/TREES.md`, `docs/TERRAIN.md`, `docs/DRESSING_KINDS.md`, `docs/EDITING_MODELS.md`, `docs/APPROVALS.md`,
`docs/AROUND_THE_CLOCK.md`.

---

## The MCP connector for Claude

RPG_Forge is an **MCP server** (a "connector"). Once it is added to the Claude desktop app, Claude can work the forge
from a chat: check the queues, queue art jobs, add to the world list, look at what was made, run Blender scripts, take in
photos, approve (only when you allow it), and write to you through the Mail. It works in chats on the PC that runs the
forge, and in cloud chats linked to that PC.

### Setting up Claude, start to finish

1. **Install the Claude desktop app** on the PC that runs the forge and sign in. Connectors that run on your own computer
   (the forge, Blender, Godot) need the desktop app. Chats in the browser or on your phone can still use them when they
   are linked to that PC through the desktop app.
2. **Add the forge's connector** with Way 1 or Way 2 below.
3. **Give Claude the folders.** In a chat, use **+ → Add folder** to add `RPG_Forge` and your game's folder. The
   connector lets Claude *operate* the forge. The folders let it *read and edit* files: the adapter, place plans, build
   plans, docs. Add only the folders the work needs.
4. **Add the companion connectors** you want (see below): Blender, Godot, Suno.
5. **Tell the forge what Claude may approve.** Assistants can always queue, check and propose. Approving and delivering
   are yours unless you switch it on:
   - **Settings → Approvals → "Fable may approve for me"**: Claude Fable approves made things on its own, signed
     "Claude Fable, for <owner>". Words (dialogue, lyrics, rulings) always stay yours.
   - **`concur.bat`**: gives your OK for Claude Opus to approve and deliver for the next 30 minutes
     (`concur.bat status`, `concur.bat close`).
   - **Tasks → Don't wait for me**: lets questions take their default answer, or go to an assistant, when you're busy.
6. **Brief it in the first chat.** For example: *"Read `docs/CLAUDE.md` in RPG_Forge, then run `forge_status` and tell me
   where my game stands."* `docs/CLAUDE.md` is the hand-off page any new session can work from.
7. **Work as a team.** Claude writes to you through the **Mail** (Messages), and you answer there. Things waiting on
   either side are on **Tasks**. Everything you've ruled is kept in **Notes → Rulings**, so a new session doesn't ask
   again.

### Add the forge's connector (once)

**Way 1 — the settings entry**

1. Run `install.bat` first if you haven't.
2. Double-click **`mcp_setup.bat`**. It makes a small environment of its own (`venv_mcp`, so the art worker's is never
   touched), installs the MCP library (`requirements-mcp.txt`) and runs a self-test.
3. It offers to add the forge to Claude's settings. **Y**: it keeps a copy of the settings file and leaves every other
   entry alone. **N**: it puts the lines on the clipboard; paste them into Claude → Settings → Developer → Edit Config,
   inside `"mcpServers"`.
4. **Quit Claude fully** (right-click its icon by the clock → Quit) and open it again.

**Way 2 — the extension file** (use this if Claude shows no forge tools after Way 1 — the **Microsoft Store** install of
Claude needs it; `mcp_setup.bat` tells you which install it found)

1. Run `mcp_setup.bat` once (it makes `venv_mcp`), then double-click **`mcp_extension.bat`**. It makes
   `local\mcp\rpg-forge.mcpb` and opens the folder with it selected.
2. In Claude: **Settings → Desktop app → Manage** (beside Extensions) → **Advanced settings → Extension Developer →
   Install Extension…** → pick the file → **Install**. (Or double-click the file, or drag it onto the Extensions page.)
3. If the tools don't show, quit Claude fully and reopen it.

Only one way is needed — both are named `rpg-forge`. `mcp_extension.bat` offers to remove the settings entry if it finds
one. The extension file's paths belong to the computer that made it; on another PC, run both .bat files there.

**Check it:** `mcp_check.bat` re-runs the self-test and changes nothing. When the connector starts,
`logs\forge_<date>.log` gains the line *"mcp: the connector started"*. In a chat, ask Claude to run `forge_status`.

### Companion connectors

These are separate MCP servers that sit beside the forge's connector, so Claude can work inside those programs directly.

| Connector | What Claude can do | Set it up |
|---|---|---|
| **Blender** | Look at the open scene, take screenshots, run Python in your live Blender, search Blender's docs | Install Blender's MCP add-on (Edit → Preferences → Add-ons → Install from Disk), enable it and start its server, then add the Blender connector in Claude as the add-on's instructions say. Quit Claude fully and reopen. For unattended work the forge's own `blender.run` is better: it runs Blender in the background with one add-on profile and doesn't touch your open window. |
| **Godot** | Open the editor, run the project and read its debug output, create scenes, add nodes | Uses Coding-Solo's **godot-mcp** (MIT). `godot_extension.bat` shows this PC's packed extension (`local\mcp\godot-<game>.mcpb`, pointed at one game's Godot). Install it like the forge's: Settings → Desktop app → Manage → Advanced settings → Extension Developer → Install Extension… For a different game or PC, ask Claude to pack godot-mcp again, pointed at that game's Godot and project folder. |
| **Suno** | Make and fetch songs, stems and covers; manage playlists | A claude.ai connector: Settings → Connectors → Suno, signed in with your Suno account. Before a draft goes to Suno, the forge's `music.review` checks it. |
| **Others** | Anything with an MCP server (Google Drive, GitHub, Notion…) | Claude → Settings → Connectors. The forge doesn't need them, but they can sit next to it. |

**One name per connector.** If a connector is in both Claude's settings file and an extension, two copies answer to
one name. Keep only one.

### The tools Claude gets

| Tool | What it does |
|---|---|
| `forge_status` | Everything at a glance: art queue, world queue and backlog in hours, the never-stop launcher, ComfyUI, the disk, what waits for approval. **Start here.** |
| `forge_search` | Finds the operation for what you want to do, with its exact input. Empty: lists every operation and job type. |
| `forge_call` | Runs one operation: `op`, `input`, `who`, `dry_run`, `idempotency_key`. |
| `forge_job` | One art job, with its contact sheet as a picture. |
| `forge_wait` | Waits up to 50 s for an art job, then shows it. |
| `forge_area` | A place: its things on the world list and their states, and the game's own pictures of it. |
| `forge_pictures` | Any picture inside the forge folder, by path, downsized. |

### The operations (`forge_call`)

| Group | Read | Change |
|---|---|---|
| Overview | `status`, `clock.status`, `focus.status` | `focus.set`, `focus.resume` |
| Art queue | `jobs.types`, `jobs.list`, `jobs.get` | `jobs.submit`, `jobs.submit_batch`, `jobs.retry_failed` |
| World list | `world.list`, `world.redo_plan` | `world.add`, `world.hold`, `world.make_again`, `world.try_again`, `world.straighten`, `world.place_again`, `world.match_and_release`\*, `world.release_as_made`\* |
| Approvals & delivery | `approvals.plan`, `approvals.log` | `approvals.all`\*, `approvals.undo`, `models.deliver`\* |
| Places & areas | `places.list`, `places.show`, `areas.check`, `areas.board`, `slice.board` | `places.compile` (starts no generation), `places.take_pictures` |
| Blender | `blender.profiles`, `blender.status` | `blender.run` (a script in Blender, in the background, with one add-on profile) |
| Photographic Studio | `studio.schema` | `studio.run` (edit, clean, match, depth, cutout, relight, restore, stack…) |
| Photos & libraries | `scans.list`, `library.search` (incl. Poly Haven online) | `scans.intake`, `library.import` (Poly Haven, ambientCG, a folder with its licence line) |
| Looks | — | `look.lut` (a Photoshop .cube grade → a Godot colour-correction texture) |
| Tools | `tools.list` | — |
| Requests & Mail | `provide.list`, `mail.inbox` | `provide.add`, `mail.to_bill` |
| Songs | `music.review` (a draft, or every sheet; writes only its report) | — |

\* An approval. Only **Claude Fable** may do it, and only while **Settings → Approvals → "Fable may approve for me"** is
on; it is signed "Claude Fable, for <owner>". **Claude Opus** may approve only with your concurrence: run
`concur.bat` to give your OK for 30 minutes (`concur.bat status` / `concur.bat close`). Anyone else gets `needs_approval`.

### What a call looks like

```
forge_call(op="jobs.submit",
           input={"job": {"type": "concept", "name": "inn_dusk", "prompt": "{{style.house}}, a roadside inn at dusk"}},
           who="Claude Fable",
           dry_run=true)
```

Run with `dry_run: true` first to see what would happen, then again without it. Every answer has one shape: `done`,
`running`, `needs_approval`, `dry_run`, or `error` with a `code` (`invalid_input`, `not_found`, `refused`, `conflict`,
`in_progress`, `outcome_unknown`, `unsupported`, `internal`) and exactly one `next` step.

### The rules it keeps

- **No back doors.** Every change goes through the same function the suite uses, so licence checks, look blocks and
  refusals are the forge's own. If the suite would refuse it, the connector refuses it.
- **Signed by a Claude.** `who` is required on every change and must start with "Claude" — the connector can never act
  as the person.
- **Dry run and safe retries.** `dry_run` writes nothing; an `idempotency_key` makes a retried call return the first
  answer and do nothing again.
- **Never offered:** deleting anything; starting or stopping the world queue or launcher; settings; canon, lyrics or
  rulings; shell commands.
- **Writes only inside the forge** (`logs\`, `local\mcp\`, the queues), except Claude's settings file when you say Y.
- Each call runs the forge's newest code — **no restart needed** after an update.

Full detail: `docs/MCP.md`. For assistants working in the folders directly: `docs/CLAUDE.md` and `docs/PROTOCOL.md`.

---

## Connecting other tools

RPG_Forge is meant to be the hub: it drives the programs you already have rather than replacing them. Every tool is
**optional**. If one is missing, the jobs that need it say so and everything else keeps working.

### The four ways a tool connects

| Way | How it works | Tools |
|---|---|---|
| **1. Driven by the forge** | The forge runs the program's command line in the background, as a job, and files the result with provenance. | ComfyUI, Blender, Filter Forge, Material Maker, Godot (still mode), Photographic Studio, faster-whisper, Rhubarb |
| **2. Hand-off folder** | For programs with no command line. The forge writes a folder of inputs and a README saying what to make. You run the program's batch on it, then the forge files what comes back. | Topaz Gigapixel, Photoshop, Upscayl, anything that batch-processes a folder |
| **3. The Libraries shelf** | Assets downloaded once, each kept with its licence line, then searched and used like your own. | Poly Haven, ambientCG (CC0, fetched by id), Megascans on Fab, BlenderKit, your own photo scans |
| **4. A Claude connector** | The program has its own MCP server, so Claude works in it directly, next to the forge's connector. | Blender (its MCP add-on), Godot (godot-mcp), Suno |

### How the forge finds a tool

The list of tools is `forge/tools/registry.json`. Each entry gives the usual install paths, the licence, what the tool is
for and which operation drives it. A tool is **found** when the first of its paths exists. To see what is found:

- **Workshop → Outside tools** in the suite, or `doctor.bat`
- `python -m forge.toolsreg` (one line per tool), or the connector's `tools.list`

**If a tool is installed somewhere else**, point the forge at it in `forge.json`. Nothing else needs changing:

```json
"tools": {
  "filter_forge":   { "exe": "E:\\Apps\\Filter Forge 15\\Bin\\FFXCmdRenderer-x64.exe", "library_dirs": [] },
  "material_maker": { "exe": "E:\\Apps\\MaterialMaker\\material_maker.exe" },
  "gigapixel":      { "exe": "E:\\Apps\\Topaz Gigapixel\\Topaz Gigapixel.exe" }
},
"threed": { "blender_program": "E:\\Apps\\Blender 5.3\\blender.exe" }
```

The two exceptions: **Godot** is set per computer in the suite (**Settings → This computer → Godot**), and the
**Photographic Studio** is found through the `STUDIO_DIR` environment variable (the folder that holds `studio-cli.bat`).

### Setting up each tool

| Tool | Install | Point the forge at it | Then |
|---|---|---|---|
| **ComfyUI** | `install_comfy.bat` (into `engines\ComfyUI`); extras: `install_comfy_faces.bat`, `install_comfy_aux.bat`, `install_comfy_gguf.bat` | Automatic. Its address is `forge.json → comfy.url` (default `http://127.0.0.1:8188`) | `start_comfy.bat` on its own, or `run_worker.bat`, which starts it for you |
| **3D engines** (TRELLIS.2, Pixal3D, rigging) | Settings → This computer → **3D tools → Install** | Automatic | `python -m forge 3d check` |
| **Blender** | blender.org (5.x) | `forge.json → threed.blender_program` | Add-ons are enabled per job from *profiles* (trees, buildings, ruins, terrain, godot_export…): `forge/threed/blender/profiles.json`, listed in `docs/BLENDER_ADDONS.md`. Install an add-on in Blender once and add it to a profile. |
| **Godot** | godotengine.org, or the copy inside your game folder | Settings → This computer → Godot; your adapter's `play_command()` says how to start the game at a place | 3D → Places → *Open in the game here* and *Take the pictures* |
| **Filter Forge** | Its installer (needs your licence for commercial use) | `forge.json → tools.filter_forge.exe` (the command-line renderer, `FFXCmdRenderer-x64.exe`); `library_dirs` adds filter folders | `filter_forge` jobs; `ff_picks.bat`; `docs/MATERIALS.md` |
| **Material Maker** | github.com/RodZill4/material-maker (MIT); unzip into `engines\material_maker` | Automatic there, otherwise `tools.material_maker.exe` | `material_maker` jobs; `material_maker.bat` |
| **Photographic Studio By Bill** | Its own repository | `STUDIO_DIR` = its folder | `studio.run` from Claude; `scans_intake.bat` develops raw photos with it |
| **RealityScan** | Epic Games Launcher | Found in its usual install paths | Object scans in `scans\incoming\<date>_<subject>\` → `scans_intake.bat` |
| **faster-whisper** · **Rhubarb** | `get_whisper.bat` · `get_rhubarb.bat` (into the forge folder) | Automatic | Word times and mouth shapes for spoken lines; Characters → Voice bench |
| **Gigapixel**, **Upscayl**, other folder tools | Their installers | Not needed (it's done by hand) | `handoff_out.bat <name> <batch or job ids>` writes `out\handoff\<name>\in\` with a README. Run the tool's batch into `…\out\`, then `handoff_in.bat <name>`. |
| **Photoshop** | Adobe | Not needed (it's done by hand) | Grade the stills the forge renders, then *File → Export → Color Lookup Tables (.cube)*. `look.lut` turns the .cube into the game's colour correction. |
| **Poly Haven · ambientCG** | Nothing to install | Online | `library.search` / `library.import` (Claude), fetched at 1k/2k/4k with the CC0 line kept |
| **Megascans (Fab) · BlenderKit** | Your Epic / BlenderKit account | Download into `library\incoming\fab\` | `library.import` with source `fab` / `blenderkit` and the asset's licence line |

### Licences for outside tools

The forge refuses to deliver something made by a tool whose licence it doesn't know. Record one once with
**`handoff_tool_add.bat`**: it asks the name, version, whether commercial use is allowed, any condition, and where you
checked (`handoff_tool_add.bat list` shows what's on file). Model licences work the same way with `licence.bat`.

### Adding a new tool

1. Add an entry to `forge/tools/registry.json`: `id`, `name`, `paths` (where it usually installs), `licence`, `for`, and
   `op` (the operation or job type that drives it) or `by_hand` (what the person does).
2. Record its licence with `handoff_tool_add.bat`.
3. If the forge should **drive** it, add a job type as a plug-in in `forge/plugins/` (see `filter_forge.py` or
   `materials.py` for the pattern). A running worker picks up a new plug-in before its next job, so no restart is needed.
   If it has no command line, use the hand-off folder instead; that needs no code.

Or ask Claude to do all three. The registry and plug-ins are written to be extended that way.

---

## Everyday .bat files

There are many .bat files; these are the ones you'll actually use. (One-off run scripts for a particular night's work,
such as the `trellis_*` trials, are kept for record and can be ignored.)

| Setup | Daily | Art & review | Story, music, game |
|---|---|---|---|
| `install.bat` | `forge.bat` | `submit.bat` | `mail.bat` |
| `install_comfy.bat` | `run_worker.bat` | `review.bat` · `rate.bat` | `review_songs.bat` |
| `pull_model.bat` · `pull_flux.bat` | `art_around_the_clock.bat` | `bakeoff.bat` · `bakeoff_report.bat` | `characters.bat` |
| `pull_quality.bat` | `make_what_we_need.bat` | `approve.bat` · `deliver.bat` | `sprite_intake.bat` |
| `doctor.bat` · `kit_check.bat` | `eta.bat` · `night_report.bat` | `retry_failed.bat` | `floor_plans.bat` |
| `scan_models.bat` · `models_report.bat` | `pause.bat` · `resume.bat` | `wanted.bat` · `produce.bat` | `feedback_in.bat` (playtest notes) |
| `mcp_setup.bat` · `mcp_extension.bat` · `mcp_check.bat` | `concur.bat` | `scans_intake.bat` (your photos → textures) | `loudness.bat` (music levels) |
| `licence.bat` · `licences.bat` | `push.bat` | `ff_picks.bat` · `material_maker.bat` | `terrain_bake.bat` |

Every command is also available as `python -m forge <command>` (run `python -m forge` for the list). `run_tests.bat`
runs the test suite and is safe while the worker renders.

---

## On a Mac

The suite (everything except making pictures and 3D) runs on macOS:

1. Python 3.11+ from python.org (the official installer).
2. This repository (GitHub → Code → Download ZIP, or `git clone`) and a copy of the game's folder.
3. Double-click **`install_mac.command`** once, then **`forge.command`**. If Finder won't open them, run
   `chmod +x *.command` once in Terminal in this folder.
4. The first time, it asks who you are and where the game folder is on this Mac (Settings → This computer).

Messages, Tasks, Story, Music, Characters, Notes and Review & approve all work. The connector on a Mac:
`mcp_setup.command`. Any forge command: `./forge.command <words>`. Linux: `python -m venv venv && . venv/bin/activate &&
pip install -r requirements.txt && python -m forge suite`.

The suite's tests run on Windows, macOS and Linux at every push:
![suite tests](https://github.com/photogbill/RPG_Forge/actions/workflows/suite.yml/badge.svg)

---

## Pushing changes (git)

**`push.bat`** commits and pushes. Whoever changed the files (a person, a script, Claude) writes what changed in
`COMMIT_MESSAGE.txt` at the repository root. `push.bat` uses it and records it in `CHANGELOG.md`; with no file, it asks
you for one line.

**Commit messages never name a game.** RPG_Forge is a tool for every game, and its history is public. A message
describes what changed in the forge (the code, the tools, the docs). The game's own notes stay in the game's folder.
`push.bat` checks the message first (`forge/commit_check.py`). The words it looks for come from the games on your PC:
each game's id and folder paths, its adapter's name, places and people, and anything listed in
`games/<id>/private_words.txt`. If the message names any of them, Notepad opens so you can fix it, and nothing is
committed until it's clean. Model collections, outputs, logs, the queue state, `local\` and every game's own folder are git-ignored — a push
never uploads your weights, your photos or your game.

---

## Troubleshooting

| Problem | Try |
|---|---|
| "Run install.bat first" | `venv\` is missing — run `install.bat`. |
| Jobs sit in pending | Is the worker running (▶ Start, or `run_worker.bat`)? Is the queue paused (`resume.bat`)? Under 40 GB free the queue parks itself. |
| A job failed | `night_report.bat` or Art → Queue & pictures says why; `retry_failed.bat` puts it back. |
| "model not found" / refused for licence | `doctor.bat`, then `models_report.bat`; record a licence you checked with `licence.bat`. |
| Claude shows no forge tools | Quit Claude fully and reopen; if still nothing, use the extension way (`mcp_extension.bat`). Check `logs\forge_<date>.log` for "the connector started". |
| `forge_status` slow | It should answer in a second or two; its answer ends with `took_seconds` per part, and slow parts are logged. |
| The suite says a tab "needs" something | That line names what's missing (a hook in your adapter, a tool, a later build). |
| Your edits were not saved | Someone else saved the file first — the suite shows both versions and writes nothing until you choose. |

Logs for everything: `logs\`.

---

## Repository map

```
forge/              the package: queue, CLI, engines (ComfyUI graphs), jobs, plugins
  suite/            the browser suite (forge.bat): areas, Mail, safe save, journal, adapter contract
  threed/           3D: world queue, checks, places, terrain, trees, Blender scripts
  mcpserver/        the MCP connector
  tools/            the outside-tool register
forge.json          configuration (paths, ComfyUI url, model folders, defaults)
games/              one folder per game (git-ignored); games/_example is the template
jobs/               pending/ running/ done/ failed/ paused/ — the queue; templates/ — one example per job type
out/                results, one folder per job id
models/             weights (ignored) + models.json registry and licences.json
palettes/           master palettes (.hex, Lospec format)
engines/            ComfyUI and other installed engines (ignored)
local/              this PC's own settings, keys and extension files (ignored)
docs/               the reference documents (below)
tests/              pytest
```

## Further reading

| Doc | About |
|---|---|
| `docs/MCP.md` | The connector in full |
| `docs/CLAUDE.md` · `docs/PROTOCOL.md` | Hand-off notes and the folder protocol for AI assistants |
| `docs/JOB_TYPES.md` | Every job type and field (generated from the code) |
| `docs/APPROVALS.md` · `docs/AROUND_THE_CLOCK.md` | Approving, undo, and the never-stop launcher |
| `docs/FLOOR_PLANS.md` · `docs/TILES.md` · `docs/MATERIALS.md` | Towns, tiles and materials |
| `docs/TERRAIN.md` · `docs/TREES.md` · `docs/DRESSING_KINDS.md` · `docs/EDITING_MODELS.md` · `docs/ANIMALS.md` | 3D detail |
| `docs/SONG_REVIEW.md` | The Suno sheet reviewer |
| `docs/LICENSING.md` · `docs/model_licences/` | Licences of models and tools |
| `docs/ROADMAP.md` | What's planned |
| `docs/BUILD_NOTES.md` | The previous README: build-by-build notes with every detail |

## Licence

MIT for the code. Models, palettes, outside tools and library assets carry their own licences — see `docs/LICENSING.md`,
`models/models.json` and the tool register (`tools.list`).
