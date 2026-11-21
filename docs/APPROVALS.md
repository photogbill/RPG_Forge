# Approvals made easy (BUILD 78, 2026-11-18)

✦ William, 2026-11-17 23:36–00:00: "I need it to be an easy approval system … I trust your judgement Claude, we're a
team, i'm not a boss on this, i'm a coworker." · "I would rather notice something wrong to fix later, than to go item by
item which takes longer." · "it was always my intention that you could approve as well."

## Approve everything here

At the top of **3D → World list** and **Art → Review & approve**: one card, the count on its button, and one plain line a
group saying what will happen before anything does. It uses the page's own functions, one after another — nothing new
is invented and nothing is remade.

| Page | What the button does | What it leaves (said on the card) |
|---|---|---|
| World list | held for colours alone → **Match and release** (a body back to the queue for its skeleton and motions; a prop or building to Review & approve) · an entry with `"release": "as made"` → **Release as made** · a lean whose only other fault is its colours → **Straighten**, then match | the picture gate's holds (no body made yet), a real fault (a loose piece …), which way is up, failed things |
| Review & approve | every 3D model waiting → **Approve** (licence check, held for Deliver) · the newest picture for each wanted thing → **Approve** (held for Deliver) | older takes of the same thing, kits (their table), anything made with a tool not known commercial-OK |

Nothing goes into the game until **Deliver** — approving holds, Deliver copies.

## Undo, a thing at a time

Every thing the button touched is a line in `out/approvals/<game>.jsonl` (git-ignored) with its state from before. The
card's "What was approved here" lists them; **Undo** puts one back while it is still where the button left it. A thing
that has moved on (the queue made it; it was delivered) is not undone: the message says what to do instead. A try taken
off Review & approve is marked `withdrawn`, never deleted.

## "Fable may approve for me"

Settings → **Approvals**. With it on, the assistants it names may approve for the person, and every such approval is
written as **"Claude Fable, for William"** — never as him. Only a person turns it on or off. A game may say its default in
`games/<id>/approvals.json`; the person's own switch on this computer (`local/suite.json` → `approvals`) wins. It covers
made things only: releases on the World list and Review & approve. Canon, lyrics, rulings and approved text stay the
person's.

From a session: `python -m forge approvals plan|all|undo|log|setting --page world|review [--who "Claude Fable"]`.

## Repairs that came with it

- The queue failed every body it checked after BUILD 73 ("Object of type ndarray is not JSON serializable"): the colour
  check's `head_pairs` (pixels) were left in what it writes. `checks.jsonable` and the queue's own writer keep numbers and
  drop pixels.
- An adopted body released with Match and release went round its checks as if nobody had released it; now it is matched
  to its picture (the moving copy too) and a colour miss that is left does not hold it.
- `world-fix try-again` (failed things back in line, keeping what they had — not Make again), `world-fix place-again`
  (a prop sent to Review & approve "sized without Blender" placed again from the forge; the old try withdrawn),
  `world-fix as-made`.
- The forge's own Blender is no longer handed a colour config or scripts folder from a Blender that started the forge
  (the night's "OpenColorIO config error", exit 3221226505).

## Changes that wait for an idle queue

`put_in_waiting_changes.bat` (`forge/sync_when_idle.py`). While the world queue runs, a session adds only new files; an
edit to an existing file waits in `_xfer/waiting/<name>/` (manifest + files). The .bat asks before stopping the queue
(after the thing in hand), checks every file against the copy the session started from (a changed one is never
overwritten — the whole package waits and says which), keeps what each file was, runs the package's tests (all put back
if one fails), runs its after-steps, and starts the queue again.
