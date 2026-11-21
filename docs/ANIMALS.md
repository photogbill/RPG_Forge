# Animals in the world queue (BUILD 84 part 3)

## Tonight's floor (built)

An entry with `"rig_kind": "animal"` is painted with the thing words (one subject alone, no people), made into a body by
the image-to-3D step, and then — never the person's route:

- no picture gate (it measures people: arms, a head over a height);
- no person's checks (the face, the hair, the head match, a smile): it is checked as a thing is — level, loose pieces,
  glass, thin parts, its colours against its picture with the highlights out; colours put right by one gain if needed;
- no person's skeleton (the riggers' humanoid templates, `mixamo` or `vroid`) and no person's motions (the Quaternius
  Universal Animation Library is humanoid);
- sized to its `real_size_m`, stood on the floor, made with `"moves": "none yet"` — a dog asleep on a porch, a steer in a
  field. Review & approve shows its motions step as skipped, with why.

`world-fix animal-again <ids>` remakes an animal that was given a person's skeleton before this (the body made from its
picture is kept; its try in Review & approve is withdrawn; its skeleton and motions are set aside, renamed). `world-fix
unhold <ids>` takes the animals that were held "until animals can be made" off hold.

## The real route (not built — the next build for the forge lane)

**The skeleton.** The rigging tools already installed offer it: UniRig's `UniRigAutoRig` node takes
`"skeleton_template": "articulationxl"` — "outputs native skeleton (any 3D asset)" — beside `mixamo` (humanoids).
UniRig (VAST-AI) is MIT (`threed/licences.py`). The node pack around it (ComfyUI-UniRig) carries a GPL-3.0 licence file
on this computer: it is a tool the forge runs, not code that ships in a game, and what it makes is not its code — note it
in `licences.py` (it says "as published by its author" today). `rig.py` would pass `skeleton_template` from the body
(`articulationxl` for `kind: animal`).

**Which bone is which.** An ArticulationXL skeleton has no names a motion could be aimed at, so a Blender step reads its
shape: the chains whose tips reach the floor are legs (front pair and back pair by which end of the body they sit),
the chain from the hips toward the head end is the spine and neck, beyond the hips the tail. A four-legged animal with
anything but four floor chains is held for a person.

**The motions.** Five to start, as BUILD 84 asks: stand, walk, run, strike, fall. Two sources, tried in this order:

1. Quaternius' animated animal packs, CC0 — the farm animals (cow, horse, llama, pig, pug, sheep) carry Death, Idle,
   Jump, Run and Walk; the earlier pack has a wolf, a dog and a cat. Their skeletons are their own, so a motion is moved
   chain by chain (each leg's segments, the spine, the neck, the tail: the rotation of each segment, scaled to the
   segment count), not bone by name. The wolf for the coyote and the dog, the pig for the hog, the horse or cow for the
   steer, Death for fall, Jump's take-off for strike.
2. Keyed motions written by the forge where the transfer looks wrong: a diagonal gait (walk), a gallop's rotary gait
   (run), a lunge of the forequarters with the head down (strike), a roll onto the side (fall), breathing on the
   stand. Each fitted with its ground speed, as the people's motions are.

**A snake is not rigged.** Two or three keyed poses — coiled, raised to strike, moving — as separate models or shape
keys of one, chosen by the game.

**Tests to write with it.** An animal's skeleton never has a person's bone names; each of the five motions moves the
four legs; the snake has its poses and no skeleton; the stand-in rigging ComfyUI answers `articulationxl`.
