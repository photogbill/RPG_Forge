# games/

One folder per game: `games/<game>/` holds that game's forge settings (`forge.game.json`), its wanted list, prompt
blocks, character registry, batches and bake-off suites. **Every game folder is git-ignored** — RPG_Forge is a public,
game-agnostic engine and nothing specific to one game is pushed (William, 2026-11-10). Start a game by copying
`games/_example/` (the only folder that is pushed). A game's session notes (plans, hand-offs) live in `local/<game>/`,
also never pushed.

**The suite's Story side (BUILD 01).** A game also gets `workbench_adapter.py` (class `Adapter(GameAdapter)`, see
`forge/suite/adapter.py`): where its data files are, its own validator, and how to read places, lines, quests, music
slots and people out of them. Copy `games/_example/workbench_adapter.py` to start. A relative `game_root` hangs off
`games/<id>/` (the example keeps its made-up content in `games/_example/game/`). A per-PC override of where a game's
folder is goes in `local/suite.json` → `game_roots`.
The example game also carries three letters in `games/_example/game/mail/` — the Mail's format and the letter standard
(docs/CLAUDE.md) by example.
