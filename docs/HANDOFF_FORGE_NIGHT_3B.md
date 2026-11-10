# Hand-off — RPG_Forge, Night 3 part B (Opus, 2026-11-10 00:51 → 01:35)

Plan: `docs/ROADMAP_NIGHT_3.md` G13 and G14 (its Progress section is updated). **Tests: 139 → 155, all green**
(`python -m pytest`). The bake-off kept running the whole time; no file the worker reloads was edited — both items are
plug-ins with their helpers in new files (`forge/night3b/`), and the live worker logged picking them up
(01:09 `handoff_file, handoff_kit`, 01:14 `filter_forge`).

## Contract changes

None. `handoff_kit` writes the same six slot files as `scene_kit` (`kit check` and `approve --set` work on it);
`filter_forge` writes `<slot>_n.png` in the game's OpenGL convention.

## G13 — a hand-off folder for an outside tool (done)

| Command | What |
|---|---|
| `handoff_out.bat <name> <batch or job ids>` | copies each job's raw render (the one before the forge's own upscale; its finished picture if no raw was kept) to `out\handoff\<name>\in\<job id>__raw.png`, with `README.txt` (what size to make each one, where to save) and `handoff.json` |
| `handoff_in.bat <name> ["<tool name version>"]` | matches what is in `…\done` by the job id at the start of each name (the tool may add its own tag after `__` — Gigapixel does), checks sizes (same shape at another size → resized and said; another shape → refused and named), names **missing** and **extra** files, then queues one small job per picture at priority 10: **`handoff_kit`** (GPU, seconds: depth / normals / glow / layers rebuilt from the returned picture with the source kit's settings) for a kit, **`handoff_file`** (CPU) otherwise. `--no-submit` writes `jobs.json` instead |
| `handoff_tool_add.bat` | the tool register — one licence line per tool, asked one question at a time; `handoff_tool_add.bat list` shows them. Kept in `models/licences.json` beside the model licences (written atomically — the worker reads that file), so `approve` checks a tool exactly like a model |

Provenance of a filed picture: the source job's models (followed through `inputs`) + the tool as a licence line
(`role: outside_tool`). `approve` now runs a pre-flight that names every outside tool in the picture's history and,
for one with no licence on file, **asks for it there and then** (at a console; otherwise it prints the .bat to run).
A tool's `licence_condition` prints with the other conditions (`manifest.licence_conditions` now reads it from
`licences.json` too). Nothing in the code names a product.

**For William — record your two tools once** (or answer approve's question when it first asks):

    handoff_tool_add.bat "Gigapixel AI" "6.2.2" yes "annual revenue under US$1M" "Topaz Labs licensing page for standard licences, checked 2026-11-09"
    handoff_tool_add.bat "Filter Forge" "9.006" yes "" "William: used for commercial photography work; filters themselves may not be redistributed"

Use the version exactly as Gigapixel's Help → About shows it — the picture's provenance carries whatever you type in
`handoff_in.bat`. The 6.2.2 installer's own EULA text is still not on file (`docs/model_licences/` when you have it).

## G14 — a Filter Forge driver (done; the normal-map half of the proof needs one preset from William)

**What the renderer really takes** (read from `Filter Forge Help.chm` → Command-Line Renderer, `BatchSample.xml`,
and the element names inside `FFXCmdRenderer-x64.exe`): per task `Image` (picture, or empty + width/height for a
texture), `Selection`, `Result` (path, format, Options), `Filter` (.ffxml path), `Preset` (number from 0); one
`GlobalSettings` with `RenderingOptions` (incl. `NormalMapFlipY`: true = OpenGL) and `BitmapFormatOptions`.
**There is no task element for seamless, size, variation or the channel** — the help says the preset stores them
(Settings tab + the Render Channels menu). So:

- **A channel is a preset.** `"channels": {"final": 0, "normal": 9, "height": 10}` — one task per channel. Every one of
  the 694 factory presets in the 103 bundled filters renders the final image; asking a factory preset for a normal
  map is refused with how to save one. Filter Forge's own channel-file suffixes (`-normal`, `-height`, `-rough`, `-ao`,
  `-emis`, … taken from the renderer) are collected too.
- **Normals:** `NormalMapFlipY` true (OpenGL per the help). When a height or bump channel is rendered in the same job,
  the forge *measures* the convention against its own OpenGL normals from that height and flips green if it came back
  DirectX (tested both ways with a fake renderer). `<slot>_n.png` is 8-bit RGB for the game.
- **Seamless:** checked against the preset's own setting (factory presets; your own presets aren't in the filter
  file, so taken on trust) and the result's wrap seam is **measured** every time (`measured.seam`, a 2×2 tiling on
  the contact sheet, a note over 1.5).
- `forge.json` → `tools.filter_forge.exe` (re-read at job time, so the running worker saw it without a restart).
  Absent / missing → the job fails with a plain message and `doctor` says "Filter Forge: not installed".
- Read-only: filters are used by **path**, never copied; results, `tasks.xml`, `render.log` and Filter Forge's temp
  files go to the job's own out folder. `.gitignore` now has `*.ffxml` and `/*.exe` (see Surprises).
- Provenance: filter file name, path, name, library id (`242-5`), kind, presets per channel, Filter Forge version
  (read from the exe: 9.006.53910), the measurements, and the tool as a licence line `Filter Forge 9.006`.

Commands: `filter_forge.bat` (is it set up + licence line), `filter_forge.bat list` (bundled + your own library under
%APPDATA%, read-only), `filter_forge.bat presets Library_242-5`, `python -m forge filter-forge task <job.json>` (the XML
without running it), `filter_forge_proof.bat [normal preset] [height preset]`.

### The proof run (real renders on the worker, priority 10, batch `night3_proof`)

1. **Failed** — the renderer printed its usage: it does not accept `-l <folder\prefix>`. Now only the task file is
   passed (its own log stays in %TEMP%; the console text is kept as `render.log`).
2. **Failed** — `Item 'BMP' not found in item 'BitmapFormatOptions'`: the renderer insists on every format section.
   The block is now BatchSample.xml's, with PNG set to 16-bit (test added).
3. **Done in 6 s** — `20261110-061836-g14_ff_proof_wet_stone_1024-0db7`: bundled *Wet Stone* (Library_242-5, preset 0,
   Seamless Tiling on) at 1024×1024, 16-bit RGBA PNG. Copies in `out/_tests/night3b/ff_proof/`.

The two failed jobs are mine and are left in `jobs/failed/` (the morning report will show them under night3_proof).

**Not done: the normal map.** No factory preset renders one, and a preset can only be saved in Filter Forge's own
window. William: open *Wet Stone*, Render Channels menu → **Normal**, Presets tab → Add Preset; do the same with
**Height**; then `filter_forge.bat presets Library_242-5` shows the numbers (factory 0–6, yours follow — I could not
confirm from here that your presets are numbered after the factory ones; if the render comes back as the plain stone
picture, that is why) and `filter_forge_proof.bat <normal> <height>` queues it; the forge measures the normal map's
convention against the height map.

## Surprises

- **Seamless Tiling did not survive the command-line renderer.** Every "seamless" render came back with a visible
  wrap seam: Wet Stone preset 0 and preset 3 at 1024 and 2048 (seam ≈ 2–3, a faint 1-px line at 2× zoom), and the
  simple *Wood* filter at 512, 600, 800 and 1024 (top/bottom seam 10–16 — the stripes plainly don't line up; close-ups
  in `out/_tests/night3b/ff_proof/`). Not a size effect. Until someone finds the reason, treat Filter Forge textures as
  "make tileable in the forge before tiling" — the seam score will say when one is already fine. This bears directly on
  Fable's planned "seamless ground texture" test.
- **The Filter Forge installers (92 MB and 229 MB) were in the repo root, untracked.** `push.bat` runs `git add -A`,
  so the next push would have tried to upload them to the public repo (GitHub refuses files over 100 MB, so it would
  have failed half-way). `.gitignore` now excludes `/*.exe` and `*.ffxml`. They are safe to move or delete whenever
  you like — Filter Forge is installed.
- The worker writes into `logs/forge_2026-11-09.log` past midnight (it opened that file when it started).
- VM-submitted jobs still get UTC ids (the proof jobs say 06:18 for 01:18).

## Next session (Fable)

The plan in the Night 3B kickoff stands; with the seam finding, the ground-texture test should include the forge's own
make-tileable step, and the Iraq-frame photo effects are the most direct use (effect filters keep the picture's size,
`input` = the frame).
