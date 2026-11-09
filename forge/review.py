"""Review sheets as a command (roadmap F8): labelled grids + an index.html that exports ratings.json — no server.

    python -m forge review <suite-or-batch> [--by category|model|type] [--thumb 256]
    python -m forge rate <suite-or-batch> --import ratings.json        (the file the page's Export button saved)

A target is a bake-off suite name (batch "bakeoff/<suite>") or any batch name. Output: out/review/<target>/
sheet_<group>_NN.png (labelled grids, at most 24 cells a page) and index.html (cards grouped the same way, a 1–5
radio row and a note per card, borders coloured by licence: green = every model commercial-OK, red = a
non-commercial model, grey = unknown). The page remembers nothing; "Export ratings" downloads a JSON file, and
`rate --import` merges it — into the bake-off's own ratings.json for a suite, else out/review/<target>/ratings.json.
"""
from __future__ import annotations
import html, json, re
from datetime import datetime
from pathlib import Path

from PIL import Image

from . import config as cfgmod
from .ops import sheet as sh


def safe(name: str) -> str:
    return re.sub(r"[^\w.\-]+", "_", name).strip("_") or "review"


def collect(cfg: dict, target: str) -> list[dict]:
    jobs, out = cfgmod.path_of(cfg, "jobs"), cfgmod.path_of(cfg, "out")
    wanted = {target, f"bakeoff/{target}"}
    rows = []
    for state in ("done", "failed"):
        for p in sorted((jobs / state).glob("*.json")):
            try:
                j = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if j.get("tombstone") or j.get("batch") not in wanted:
                continue
            d = out / j["id"]
            prov = {}
            if (d / "prov.json").exists():
                try:
                    prov = json.loads((d / "prov.json").read_text(encoding="utf-8"))
                except ValueError:
                    pass
            outs = (j.get("result") or {}).get("outputs") or []
            imgs = [d / o for o in outs if str(o).lower().endswith(".png") and (d / o).exists()]
            meta = j.get("meta") or {}
            rows.append({"id": j["id"], "state": state, "type": j.get("type"), "name": j.get("name"), "error": j.get("error"),
                         "images": imgs, "meta": meta, "checkpoint": meta.get("checkpoint") or prov.get("checkpoint") or "",
                         "lora": meta.get("lora") or ", ".join(l.get("name", "") for l in prov.get("loras") or []),
                         "category": meta.get("category") or j.get("type"), "prompt_id": meta.get("prompt_id") or j.get("name"),
                         "commercial_ok": prov.get("commercial_ok")})
    return rows


def group_key(r: dict, by: str) -> str:
    if by == "model":
        return Path(r["checkpoint"]).stem or "(unknown model)"
    if by == "type":
        return r["type"] or "?"
    return f"{r['category']}/{r['prompt_id']}" if r.get("meta") else (r["category"] or "?")


def label(r: dict, by: str) -> str:
    lo = Path(r["lora"]).stem if r["lora"] and "," not in r["lora"] else (r["lora"] or "no LoRA")
    if by == "model":
        return f"{r['prompt_id']} · {lo}"
    return f"{Path(r['checkpoint']).stem or r['name']} · {lo}"


def ratings_file(cfg: dict, target: str) -> Path:
    suite = cfgmod.path_of(cfg, "out") / "bakeoff" / target
    if suite.exists():
        return suite / "ratings.json"
    return cfgmod.path_of(cfg, "out") / "review" / safe(target) / "ratings.json"


def _detail_thumb(src: Path, det: dict, dest: Path, thumb: int) -> None:
    """The 1:1 detail crop (N9d) — the same crop the bake-off report's detail sheets use."""
    from .bakeoff import detail_crop
    with Image.open(src) as im:
        c = detail_crop(im.convert("RGB"), det)
    c.thumbnail((thumb * 2, thumb * 2))
    c.save(dest, "JPEG", quality=88)


def build(cfg: dict, target: str, by: str = "category", thumb: int = 256) -> Path:
    rows = collect(cfg, target)
    if not rows:
        raise ValueError(f"no finished jobs in batch '{target}' or 'bakeoff/{target}'")
    from . import detail as dt
    dt.apply(target, rows)          # crops moved with `bakeoff report --detail-at/--detail-auto`
    out_dir = cfgmod.path_of(cfg, "out") / "review" / safe(target)
    tdir = out_dir / "thumbs"
    tdir.mkdir(parents=True, exist_ok=True)
    rf = ratings_file(cfg, target)
    ratings = json.loads(rf.read_text(encoding="utf-8")) if rf.exists() else {}
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(group_key(r, by), []).append(r)
    sheets = []
    cards_html = []
    for gname in sorted(groups):
        rs = sorted(groups[gname], key=lambda r: (r["checkpoint"], r["lora"], r["id"]))
        cells, labels = [], []
        for r in rs:
            if r["images"]:
                cells.append(Image.open(r["images"][0]).convert("RGB"))
            else:
                cells.append(Image.new("RGB", (thumb, thumb), (90, 20, 24)))
            labels.append(label(r, by) if r["images"] else f"FAILED: {(r['error'] or '')[:40]}")
        for page in range(0, len(cells), 24):
            sheet = sh.contact_sheet(cells[page:page + 24], labels[page:page + 24], cols=6, cell=(thumb, thumb),
                                     title=f"{target} · {gname}")
            name = f"sheet_{safe(gname)}_{page // 24 + 1:02d}.png"
            sheet.save(out_dir / name)
            sheets.append(name)
        cards = []
        for r in rs:
            tname = None
            if r["images"]:
                tname = f"thumbs/{r['id']}.jpg"
                im = Image.open(r["images"][0]).convert("RGB")
                im.thumbnail((thumb * 2, thumb * 2))
                im.save(out_dir / tname, "JPEG", quality=85)
            lic = "ok" if r["commercial_ok"] is True else ("nc" if r["commercial_ok"] is False else "unk")
            cur = ratings.get(r["id"], {})
            radios = "".join(
                f'<label><input type="radio" name="{r["id"]}" value="{v}"{" checked" if cur.get("score") == v else ""}>{v}</label>'
                for v in range(1, 6))
            img = (f'<a href="../../{r["id"]}/{html.escape(r["images"][0].name)}" target="_blank"><img src="{tname}" loading="lazy"></a>'
                   if tname else f'<div class="fail">{html.escape((r["error"] or "failed")[:200])}</div>')
            det = (r.get("meta") or {}).get("detail")
            if tname and isinstance(det, dict):
                dname = f"thumbs/{r['id']}_detail.jpg"
                try:
                    _detail_thumb(r["images"][0], det, out_dir / dname, thumb)
                    img += (f'<div class="det"><img src="{dname}" loading="lazy" title="1:1 detail crop at {det.get("at")}">'
                            f'<span>1:1 detail {int(det.get("size") or 512)} px</span></div>')
                except Exception:  # noqa: BLE001 — a missing crop must not stop the review page
                    pass
            cards.append(f'<div class="card {lic} t-{html.escape(str(r["type"]))}" data-id="{r["id"]}">{img}'
                         f'<div class="lab">{html.escape(label(r, by))}</div><div class="id">{r["id"]}</div>'
                         f'<div class="rate">{radios}</div><input class="note" placeholder="note" value="{html.escape(cur.get("note", ""))}"></div>')
        cards_html.append(f'<h2>{html.escape(gname)} <small>({len(rs)})</small></h2><div class="grid">{"".join(cards)}</div>')
    page = PAGE.replace("{{TITLE}}", html.escape(f"{target} — review by {by}")).replace("{{BODY}}", "".join(cards_html)) \
               .replace("{{TARGET}}", json.dumps(target)).replace("{{WHEN}}", datetime.now().strftime("%Y-%m-%d %H:%M"))
    (out_dir / "index.html").write_text(page, encoding="utf-8", newline="\n")
    return out_dir


def import_ratings(cfg: dict, target: str, path: str | Path) -> tuple[Path, int]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    data = data.get("ratings", data)
    rf = ratings_file(cfg, target)
    cur = json.loads(rf.read_text(encoding="utf-8")) if rf.exists() else {}
    n = 0
    for jid, v in data.items():
        if not isinstance(v, dict) or not v.get("score"):
            continue
        cur[jid] = {"score": int(v["score"]), "note": str(v.get("note") or ""), "when": datetime.now().isoformat(timespec="seconds")}
        n += 1
    rf.parent.mkdir(parents=True, exist_ok=True)
    rf.write_text(json.dumps(cur, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    return rf, n


PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>{{TITLE}}</title>
<style>
body{background:#16161a;color:#e8e4d8;font:14px/1.4 system-ui,Segoe UI,sans-serif;margin:0;padding:16px 20px 80px}
h1{font-size:20px;margin:0 0 4px}h2{font-size:16px;margin:28px 0 8px;color:#f0c674;border-bottom:1px solid #333}
small{color:#888;font-weight:normal}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}
.card{background:#202026;border:3px solid #555;border-radius:8px;padding:6px}.card.ok{border-color:#3fb950}
.card.nc{border-color:#f85149}.card.unk{border-color:#6e7681}.card img{width:100%;border-radius:4px;display:block}
.lab{font-weight:600;margin-top:4px;word-break:break-word}.id{color:#777;font-size:11px}.fail{height:180px;background:#4a1418;
padding:8px;font-size:12px;overflow:hidden}.rate label{margin-right:8px;cursor:pointer}.note{width:100%;box-sizing:border-box;
background:#111;color:#ddd;border:1px solid #333;border-radius:4px;padding:3px;margin-top:4px}
#bar{position:fixed;left:0;right:0;bottom:0;background:#0d0d10;border-top:1px solid #333;padding:10px 20px;display:flex;gap:16px;align-items:center}
button{background:#f0c674;color:#111;border:0;border-radius:6px;padding:8px 14px;font-weight:700;cursor:pointer}
.key span{display:inline-block;width:12px;height:12px;border-radius:3px;margin:0 4px 0 12px;vertical-align:middle}
.det{position:relative;margin-top:4px}.det span{position:absolute;left:4px;bottom:4px;background:rgba(0,0,0,.65);color:#f0c674;font-size:11px;padding:1px 5px;border-radius:3px}
</style></head><body>
<h1>{{TITLE}}</h1><div class="key">built {{WHEN}} · border = licence:<span style="background:#3fb950"></span>all commercial-OK
<span style="background:#f85149"></span>non-commercial model<span style="background:#6e7681"></span>unknown</div>
{{BODY}}
<div id="bar"><button onclick="exportRatings()">Export ratings.json</button><span id="count"></span>
<span style="color:#888">then: rate.bat {{TARGET}} (pick the downloaded file)</span></div>
<script>
const TARGET={{TARGET}};
function collect(){const out={};document.querySelectorAll('.card').forEach(c=>{const id=c.dataset.id;
const r=c.querySelector('input[type=radio]:checked');const note=c.querySelector('.note').value;
if(r){out[id]={score:parseInt(r.value),note:note};}});return out;}
function upd(){document.getElementById('count').textContent=Object.keys(collect()).length+' rated';}
document.addEventListener('change',upd);upd();
function exportRatings(){const blob=new Blob([JSON.stringify({target:TARGET,ratings:collect()},null,1)],{type:'application/json'});
const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='ratings_'+TARGET.replace(/[^\\w.-]+/g,'_')+'.json';a.click();}
</script></body></html>
"""
