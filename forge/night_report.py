"""The morning report (Night 3, G1): "what happened while I slept?" — one page from the queue folders and out/.

    python -m forge report night [--since 2026-11-08T20:00] [--until …] [--hours 12] [--all]
        → out/reports/night_<date>.html and .md     (night_report.bat opens the page)

Per batch (a bake-off suite is batch "bakeoff/<suite>"): queued, done, failed (each cause once, with a count and the
error's first line), skipped as already done (from the suite's plan.json), wall time, seconds per render by checkpoint;
the slowest and the failed cells by name; every model used with its licence colour; for a suite, a link to its
index.html and a strip of thumbnails; and a "what to run next" block built from what exists. Read-only: it never
touches jobs/ and writes only under out/reports/.
"""
from __future__ import annotations
import html, json, re, statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image

from . import config as cfgmod

STATES = ("done", "failed", "pending", "running", "paused")
LIC_COLOUR = {"ok": "#3fae5a", "no": "#d04848", "unknown": "#8a8a8a"}


def _ts(s) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s)[:19])
    except ValueError:
        return None


def load_jobs(jobs_dir: Path) -> list[dict]:
    rows = []
    for st in STATES:
        for p in sorted((jobs_dir / st).glob("*.json")):
            try:
                j = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if j.get("tombstone"):
                continue
            j["_state"] = st
            rows.append(j)
    return rows


def window(jobs: list[dict], since: datetime | None, until: datetime | None) -> list[dict]:
    """Finished jobs whose finished_at falls in [since, until]; every pending/running/paused job is kept (it is
    what is still to come)."""
    out = []
    for j in jobs:
        if j["_state"] in ("done", "failed"):
            t = _ts(j.get("finished_at"))
            if t is None or (since and t < since) or (until and t > until):
                continue
        out.append(j)
    return out


def cause(err: str | None) -> str:
    """One line per kind of failure: the first line, numbers folded, so 20 identical errors read as one cause."""
    first = (str(err or "unknown error").strip().splitlines() or ["unknown error"])[0]
    return re.sub(r"\d+", "#", first)[:160]


def suite_of(batch: str | None) -> str | None:
    b = str(batch or "")
    return b.split("/", 1)[1] if b.startswith("bakeoff/") else None


def models_of(j: dict) -> list[str]:
    ms = []
    if j.get("checkpoint"):
        ms.append(Path(str(j["checkpoint"])).name)
    for lo in j.get("loras") or []:
        n = lo.get("name") if isinstance(lo, dict) else lo
        if n:
            ms.append(Path(str(n)).name)
    return ms


class Licences:
    """File name → ok / no / unknown, from models/models.json and models/licences.json (same rules as approve)."""

    def __init__(self, root: Path):
        self.map: dict[str, tuple[str, str]] = {}
        reg = root / "models" / "models.json"
        if reg.exists():
            for mname, m in json.loads(reg.read_text(encoding="utf-8")).get("models", {}).items():
                for f in list(m.get("files", [])) + list((m.get("save_as") or {}).values()):
                    self.map[Path(f).name] = (self._c(m.get("commercial_ok")), str(m.get("license") or "?"))
        loc = root / "models" / "licences.json"
        if loc.exists():
            for name, rec in json.loads(loc.read_text(encoding="utf-8")).items():
                if isinstance(rec, dict):
                    self.map.setdefault(name, (self._c(rec.get("commercial_ok")), str(rec.get("license") or "?")))

    @staticmethod
    def _c(v) -> str:
        return "ok" if v is True else ("no" if v is False else "unknown")

    def of(self, name: str) -> tuple[str, str]:
        return self.map.get(Path(name).name, ("unknown", "not on record"))


def image_of(out_root: Path, j: dict) -> Path | None:
    d = out_root / str(j.get("id"))
    for o in ((j.get("result") or {}).get("outputs") or []):
        if str(o).lower().endswith((".png", ".jpg")) and (d / o).exists():
            return d / o
    if d.exists():
        pngs = sorted(p for p in d.glob("*.png") if not p.name.startswith(("raw", "control", "contact")))
        if pngs:
            return pngs[0]
    return None


def summarise(jobs: list[dict], out_root: Path, lic: Licences) -> dict:
    groups: dict[str, list[dict]] = defaultdict(list)
    for j in jobs:
        groups[str(j.get("batch") or "(no batch)")].append(j)
    batches = []
    all_done = [j for j in jobs if j["_state"] == "done"]
    for name, js in sorted(groups.items()):
        st = Counter(j["_state"] for j in js)
        if not (st["done"] or st["failed"]):
            batches.append({"name": name, "suite": suite_of(name), "counts": dict(st), "only_waiting": True})
            continue
        fin = [j for j in js if j["_state"] in ("done", "failed")]
        starts = [t for t in (_ts(j.get("started_at")) for j in fin) if t]
        ends = [t for t in (_ts(j.get("finished_at")) for j in fin) if t]
        wall = (max(ends) - min(starts)).total_seconds() if starts and ends else None
        per_ck: dict[str, list[float]] = defaultdict(list)
        for j in js:
            s = (j.get("result") or {}).get("seconds")
            if j["_state"] == "done" and isinstance(s, (int, float)):
                per_ck[Path(str(j.get("checkpoint") or j.get("type") or "?")).name].append(float(s))
        causes = Counter(cause(j.get("error")) for j in js if j["_state"] == "failed")
        skipped = None
        suite = suite_of(name)
        if suite:
            pf = out_root / "bakeoff" / suite / "plan.json"
            if pf.exists():
                try:
                    se = json.loads(pf.read_text(encoding="utf-8")).get("skipped_existing")
                    skipped = sum(se.values()) if isinstance(se, dict) else (len(se) if isinstance(se, list) else se)
                except (OSError, ValueError):
                    pass
        batches.append({
            "name": name, "suite": suite, "counts": dict(st), "queued": len(js), "skipped": skipped,
            "wall_s": wall, "first": min(starts).isoformat() if starts else None, "last": max(ends).isoformat() if ends else None,
            "sec_by_ckpt": {k: {"n": len(v), "median": round(statistics.median(v), 1), "max": round(max(v), 1)}
                            for k, v in sorted(per_ck.items())},
            "causes": causes.most_common(),
            "failed": [{"id": j["id"], "name": j.get("name"), "cause": cause(j.get("error"))} for j in js if j["_state"] == "failed"],
            "index": f"../bakeoff/{suite}/index.html" if suite and (out_root / "bakeoff" / suite / "index.html").exists() else None,
        })
    timed = [(float((j.get("result") or {}).get("seconds")), j) for j in all_done
             if isinstance((j.get("result") or {}).get("seconds"), (int, float))]
    slowest = [{"id": j["id"], "name": j.get("name"), "batch": j.get("batch"), "seconds": s}
               for s, j in sorted(timed, key=lambda x: -x[0])[:8]]
    used = Counter(m for j in jobs if j["_state"] in ("done", "failed") for m in models_of(j))
    models = [{"file": m, "uses": n, "licence": lic.of(m)[0], "license": lic.of(m)[1]} for m, n in used.most_common()]
    nxt = []
    for b in batches:
        if b.get("suite") and not b.get("only_waiting"):
            waiting = sum(b["counts"].get(s, 0) for s in ("pending", "running", "paused"))
            if waiting:
                nxt.append(f"bakeoff_report.bat {b['suite']}   (after the {waiting} still queued finish)")
            else:
                nxt.append(f"bakeoff_report.bat {b['suite']}")
                nxt.append(f"review_compact.bat {b['suite']}")
    if any(b["counts"].get("failed") for b in batches):
        nxt.append("retry_failed.bat <batch>   (only after the cause above is fixed)")
    return {"batches": batches, "slowest": slowest, "models": models, "next": nxt,
            "totals": dict(Counter(j["_state"] for j in jobs))}


def thumb_strip(out_root: Path, jobs: list[dict], dest: Path, n: int = 8, h: int = 120) -> Path | None:
    """A strip of up to n thumbnails, picked evenly across the batch's done jobs."""
    done = [j for j in jobs if j["_state"] == "done"]
    if not done:
        return None
    step = max(1, len(done) // n)
    tiles = []
    for j in done[::step][:n]:
        p = image_of(out_root, j)
        if p is None:
            continue
        try:
            with Image.open(p) as im:
                im = im.convert("RGB")
                im.thumbnail((h * 3, h))
                tiles.append(im.copy())
        except OSError:
            continue
    if not tiles:
        return None
    strip = Image.new("RGB", (sum(t.width for t in tiles) + 4 * (len(tiles) - 1), h), (20, 20, 24))
    x = 0
    for t in tiles:
        strip.paste(t, (x, (h - t.height) // 2))
        x += t.width + 4
    dest.parent.mkdir(parents=True, exist_ok=True)
    strip.save(dest, "JPEG", quality=82)
    return dest


def _dur(s) -> str:
    if s is None:
        return "-"
    s = int(s)
    return f"{s // 3600}h{(s % 3600) // 60:02d}m" if s >= 3600 else f"{s // 60}m{s % 60:02d}s"


def to_markdown(rep: dict, title: str) -> str:
    L = [f"# {title}", "", f"Totals in this window: " + ", ".join(f"{k} {v}" for k, v in sorted(rep["totals"].items())), ""]
    for b in rep["batches"]:
        c = b["counts"]
        if b.get("only_waiting"):
            L.append(f"## {b['name']} — not started yet ({', '.join(f'{k} {v}' for k, v in c.items())})")
            L.append("")
            continue
        L.append(f"## {b['name']}")
        L.append(f"- done {c.get('done', 0)} · failed {c.get('failed', 0)} · still queued now {c.get('pending', 0) + c.get('running', 0) + c.get('paused', 0)}"
                 + (f" · skipped as already done {b['skipped']}" if b.get("skipped") is not None else ""))
        L.append(f"- wall time {_dur(b['wall_s'])} ({(b['first'] or '')[:16]} → {(b['last'] or '')[:16]})")
        if b["sec_by_ckpt"]:
            L.append("- seconds per render by checkpoint: " + "; ".join(f"{k} {v['median']}s (n {v['n']}, max {v['max']})"
                                                                      for k, v in b["sec_by_ckpt"].items()))
        for cz, n in b["causes"]:
            L.append(f"- **failed ×{n}:** `{cz}`")
        if b.get("index"):
            L.append(f"- bake-off page: {b['index']}")
        if b.get("strip"):
            L.append(f"- ![]({b['strip']})")
        L.append("")
    if rep["slowest"]:
        L += ["## Slowest renders", ""] + [f"- {s['seconds']}s — {s['name']} ({s['batch']})" for s in rep["slowest"]] + [""]
    if rep["models"]:
        L += ["## Models used", ""] + [f"- [{m['licence']}] {m['file']} — {m['license']} ({m['uses']} jobs)" for m in rep["models"]] + [""]
    if rep["next"]:
        L += ["## What to run next", ""] + [f"- `{n}`" for n in rep["next"]] + [""]
    return "\n".join(L)


def to_html(rep: dict, title: str, reports_dir: Path) -> str:
    e = html.escape

    parts = [f"<!doctype html><meta charset=utf-8><title>{e(title)}</title><style>"
             "body{background:#16161b;color:#e8e8ee;font:14px/1.5 'Segoe UI',system-ui,sans-serif;margin:24px;max-width:1200px}"
             "h1{color:#f0b450}h2{border-bottom:1px solid #333;padding-bottom:4px;margin-top:28px}"
             ".pill{display:inline-block;border:1px solid #444;border-radius:12px;padding:1px 10px;margin:2px}"
             ".ok{border-color:#3fae5a}.bad{border-color:#d04848;color:#ff9a9a}table{border-collapse:collapse}"
             "td,th{padding:3px 10px;border-bottom:1px solid #2a2a33;text-align:left}code{color:#ffd08a}"
             "a{color:#8ac4ff}.lic{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px}"
             "img.strip{max-width:100%;border-radius:6px;margin-top:6px}</style>",
             f"<h1>{e(title)}</h1><p>" + "".join(f"<span class='pill {'bad' if k == 'failed' and v else 'ok' if k == 'done' else ''}'>{e(k)} {v}</span>"
                                             for k, v in sorted(rep["totals"].items())) + "</p>"]
    if rep["next"]:
        parts.append("<h2>What to run next</h2><ul>" + "".join(f"<li><code>{e(n)}</code></li>" for n in rep["next"]) + "</ul>")
    for b in rep["batches"]:
        c = b["counts"]
        if b.get("only_waiting"):
            parts.append(f"<h2>{e(b['name'])} <small style='color:#888'>not started yet — "
                         + e(", ".join(f"{k} {v}" for k, v in c.items())) + "</small></h2>")
            continue
        q = c.get('pending', 0) + c.get('running', 0) + c.get('paused', 0)
        parts.append(f"<h2>{e(b['name'])}</h2><p><span class='pill ok'>done {c.get('done', 0)}</span>"
                     f"<span class='pill {'bad' if c.get('failed') else ''}'>failed {c.get('failed', 0)}</span>"
                     f"<span class='pill'>still queued now {q}</span>"
                     + (f"<span class='pill'>skipped as done {b['skipped']}</span>" if b.get('skipped') is not None else "")
                     + f"<span class='pill'>wall {_dur(b['wall_s'])}</span> "
                     f"<small style='color:#888'>{e((b['first'] or '')[:16])} → {e((b['last'] or '')[:16])}</small></p>")
        if b.get("index"):
            parts.append(f"<p><a href='{e(b['index'])}'>open the bake-off page</a></p>")
        if b.get("strip"):
            parts.append(f"<img class=strip src='{e(b['strip'])}'>")
        if b["sec_by_ckpt"]:
            parts.append("<table><tr><th>checkpoint</th><th>renders</th><th>median s</th><th>max s</th></tr>" + "".join(
                f"<tr><td>{e(k)}</td><td>{v['n']}</td><td>{v['median']}</td><td>{v['max']}</td></tr>" for k, v in b["sec_by_ckpt"].items()) + "</table>")
        if b["causes"]:
            parts.append("<p><b style='color:#ff9a9a'>Failures by cause</b></p><ul>" + "".join(
                f"<li>×{n} <code>{e(cz)}</code></li>" for cz, n in b["causes"]) + "</ul>")
            parts.append("<details><summary>failed cells</summary><ul>" + "".join(
                f"<li>{e(str(f['name']))} <small style='color:#888'>{e(f['id'])}</small></li>" for f in b["failed"]) + "</ul></details>")
    if rep["slowest"]:
        parts.append("<h2>Slowest renders</h2><table>" + "".join(
            f"<tr><td>{s['seconds']} s</td><td>{e(str(s['name']))}</td><td>{e(str(s['batch']))}</td></tr>" for s in rep["slowest"]) + "</table>")
    if rep["models"]:
        parts.append("<h2>Models used</h2><table>" + "".join(
            f"<tr><td><span class=lic style='background:{LIC_COLOUR[m['licence']]}'></span>{e(m['file'])}</td><td>{e(m['license'])}</td><td>{m['uses']} jobs</td></tr>"
            for m in rep["models"]) + "</table><p style='color:#888'>green = commercial OK · red = not · grey = no licence on record "
            "(<code>licence.bat</code>)</p>")
    return "\n".join(parts)


def build(cfg: dict, since: datetime | None = None, until: datetime | None = None, hours: float | None = 12.0,
          everything: bool = False, now: datetime | None = None) -> tuple[Path, Path, dict]:
    jobs_dir, out_root = cfgmod.path_of(cfg, "jobs"), cfgmod.path_of(cfg, "out")
    now = now or datetime.now()
    if everything:
        since = until = None
    elif since is None and hours:
        since = now - timedelta(hours=float(hours))
    js = window(load_jobs(jobs_dir), since, until)
    rep = summarise(js, out_root, Licences(cfgmod.ROOT if (cfgmod.ROOT / "models").exists() else out_root.parent))
    stamp = (until or now).strftime("%Y-%m-%d")
    reports = out_root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    by_batch = defaultdict(list)
    for j in js:
        by_batch[str(j.get("batch") or "(no batch)")].append(j)
    for b in rep["batches"]:
        if b.get("only_waiting"):
            continue
        safe = re.sub(r"[^\w.-]+", "_", b["name"])
        sp = thumb_strip(out_root, by_batch[b["name"]], reports / f"night_{stamp}_{safe}.jpg")
        b["strip"] = sp.name if sp else None
    span = "everything on record" if everything else f"{(since.isoformat(timespec='minutes') if since else 'start')} → {(until or now).isoformat(timespec='minutes')}"
    title = f"The forge overnight — {span}"
    rep["title"], rep["since"], rep["until"] = title, since.isoformat() if since else None, (until or now).isoformat()
    md, ht = reports / f"night_{stamp}.md", reports / f"night_{stamp}.html"
    md.write_text(to_markdown(rep, title), encoding="utf-8")
    ht.write_text(to_html(rep, title, reports), encoding="utf-8")
    (reports / f"night_{stamp}.json").write_text(json.dumps(rep, indent=1, default=str), encoding="utf-8")
    return ht, md, rep


def latest(cfg: dict) -> Path | None:
    r = cfgmod.path_of(cfg, "out") / "reports"
    hs = sorted(r.glob("night_*.html")) if r.exists() else []
    return hs[-1] if hs else None
