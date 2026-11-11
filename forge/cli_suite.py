"""Suite commands (BUILD 01): the app, the journal, the identity, and the data round-trip check.

    python -m forge suite [--port 8770] [--no-browser]       the suite (forge.bat)
    python -m forge identity [name]                          who this install signs as (FORGE_IDENTITY overrides)
    python -m forge journal add <kind> [object] [--note "…"] [--who "<name>"] [--game <id>]
    python -m forge journal show [--game <id>] [--since 2026-11-10T00:00] [--limit 30]
    python -m forge suite-check [--game <id>]                every game (or one): its adapter's counts, and every data
                                                             file loaded and saved with no edit → identical bytes
    python -m forge mail list [--box inbox|sent|drafts|archive|all] [--unread]      the Mail (mail.bat) — as --who / the identity
    python -m forge mail read <id>                           the whole thread, open questions marked; marks it read
    python -m forge mail send --to "<name>" --subject "…" (--body "…" | --body-file f.md) [--questions q.json] [--attach path]
    python -m forge mail reply <id> (--body "…" | --body-file f.md) [--answers a.json]
    python -m forge orders add --for "<name>" --title "…" [--detail "…"] [--priority now|soon|someday] [--object <ref>]
    python -m forge orders list [--for "<name>"] [--all]      the work orders a session starts from
    python -m forge orders done <id> [--note "…"] [--drop]
    python -m forge away [--who "<name>"] [--since <time>] [--mark]   what everyone else did since <name> last worked
                                                             → journal/DIGEST_for_<group>.md; --mark starts a new session
    python -m forge music board [--state needed] [--singer Sarah]   the Music board: counts, next most useful, the slots
    python -m forge music propose <slot> --brief-file b.md [--style style-2|new] [--subject "…"]   a brief → a letter to the game's owner
    python -m forge music write <slot> --title "…" --file song.md [--note "…"]   a version of an agreed song (kept; never over)
    python -m forge music answer <slot> <yes|"yes, but…"|no|"I'll write this one"|"not yet"> [--note "…"]   (a person only)
    python -m forge music deliver <slot> --file track.ogg | --inbox name.ogg [--loop-start s] [--loop-end s] [--trim-db d]
    python -m forge music sheets | sheet <id>                the style sheets (profiles) and one of them as text
  Every command takes --game <id> (default: local/suite.json) and signs as --who / --from / --by, else FORGE_IDENTITY.
"""
from __future__ import annotations
import json, sys


def _opt(args: list[str], name: str, default=None):
    if name in args:
        i = args.index(name)
        if i + 1 < len(args):
            return args[i + 1]
    return default


def _pos(args: list[str], flags=("--port", "--note", "--who", "--game", "--since", "--limit")) -> list[str]:
    out, skip = [], False
    for a in args:
        if skip:
            skip = False
            continue
        if a in flags:
            skip = True
            continue
        if not a.startswith("--"):
            out.append(a)
    return out


def cmd_suite(cfg: dict, args: list[str]) -> int:
    from .suite import server
    return server.serve(cfg, int(_opt(args, "--port", server.PORT)), open_browser="--no-browser" not in args)


def cmd_identity(cfg: dict, args: list[str]) -> int:
    from .suite import settings
    pos = _pos(args)
    if pos:
        print(f"this install now signs as: {settings.set_identity(' '.join(pos))}")
    else:
        print(f"this install signs as: {settings.identity() or '(nobody yet — python -m forge identity <name>)'}")
    return 0


def cmd_journal(cfg: dict, args: list[str]) -> int:
    from . import config as cfgmod
    from .suite import games, journal, settings
    pos = _pos(args)
    if not pos or pos[0] not in ("add", "show"):
        print(__doc__)
        return 2
    gid = _opt(args, "--game") or cfgmod.default_game(cfg)
    root = games.game_root(cfg, gid)
    if not root or not root.is_dir():
        print(f"the game folder for '{gid}' is not reachable ({root})")
        return 1
    if pos[0] == "add":
        if len(pos) < 2:
            print("usage: journal add <kind> [object] [--note …] [--who …]")
            return 2
        who = _opt(args, "--who") or settings.identity()
        if not who:
            print("who is writing? pass --who \"<name>\" or set FORGE_IDENTITY")
            return 2
        e = journal.append(root, who, pos[1], pos[2] if len(pos) > 2 else None, note=_opt(args, "--note"))
        print(f"journal ({gid}): {e['time']} {e['who']} {e['kind']} {e.get('obj', '')}")
        return 0
    for e in journal.read(root, since=_opt(args, "--since"), limit=int(_opt(args, "--limit", 30))):
        extra = f" — {e['note']}" if e.get("note") else ""
        print(f"{e['time']}  {e['who']:<14} {e['kind']:<8} {e.get('obj', '')}{extra}")
    return 0


def cmd_suite_check(cfg: dict, args: list[str]) -> int:
    from .suite import games
    from .suite.jsondoc import JsonDoc
    want = _opt(args, "--game")
    bad_total = 0
    for gid in games.game_ids(cfg):
        if want and gid != want:
            continue
        if not games.has_adapter(cfg, gid):
            print(f"{gid}: no workbench_adapter.py — skipped")
            continue
        a = games.adapter(cfg, gid)
        s = a.summary()
        if not s["root_exists"]:
            print(f"{gid}: game folder not reachable ({a.root}) — skipped")
            continue
        n, bad = 0, []
        for rel in a.data_files():
            raw = a.path(rel).read_bytes()
            doc = a.read_doc(rel)
            n += 1
            if doc.to_bytes() != raw:
                bad.append(rel)
            elif isinstance(doc, JsonDoc) and doc.value != json.loads(raw.decode("utf-8-sig")):
                bad.append(rel + " (values differ)")
        bad_total += len(bad)
        counts = ", ".join(f"{k} {s[k]['count']}" for k in ("places", "lines", "quests", "music_slots", "people") if k in s)
        print(f"{gid} ({s['name']}): {counts}; {n} data files round-trip {'byte-identical' if not bad else 'with differences'}")
        for b in bad[:20]:
            print(f"   DIFFERS: {b}")
        for e in s["errors"]:
            print(f"   PROBLEM: {e}")
    return 1 if bad_total else 0


def _args(args: list[str]) -> tuple[list[str], dict]:
    """Positional words and --flags (a flag followed by a non-flag takes it as its value; --attach repeats)."""
    pos, opts, i = [], {}, 0
    while i < len(args):
        a = args[i]
        if a.startswith("--"):
            k = a[2:]
            if i + 1 < len(args) and not args[i + 1].startswith("--"):
                v = args[i + 1]
                i += 1
            else:
                v = True
            if k == "attach":
                opts.setdefault("attach", []).append(v)
            else:
                opts[k] = v
        else:
            pos.append(a)
        i += 1
    return pos, opts


def _game(cfg: dict, opts: dict):
    from . import config as cfgmod
    from .suite import games
    gid = opts.get("game") or cfgmod.default_game(cfg)
    root = games.game_root(cfg, gid)
    if not root or not root.is_dir():
        raise SystemExit(f"the game folder for '{gid}' is not reachable ({root})")
    adp = games.adapter(cfg, gid) if games.has_adapter(cfg, gid) else None
    return gid, root, adp


def _who(opts: dict, *keys) -> str:
    from .suite import settings
    for k in keys:
        if isinstance(opts.get(k), str):
            return opts[k]
    w = settings.identity()
    if not w:
        raise SystemExit("who is this? pass --who \"<name>\" (or --from / --by), or set FORGE_IDENTITY")
    return w


def _body(opts: dict) -> str:
    if isinstance(opts.get("body-file"), str):
        from pathlib import Path
        return Path(opts["body-file"]).read_text(encoding="utf-8")
    return str(opts.get("body") or "") if opts.get("body") is not True else ""


def _json_file(opts: dict, key: str):
    if isinstance(opts.get(key), str):
        from pathlib import Path
        return json.loads(Path(opts[key]).read_text(encoding="utf-8"))
    return None


def cmd_mail(cfg: dict, args: list[str]) -> int:
    from .suite import mail
    pos, opts = _args(args)
    if not pos or pos[0] not in ("list", "read", "send", "reply"):
        print(__doc__)
        return 2
    gid, root, adp = _game(cfg, opts)
    if pos[0] == "list":
        who = _who(opts, "who")
        rows = mail.box(root, who, str(opts.get("box") or "inbox"), query=opts.get("search") if isinstance(opts.get("search"), str) else None)
        if opts.get("unread"):
            rows = [r for r in rows if r["unread"]]
        print(f"{gid} — {opts.get('box') or 'inbox'} of {who}: {len(rows)} letter(s)")
        for r in rows:
            mark = "●" if r["unread"] else " "
            qs = f"  [{r['open_questions']} open question(s)]" if r["open_questions"] else ""
            print(f" {mark} {r['date'][:16].replace('T', ' ')}  {r['from']:<14} {r['subject']}{qs}\n      {r['id']}")
        return 0
    if pos[0] == "read":
        if len(pos) < 2:
            print("usage: mail read <id>")
            return 2
        who = _who(opts, "who")
        v = mail.thread_view(root, pos[1], who)
        print(f"# {v['subject']}  ({v['open_questions']} open question(s) on this thread)\n")
        for l in v["letters"]:
            print(f"--- {l['date'].replace('T', ' ')}  {l['from']} → {l['to']}  [{l['id']}]")
            print(l["body"], "\n")
            for q in l["questions"]:
                st = ("ANSWERED: " + str(q["answer"].get("choice") or q["answer"].get("text"))) if q["answer"] else ("PARKED (" + q["parked"] + ")" if q["parked"] else "OPEN")
                print(f"  ? {q['id']}: {q['question']}  — {st}")
                if q.get("recommendation"):
                    print(f"      recommends: {q['recommendation']}")
            for a in l["answers"]:
                print(f"  ✓ {a.get('id')}: {a.get('choice') if a.get('choice') is not None else a.get('text')}" +
                      (f"  [{a['applied']['message']}]" if a.get("applied") else ""))
            if l["folder"] == mail.folder_for(who):
                mail.mark_read(root, who, l["id"])
        return 0
    if pos[0] == "send":
        frm = _who(opts, "from", "who")
        if not isinstance(opts.get("to"), str) or not isinstance(opts.get("subject"), str):
            print("usage: mail send --to \"<name>\" --subject \"…\" (--body … | --body-file …)")
            return 2
        l = mail.send(root, frm, opts["to"], opts["subject"], _body(opts), questions=_json_file(opts, "questions"),
                      attachments=opts.get("attach"))
        print(f"sent: mail/{l.folder}/{l.id}.md")
        return 0
    if len(pos) < 2:
        print("usage: mail reply <id> (--body … | --body-file …) [--answers a.json]")
        return 2
    frm = _who(opts, "from", "who")
    l = mail.reply(root, pos[1], frm, _body(opts), answers=_json_file(opts, "answers"), adp=adp)
    print(f"sent: mail/{l.folder}/{l.id}.md")
    for a in l.answers:
        if a.get("applied"):
            print(f"  {a['id']}: {a['applied']['message']}")
    return 0


def cmd_orders(cfg: dict, args: list[str]) -> int:
    from .suite import orders
    pos, opts = _args(args)
    if not pos or pos[0] not in ("add", "list", "done"):
        print(__doc__)
        return 2
    gid, root, _adp = _game(cfg, opts)
    if pos[0] == "add":
        o = orders.add(root, _who(opts, "by", "who"), str(opts.get("for") or ""), str(opts.get("title") or ""),
                       detail=str(opts.get("detail") or "") if opts.get("detail") is not True else "",
                       priority=str(opts.get("priority") or "soon"), obj=opts.get("object") if isinstance(opts.get("object"), str) else None)
        print(f"work order for {o['for']} ({o['priority']}): {o['title']}  [{o['id']}]")
        return 0
    if pos[0] == "list":
        rows = orders.listing(root, opts.get("for") if isinstance(opts.get("for"), str) else None, None if opts.get("all") else "open")
        print(f"{gid} — work orders{' for ' + opts['for'] if isinstance(opts.get('for'), str) else ''}: {len(rows)}")
        for o in rows:
            print(f"  [{o['priority']:<7}] {o['title']}  — for {o['for']}, from {o['by']} {o['created'][:16].replace('T', ' ')}"
                  + (f"  ({o['status']})" if o['status'] != 'open' else "") + f"\n             {o['id']}" + (f"  · about {o['object']}" if o.get('object') else ""))
            if o.get("detail"):
                print(f"             {o['detail']}")
        return 0
    if len(pos) < 2:
        print("usage: orders done <id> [--note …] [--drop]")
        return 2
    o = orders.close(root, pos[1], _who(opts, "who", "by"), note=str(opts.get("note") or "") if opts.get("note") is not True else "",
                     status="dropped" if opts.get("drop") else "done")
    print(f"{o['status']}: {o['title']}")
    return 0


def cmd_away(cfg: dict, args: list[str]) -> int:
    from .suite import away, journal
    _pos2, opts = _args(args)
    gid, root, _adp = _game(cfg, opts)
    who = _who(opts, "who")
    p, d = away.write(root, who, opts.get("since") if isinstance(opts.get("since"), str) else None)
    print(away.markdown(d))
    print(f"(written to {p})")
    if opts.get("mark"):
        journal.append(root, who, "session", "start", note="read the digest; working from here")
    return 0



def cmd_music(cfg: dict, args: list[str]) -> int:
    from pathlib import Path
    from .suite import music
    pos, opts = _args(args)
    if not pos or pos[0] not in ("board", "propose", "write", "answer", "deliver", "sheets", "sheet"):
        print(__doc__)
        return 2
    gid, root, adp = _game(cfg, opts)
    if adp is None:
        raise SystemExit(f"{gid} has no Story adapter — the Music board reads its slots through it")
    num = lambda k: float(opts[k]) if isinstance(opts.get(k), str) else None
    try:
        if pos[0] == "board":
            b = music.board(adp)
            c = b["counts"]
            print(f"{gid} — " + " · ".join(f"{k} {c[k]}" for k in music.STATES) + f" · the owner's own {c['own']} · inherits {c['inherits']}")
            print("next most useful:")
            for r in b["next"]:
                print(f"  {r['id']}  — {r['why']}")
            for s in b["slots"]:
                if isinstance(opts.get("state"), str) and s["state"] != opts["state"]:
                    continue
                names = [g.get("name") for g in s.get("singers") or []]
                if isinstance(opts.get("singer"), str) and opts["singer"] not in names:
                    continue
                print(f"  [{s['state']:<9}] {s['id']}  — {s.get('scene') or ''}" + (f"  ({', '.join(n for n in names if n)})" if names else "")
                      + ("  [the owner's own]" if s.get("own") else "") + (f"  [shares {s['via']}]" if s.get("via") else ""))
            for f in b["inbox"]:
                g = f["guess"]
                print(f"  inbox: {f['name']}" + (f" → delivered to {f['delivered_to']}" if f["delivered_to"] else (f" → looks like {g['id']} ({g['score']})" if g else "")))
            return 0
        if pos[0] == "sheets":
            for s in music.sheets(adp):
                print(f"  {s['id']:<24} {s['name']:<28} styles {s['styles']} · songs {s['songs']} · open {s['open']}")
            return 0
        if pos[0] == "sheet":
            print(music.render_sheet(music.sheet(adp, pos[1])))
            return 0
        if len(pos) < 2:
            print(__doc__)
            return 2
        sid = pos[1]
        who = _who(opts, "who", "by")
        if pos[0] == "propose":
            r = music.propose(adp, sid, who, Path(opts["brief-file"]).read_text(encoding="utf-8") if isinstance(opts.get("brief-file"), str) else _body(opts),
                              style=opts.get("style") if isinstance(opts.get("style"), str) else None,
                              subject=opts.get("subject") if isinstance(opts.get("subject"), str) else None)
        elif pos[0] == "write":
            r = music.write_song(adp, sid, who, str(opts.get("title") or ""), Path(opts["file"]).read_text(encoding="utf-8"),
                                 note=opts.get("note") if isinstance(opts.get("note"), str) else "")
        elif pos[0] == "answer":
            r = music.answer(adp, sid, who, pos[2] if len(pos) > 2 else "", opts.get("note") if isinstance(opts.get("note"), str) else "")
        else:
            if isinstance(opts.get("inbox"), str):
                r = music.deliver(adp, sid, who, inbox_name=opts["inbox"], loop_start=num("loop-start"), loop_end=num("loop-end"), trim_db=num("trim-db"))
            else:
                f = Path(opts["file"])
                r = music.deliver(adp, sid, who, data=f.read_bytes(), filename=f.name, loop_start=num("loop-start"), loop_end=num("loop-end"), trim_db=num("trim-db"))
        print(r["message"])
        return 0
    except music.MusicRefused as e:
        print(f"refused: {e}")
        return 1

COMMANDS = {"suite": cmd_suite, "identity": cmd_identity, "journal": cmd_journal, "suite-check": cmd_suite_check,
            "mail": cmd_mail, "orders": cmd_orders, "away": cmd_away, "music": cmd_music}
