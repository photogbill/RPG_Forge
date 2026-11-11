#!/usr/bin/env python3
"""The example game's own checker. Whole game: python tools/validate.py   One file: python tools/validate.py --file <path>
A file is judged by its name and its folder's name, so a copy in a folder of the same name is checked like the real one.
Prints PROBLEM: lines and exits 1 when something is wrong; prints OK and exits 0 otherwise."""
import json, os, sys

STATUSES = (None, "draft", "approved", "flagged")


def check_one(path):
    out = []
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
    except Exception as e:
        return ["%s doesn't read as JSON: %s" % (os.path.basename(path), e)]
    name, folder = os.path.basename(path), os.path.basename(os.path.dirname(path))
    if folder == "places":
        for k in ("id", "name", "kind"):
            if not data.get(k):
                out.append("%s: a place needs '%s'" % (name, k))
        if data.get("status") not in STATUSES:
            out.append("%s: status must be draft, approved or flagged" % name)
    if folder == "dialogue":
        for i, l in enumerate(data.get("lines", [])):
            if not isinstance(l, dict) or not str(l.get("text", "")).strip():
                out.append("%s: line %d has no words" % (name, i + 1))
            elif l.get("status") not in STATUSES:
                out.append("%s: line %d status must be draft, approved or flagged" % (name, i + 1))
    if name == "music.json":
        for k, v in data.items():
            if not isinstance(v, dict) or "purpose" not in v:
                out.append("music.json: slot '%s' needs a purpose" % k)
    if name == "characters.json":
        for k, v in data.items():
            if not isinstance(v, dict) or not v.get("name"):
                out.append("characters.json: '%s' needs a name" % k)
    if name == "quests.json":
        for k, v in data.items():
            if not isinstance(v, dict) or not v.get("title") or not v.get("steps"):
                out.append("quests.json: '%s' needs a title and steps" % k)
    return out


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--file":
        problems = check_one(sys.argv[2])
    else:
        root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
        problems = []
        for d, _, files in os.walk(root):
            for f in files:
                if f.endswith(".json"):
                    problems += check_one(os.path.join(d, f))
    for p in problems:
        print("PROBLEM:", p)
    print("OK" if not problems else "%d problems" % len(problems))
    sys.exit(1 if problems else 0)
