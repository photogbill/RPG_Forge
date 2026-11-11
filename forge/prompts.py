"""The prompt library (Night 3, G6): named blocks, `{{block.name}}` references, expanded by `submit`; and the never-list.

    games/<game>/prompts/*.json     {"blocks": {"style.house": "…", "light.dusk_sodium": "…"}}   (any number of files)
    games/<game>/prompts/never.json {"words": […], "lora_triggers_forbidden": […]}

A job's `prompt` / `negative` may contain `{{style.house}}`; `submit` (and `bakeoff submit`) replaces every reference
with the block's text before the job reaches the queue — the worker only ever sees plain text. The job records what it
was built from: `prompt_blocks` (the names) and `prompt_library` (a hash of the library's text), so a picture can be
traced back to the exact words. A block may reference other blocks (cycles are refused). An unknown reference refuses
the submit and names it.

Shelves (William's own prompting method, 2026-11-09): movement.* technique.* medium.* process.* period.* purpose.*
quality.* beside style.* light.* place.* era.* neg.* — the forge ships placeholders only; the words are Fable's and
William's.

The never-list: words that must never be in a submitted prompt (whole words, case-blind), checked after expansion.
It is how William's ruling on artist-named LoRAs is kept (2026-11-09): the LoRA may be used; the artist's name and
the LoRA's trigger keywords never go in a prompt.

    python -m forge prompts list | show <block> | where-used <block> | check [batch.json …] | ab <block> --on <batch>
"""
from __future__ import annotations
import hashlib, json, re
from pathlib import Path

from . import config as cfgmod

REF = re.compile(r"\{\{\s*([A-Za-z0-9_.\-]+)\s*\}\}")
SHELVES = ("style", "light", "place", "era", "neg", "skin", "layout", "movement", "technique", "medium", "process", "period", "purpose", "quality",
           "char", "mood", "pose", "icon", "culture", "fate", "enclave", "ui", "state", "sleeve")   # Night 4: characters, icons, towns
TEXT_FIELDS = ("prompt", "negative", "style_prefix")


class PromptError(ValueError):
    pass


def folder(cfg: dict, game: str) -> Path:
    return cfgmod.path_of(cfg, "games") / game / "prompts"


def load(cfg: dict, game: str) -> dict:
    """{"blocks": {name: text}, "files": {name: file}, "version": hash, "never": [...], "triggers": [...]}"""
    d = folder(cfg, game)
    blocks, files = {}, {}
    never, triggers = [], []
    if d.exists():
        for p in sorted(d.glob("*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except ValueError as e:
                raise PromptError(f"{p.name} is not valid JSON: {e}")
            if p.name == "never.json":
                never = [str(w) for w in data.get("words") or []]
                triggers = [str(w) for w in data.get("lora_triggers_forbidden") or []]
                continue
            for name, text in (data.get("blocks") or {}).items():
                if name in blocks:
                    raise PromptError(f"block '{name}' is defined twice ({files[name]} and {p.name})")
                blocks[name] = str(text)
                files[name] = p.name
    ver = hashlib.sha1(json.dumps(blocks, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:10]
    return {"blocks": blocks, "files": files, "version": ver, "never": never, "triggers": triggers}


def expand_text(text: str, blocks: dict, used: list | None = None, _stack: tuple = ()) -> str:
    used = used if used is not None else []

    def sub(m):
        name = m.group(1)
        if name not in blocks:
            raise PromptError(f"unknown prompt block {{{{{name}}}}}" + (f" (inside {_stack[-1]})" if _stack else ""))
        if name in _stack:
            raise PromptError(f"prompt blocks reference each other in a loop: {' → '.join(_stack + (name,))}")
        if str(blocks[name]).strip().upper().startswith("TODO"):
            raise PromptError(f"prompt block {{{{{name}}}}} is still a placeholder ('{blocks[name][:40]}') — write its words first")
        if name not in used:
            used.append(name)
        return expand_text(blocks[name], blocks, used, _stack + (name,))
    out = REF.sub(sub, str(text))
    return re.sub(r"\s*,\s*,+", ",", re.sub(r"\s{2,}", " ", out)).strip(" ,")


def refs(text) -> list[str]:
    return REF.findall(str(text or ""))


def expand_job(job: dict, lib: dict) -> dict:
    """A copy of the job with every reference expanded and the provenance fields set (unchanged if it uses none)."""
    if not any(refs(job.get(f)) for f in TEXT_FIELDS):
        return job
    j, used = dict(job), []
    for f in TEXT_FIELDS:
        if j.get(f) is not None and refs(j[f]):
            j.setdefault("_prompt_template", {})[f] = job[f]
            j[f] = expand_text(j[f], lib["blocks"], used)
    j["prompt_blocks"] = used
    j["prompt_library"] = lib["version"]
    j["prompt_template"] = j.pop("_prompt_template")
    return j


def never_words(lib: dict) -> list[str]:
    return [w for w in lib["never"] + lib["triggers"] if w.strip()]


def never_hits(job: dict, words: list[str]) -> list[str]:
    hits = []
    for f in TEXT_FIELDS:
        t = str(job.get(f) or "")
        for w in words:
            if re.search(r"(?<![\w])" + re.escape(w) + r"(?![\w])", t, re.IGNORECASE):
                hits.append(w)
    return sorted(set(hits), key=str.lower)


def prepare(cfg: dict, jobs: list[dict], game: str | None = None) -> list[dict]:
    """Expand every job and check the never-list. Raises PromptError naming the job and the word / block."""
    out = []
    libs = {}
    for j in jobs:
        g = j.get("game") or game or cfgmod.default_game(cfg)
        if g not in libs:
            libs[g] = load(cfg, g)
        lib = libs[g]
        try:
            e = expand_job(j, lib)
        except PromptError as err:
            raise PromptError(f"job '{j.get('name') or j.get('id') or '?'}': {err}")
        bad = never_hits(e, never_words(lib))
        if bad:
            raise PromptError(f"job '{j.get('name') or j.get('id') or '?'}': the prompt contains {', '.join(repr(b) for b in bad)}, "
                              f"which is on the never-list (games/{g}/prompts/never.json)")
        out.append(e)
    return out


def text_key(job: dict) -> str:
    return hashlib.sha1(json.dumps([job.get("batch"), job.get("name"), job.get("type")] +
                                   [job.get(f) for f in TEXT_FIELDS], ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def filter_changed(cfg: dict, jobs: list[dict]) -> tuple[list[dict], int]:
    """For library-built jobs: skip a job whose batch · name · type · expanded text already has a done/pending/running/
    paused job — so changing one block and re-submitting re-renders only the jobs that block reaches."""
    have = set()
    root = cfgmod.path_of(cfg, "jobs")
    for st in ("done", "pending", "running", "paused"):
        for p in (root / st).glob("*.json"):
            try:
                have.add(text_key(json.loads(p.read_text(encoding="utf-8"))))
            except (OSError, ValueError):
                continue
    keep, skipped = [], 0
    for j in jobs:
        if text_key(j) in have:
            skipped += 1
        else:
            keep.append(j)
    return keep, skipped


def where_used(cfg: dict, block: str) -> list[dict]:
    """Jobs (queued or finished) built with this block, and batch files that reference it."""
    hits = []
    root = cfgmod.path_of(cfg, "jobs")
    for st in ("pending", "running", "paused", "done", "failed"):
        for p in sorted((root / st).glob("*.json")):
            try:
                j = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if block in (j.get("prompt_blocks") or []):
                hits.append({"where": st, "id": j.get("id"), "name": j.get("name"), "batch": j.get("batch")})
    games = cfgmod.path_of(cfg, "games")
    for p in sorted(games.glob("*/batches/*.json")):
        try:
            txt = p.read_text(encoding="utf-8")
        except OSError:
            continue
        if re.search(r"\{\{\s*" + re.escape(block) + r"\s*\}\}", txt):
            hits.append({"where": "batch file", "id": None, "name": p.name, "batch": str(p.relative_to(games))})
    return hits


def check_library(lib: dict) -> list[str]:
    """Problems in the library itself: unknown refs inside blocks, loops, names off the shelves, never-words in blocks."""
    probs = []
    for name, text in lib["blocks"].items():
        if name.split(".")[0] not in SHELVES:
            probs.append(f"{name}: not on a known shelf ({', '.join(SHELVES)}) — allowed, but check the spelling")
        try:
            expand_text(text, lib["blocks"], [], (name,))
        except PromptError as e:
            probs.append(f"{name}: {e}")
        bad = never_hits({"prompt": text}, never_words(lib))
        if bad:
            probs.append(f"{name}: contains never-list word(s) {', '.join(bad)}")
    return probs


def ab_drafts(cfg: dict, block: str, batch: str, n: int = 4, game: str | None = None) -> Path:
    """A `_draft` batch: for up to n finished jobs of `batch` that used `block`, the same job twice — with the block and
    without it — same seed, so the block is judged on its own before it is trusted."""
    game = game or cfgmod.default_game(cfg)   # never a literal game (RPG_Forge is game-agnostic)
    lib = load(cfg, game)
    if block not in lib["blocks"]:
        raise PromptError(f"unknown block '{block}'")
    root = cfgmod.path_of(cfg, "jobs")
    picks = []
    for p in sorted((root / "done").glob("*.json")):
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if j.get("batch") in (batch, f"bakeoff/{batch}") and (block in (j.get("prompt_blocks") or []) or not j.get("prompt_blocks")):
            picks.append(j)
        if len(picks) >= n:
            break
    if not picks:
        raise PromptError(f"no finished jobs in '{batch}'")
    jobs = []
    keep = ("type", "game", "checkpoint", "loras", "size", "target", "steps", "cfg", "sampler", "scheduler", "graph", "init",
            "denoise", "control", "refine", "freeu")
    for j in picks:
        tmpl = (j.get("prompt_template") or {}).get("prompt") or j.get("prompt") or ""
        with_b = tmpl if refs(tmpl) and block in refs(tmpl) else f"{{{{{block}}}}}, {tmpl}"
        without = re.sub(r"\{\{\s*" + re.escape(block) + r"\s*\}\}\s*,?\s*", "", with_b).strip(" ,")
        base = {k: j[k] for k in keep if j.get(k) is not None}
        seed = j.get("seed") if isinstance(j.get("seed"), int) and j.get("seed") >= 0 else 1001
        jobs.append({**base, "name": f"ab_{block.replace('.', '_')}_{j.get('name')}_with", "prompt": with_b, "seed": seed})
        jobs.append({**base, "name": f"ab_{block.replace('.', '_')}_{j.get('name')}_without", "prompt": without, "seed": seed})
    out = cfgmod.path_of(cfg, "games") / game / "batches" / f"draft_ab_{block.replace('.', '_')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"_draft": f"A/B for {{{{{block}}}}}: same seed with and without — check, delete this line, submit",
                               "batch": f"ab_{block.replace('.', '_')}", "jobs": jobs}, indent=1, ensure_ascii=False), encoding="utf-8")
    return out
