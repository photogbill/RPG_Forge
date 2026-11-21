# Song review — every Suno sheet checked before it is made (2026-11-19)

✦ William, 2026-11-19 14:57: "build an automatic music lyric review tool into forge, that analyzes the style input and lyrics
(or for instrumental what goes in the lyric box), and ensures that its complex and up to the quality expected of this game."

**Double-click `review_songs.bat`.** It reviews every sheet the game lists (`games/<game>/song_review.json`) and opens the
report. To review one file or folder instead, use `review_songs.bat "<path>"`; to see only what needs work, add `--problems`.
From a chat, the connector's `music.review` reviews a draft before it goes into a sheet.

**It never changes a word.** It writes `out/song_review/<game>/<date>/REPORT.md` (and `review.json`). Each piece gets one
of three verdicts:

- **ready** — the only verdict that may go to Suno (`song_review.ready()` is the gate).
- **needs work**
- **fails**

Each finding says what to change.

## What it checks

| Part | Checks | Whose rule |
|---|---|---|
| Style box | Under 1000 characters, and not thin. Concrete instruments, an idiom, and production words. A tempo and a key or mode, plus how the piece changes over time: required for instrumentals, notes for songs. Not mostly generic words. No artist names except Gilmour and Queen-esque. | William's Suno rules; his verdict on the first instrumental sheet ("very generic … just … bad") |
| An instrumental's lyrics box | Tags only (any words outside brackets get sung). Enough sections of enough kinds, the instruments named per section, something that develops, and an `[End]`. | His "what happens, in brackets" way |
| A song's lyrics box | Under 5000 characters. Sections, paired brackets, no all-caps (acronyms are fine), a single voice, every vocal tag carrying its timbre, relayed dialogue as quoted narration. Then the words themselves: vocabulary, repetition, abstract words, rhyme, clichés. | His Suno rules; the words judged against his own finished lyrics |
| Voice locks | The style box and tags must carry the singer's voice from `music/styles/<singer>.json`, and never the wrong gender. If there is no profile, the canon comes first; only if the voice is nowhere does it say to ask William. A voice is never invented. If there is no profile but the sheet's own **Voice:** line is carried, that's a warning, not a failure. | "Always check for character history … if you don't find it ask" |
| Across sheets | A title is never reused (the same song listed in two places is fine). Never a character's name as a title. Styles too alike within one sheet are flagged. | His title rule; "consider the variety of music" |

Spoken pieces (monologues, narration) are judged by the rules, not as songs.

## Where the bar sits

The bar was measured on 2026-11-19 from William's own work:

- **His finished lyrics** in the game's Lyrics Inbox: vocabulary richness never under 0.87, abstract words under 7%,
  repeats under 16%, 20 or more lines, 4 or more sections.
- **The 93 instrumentals he has made and kept** from the master sheet: 12 or more descriptors, 7 or more sections of 5 or
  more kinds, every one with a tempo and a key.

The thresholds sit just under his own floor. Of the instrumentals he kept, 86 of 93 pass. His own songs fail only where a
singer has no voice profile yet. A game can tune any rule in `games/<id>/song_review.json` → `"rules"`.

**First run, 2026-11-19, on what is still to make** (the master sheet's to-make pieces, Calliope's songs, Songs Needed):
159 sheets, 153 ready, 6 need work, none fail.
