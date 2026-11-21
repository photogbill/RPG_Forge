"""Materials (BUILD 87): true channel sets, a second source, no repeats, and wear as a layer.

A material here is a seamless set of pictures a game engine lights: colour, a normal map, height, roughness, occlusion
(and metal or emission where the surface has them). Four parts, each its own module:

  ffchannels.py   Filter Forge renders every channel of a filter — not only the final picture — from a working copy of
                  the filter whose presets carry the channel (Filter Forge's own help: a preset stores the state of the
                  Render Channels menu, and the command line renders only presets that sit inside the filter file).
  mm.py           Material Maker driven from its command line: a graph (.ptex) → a set at 2048, with a seed and named
                  parameters, so one graph gives the same surface in two states.
  mix.py          Three seeds of a ground mixed by a noise mask (a street never shows its tile), and wear as decals
                  with their own normals (laid over a place and lifted again, never baked in).
  look.py         What a reviewer looks at: every channel, a lit plane under a moving light, a lit ball, one sheet a
                  town.

docs/MATERIALS.md is the guide. Nothing here names a game: a game's own choices (which materials are a town's, which
state belongs to which era, where its library is) live in games/<id>/materials/materials.json.
"""
