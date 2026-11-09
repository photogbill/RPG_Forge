# Palettes

One `rrggbb` per line (Lospec's `.hex` export). `.gpl` (GIMP) and `.json` lists also load.

| File | Colours | Author | Source |
|---|---|---|---|
| `resurrect-64.hex` | 64 | Kerrie Lake | https://lospec.com/palette-list/resurrect-64 |
| `endesga-64.hex` | 64 | Endesga | https://lospec.com/palette-list/endesga-64 |

Add any Lospec palette with `python -m forge palette pull <slug>` (e.g. `apollo`, `sweetie-16`).
Palettes are their authors' work, shared on Lospec for use in art; credit them in your game's credits.
A game picks its master palette in `games/<game>/forge.game.json` (`"palette": "resurrect-64"`).
