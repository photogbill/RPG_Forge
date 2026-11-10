"""G12: nine-slice margins found on a synthetic frame, snapped to ×3; the preview never stretches a corner; states."""
import numpy as np
from PIL import Image, ImageDraw

from forge.ops import ui_pieces as ui


def frame(w=240, h=150, border=21):
    im = Image.new("RGBA", (w, h), (60, 50, 40, 255))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, w - 1, h - 1], outline=(220, 180, 90, 255), width=border)
    for c in ((0, 0), (w - border, 0), (0, h - border), (w - border, h - border)):     # ornamented corners
        d.ellipse([c[0] + 4, c[1] + 4, c[0] + border - 4, c[1] + border - 4], fill=(240, 60, 60, 255))
    return im


def test_margins_detected_and_snapped():
    piece, m, rep = ui.nine_slice(frame(), tileable=False)
    assert m == {"left": 21, "top": 21, "right": 21, "bottom": 21}                   # 21 is already a multiple of 3
    _, m2, _ = ui.nine_slice(frame(border=20), tileable=False)
    assert all(v == 21 for v in m2.values())                                          # 20 → snapped up to 21
    assert rep["godot"]["patch_margin_left"] == 21 and rep["size"] == [240, 150]
    _, m3, r3 = ui.nine_slice(frame(), margins={"left": 30, "top": 9, "right": 30, "bottom": 9})
    assert m3 == {"left": 30, "top": 9, "right": 30, "bottom": 9} and r3["detected"] is False


def test_preview_keeps_corners_1to1_and_states():
    piece, m, _ = ui.nine_slice(frame())
    for size in ((500, 120), (300, 400)):
        big = np.asarray(ui.draw_nine(piece, m, size))
        src = np.asarray(piece)
        L, T = m["left"], m["top"]
        assert np.array_equal(big[:T, :L], src[:T, :L])                               # top-left corner untouched
        assert np.array_equal(big[-T:, -L:], src[-T:, -L:])                           # bottom-right corner untouched
    assert ui.stretch_preview(piece, m).width > piece.width * 3
    st = ui.button_states(frame(90, 40, 12))
    assert set(st) == {"normal", "hover", "pressed", "disabled"}
    lum = {k: np.asarray(v.convert("L")).mean() for k, v in st.items()}
    assert lum["hover"] > lum["normal"] > lum["pressed"]
    assert np.asarray(st["disabled"])[..., 3].max() < 255
