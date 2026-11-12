"""The archetype library — what kind of place a town has become, as layout rules.

An archetype is district roles, required buildings, a layout rule, set dressing, a story element and the place where
gear gets better. Every one has a War version (the belief just starting) and an After version (the belief gone too
far). ◆ All of these are proposals; the person who owns a game assigns them to its real places — the generator never
invents a place, it only lays out the one it is given.

Building kinds are generic (inn, store, clinic…); a game's adapter says which of its own services each one is.
"""
from __future__ import annotations

# ---------------------------------------------------------------- building kinds
# size: (min w, min h, max w, max h) on a town map, in cells · interior: the kit its door opens into (None = no door)
KINDS: dict[str, dict] = {
    "inn":            {"size": (7, 5, 9, 6), "interior": "inn", "label": "INN"},
    "store":          {"size": (6, 5, 8, 6), "interior": "store", "label": "STORE"},
    "gas_station":    {"size": (7, 4, 9, 5), "interior": "gas_station", "label": "GAS"},
    "diner":          {"size": (6, 4, 8, 5), "interior": "diner", "label": "DINER"},
    "clinic":         {"size": (6, 5, 8, 6), "interior": "clinic", "label": "CLINIC"},
    "church":         {"size": (7, 6, 9, 8), "interior": "church", "label": "CHURCH"},
    "parts":          {"size": (6, 4, 8, 5), "interior": "workshop", "label": "PARTS"},
    "bar":            {"size": (6, 4, 8, 5), "interior": "diner", "label": "BAR"},
    "smith":          {"size": (6, 5, 8, 6), "interior": "workshop", "label": "ARMS", "upgrade": ["weapon", "armor"]},
    "trinkets":       {"size": (5, 4, 6, 5), "interior": "store", "label": "TRINKETS", "upgrade": ["accessory"]},
    "stall":          {"size": (3, 2, 4, 3), "interior": None, "label": "STALL"},
    "house":          {"size": (5, 4, 7, 5), "interior": "house", "label": ""},
    "shanty":         {"size": (3, 3, 4, 4), "interior": None, "label": ""},
    "tent":           {"size": (3, 3, 4, 3), "interior": None, "label": ""},
    "ruin":           {"size": (4, 4, 7, 5), "interior": None, "label": ""},
    "hall":           {"size": (9, 6, 12, 8), "interior": "hall", "label": "HALL"},
    "counting_house": {"size": (10, 7, 13, 8), "interior": "hall", "label": "COUNTING HOUSE"},
    "cathedral":      {"size": (11, 8, 13, 10), "interior": "church", "label": "CATHEDRAL"},
    "silo":           {"size": (4, 4, 4, 4), "interior": None, "label": "SILO"},
    "tower":          {"size": (3, 3, 3, 3), "interior": None, "label": "TOWER"},
    "grain_store":    {"size": (7, 5, 8, 6), "interior": "vault", "label": "GRAIN STORE"},
    "lord_house":     {"size": (8, 6, 10, 7), "interior": "house", "label": "THE LORD'S HOUSE"},
    "booth":          {"size": (3, 3, 3, 3), "interior": None, "label": "TOLL"},
    "repair_bay":     {"size": (7, 5, 8, 6), "interior": "workshop", "label": "REPAIR BAY"},
    "bakery":         {"size": (5, 4, 6, 5), "interior": "store", "label": "BAKERY"},
    "lookout":        {"size": (3, 3, 3, 3), "interior": None, "label": "LOOKOUT"},
    "clubhouse":      {"size": (8, 6, 10, 7), "interior": "hall", "label": "CLUBHOUSE"},
    "office":         {"size": (6, 5, 8, 6), "interior": "hall", "label": "OFFICE"},
    "memorial":       {"size": (5, 5, 7, 7), "interior": None, "label": "MEMORIAL"},
}

# ---------------------------------------------------------------- the archetypes
def _a(**kw) -> dict:
    kw.setdefault("roles", ["market", "housing", "housing", "workshop"])
    kw.setdefault("signature", [])
    kw.setdefault("filler", ["house"])
    kw.setdefault("dressing", [])
    kw.setdefault("dead_ends_ok", False)
    kw.setdefault("ground", "ground")
    kw.setdefault("ruined", {"war": False, "after": False})
    kw.setdefault("enterable_houses", 3)
    return kw


ARCHETYPES: dict[str, dict] = {
    "buried_town": _a(
        name="The Buried Town", mark="✦",
        pitch="Destroyed and rebuilt underground in case the fire returns. The surface is a scorched decoy whose "
              "chimneys are air shafts; below, galleries ring a freight-elevator shaft, homes fill the old storm "
              "drains, a hydroponics cavern glows purple, and a blast door is the only gate. Fire drills seal the town; "
              "the law is no light on the surface after dark.",
        rule="buried", roles=["market", "housing", "housing", "hydroponics", "workshop"],
        signature=[{"kind": "hall", "label": "THE GALLERY MARKET", "role": "market"}],
        story={"war": "the first shaft, shored with road signs", "after": "the blast door"},
        upgrade={"war": "a machine shop working by lamplight", "after": "the machinist under the main shaft"},
        accessory={"war": "a tinker's bench", "after": "a charm-seller in the gallery"},
        filler=["house"], dressing=["rubble"], law="No light on the surface after dark.",
        ruined={"war": False, "after": True}),
    "purity_town": _a(
        name="The Purity Town",
        pitch="Extremism against the machines: a checkpoint at every street mouth, a scanner arch that tests for "
              "seams, synthetic-free signs, a 'recycling' yard at the edge nobody looks at. Clean, white, flower boxes. "
              "Concentric rings, each one checked; a crane in the square shaped like a gallows.",
        rule="rings", roles=["square", "market", "housing", "housing", "yard"],
        signature=[{"kind": "clubhouse", "label": {"war": "CLUBHOUSE (SIGN-IN)", "after": "REGISTRY"}, "role": "square"}],
        story={"war": "the sign-in table at the clubhouse door", "after": "the scanner arch at the inner ring"},
        upgrade={"war": "a gun store with a bell", "after": "the licensed armourer (synthetics refused at the door)"},
        accessory={"war": "a jeweller", "after": "a licensed jeweller who checks papers"},
        filler=["house"], dressing=["fence"]),
    "congregation": _a(
        name="The Congregation of the Machine",
        pitch="The opposite extremism: humans who worship the synthetics as gods. A cathedral built around a dead war "
              "machine, pews facing its chest cavity, offerings of batteries and copper wire. Pilgrims' tents spread "
              "outward; every street points at the altar.",
        rule="radial", roles=["altar", "pilgrims", "pilgrims", "market", "housing"],
        signature=[{"kind": "cathedral", "label": "THE CATHEDRAL", "role": "altar"}],
        story={"war": "the machine they found in the field, under a tarp", "after": "the altar — the dead machine's open chest"},
        upgrade={"war": "a salvage trader", "after": "the relic dealer (a synthetic part sold as a holy object)"},
        accessory={"war": "a medal-maker", "after": "a seller of blessed copper charms"},
        filler=["tent", "shanty"], dressing=["rubble"]),
    "ledger_town": _a(
        name="The Ledger Town",
        pitch="A quartermaster camp at a ruin's edge: everything rationed, queued and written down. The streets are "
              "queue lanes with rope barriers; the biggest building is the counting house.",
        rule="queues", roles=["counting", "market", "housing", "stores"],
        signature=[{"kind": "counting_house", "label": "THE COUNTING HOUSE", "role": "counting"}],
        story={"war": "the first ration board", "after": "the ledger on its lectern"},
        upgrade={"war": "the quartermaster's armoury", "after": "the issue window (by chit only)"},
        accessory={"war": "a trader at the queue's end", "after": "the chit-exchange's back table"},
        filler=["tent", "house"], dressing=["fence"]),
    "wall_of_names": _a(
        name="The Wall of Names",
        pitch="The town writes its dead on every wall, so walls are the point: long blank-faced streets where names "
              "are added, chalk stalls, a memorial maze at the heart. Maximise wall length.",
        rule="walls", roles=["memorial", "housing", "market", "housing"],
        signature=[{"kind": "memorial", "label": "THE MAZE", "role": "memorial"}],
        story={"war": "the first name, chalked on the post office", "after": "the newest name, still wet"},
        upgrade={"war": "a hardware store's back room", "after": "the stonecutter who also cuts plate"},
        accessory={"war": "a chalk stall", "after": "a seller of name-tags"},
        filler=["house"], dressing=["rubble"]),
    "swollen_city": _a(
        name="The Swollen City",
        pitch="Refugees: the old centre is packed and the overflow climbs — shanties on overpasses, rope bridges "
              "between parking decks, a market in a drained stadium. Vertical layers, bridges as streets.",
        rule="decks", roles=["core", "core", "decks", "market"],
        signature=[{"kind": "hall", "label": "THE STADIUM MARKET", "role": "market"}],
        story={"war": "the first tents in the parking deck", "after": "the rope bridge everyone crosses"},
        upgrade={"war": "a pawn shop with guns", "after": "a smith on the third deck"},
        accessory={"war": "a street vendor", "after": "a black-market stall under the overpass"},
        filler=["shanty", "house"], dressing=["rubble"], dead_ends_ok=True),
    "toll_kingdom": _a(
        name="The Toll Kingdom",
        pitch="A bridge, pass or dam held by one family. The town is a gauntlet along the crossing — booths, a ledger "
              "of who owes, the lord's house above the gate. You pay to cross both ways.",
        rule="gauntlet", roles=["gate", "market", "housing", "gate"],
        signature=[{"kind": "lord_house", "label": "THE LORD'S HOUSE", "role": "gate"}],
        story={"war": "the first chain across the road", "after": "the toll ledger at the gate"},
        upgrade={"war": "a gun counter at the bait shop", "after": "the family's armourer"},
        accessory={"war": "a trader at the booth", "after": "a fence who buys what the toll took"},
        filler=["house"], dressing=["fence"]),
    "moving_town": _a(
        name="The Moving Town",
        pitch="A convoy that becomes a town when it stops: vehicles circled, awnings between them, a market in the "
              "middle. Laid out from its vehicle list, in a different place each time you meet it.",
        rule="convoy", roles=["market", "camp"], signature=[],
        story={"war": "the lead truck with the map on its hood", "after": "the lead truck's painted route"},
        upgrade={"war": "a mechanic's flatbed", "after": "the armourer's trailer"},
        accessory={"war": "a trinket stall", "after": "the trinket stall that is always first to set up"},
        filler=["tent"], dressing=[], dead_ends_ok=True),
    "pretend_town": _a(
        name="The Pretend Town",
        pitch="It decided the war never happened: picket fences, a working soda fountain, a 1950s main street kept "
              "with terrifying effort. One locked street holds everything they pretend away. Perfect symmetry, "
              "with one wrong block.",
        rule="symmetric", roles=["main", "housing", "housing", "main"],
        signature=[{"kind": "diner", "label": "SODA FOUNTAIN", "role": "main"}],
        story={"war": "the parade they held anyway", "after": "the locked street's gate"},
        upgrade={"war": "a hardware store", "after": "the hardware store that sells nothing after 1959"},
        accessory={"war": "a jeweller", "after": "a jeweller with a window display from another century"},
        filler=["house"], dressing=["field"]),
    "quarantine": _a(
        name="The Quarantine",
        pitch="Walled inside a wall: the healthy outside, the sick or 'touched' inside, a single airlock gate run by "
              "people in suits. The inside is where the interesting quests are.",
        rule="nested", roles=["outside", "outside", "inside", "inside"],
        signature=[{"kind": "clinic", "label": "THE AIRLOCK CLINIC", "role": "outside"}],
        story={"war": "the first tape across a door", "after": "the airlock gate"},
        upgrade={"war": "a surplus store", "after": "a smith who works through a hatch"},
        accessory={"war": "a pharmacy counter", "after": "a charm-seller inside the wall"},
        filler=["house"], dressing=["fence"]),
    "salvage_republic": _a(
        name="The Scrap Cathedral / Salvage Republic",
        pitch="Built from war wreckage: war-machine plating as roofs, tank hulls as houses, rotor blades as fences. "
              "Each district is named for the wreck it was built from.",
        rule="wrecks", roles=["wreck", "wreck", "wreck", "market"], signature=[],
        story={"war": "the first wreck they dragged in", "after": "the biggest wreck, now the town hall"},
        upgrade={"war": "a scrapper's bench", "after": "the plating smith"},
        accessory={"war": "a tinker", "after": "a scrap-jeweller"},
        filler=["shanty", "house"], dressing=["rubble"]),
    "sanctuary": _a(
        name="The Sanctuary",
        pitch="Synthetics and humans living openly — repair bays next to bakeries. The defences face outward, and the "
              "hidden tunnels out matter as much as the gate.",
        rule="sanctuary", roles=["market", "housing", "workshop", "housing"],
        signature=[{"kind": "repair_bay", "label": "REPAIR BAY", "role": "workshop"},
                   {"kind": "bakery", "label": "BAKERY", "role": "workshop"}],
        story={"war": "the first door left unlocked for them", "after": "the tunnel mouth behind the bakery"},
        upgrade={"war": "a workshop that fixes both", "after": "the repair bay's armoury"},
        accessory={"war": "a tinker", "after": "a maker of charms for both kinds"},
        filler=["house"], dressing=["field"]),
    "fortress_farm": _a(
        name="The Fortress Farm",
        pitch="Fields inside earthworks, watchtowers on silos, a grain store with a vault door. The fields are the "
              "town; the houses are few.",
        rule="fields", roles=["fields", "fields", "yard", "housing"],
        signature=[{"kind": "grain_store", "label": "GRAIN STORE", "role": "yard"},
                   {"kind": "silo", "label": "SILO", "role": "yard"}],
        story={"war": "the berm going up", "after": "the vault door of the grain store"},
        upgrade={"war": "the farm-supply counter", "after": "a smith in the barn"},
        accessory={"war": "a feed-store trinket shelf", "after": "a harvest-charm seller"},
        filler=["house"], dressing=["field", "fence"]),
    "ghost_town": _a(
        name="The Ghost Town That Isn't",
        pitch="Empty by day; the people live in the old mine or the basements and come up at night. Two states: day "
              "and night.",
        rule="twostate", roles=["main", "housing", "housing", "mine"],
        signature=[{"kind": "hall", "label": "THE MINE HEAD", "role": "mine"}],
        story={"war": "the last shop with its lights on", "after": "the mine head's lit doorway at night"},
        upgrade={"war": "a hardware store", "after": "a smith who opens at midnight"},
        accessory={"war": "a pawn shop", "after": "a night trader"},
        filler=["ruin", "house"], dressing=["rubble"]),
    "glass_field": _a(
        name="The Glass Field",
        pitch="The ground has fused to glass. Nothing is built on it — only around its rim, facing in: pilgrims, "
              "scavengers and a lookout tower.",
        rule="rim", roles=["rim", "rim", "rim", "pilgrims"],
        signature=[{"kind": "lookout", "label": "LOOKOUT", "role": "rim"}],
        story={"war": "the glow on the horizon", "after": "the glass, and what shows through it"},
        upgrade={"war": "a surplus truck", "after": "a scavenger smith who works the glass's edge"},
        accessory={"war": "a trader", "after": "a seller of glass shards as charms"},
        filler=["tent", "shanty"], dressing=["rubble"], ruined={"war": False, "after": True}),
}

ERAS = ("war", "after")


def get(aid: str) -> dict:
    if aid not in ARCHETYPES:
        raise KeyError(f"no archetype '{aid}' — known: {', '.join(sorted(ARCHETYPES))}")
    return ARCHETYPES[aid]


def listing() -> list[dict]:
    return [{"id": k, "name": v["name"], "mark": v.get("mark", "◆"), "rule": v["rule"], "pitch": v["pitch"],
             "story": v["story"], "upgrade": v["upgrade"], "accessory": v["accessory"]}
            for k, v in ARCHETYPES.items()]
