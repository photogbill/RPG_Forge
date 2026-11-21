"""concur.bat — William gives his OK for the assistants that need it (Opus, 2026-11-20).

William, 2026-11-20 23:08-23:10: "add Opus to the approval list, but only if i give concurrence" -> "Opus approvals need
my OK". Running this opens a 30-minute window in which the assistants named under "assistants_with_concurrence" in the
game's approvals.json may approve and deliver, signed "<assistant>, for William (concurred hh:mm)".
  concur.bat           open it (asks y/n)
  concur.bat close     close it now
  concur.bat status    show whether one is live
"""
from __future__ import annotations

import sys

from . import config as cfgmod
from .suite import approve_all


def main(argv: list[str]) -> int:
    cfg = cfgmod.load()
    gid = cfgmod.default_game(cfg)
    names = approve_all._concur_names(cfg, gid)
    cmd = (argv[0].lower() if argv else "open")
    if cmd == "status":
        c = approve_all.concurrence(cfg, gid)
        print(f"{gid}: " + (f"concurrence live until {c['until'][11:16]} for {', '.join(c['for'])}" if c else "no concurrence live"))
        return 0
    if cmd == "close":
        approve_all.close_concurrence(cfg, gid)
        print(f"{gid}: concurrence closed — {', '.join(names) or 'no one'} can't approve now.")
        return 0
    if not names:
        print(f"{gid}: no assistant needs your concurrence (approvals.json names none)."); return 0
    a = input(f"Let {', '.join(names)} approve and deliver on {gid} for the next "
              f"{approve_all.CONCUR_MINUTES} minutes? (y/n): ").strip().lower()
    if a not in ("y", "yes"):
        print("Nothing opened."); return 0
    c = approve_all.open_concurrence(cfg, gid, "William")
    print(f"Done. {', '.join(c['for'])} may approve until {c['until'][11:16]}. concur.bat close ends it sooner.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
