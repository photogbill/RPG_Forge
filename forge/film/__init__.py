"""Filming a set piece to its music — game-neutral (BUILD 43).

    beatmap    a song's beats, bars, local tempo, loudness, silences, hits and held notes, written as a file a person can
               correct (by-hand fields survive a re-run), and drawn over the waveform as a picture
    conductor  a conductor's hands made from a beat map: the standard patterns, the ictus a little before the sound, the
               size following the loudness, the left hand's cues and cut-offs, and his acting beats on top
    cuesheet   one number of a filmed set piece as data: marks, moves, paths, cameras, sounds and props on the song's clock;
               checked (marks exist, moves exist, nobody lands a blow, a throw's top lands on a strong beat) and resolved to
               seconds for the renderer
    encode     the rendered frames and the song into an upload file (ffmpeg)

Nothing here names a game: a game's cue sheets, marks and casts live in the game's own folders and are handed in.
The Blender half is `forge/threed/blender/cue_render.py` and `key_conductor.py`; the job types are `forge/plugins/film.py`.
"""
