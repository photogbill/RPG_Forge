"""The licence gate (BUILD 71 part 4): before any voice tool is installed, its code, its weights and whatever they bundle
are each on the add-on rule's list — or say in words that a sold game may use them and what they make. Non-commercial,
research-only or "by permission" is never installed, however good."""
from __future__ import annotations

ALLOWED = ("mit", "bsd", "apache-2.0", "apache 2.0", "apache", "zlib", "cc0", "isc", "mpl-2.0")
REFUSED = ("non-commercial", "noncommercial", "nc", "cc-by-nc", "research", "by permission", "coqui public model license",
           "cpml", "flux non-commercial")


def gate(parts: dict) -> tuple[bool, list[str]]:
    """parts: {"code": "MIT", "weights": "Apache-2.0", "bundles": "..."} → (ok, reasons)."""
    why = []
    for k, v in parts.items():
        low = str(v or "").lower()
        if not low:
            why.append(f"{k}: no licence given — read it before installing")
        elif any(r in low.replace("_", "-") for r in REFUSED) and not any(a == low for a in ALLOWED):
            why.append(f"{k}: {v} — not for a sold game")
        elif not any(a in low for a in ALLOWED) and "commercial use" not in low:
            why.append(f"{k}: {v} — not on the list (MIT, BSD, Apache-2.0, zlib, CC0); write in words what a sold game may do")
    return (not why, why)
