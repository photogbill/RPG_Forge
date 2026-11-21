"""Song review — every Suno sheet checked before it is made (2026-11-19).

✦ William, 2026-11-19 14:57: "build an automatic music lyric review tool into forge, that analyzes the style input and lyrics
(or for instrumental what goes in the lyric box), and ensures that its complex and up to the quality expected of this game."

    python -m forge.song_review [--game <id>] [file or folder …] [--all-status] [--problems]
    review_songs.bat                                   the same, for every sheet the game lists, report opened

What "the quality expected" means here — each rule is William's, or measured from his own finished songs:
- **His Suno rules** (the rock opera's craft rules): style box under 1000 characters, lyrics under 5000; square brackets
  are Suno tags; no all-caps (mispronounced — use a delivery tag); a single voice (male and female together is unreliable),
  every vocal tag with its full timbre, never only a name; relayed dialogue as quoted narration; no artist names but
  "Gilmour" and "Queen-esque"; never a character's name as a title; a title never reused (takes that share a name colour
  each other); an instrumental's lyrics box holds tags only (any words get sung).
- **Voice locks** ("Always check for character history when working on song lyrics or determining voice types"): a named
  singer's style box must carry the voice in the singer's profile (music/styles/<singer>.json). No profile, or its voice
  still open: **ask William** — the tool never invents a voice.
- **Not generic** (his verdict on the first instrumental sheet, 2026-11-16: "very generic … they are just … bad"; the
  characters' own styles were fine because each "is specific, not generic"): a style box needs concrete instruments, an
  idiom, production words, a tempo, a key or mode, and what the piece does over time; a box mostly made of generic words is
  flagged, and so is one too like another in the same sheet ("consider the variety of music").
- **Complex enough**: sections, how the piece develops, and for words — vocabulary, rhyme, imagery, little repetition,
  no clichés — held against his own finished lyrics (the game's Lyrics Inbox), not against a number made up here.

It **never changes a word** of a sheet: it writes a report (out/song_review/<game>/<date>/REPORT.md and review.json) and
answers "ready", "needs work" or "fails" for each piece, with what to change. `ready(result)` is the gate a Suno run can
use. Nothing here names a game: a game lists its sheets in games/<id>/song_review.json.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

from .log import get

log = get("songs")

# ------------------------------------------------------------------------------------------------ the rules (a game may tune them)
RULES = {
    # Calibrated 2026-11-19 against William's own finished lyrics (Lyrics Inbox: vocabulary richness never under 0.87,
    # abstract words under 7%, repeats under 16%, 20+ lines, 4+ sections) and the instrumentals he has made and kept from
    # the master sheet (12+ descriptors, 7+ sections of 5+ kinds, every one with a tempo and a key). Thresholds sit just
    # under his own floor: a sheet below what he writes is flagged; his own songs pass.
    "style_max": 1000, "lyrics_max": 5000,
    "style_min_vocal": 150, "style_min_inst": 250, "descriptors_min_vocal": 6, "descriptors_min_inst": 10,
    "instruments_min": 2,
    "vocal_lines_min": 16, "vocal_sections_min": 4, "vocal_kinds_min": 2,
    "inst_sections_min": 5, "inst_kinds_min": 4, "inst_instruments_min": 2,
    "repeat_share_max": 0.35, "mattr_min": 0.80, "rhyme_min": 0.20, "abstract_share_max": 0.15,
    "similar_max": 0.55, "generic_share_max": 0.35,
    "ready_score": 65,
    "allowed_artists": ["gilmour", "queen-esque"],
    "acronyms": ["AI", "OK", "TV", "DJ", "USA", "US", "UN", "EU", "FBI", "CIA", "NSA", "EMP", "CEO", "GPS", "SOS", "BPM",
                 "MEHA", "DNA", "MRI", "ICU", "IV", "HQ", "VIP", "UFO", "NASA", "PTSD", "MRE", "SUV", "ATM", "LED", "TNT"],
    "skip_status": ["made_filed", "made_in_game", "no_song", "later", "yours", "space"],
}

INSTRUMENTS = """accordion bagpipe bagpipes balalaika bandoneon banjo bass bassoon bell bells bongo bongos bouzouki brass bugle
cajon castanets celesta cello cellos chimes choir cimbalom clarinet clavinet conga congas contrabass cornet cowbell cymbal
cymbals didgeridoo djembe drum drums duduk dulcimer erhu euphonium fiddle flugelhorn flute flutes glockenspiel gong guitar
guitars harmonica harmonium harp harpsichord hammond horn horns kalimba kantele kazoo keys koto lute lyre mandolin marimba
mellotron moog oboe ocarina organ oud pedal piano piccolo pipa rhodes sackbut sampler santur saxophone sax sequencer shakuhachi
shamisen sitar snare sousaphone steel strings synth synths synthesizer synthesizers tabla taiko tambourine theremin timpani
tom toms triangle trombone trombones trumpet trumpets tuba ukulele vibraphone vibes viola violas violin violins vocoder
whistle wurlitzer xylophone zither 808 turntable turntables typewriter string kick pad pads arpeggiator bassline
drum-machine handpan steelpan hurdy-gurdy""".split()
GENRES = """ambient americana anthem bebop bluegrass blues bolero bossa breakbeat cajun calypso celtic chanson chiptune
classical country cumbia dance darkwave disco dirge doom drill dub dubstep electro electronic electronica emo flamenco folk
funk fusion garage gospel grime grunge hardcore hip-hop house idm indie industrial jazz klezmer lounge mambo march mariachi
metal minimalist motown neoclassical new-wave noir oratorio opera operatic orchestral polka pop post-rock prog progressive
psychedelic punk ragtime reggae requiem rnb rock rockabilly salsa samba score shoegaze ska soul soundtrack surf swing symphonic
synthwave tango techno trance trap trip-hop waltz zydeco baroque romantic renaissance medieval cinematic chamber
big-band second-line""".split()
PRODUCTION = """analog audiophile close compression distorted dry fuzz lo-fi live master mic mixed mono overdriven production
recorded recording reverb reverb-drenched room stereo studio tape vinyl warm wet hall cathedral bright dark saturated
crisp sidechained gated echo delay""".split()
DYNAMICS = """build builds building swell swells crescendo drops drop falls rises rising returns returning alone enters
joins slides slows stops breaks break breakdown modulates modulation key-change lifts lift ends ending begins starts
starting climax quiet loud sparse fuller grows grow fades fade slide lifts raises raised doubles doubling halves
answer answers answering trade trades trading swap returns comes back drops away kicks kick""".split()
GENERIC = """epic beautiful emotional cinematic amazing awesome nice good great powerful intense dramatic atmospheric
background music song track sound vibes vibe mood moody chill catchy""".split()
VOICE_WORDS = """soprano mezzo mezzo-soprano alto contralto tenor heldentenor baritone baritenor bass basso countertenor
falsetto belt crooner rap rapper vocals vocal voice voiced singer sung choir chorus""".split()
VOICE_TYPES = ["coloratura", "soprano", "mezzo", "contralto", "alto", "countertenor", "heldentenor", "baritenor", "tenor",
               "baritone", "bass", "basso", "belt", "falsetto", "crooner", "sprechgesang"]
ABSTRACT = set("""love pain soul heart hearts dream dreams forever destiny fate hope hopes despair sorrow glory freedom truth
lies life death time light dark darkness fire tears world night day feel feeling feelings emotion emotions spirit""".split())
CLICHES = ["heart of gold", "set me free", "break these chains", "break the chains", "rise up", "never give up",
           "light up the night", "stand tall", "through the fire", "tears fall like rain", "in the dark of night",
           "fire in my soul", "burning desire", "against all odds", "no turning back", "till the end of time",
           "until the end of time", "touch the sky", "reach for the stars", "spread my wings", "heart and soul",
           "deep inside", "inside my heart", "we will rise", "shine so bright", "lost in the dark", "the light within",
           "forever and ever", "cold as ice", "as one we stand", "take my hand", "one more time", "edge of the world"]
KNOWN_ARTISTS = ["hans zimmer", "john williams", "nobuo uematsu", "pink floyd", "queen", "beatles", "metallica", "mozart",
                 "beethoven", "bach", "wagner", "led zeppelin", "radiohead", "daft punk", "taylor swift", "beyonce", "adele",
                 "michael jackson", "freddie mercury", "ennio morricone", "danny elfman", "howard shore", "vangelis",
                 "they might be giants", "billie eilish", "lady gaga", "elvis", "ac/dc", "iron maiden", "nightwish"]
SECTION_KINDS = ["intro", "verse", "pre-chorus", "prechorus", "chorus", "post-chorus", "hook", "bridge", "breakdown", "build",
                 "drop", "solo", "interlude", "instrumental", "outro", "end", "coda", "refrain", "theme", "movement", "call",
                 "response", "dirge", "spoken", "break", "reprise", "finale", "overture", "aria", "recitative"]
STOP = set("""the a an and or but of to in on at for with by from up down out over under into onto as is are was were be been
being it its this that these those i me my mine you your yours he him his she her hers we us our they them their what which who
whom whose not no so too very just can will would could should do does did done have has had all any some each every own same
than then there here when where why how if while am oh yeah ah ooh la na""".split())


# ------------------------------------------------------------------------------------------------ reading sheets
def _words(text: str) -> list[str]:
    return [re.sub(r"'s$|'$", "", w) for w in re.findall(r"[a-z][a-z'\-]*", text.lower())]


def descriptors(style: str) -> list[str]:
    return [d.strip() for d in re.split(r"[,;\n]|\.\s", style or "") if d.strip()]


def tags_and_lines(lyrics: str) -> tuple[list[str], list[str]]:
    """([tag contents], [sung or spoken lines]) — a tag is anything in square brackets."""
    tags, lines = [], []
    for raw in (lyrics or "").splitlines():
        ln = raw.strip()
        if not ln:
            continue
        found = re.findall(r"\[([^\]]*)\]", ln)
        tags += found
        rest = re.sub(r"\[[^\]]*\]", "", ln).strip()
        if rest and rest not in ("```",):
            lines.append(rest)
    return tags, lines


def song(title="", style="", lyrics="", instrumental=None, singers=None, source="", sid="", exclude="") -> dict:
    tags, lines = tags_and_lines(lyrics)
    if instrumental is None:
        instrumental = any(t.strip().lower() == "instrumental" for t in tags) or (bool(tags) and not lines)
    spoken = bool(re.search(r"\b(spoken|monologue|narration|narrated|spoken word)\b", f"{title} {style[:200]}".lower())) \
        and not instrumental
    return {"id": sid or title, "title": title.strip(), "style": (style or "").strip(), "lyrics": lyrics or "",
            "instrumental": bool(instrumental), "spoken": spoken, "singers": [s for s in (singers or []) if s],
            "source": source, "exclude": exclude or ""}


def parse_master(path: Path, all_status: bool = False, rules: dict | None = None) -> tuple[list[dict], list[str]]:
    """A master music sheet: {"pieces": [{"title", "style", "lyrics", "has_words", "voices", "status", …}]}."""
    rules = rules or RULES
    d = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    out, skipped = [], []
    for p in d.get("pieces") or []:
        if not (p.get("style") or p.get("lyrics")):
            continue
        if not all_status and p.get("status") in rules["skip_status"]:
            skipped.append(f"{p.get('title')} ({p.get('status')})")
            continue
        v = p.get("voices")
        singers = [x if isinstance(x, str) else (x.get("name") or x.get("character") or "") for x in v] if isinstance(v, list) else []
        out.append(song(p.get("title") or p.get("key"), p.get("style") or "", p.get("lyrics") or "",
                        instrumental=not p.get("has_words"), singers=singers, sid=str(p.get("number") or p.get("key") or ""),
                        source=f"{Path(path).name} #{p.get('number') or p.get('key')}", exclude=p.get("exclude_styles") or ""))
    return out, skipped


def _block(text: str, heading_words: tuple) -> str | None:
    """The fenced block (or the text) under a heading whose words include any of heading_words."""
    m = None
    for hm in re.finditer(r"^#{1,4}\s*(.+)$", text, re.M):
        h = hm.group(1).lower()
        if any(w in h for w in heading_words):
            m = hm
            break
    if not m:
        return None
    after = text[m.end():]
    nxt = re.search(r"^#{1,4}\s", after, re.M)
    body = after[: nxt.start()] if nxt else after
    fence = re.search(r"```[a-z]*\n(.*?)```", body, re.S)
    return (fence.group(1) if fence else body).strip()


def parse_md(path: Path) -> tuple[dict | None, str]:
    """A Suno .md sheet: '## … Style' and '## … Lyrics' blocks (fenced or not), or 'Style:' / '> style' lines."""
    text = Path(path).read_text(encoding="utf-8-sig")
    lyrics = _block(text, ("lyrics", "lyric box", "lyrics box"))
    style = _block(text, ("suno style", "suno — style", "suno - style", "suno style line")) if "suno" in text.lower() else None
    if style is None and lyrics is not None:          # any "Style" heading only when the file is a song (it has lyrics)
        style = _block(text, ("style",))
    if style is None:
        m = re.search(r"^\*{0,2}(?:suno )?style\*{0,2}\s*[:—-]\s*(.+)$", text, re.I | re.M)
        style = m.group(1).strip() if (m and lyrics is not None) else None
    if not style:
        return None, "no Suno style in this file yet"
    title = (re.search(r"^#\s+(.+)$", text, re.M) or re.search(r"\*\*Working title:\*\*\s*(.+)", text))
    title = title.group(1).strip() if title else Path(path).stem
    singers = []
    stem = Path(path).stem.replace("_", " ")
    fm = re.search(r"\(([A-Za-z][A-Za-z' ]+)\)\s*$", stem)       # William's convention: the singer in the file name
    if fm:
        singers.append(fm.group(1).strip().title() if fm.group(1).isupper() else fm.group(1).strip())
    else:
        for pat in (r"\*\*Singer[^*]*:\*\*\s*([^:—\-\n(]+)", r"\*\*Character:\*\*\s*([^—\-\n(]+)"):
            mm = re.search(pat, text, re.M)
            if mm:
                singers.append(mm.group(1).strip())
                break
    vm = re.search(r"\*\*Voice:\*\*\s*(.+)", text)
    inst = None
    if re.search(r"\binstrumental\b", Path(path).stem, re.I):
        inst = True
    s = song(title, style, lyrics or "", instrumental=inst, singers=singers, source=str(path))
    s["voice_line"] = vm.group(1).strip() if vm else ""
    return s, ""


def collect(paths: list[Path], all_status: bool = False, rules: dict | None = None) -> tuple[list[dict], list[str]]:
    songs, skipped = [], []
    for p in paths:
        p = Path(p)
        files = sorted(p.rglob("*.md")) + sorted(p.rglob("*.json")) if p.is_dir() else [p]
        for f in files:
            try:
                if f.suffix.lower() == ".json":
                    head = f.read_text(encoding="utf-8-sig")[:4000]
                    if '"pieces"' not in head:
                        continue
                    s, sk = parse_master(f, all_status, rules)
                    songs += s
                    skipped += sk
                elif f.suffix.lower() == ".md":
                    s, why = parse_md(f)
                    if s:
                        songs.append(s)
                    else:
                        skipped.append(f"{f.name} ({why})")
            except (OSError, ValueError) as ex:
                skipped.append(f"{f.name} (could not be read: {ex})")
    return songs, skipped


# ------------------------------------------------------------------------------------------------ voice locks
def load_profiles(styles_dir: Path | None) -> dict:
    """{lowercase name or id: profile} from music/styles/*.json."""
    out = {}
    if styles_dir and Path(styles_dir).is_dir():
        for f in sorted(Path(styles_dir).glob("*.json")):
            try:
                p = json.loads(f.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError):
                continue
            for k in {str(p.get("name") or ""), str(p.get("id") or f.stem), f.stem}:
                if k:
                    out[k.lower()] = p
    return out


def _spot(v):
    if isinstance(v, dict):
        return None if v.get("open") else v.get("value")
    return v


def _unnegated(low: str) -> str:
    """'no male vocals, no rap' and the like taken out, so a 'no X' never counts as asking for X."""
    return re.sub(r"\b(no|without|not)\s+[a-z\- ]+?(?=,|;|\.|$)", "", low)


def voice_of(profile: dict) -> dict:
    """{"words": [voice-type words], "female": bool|None, "text": the voice in words} from a profile's voice."""
    v = profile.get("voice") or {}
    parts = []
    for k in ("type", "delivery"):
        x = _spot(v.get(k))
        if isinstance(x, list):
            parts += [str(i) for i in x]
        elif x:
            parts.append(str(x))
    text = " · ".join(parts)
    low = _unnegated(text.lower())
    words = [w for w in VOICE_TYPES if re.search(rf"\b{re.escape(w)}", low)]
    if not words:                                    # the voice written only in the styles' Suno words (e.g. "Baritone Lead")
        for st in profile.get("styles") or []:
            for k in ("suno_input", "genre", "voice", "vocals"):
                x = _spot(st.get(k)) if isinstance(st, dict) else None
                x = " ".join(map(str, x)) if isinstance(x, list) else str(x or "")
                if x:
                    text = text or x
                    low = _unnegated(x.lower())
                    words += [w for w in VOICE_TYPES if re.search(rf"\b{re.escape(w)}", low) and w not in words]
    female = True if re.search(r"\bfemale\b|soprano|mezzo|contralto", low) else (False if re.search(r"\bmale\b|tenor|baritone|\bbass", low) else None)
    return {"words": words, "female": female, "text": text}


# ------------------------------------------------------------------------------------------------ measures
def _rhyme_key(word: str) -> str:
    w = re.sub(r"[^a-z]", "", word.lower())
    m = re.search(r"[aeiouy]+[^aeiouy]*$", w)
    return m.group(0) if m else w


def rhyme_share(lines: list[str]) -> float:
    ends = [(_words(ln) or [""])[-1] for ln in lines]
    keys = [_rhyme_key(e) for e in ends]
    hit = 0
    for i, k in enumerate(keys):
        if not k or len(k) < 2:
            continue
        near = [j for j in range(max(0, i - 4), min(len(keys), i + 5)) if j != i]
        if any(keys[j] == k and ends[j] != ends[i] for j in near):
            hit += 1
    return hit / len(lines) if lines else 0.0


def mattr(tokens: list[str], window: int = 30) -> float:
    """Moving-average type-token ratio of content words (length-fair vocabulary richness)."""
    if not tokens:
        return 0.0
    if len(tokens) <= window:
        return len(set(tokens)) / len(tokens)
    vals = [len(set(tokens[i:i + window])) / window for i in range(len(tokens) - window + 1)]
    return sum(vals) / len(vals)


def measure(s: dict) -> dict:
    style_low = s["style"].lower()
    sw = set(_words(style_low))
    tags, lines = tags_and_lines(s["lyrics"])
    tag_text = " ".join(tags).lower()
    kinds = sorted({k for t in tags for k in SECTION_KINDS if re.match(rf"\s*{re.escape(k)}\b", t.lower())})
    content = [w for w in _words(" ".join(lines)) if w not in STOP and len(w) > 2]
    norm_lines = [re.sub(r"[^a-z ]", "", ln.lower()).strip() for ln in lines]
    repeats = len(norm_lines) - len(set(norm_lines))
    descs = descriptors(s["style"])
    generic = [d for d in descs if set(_words(d)) and set(_words(d)) <= set(GENERIC) | STOP]
    return {
        "style_chars": len(s["style"]), "lyrics_chars": len(s["lyrics"]),
        "descriptors": len(descs), "generic_descriptors": len(generic),
        "instruments": sorted(sw & set(INSTRUMENTS)), "genres": sorted(sw & set(GENRES)),
        "production": sorted(sw & set(PRODUCTION)), "dynamics": sorted(sw & set(DYNAMICS)),
        "tempo": bool(re.search(r"\b\d{2,3}\s*bpm\b", style_low) or re.search(r"\b(adagio|andante|allegro|presto|largo|moderato)\b", style_low)),
        "key": bool(re.search(r"\b[a-g](\s?(#|♯|b|♭|sharp|flat))?\s+(major|minor)\b", style_low) or
                    re.search(r"\b(dorian|phrygian|lydian|mixolydian|aeolian|locrian|harmonic minor|modal)\b", style_low)),
        "voice_words": sorted(sw & set(VOICE_WORDS)),
        "tags": len(tags), "section_kinds": kinds, "sections": sum(1 for t in tags if any(re.match(rf"\s*{re.escape(k)}\b", t.lower()) for k in SECTION_KINDS)),
        "tag_instruments": sorted(set(_words(tag_text)) & set(INSTRUMENTS)),
        "tag_dynamics": sorted(set(_words(tag_text)) & set(DYNAMICS)),
        "lines": len(lines), "repeat_share": round(repeats / len(lines), 2) if lines else 0.0,
        "mattr": round(mattr(content), 3), "rhyme_share": round(rhyme_share(lines), 2),
        "abstract_share": round(sum(1 for w in content if w in ABSTRACT) / len(content), 2) if content else 0.0,
        "cliches": [c for c in CLICHES if c in " ".join(norm_lines)],
    }


# ------------------------------------------------------------------------------------------------ the checks
def _f(level, check, message, fix=""):
    d = {"level": level, "check": check, "message": message}
    if fix:
        d["fix"] = fix
    return d


def check_style(s: dict, m: dict, r: dict) -> list[dict]:
    out = []
    inst = s["instrumental"]
    soft = "warn" if inst else "info"          # tempo, key, production, development: needed in game music; notes for songs
    style_min = r["style_min_inst"] if inst else r["style_min_vocal"]
    desc_min = r["descriptors_min_inst"] if inst else r["descriptors_min_vocal"]
    n = m["style_chars"]
    if n == 0:
        return [_f("fail", "style", "the style box is empty")]
    if n > r["style_max"]:
        out.append(_f("fail", "style length", f"{n} characters — Suno's style box takes {r['style_max']}", "cut descriptors, keep the specific ones"))
    elif n < style_min:
        out.append(_f("warn", "style length", f"only {n} characters — thin for this game (William's own style lines run 160–730, "
                      "the instrumentals he kept 370–700)",
                      "name the idiom, the instruments, the production, the tempo, the key and what the piece does over time"))
    if m["descriptors"] < desc_min:
        out.append(_f("warn", "specific", f"{m['descriptors']} descriptors — fewer than {desc_min}"))
    if len(m["instruments"]) < r["instruments_min"]:
        out.append(_f("fail" if not m["instruments"] else "warn", "instruments",
                      f"{len(m['instruments'])} named instruments ({', '.join(m['instruments']) or 'none'}) — a specific sound names at least {r['instruments_min']}",
                      "say which instruments carry the tune, the harmony and the rhythm"))
    if not m["genres"]:
        out.append(_f("info", "idiom", "no idiom word this tool knows — check the style names one (e.g. '1960s lounge bossa nova')"))
    if not m["tempo"]:
        out.append(_f(soft, "tempo", "no tempo (a BPM)"))
    if not m["key"]:
        out.append(_f(soft, "key", "no key or mode (e.g. 'B minor', 'Dorian')"))
    if not m["production"]:
        out.append(_f(soft, "production", "no production words (room, mic, studio, analog, reverb …)"))
    if not m["dynamics"] and not (inst and m["tag_dynamics"]):
        out.append(_f(soft, "development", "nothing about how the piece changes (starts with …, builds, drops to …, lifts a key, ends on …)"))
    if m["descriptors"] and m["generic_descriptors"] / m["descriptors"] > r["generic_share_max"]:
        out.append(_f("warn", "generic", f"{m['generic_descriptors']} of {m['descriptors']} descriptors are generic words (epic, cinematic, emotional …)",
                      "replace them with concrete sounds"))
    low = s["style"].lower()
    for a in KNOWN_ARTISTS:
        if re.search(rf"\b{re.escape(a)}\b", low) and not any(ok in low for ok in r["allowed_artists"] if a in ok):
            out.append(_f("fail", "artist name", f"'{a}' — Suno refuses artist names; only {', '.join(r['allowed_artists'])} are allowed",
                          "describe the sound instead"))
    for mm in re.finditer(r"\bin the style of ([A-Z][\w'.]+(?: [A-Z][\w'.]+)*)|\b([A-Z][\w'.]+(?: [A-Z][\w'.]+)*)-esque\b", s["style"]):
        name = (mm.group(1) or mm.group(2) or "").lower()
        if name and not any(name in ok or ok.startswith(name) for ok in r["allowed_artists"]):
            out.append(_f("warn", "artist name", f"'{mm.group(0)}' reads as a named artist — Suno may refuse it"))
    return out


def check_vocal(s: dict, m: dict, r: dict, profiles: dict) -> list[dict]:
    out = []
    tags, lines = tags_and_lines(s["lyrics"])
    if m["lyrics_chars"] > r["lyrics_max"]:
        out.append(_f("fail", "lyrics length", f"{m['lyrics_chars']} characters — Suno's lyrics box takes {r['lyrics_max']}"))
    spoken = s.get("spoken")
    if not spoken and m["lines"] < r["vocal_lines_min"]:
        out.append(_f("warn", "length", f"{m['lines']} sung lines — short for a song with words"))
    if not spoken and (m["sections"] < r["vocal_sections_min"] or len(m["section_kinds"]) < r["vocal_kinds_min"]):
        out.append(_f("warn", "structure", f"{m['sections']} sections of {len(m['section_kinds'])} kinds ({', '.join(m['section_kinds']) or 'none'})",
                      "verse / pre-chorus / chorus / bridge / outro — a bridge or a turn that isn't repeated"))
    if s["lyrics"].count("[") != s["lyrics"].count("]"):
        out.append(_f("fail", "tags", "square brackets don't pair up — Suno will sing a broken tag"))
    caps = sorted({w for w in re.findall(r"\b[A-Z][A-Z'\-]{2,}\b", "\n".join(lines)) if w.strip("'-") not in r["acronyms"]})
    if caps:
        out.append(_f("warn", "all caps", f"all-caps words get mispronounced: {', '.join(caps[:8])}", "lower case, with a delivery tag on the line before"))
    tl = " ".join(tags).lower()
    male = re.search(r"(?<!no )(?<!fe)\bmale (lead )?vocal", tl)
    female = re.search(r"(?<!no )\bfemale (lead )?vocal", tl)
    if male and female:
        out.append(_f("fail", "single voice", "both male and female vocal tags — dual voices are unreliable in Suno",
                      "one voice; relay the other as quoted narration with a delivery tag above it"))
    names = set(profiles)
    bare = [t for t in tags if t.strip().lower() in names]
    if bare:
        out.append(_f("warn", "timbre", f"tags that only name a singer: {', '.join('[' + b + ']' for b in bare[:5])}",
                      "every vocal tag carries the full timbre descriptor"))
    script = [ln for ln in lines if re.match(r"^[A-Z][A-Za-z ]{1,24}:\s", ln)]
    if script:
        out.append(_f("warn", "dialogue", f"{len(script)} line(s) written as 'Name: …' — Suno sings the name",
                      "relayed dialogue as plain quoted text, the delivery tag on the line before"))
    if m["repeat_share"] > r["repeat_share_max"]:
        out.append(_f("warn", "repetition", f"{int(m['repeat_share'] * 100)}% of lines repeat"))
    if m["mattr"] and m["mattr"] < r["mattr_min"]:
        out.append(_f("warn", "vocabulary", f"vocabulary richness {m['mattr']} — below this game's standard ({r['mattr_min']})"))
    if not spoken and m["lines"] >= 8 and m["rhyme_share"] < r["rhyme_min"]:
        out.append(_f("info", "rhyme", f"few lines rhyme ({int(m['rhyme_share'] * 100)}%) — fine if meant"))
    if m["abstract_share"] > r["abstract_share_max"]:
        out.append(_f("warn", "imagery", f"{int(m['abstract_share'] * 100)}% of the words are abstract (love, soul, fate …)",
                      "concrete things seen, held and heard"))
    for c in m["cliches"]:
        out.append(_f("warn", "cliché", f"'{c}'"))
    # voice locks
    for name in s["singers"]:
        p = profiles.get(name.strip().lower())
        vl = (s.get("voice_line") or "").lower()
        vl_words = [w for w in VOICE_TYPES if re.search(rf"\b{re.escape(w)}", _unnegated(vl))]
        if not p and vl_words and any(re.search(rf"\b{re.escape(w)}", _unnegated(s["style"].lower())) for w in vl_words):
            out.append(_f("warn", "voice lock", f"no profile for {name} in music/styles; the sheet's own Voice line "
                          f"('{s['voice_line'][:80]}') is what the style carries", f"write it into music/styles/{name.lower()}.json"))
            continue
        if not p:
            out.append(_f("fail", "voice lock", f"no profile for {name} in music/styles — find {name}'s voice in the canon "
                          f"({r.get('canon_hint') or 'the master write-up and the lyrics'}) and write it into the profile; "
                          "only if it is nowhere, ask William (a voice is never invented)"))
            continue
        v = voice_of(p)
        if not v["words"]:
            out.append(_f("fail", "voice lock", f"{name}'s profile has no voice type written down yet — find it in the canon "
                          f"({r.get('canon_hint') or 'the master write-up and the lyrics'}); only if it is nowhere, ask William"))
            continue
        low = _unnegated((s["style"] + ", " + ", ".join(tags)).lower())
        if not any(re.search(rf"\b{re.escape(w)}", low) for w in v["words"]):
            out.append(_f("fail", "voice lock", f"neither the style box nor the tags carry {name}'s voice (on file: {v['text'][:160]})",
                          f"name it: {', '.join(v['words'])}"))
        if v["female"] is True and re.search(r"(?<!no )(?<!fe)\bmale vocal", s["style"].lower()):
            out.append(_f("fail", "voice lock", f"{name} sings in a female voice; the style box asks for a male one"))
        if v["female"] is False and re.search(r"(?<!no )\bfemale vocal", s["style"].lower()):
            out.append(_f("fail", "voice lock", f"{name} sings in a male voice; the style box asks for a female one"))
    if not s["singers"] and not m["voice_words"]:
        out.append(_f("warn", "voice", "no singer named and no voice in the style box — Suno will choose one",
                      "name the voice: gender, type, timbre"))
    return out


def check_instrumental(s: dict, m: dict, r: dict) -> list[dict]:
    out = []
    tags, lines = tags_and_lines(s["lyrics"])
    if not s["lyrics"].strip():
        return [_f("warn", "lyrics box", "the lyrics box is empty — tags there give the piece its shape (William's way: what happens, in brackets)")]
    if lines:
        out.append(_f("fail", "words", f"{len(lines)} line(s) outside brackets — Suno will sing them: '{lines[0][:60]}'",
                      "everything in an instrumental's lyrics box goes in square brackets"))
    if m["sections"] < r["inst_sections_min"] or len(m["section_kinds"]) < r["inst_kinds_min"]:
        out.append(_f("warn", "structure", f"{m['sections']} sections of {len(m['section_kinds'])} kinds — a piece this game uses needs more shape"))
    if len(m["tag_instruments"]) < r["inst_instruments_min"]:
        out.append(_f("warn", "what happens", f"the tags name {len(m['tag_instruments'])} instruments — say who plays each section"))
    if not m["tag_dynamics"] and not re.search(r"up a key|key change|half-time|double-time|tempo", " ".join(tags).lower()):
        out.append(_f("warn", "development", "nothing develops in the tags (enters, builds, drops out, up a key, returns …)"))
    voc = set(_words(s["style"].lower())) & {"vocals", "vocal", "singer", "sung", "lyrics", "rap", "soprano", "tenor", "baritone", "mezzo", "alto"}
    if voc and "instrumental" not in s["style"].lower() and "wordless" not in s["style"].lower():
        out.append(_f("warn", "instrumental", f"vocal words in an instrumental's style ({', '.join(sorted(voc))})",
                      "say 'Instrumental' (a wordless choir is fine)"))
    if not any(t.strip().lower() == "end" for t in tags):
        out.append(_f("info", "end", "no [End] tag — Suno ends more cleanly with one"))
    return out


def score(s: dict, m: dict) -> int:
    """0–100: richness of the style box, shape of the lyrics box, and — with words — the words themselves."""
    pts = 0.0
    pts += min(m["descriptors"], 14) / 14 * 15
    pts += min(len(m["instruments"]), 5) / 5 * 10
    pts += 5 * bool(m["genres"]) + 4 * bool(m["tempo"]) + 4 * bool(m["key"]) + 4 * bool(m["production"]) + 8 * bool(m["dynamics"])
    pts -= 10 * (m["generic_descriptors"] / m["descriptors"] if m["descriptors"] else 1)
    if s["instrumental"]:
        pts += min(m["sections"], 8) / 8 * 15 + min(len(m["section_kinds"]), 6) / 6 * 10
        pts += min(len(m["tag_instruments"]), 5) / 5 * 15 + min(len(m["tag_dynamics"]), 4) / 4 * 10
    else:
        pts += min(m["sections"], 8) / 8 * 8 + min(len(m["section_kinds"]), 5) / 5 * 7
        pts += max(0.0, min(1.0, (m["mattr"] - 0.55) / 0.35)) * 15
        pts += min(m["rhyme_share"], 0.6) / 0.6 * 6
        pts += max(0.0, 1 - m["repeat_share"] / 0.6) * 6
        pts += max(0.0, 1 - m["abstract_share"] / 0.4) * 8
        pts -= 4 * len(m["cliches"])
    return int(max(0, min(100, round(pts))))


def review(s: dict, profiles: dict | None = None, rules: dict | None = None) -> dict:
    r = {**RULES, **(rules or {})}
    profiles = profiles or {}
    m = measure(s)
    found = check_style(s, m, r) + (check_instrumental(s, m, r) if s["instrumental"] else check_vocal(s, m, r, profiles))
    title_low = s["title"].strip().lower()
    if title_low and title_low in profiles:
        found.append(_f("fail", "title", f"'{s['title']}' is a character's name — never a song title"))
    sc = score(s, m)
    fails = [f for f in found if f["level"] == "fail"]
    warns = [f for f in found if f["level"] == "warn"]
    verdict = "fails" if fails else ("needs work" if warns and (sc < r["ready_score"] or len(warns) >= 3) else "ready")
    if verdict == "ready" and sc < r["ready_score"] and not s.get("spoken"):   # a monologue is judged by its findings
        verdict = "needs work"
    if verdict == "needs work" and not warns:
        found.append(_f("warn", "complexity", f"{sc}/100 — under this game's bar ({r['ready_score']}), though no single rule broke",
                        "more shape: name who plays each section, how it changes, the room it's recorded in"))
    return {"id": s["id"], "title": s["title"], "source": s["source"],
            "kind": "instrumental" if s["instrumental"] else ("spoken" if s.get("spoken") else "vocal"),
            "singers": s["singers"], "verdict": verdict, "score": sc, "findings": found, "measures": m}


def ready(result: dict) -> bool:
    """The gate a Suno run uses: nothing that fails or needs work is sent to be made."""
    return result.get("verdict") == "ready"


def review_all(songs: list[dict], profiles: dict | None = None, rules: dict | None = None) -> list[dict]:
    r = {**RULES, **(rules or {})}
    results = [review(s, profiles, r) for s in songs]
    # titles: never reused (Suno lets takes that share a name colour each other)
    seen: dict[str, list[int]] = {}
    for i, s in enumerate(songs):
        if s["title"]:
            seen.setdefault(s["title"].strip().lower(), []).append(i)
    def same_song(i, j):
        a, b = songs[i], songs[j]
        n = lambda x: re.sub(r"\s+", " ", x.lower()).strip()
        return n(a["style"]) == n(b["style"])
    for t, idx in seen.items():
        if len(idx) > 1:
            for i in idx:
                others = [songs[j]["source"] for j in idx if j != i and not same_song(i, j)]
                if not others:
                    continue                      # the same song, listed in two places (a sheet and its own file)
                results[i]["findings"].append(_f("fail", "title reused", f"'{songs[i]['title']}' is also {', '.join(others[:3])}",
                                                 "a changed sheet gets a changed title"))
                results[i]["verdict"] = "fails"
    # variety: a style too like another in the same sheet
    toks = [set(w for w in _words(s["style"]) if w not in STOP and len(w) > 2) for s in songs]
    for i in range(len(songs)):
        for j in range(i + 1, len(songs)):
            if not toks[i] or not toks[j] or songs[i]["source"].split(" #")[0] != songs[j]["source"].split(" #")[0]:
                continue
            sim = len(toks[i] & toks[j]) / len(toks[i] | toks[j])
            if sim > r["similar_max"]:
                for a, b in ((i, j), (j, i)):
                    results[a]["findings"].append(_f("warn", "variety", f"style {int(sim * 100)}% like '{songs[b]['title']}'",
                                                     "make it a different idiom (William: 'consider the variety of music')"))
                    if results[a]["verdict"] == "ready":
                        results[a]["verdict"] = "needs work"
    return results


# ------------------------------------------------------------------------------------------------ the report
def write_report(results: list[dict], skipped: list[str], out_dir: Path, title: str = "") -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    order = {"fails": 0, "needs work": 1, "ready": 2}
    results = sorted(results, key=lambda x: (order[x["verdict"]], x["score"]))
    n = {k: sum(1 for x in results if x["verdict"] == k) for k in order}
    md = [f"# Song review{(' — ' + title) if title else ''} ({datetime.now():%Y-%m-%d %H:%M})", "",
          f"**{len(results)} sheets:** {n['ready']} ready · {n['needs work']} need work · {n['fails']} fail. "
          "Nothing in any sheet was changed — this is a review.", ""]
    for x in results:
        mark = {"fails": "✖", "needs work": "▲", "ready": "✔"}[x["verdict"]]
        md.append(f"## {mark} {x['title']} — {x['verdict']} · {x['score']}/100 · {x['kind']}"
                  + (f" · {', '.join(x['singers'])}" if x["singers"] else ""))
        md.append(f"*{x['source']}*")
        for f in x["findings"]:
            if f["level"] == "info" and x["verdict"] == "ready":
                continue
            md.append(f"- **{f['level']}** · {f['check']}: {f['message']}" + (f" → {f['fix']}" if f.get("fix") else ""))
        md.append("")
    if skipped:
        md += ["## Not reviewed", ""] + [f"- {s}" for s in skipped[:200]] + [""]
    (out_dir / "REPORT.md").write_text("\n".join(md), encoding="utf-8")
    (out_dir / "review.json").write_text(json.dumps({"results": results, "skipped": skipped}, indent=1, ensure_ascii=False),
                                         encoding="utf-8")
    return out_dir / "REPORT.md"


# ------------------------------------------------------------------------------------------------ the game's settings
def game_settings(cfg: dict, gid: str) -> dict:
    """games/<id>/song_review.json: {"sources": [paths under the game folder], "rules": {…}, "styles_dir": "music/styles"}."""
    from . import config as cfgmod
    p = cfgmod.path_of(cfg, "games") / gid / "song_review.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except (OSError, ValueError):
        return {}


def run(cfg: dict, gid: str, files: list[str] | None = None, all_status: bool = False) -> dict:
    from . import config as cfgmod
    from .suite import games
    st = game_settings(cfg, gid)
    rules = {**RULES, **(st.get("rules") or {})}
    try:
        root = games.game_root(cfg, gid)
    except Exception:  # noqa: BLE001
        root = None
    srcs = [Path(f) for f in files] if files else [Path(root) / s for s in st.get("sources") or []] if root else []
    profiles = load_profiles(Path(root) / (st.get("styles_dir") or "music/styles") if root else None)
    songs, skipped = collect(srcs, all_status, rules)
    results = review_all(songs, profiles, rules)
    out = cfgmod.path_of(cfg, "out") / "song_review" / gid / f"{datetime.now():%Y%m%d-%H%M%S}"
    rep = write_report(results, skipped, out, gid)
    n = {k: sum(1 for x in results if x["verdict"] == k) for k in ("ready", "needs work", "fails")}
    log.info("song review: %d sheets — %s; report %s", len(results), n, rep)
    return {"report": str(rep), "counts": n, "results": results, "skipped": skipped, "sources": [str(s) for s in srcs]}


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:  # noqa: BLE001
            pass
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    from . import config as cfgmod
    from . import log as logmod
    cfg = cfgmod.load()
    cfgmod.ensure_dirs(cfg)
    logmod.setup(cfgmod.path_of(cfg, "logs"))
    gid = None
    if "--game" in argv:
        i = argv.index("--game")
        gid = argv[i + 1] if i + 1 < len(argv) else None
    gid = gid or cfgmod.default_game(cfg)
    files = [a for k, a in enumerate(argv) if not a.startswith("--") and (k == 0 or argv[k - 1] != "--game")]
    r = run(cfg, gid, files or None, all_status="--all-status" in argv)
    if not r["sources"]:
        print(f"No sheets to review: give a file or folder, or list them in games/{gid}/song_review.json (\"sources\").")
        return 2
    c = r["counts"]
    print(f"Song review — {sum(c.values())} sheets: {c['ready']} ready · {c['needs work']} need work · {c['fails']} fail.")
    for x in sorted(r["results"], key=lambda x: x["score"]):
        if "--problems" in argv and x["verdict"] == "ready":
            continue
        print(f"  {x['verdict']:10} {x['score']:3}/100  {x['title']}")
    print(f"Report: {r['report']}")
    if "--open" in argv:
        from .suite import osopen                                    # the one place that opens a file for a person (BUILD 27)
        osopen.open_path(r["report"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
