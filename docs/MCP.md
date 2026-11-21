# The forge as a connector for Claude (BUILD 83 Part A, 2026-11-19)

✦ William, 2026-11-19 14:22: "Now we need to build MCP into RPG_Forge so that Fable and Opus can utilize it."

RPG_Forge is now an MCP server (a "connector"). Once it is added to Claude's desktop app, Claude Fable and Claude Opus can work
the forge from a chat: check the queues, queue art jobs, add to the world list, look at what was made, approve (Fable only,
while allowed), and write to William through the Mail. This works in chats on this PC, and in cloud chats linked to it
(where it appears beside Blender).

## Setting it up (once)

1. Double-click **`mcp_setup.bat`**. It:
   - makes a small Python environment of its own (`venv_mcp`), so the art worker's is never touched;
   - installs the MCP library (`requirements-mcp.txt`);
   - runs the self-test.
2. It then offers to add the forge to Claude's settings for you. Say **Y**: it keeps a copy of the settings file first, and
   leaves Blender's entry and every other entry as they were. Say **N** instead, and it puts the lines on the clipboard and
   says where to paste them (Claude → Settings → Developer → Edit Config, inside `"mcpServers"`).
3. **Quit Claude fully** (right-click its icon by the clock → Quit) and open it again.

`mcp_check.bat` runs the self-test at any time and changes nothing. On a Mac: `mcp_setup.command`.

### If Claude shows no forge tools: the extension way (BUILD 84 part 4)

On William's PC (the **Microsoft Store** install of Claude, 2026-11-19) the entry was in Claude's settings file and the app
never started the connector, even after a full quit and restart: the forge's log had no "the connector started" line. The
same app does start connectors that are installed as **extensions**. So:

1. Double-click **`mcp_extension.bat`** (after `mcp_setup.bat` has run once). It makes `local\mcp\rpg-forge.mcpb`, a small
   file that only says how to start the connector already in this folder, and opens the folder with the file selected.
2. In Claude: **Settings → Desktop app → Manage** (beside Extensions; older layout: Settings → Extensions) → **Advanced
   settings → Extension Developer → Install Extension…** → pick the file → **Install**.
3. If its tools do not show, quit Claude fully and open it again. The same page lists it under "Local MCP servers" once
   it is running, and `logs\forge_<date>.log` gains a line "mcp: the connector started".

`mcp_setup.bat` now says which install of Claude it found, and on a Store install it says to go straight to the
extension. The file's paths belong to this computer: on another computer, run the two .bat files there.

**One name, two ways in.** The settings entry and the extension are both called `rpg-forge`. Only one is needed. If both
were ever started at once, two connectors would answer to one name. `mcp_extension.bat` looks for the settings entry and
offers to take it out (it keeps a copy of the settings file first and leaves every other entry as it was). By hand: Claude →
Settings → Developer → Edit Config → delete the `"rpg-forge"` entry inside `"mcpServers"`, save, quit Claude fully and
open it again.

## The seven tools

| Tool | What it does |
|---|---|
| `forge_status` | Everything at a glance: the art queue, the world queue and its backlog in hours, the never-stop launcher, ComfyUI, the disk, and what waits for approval. Start here. |
| `forge_search` | Finds the operation for what you want, with its exact input. |
| `forge_call` | Runs one operation: `op`, `input`, `who`, `dry_run`, `idempotency_key`. |
| `forge_job` | One art job, with its contact sheet as a picture. |
| `forge_wait` | Waits up to 50 s for an art job, then shows it. |
| `forge_area` | A place: its things on the world list and the game's own pictures of it. (The area checklists are Part B, not built yet.) |
| `forge_pictures` | Any picture inside the forge folder by path, downsized. |

**`forge_status` answers in a second or two** (BUILD 84 part 4). It took 25 to 77 seconds on 2026-11-19, for two reasons,
both gone: it opened every finished job file to count them (16,700), and it read the world list three times, each time
asking the disk once a made thing a folder where that thing's Review entry was (350 × 350 questions). The art queue is now
counted from the folder's own listing, the list is read once, and every Review entry is found in one walk. Its answer ends
with `took_seconds` (the whole and each part); a status slower than 5 seconds says so in the log with its slowest part.

## The operations (`forge_call`)

| Group | Read | Change |
|---|---|---|
| Overview | `status`, `clock.status` | — |
| Art queue | `jobs.types`, `jobs.list`, `jobs.get` | `jobs.submit`, `jobs.submit_batch`, `jobs.retry_failed` |
| World list | `world.list`, `world.redo_plan` | `world.add`, `world.hold`, `world.make_again`, `world.try_again`, `world.straighten`, `world.place_again`, `world.match_and_release`\*, `world.release_as_made`\* |
| Approvals (BUILD 78) | `approvals.plan`, `approvals.log` | `approvals.all`\*, `approvals.undo`\* |
| Places | `places.list`, `places.show` | `places.compile` (starts no generation), `places.take_pictures` |
| Requests and Mail | `provide.list`, `mail.inbox` | `provide.add`, `mail.to_bill` |
| Songs | `music.review` (a draft, or every sheet — writes only its report) | — |
| Areas (Part B, first slice) | `areas.check` (delivered, people) | — |

\* An approval: only Claude Fable may do it, and only while William's "Claude Fable may approve for me" is on. It is
signed "Claude Fable, for William". Anyone else gets `needs_approval`.

## The rules it keeps

- **No new rules.** Every change goes through a function the Workbench already uses: the World list's and Places' own
  actions, BUILD 78's approvals, the Mail, `provide.add`, the queue's `submit`. So signing, licence checks, look blocks and
  refusals are the forge's own. If the Workbench would refuse it, the connector refuses it.
- **Signed by a Claude.** Every change needs `who`, and it must start with "Claude". The connector can never act as the
  person.
- **Dry run.** `dry_run: true` on any change says what would happen and writes nothing. A test checks every change
  operation against a byte-for-byte copy of the folder.
- **Safe retries.** With an `idempotency_key`, a call that is retried returns the first answer and does nothing again. The
  same key with a different input is refused as a `conflict`.
- **One answer shape:** `done`, `running` (jobs queued), `needs_approval`, `dry_run`, or `error` with a `code` and
  exactly one `next` step. The codes are `invalid_input`, `not_found`, `refused`, `conflict`, `in_progress`,
  `outcome_unknown`, `unsupported` and `internal`.
- **Not offered at all:** deleting anything; starting or stopping the world queue or the launcher; the order of need;
  settings; canon, lyrics or rulings; any shell command.
- **Where it writes:** inside the forge only (`logs/forge_<date>.log`, `local/mcp/`). The one exception is Claude's
  settings file, and only when you say Y in `mcp_setup.bat`.

## How it is built

- `forge/mcpserver/server.py` runs in `venv_mcp` and holds no forge logic. For each call it starts
  `forge/mcpserver/ops.py` in the forge's own environment (`venv\`), one process per call, so every call runs the forge's
  newest code. No restart is needed after a forge update.
- `forge/mcpserver/claude_settings.py` does the settings step (`--after-extension`: the one-name tidy-up).
- `forge/mcpserver/bundle.py` makes the extension file.
- Tests: `tests/test_build83_mcp.py` and `tests/test_build84_connector.py` (the extension file, the settings tidy-up,
  status at the size of a real night's work). The stdio test runs where the MCP library is installed.
