"""Real ground for a game's world (BUILD 77): a reader for DTED Level 0 (the forge's own), bakes of a window of it into a
height picture, a shaded relief, water and the story's edits, and the ground along a line. No graphics card; nothing of
the data itself is ever committed — the cells stay where the person keeps them (forge.json -> "dted_dir", default
local/dted, which is git-ignored)."""
