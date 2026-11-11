# The example game

A tiny made-up game that ships with RPG_Forge so the suite always has something to open, and so every test runs
without anybody's real game connected: three places, five lines, one quest, two music slots, one person. Its folder
layout is invented on purpose — `games/_example/workbench_adapter.py` is what tells the suite how to read it, and is
the model for writing an adapter for a real game.

`tools/validate.py` is the game's own checker (the suite's safe-save path runs it before anything is replaced).
The `journal/`, `proposals/`, `_workbench_backups/` and `_workbench_tmp/` folders the suite makes here are git-ignored.
