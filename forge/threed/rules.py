"""What the 3D line taught the hard way (2026-11-12 to 14), built into the workshop as checks and plain warnings — shown,
never hidden, and never a refusal: the person decides (BUILD 36, Part D).

    apose_check(text)   the picture must be an A-pose with the arms well clear of the body
    look_chips(text)    a long coat, skirt, apron, cape, wings, tail or loose long hair: what the body will do with it
    height_check(m)     a body's height is always in metres
    rigger_for(kind)    people: Make-It-Animatable with fingers; animals: UniRig after their seams are welded
    KNOWN_FAULTS        the verdict on the first 92 bodies (2026-11-14), said plainly on every screen that makes one
    standing_check(text)    BUILD 40: what the second run taught about a body's words — children and teenagers, a missing
                            limb, lettering on clothes (warnings for the Bodies form)
    body_word_rules(words, always)   the same, applied: the words the world queue paints a body's picture from
"""
from __future__ import annotations

import re

APOSE_RULE = ("Paint the picture in an A-pose: standing straight, seen from the front, both arms held straight and well away "
              "from the body (about 45 degrees), hands open, legs a little apart. Arms near the body get welded to it, and "
              "whatever the hands are near is dragged along when the arm moves.")
APOSE_EXAMPLE = ("Seen on 2026-11-13: a character painted with her arms at her sides came out with a strap of her hip gear "
                 "stuck to her arm, so it swung with every step. The same character in an A-pose came out clean.")

# words that say the arms or hands are not clear of the body (warn; a T-pose is also fine)
_BAD_POSE = [
    (r"\barms? (?:at|by|down at) (?:his|her|their|its|the)? ?sides?\b", "arms at the sides"),
    (r"\bhands? on (?:his|her|their|its|the)? ?hips?\b", "hands on the hips"),
    (r"\bcrossed arms\b|\barms crossed\b|\bfolded arms\b|\barms folded\b", "arms crossed"),
    (r"\bhands? in (?:his|her|their|its)? ?pockets?\b", "hands in pockets"),
    (r"\bholding (?:a|an|the|his|her|their)\b", "holding something"),
    (r"\b(?:three-quarter|side|back) view\b|\bfrom the side\b|\bfrom behind\b", "not seen from the front"),
    (r"\bsitting\b|\bseated\b|\bkneeling\b|\bcrouch(?:ing)?\b|\blying\b", "not standing"),
]
_NEGATED = re.compile(r"\b(?:no|not|never|without)\b[^.,;]{0,40}$")


def apose_check(text: str) -> list[str]:
    """What in the words breaks the A-pose rule (empty = nothing seen). Phrases after 'no / not / without' don't count."""
    low = " " + str(text or "").lower() + " "
    found = []
    for pat, what in _BAD_POSE:
        for m in re.finditer(pat, low):
            if not _NEGATED.search(low[max(0, m.start() - 48):m.start()]):
                found.append(what)
                break
    if "a-pose" not in low and "a pose" not in low and "t-pose" not in low and "t pose" not in low:
        found.append("the words never ask for an A-pose")
    return found


# look words -> what the body will do with them
_CHIPS = [
    (r"\b(?:long|trench|duster|great|frock|lab|over)\s*coats?\b|\bcoat to (?:the|her|his) (?:knees?|ankles?)\b|\bdusters?\b|\btrench\b",
     "long coat", "skinned to the legs: it moves with the legs, not on its own"),
    (r"\bskirts?\b|\bdress(?:es)?\b|\bgowns?\b|\brobes?\b|\bkilts?\b|\bsarong\b", "skirt or dress",
     "skinned to the legs: it splits and stretches with each step"),
    (r"\baprons?\b", "apron", "skinned to the legs"),
    (r"\bcapes?\b|\bcloaks?\b|\bmantles?\b|\bponchos?\b", "cape or cloak", "skinned to the body and arms: it won't flow"),
    (r"\bwings?\b", "wings", "need bones of their own: today's riggers give them none"),
    (r"\btails?\b", "tail", "needs bones of its own: today's riggers give it none"),
    (r"\b(?:long|loose|flowing|waist-length|shoulder-length)\b[^.,;]{0,24}\bhair\b|\bhair (?:worn )?(?:down|loose)\b|\bponytail\b|\bbraids?\b",
     "loose long hair", "comes out as one piece with the head and is skinned to the body: it won't swing"),
    (r"\bshields?\b", "shield", "welds to the arm or body"),
    (r"\b(?:shiny|glossy|satin|silk|latex|leather|metallic|chrome|polished)\b", "shiny surface",
     "highlights get baked into the colour: it looks lit from one side forever"),
    (r"\bglow(?:s|ing)?\b|\bneon\b|\bluminous\b", "glow", "glow is lost on dark characters: plan to add it in the game"),
    (r"\bholsters?\b|\bpouch(?:es)?\b|\bbelt (?:of|with)\b|\btool ?belt\b|\bhip (?:gear|bag)\b", "hip gear",
     "hands that come near it can grow extra fingers: keep the arms well clear"),
    (r"\bsmil(?:e|es|ed|ing)\b|\bgrin(?:s|ning|ned)?\b|\blaugh(?:s|ing)?\b|\bbeaming\b", "smile",
     "a smile in the picture is a smile forever: expression belongs to animation and portraits (BUILD 39)"),
]


def look_chips(text: str) -> list[dict]:
    """Warning chips for a look: [{word, what}]. Phrases after 'no / not / without' don't count."""
    low = " " + str(text or "").lower() + " "
    out = []
    for pat, word, what in _CHIPS:
        for m in re.finditer(pat, low):
            if not _NEGATED.search(low[max(0, m.start() - 48):m.start()]):
                out.append({"word": word, "what": what})
                break
    return out


def height_check(m, kind: str = "people") -> str:
    """'' when a height in metres looks right for the kind; otherwise why not (a warning, never a refusal)."""
    try:
        v = float(m)
    except (TypeError, ValueError):
        return "a height in metres is needed (1.75, not 175 or 5'9\")"
    if v <= 0:
        return "a height in metres is needed"
    if kind in ("people", "person"):
        if v > 3.0:
            return f"{v:g} m is taller than any person - is it centimetres? (1.75 m, not 175)"
        if v < 0.4:
            return f"{v:g} m is very small for a person - a baby is about 0.5 m"
    if v > 80:
        return f"{v:g} m is very large - is it centimetres or feet?"
    return ""


def rigger_for(kind: str) -> tuple[str, bool]:
    """(rigger, weld first) for a kind of body."""
    return ("unirig", True) if str(kind) in ("animal", "thing") else ("mia", False)


KNOWN_FAULTS = [
    ("bowed head and hunched shoulders", "on every body so far; the cause isn't proven yet (a T-pose test is running)"),
    ("loose hair, shields and skirts weld to the body", "they move with whatever they touch"),
    ("hands near hip gear grow extra fingers", "keep the arms well clear of belts, holsters and pouches"),
    ("shiny cloth bakes its highlights into the colour", "the body looks lit from one side in every light"),
    ("glow is lost on dark characters", "add it in the game instead"),
    ("fingers curl to near-fists in the library's walk", "a known limit of the motion library"),
    ("tacked-on style words did almost nothing", "the look comes from the description, not from style words added at the end"),
    ("a smile in the picture is a smile forever", "the face is baked in: describe a relaxed, kind expression with the mouth closed"),
]


# ------------------------------------------------------------------------------------------------ BUILD 40: standing words
# What the launch-site runs showed (2026-11-14): "Fantastic realism" painted a boy of nine and a girl of sixteen with cartoon
# proportions, and the same words starting "Hyperrealistic" and naming real proportions painted real children (adults came
# out right under either start, so the two-starts rule stands for adults). Two wordings for a one-armed man both came out
# with two arms: the shared A-pose words ask for both arms, and the picture model does not leave one out when asked.
# Clothes came out with lettering and badges nobody asked for.
YOUTH_START = "Hyperrealistic."
YOUTH_WORDS = ("Photographed, with the natural proportions of a real {age}-year-old: a head of normal size for the body, "
               "nothing exaggerated.")
NO_LETTERING = "No lettering, no badges, no logos, no name tapes on the clothes."
ONE_ARM_WORDS = ("Only one arm: on the other side there is no arm below the {where}, nothing is drawn there; the one arm is held "
                 "straight and well away from the body.")
LIMB_NOTE = ("the run of 2026-11-14 painted two arms under both wordings tried, so a missing limb is made by cutting the "
             "finished body, not by the picture — check the picture before the body is made")
_LETTERING = re.compile(r"\b(?:letter(?:ing|ed)|logo|badge|patch(?:es)?|name ?tape|insignia|printed|slogan|text on)\b", re.I)


def _youth(text: str) -> tuple[int | None, str | None]:
    from .gate import age_of, band
    a = age_of(text)
    return a, band(a)


def standing_check(text: str) -> list[str]:
    """Warnings for a body's words, from the second run. Never a refusal."""
    t = str(text or "")
    low = t.lower()
    out = []
    age, b = _youth(t)
    if b in ("child", "teen"):
        if not low.lstrip().startswith("hyperrealistic"):
            out.append(f"a {'child' if b == 'child' else 'teenager'} of {age}: start the words \"Hyperrealistic\" — "
                       "\"Fantastic realism\" painted both children of the last run with cartoon proportions")
        if "proportion" not in low:
            out.append("name real proportions (\"the natural proportions of a real " + str(age) + "-year-old, a head of "
                       "normal size for the body\") — the words that worked in the redo")
    from .gate import expectations
    if expectations({"prompt": t}).get("arms") == 1:
        out.append("a missing limb: " + LIMB_NOTE)
    if _LETTERING.search(t) and not re.search(r"\bno (?:lettering|logos?|badges?)\b", low):
        out.append("lettering or a badge is asked for: the picture model invents the words — say what it says, or leave it off")
    return out


def body_word_rules(words: str, always: str) -> tuple[str, str, list[str]]:
    """The standing words, applied to a body's picture words: (words, always words, notes of what was changed)."""
    from .gate import expectations
    notes = []
    w = str(words or "").strip()
    al = str(always or "").strip()
    age, b = _youth(w)
    if b in ("child", "teen"):
        if not w.lower().startswith("hyperrealistic"):
            w2 = re.sub(r"^\s*fantastic realism\.?\s*", "", w, flags=re.I)
            w = f"{YOUTH_START} {w2}".strip()
            notes.append(f"started the words \"Hyperrealistic\" (a {'child' if b == 'child' else 'teenager'} of {age}: "
                         "\"Fantastic realism\" painted children with cartoon proportions)")
        if "proportion" not in w.lower():
            w = w.rstrip() + " " + YOUTH_WORDS.format(age=age)
            notes.append("named real proportions for the age")
    exp = expectations({"prompt": w})
    if exp.get("arms") == 1 and "only one arm" not in w.lower():
        m = re.search(r"\b(?:below|above|at|from) the (elbow|shoulder|wrist)\b", w, re.I)
        w = w.rstrip() + " " + ONE_ARM_WORDS.format(where=(m.group(1).lower() if m else "shoulder"))
        notes.append("added one-arm pose words (the shared A-pose words ask for both arms); " + LIMB_NOTE)
    if NO_LETTERING.lower() not in al.lower() and not re.search(r"\bno lettering\b", w, re.I):
        al = (al + " " + NO_LETTERING).strip()
    return w, al, notes
