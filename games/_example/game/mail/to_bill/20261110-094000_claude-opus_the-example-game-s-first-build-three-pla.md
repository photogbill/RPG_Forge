---
from: Claude Opus
to: Bill
subject: The example game's first build — three places, five lines, one question
date: 2026-11-10T09:40:00
thread: 20261110-094000_claude-opus_the-example-game-s-first-build-three-pla
in_reply_to: 
status: sent
attachments: 
---

Bill,

The example game is in: three places, five lines, a quest, two music slots and Wren. It exists so the suite always has something to open and every test can run without your real game connected.

What you can try: open the Story side, read the Mail (you're doing it), answer the question below and press Send. Picking an answer changes the data file it names, through the same safe path every edit uses — checked, backed up, logged.

One thing I wasn't sure of: whether the ordinary-fight music should have a voice. I left it unset.

— Claude (Opus)

```questions
[
 {
  "id": "battle_vocal",
  "question": "Ordinary fights: instrumental or vocal?",
  "why": "It plays dozens of times; a voice gets old faster.",
  "recommendation": "Instrumental",
  "default": "Instrumental",
  "choices": [
   {
    "label": "Instrumental",
    "value": false
   },
   {
    "label": "Vocal",
    "value": true
   }
  ],
  "applies_to": {
   "file": "data/music.json",
   "pointer": "/battle/vocal"
  }
 }
]
```
