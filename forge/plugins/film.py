"""The film job types (BUILD 43): `beat_map` (a song's beats, bars, tempo, loudness and moments, with its picture) and
`film_encode` (rendered frames and a song into a film file). Both on the processor. A plug-in, so a running worker learns
them without a restart; the work is forge/film/."""
from __future__ import annotations

from pathlib import Path

DEPENDS = ("forge.film.beatmap", "forge.film.encode")


def beat_map(job: dict, ctx, out_dir) -> dict:
    from ..film import beatmap
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    src = Path(job["track"])
    if not src.exists():
        raise RuntimeError(f"the track is not at {src}")
    bm = beatmap.analyse(src, meter=int(job.get("meter") or 4), bpm_hint=job.get("bpm_hint"), sections=job.get("sections"))
    dst = Path(job.get("out") or out / (src.stem + ".beats.json"))
    beatmap.write(bm, dst)
    beatmap.draw(beatmap.read(dst), dst.with_suffix(".png"), audio=src)
    return {"outputs": [str(dst), str(dst.with_suffix(".png"))], "bpm": bm["tempo"]["median_bpm"], "bars": len(bm["bars"])}


def film_encode(job: dict, ctx, out_dir) -> dict:
    from ..film import encode
    out = Path(job.get("out") or Path(out_dir) / "film.mp4")
    r = encode.frames_to_film(job["frames"], out, job.get("audio"), int(job.get("fps") or 24), float(job.get("audio_from") or 0.0),
                              job.get("audio_to"), job.get("mode") or "preview", bool(job.get("muffled")))
    if not r.get("ok"):
        raise RuntimeError(r.get("error") or "ffmpeg made nothing")
    return {"outputs": [str(out)], "bytes": r["bytes"]}


JOB_TYPES = {
    "beat_map": {"needs": "cpu", "doc": "BUILD 43: a song → its beat map (beats, bars, local tempo, loudness, silences, hits, held "
                                        "notes, sections) as <name>.beats.json and a picture over the waveform. A person's "
                                        "'by_hand' corrections in an existing file are kept.",
                 "required": ["track"], "optional": {"meter": 4, "bpm_hint": None, "sections": None, "out": None}},
    "film_encode": {"needs": "cpu", "doc": "BUILD 43: numbered PNG frames (and a song window) → an H.264 film; mode preview "
                                           "(quick) or final (YouTube's upload settings); muffled = heard through a door.",
                    "required": ["frames"], "optional": {"out": None, "audio": None, "fps": 24, "audio_from": 0.0,
                                                         "audio_to": None, "mode": "preview", "muffled": False}},
}
HANDLERS = {"beat_map": beat_map, "film_encode": film_encode}
