"""The floor-plan generator (BUILD 29): layouts from a town sheet — districts → lots → interiors from kits, seeded.

    from forge.layout import town, store, archetypes
    plan = town.generate(sheet, "purity_town", "after", seed=7)      # a Plan with its interiors and levels as children
    store.write(plan, folder, adapter, sheet)                        # maps + greybox + paint guide + layout.json

Game-agnostic: a sheet is a plain dict (id, name, size, terrain, required [{kind, label, role}], signature, tiers,
vehicles, wrecks, unknowns). A game's adapter makes sheets from its own files (town_sheets) and turns a plan into its
own map format (layout_map). Nothing here names a game.
"""
