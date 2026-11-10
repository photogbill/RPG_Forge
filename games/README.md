# games/

One folder per game: `games/<game>/` holds that game's forge settings (`forge.game.json`), its wanted list, prompt
blocks, character registry, batches and bake-off suites. **Every game folder is git-ignored** — RPG_Forge is a public,
game-agnostic engine and nothing specific to one game is pushed (William, 2026-11-10). Start a game by copying
`games/_example/` (the only folder that is pushed). A game's session notes (plans, hand-offs) live in `local/<game>/`,
also never pushed.
