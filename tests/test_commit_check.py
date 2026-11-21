"""forge/commit_check.py: a commit message that names a game is caught; a game-free one passes."""
from forge.commit_check import check

WORDS = {"Harbor Hollow": "a place", "Harbor_Hollow": "a place", "games/iron_coast": "its folder", "Wren": "a person"}


def test_catches_names_and_paths_in_either_slash_direction():
    msg = "## The dresser\n- a fix for Harbor Hollow's street\n- games\\iron_coast\\places\\x.json\n- harbor_hollow ids"
    lines = sorted({n for n, _w, _why in check(msg, WORDS)})
    assert lines == [2, 3, 4]


def test_whole_words_only_and_game_free_passes():
    assert check("## The dresser on shops and lots\n- Wrenches are props now", WORDS) == []
