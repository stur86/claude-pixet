import pytest
from PIL import Image

from pixet.canvas import Canvas, CanvasError, parse_color


def pix(c: Canvas) -> list[str]:
    """Canvas as rows of hex digits, for easy comparison."""
    return ["".join(f"{c.get(x, y):x}" for x in range(c.width)) for y in range(c.height)]


def test_parse_color():
    assert parse_color("#fff") == (255, 255, 255, 255)
    assert parse_color("#11223344") == (0x11, 0x22, 0x33, 0x44)
    with pytest.raises(CanvasError):
        parse_color("#12345")


def test_line_and_rect():
    c = Canvas(5, 5)
    c.draw_line(0, 0, 4, 4, 1)
    assert [c.get(i, i) for i in range(5)] == [1] * 5
    c.new_image(4, 3)
    c.draw_rect(0, 0, 4, 3, 2)
    assert pix(c) == ["2222", "2002", "2222"]
    c.draw_rect(1, 1, 10, 10, 3, filled=True)  # clipped
    assert pix(c) == ["2222", "2333", "2333"]


def test_circle_symmetric():
    c = Canvas(7, 7)
    c.draw_circle(3, 3, 3, 1, filled=True)
    rows = pix(c)
    assert rows == rows[::-1]
    assert all(r == r[::-1] for r in rows)
    assert rows[3] == "1111111"


def test_flood_fill_region():
    c = Canvas(5, 5)
    c.draw_line(2, 0, 2, 4, 1)
    assert c.flood_fill(0, 0, 3) == 10
    assert pix(c)[0] == "33100"


def test_flood_fill_dither():
    c = Canvas(4, 4)
    c.flood_fill(0, 0, 1, dither="checker", color2=2)
    assert pix(c)[:2] == ["1212", "2121"]
    c.new_image(4, 4)
    c.flood_fill(0, 0, 1, dither="bayer", color2=2, density=0.25)
    assert sum(r.count("1") for r in pix(c)) == 4
    with pytest.raises(CanvasError):
        c.flood_fill(0, 0, 1, dither="checker")


def test_palette_and_undo():
    c = Canvas(2, 2)
    c.set_pixels([(0, 0)], 5)
    with pytest.raises(CanvasError):
        c.set_palette(["#000", "#fff"])  # index 5 in use
    c.undo()
    c.set_palette(["#000", "#fff"])
    with pytest.raises(CanvasError):
        c.set_pixels([(0, 0)], 2)
    assert c.undo() and len(c.palette) == 17


def test_output(tmp_path):
    c = Canvas(8, 4)
    c.draw_rect(0, 0, 2, 2, 8, filled=True)
    assert c.render_preview(grid=True)[:4] == b"\x89PNG"
    c.save(str(tmp_path / "a.png"), scale=2)
    img = Image.open(tmp_path / "a.png")
    assert img.size == (16, 8)
    assert img.getpixel((0, 0)) == (255, 0, 77, 255)
    assert img.getpixel((15, 7))[3] == 0


def test_png_round_trip_keeps_unused_palette(tmp_path):
    c = Canvas(3, 2)
    c.set_palette(["#00000000", "#ff0000", "#00ff0080", "#123456"])  # 3 is unused
    c.set_pixels([(0, 0)], 1)
    c.set_pixels([(2, 1)], 2)
    c.write_png(str(tmp_path / "a.png"))
    d = Canvas()
    d.read_png(str(tmp_path / "a.png"))
    assert (d.width, d.height) == (3, 2)
    assert pix(d) == pix(c)
    assert d.palette == c.palette


def test_read_png_rejects_rgba(tmp_path):
    Image.new("RGBA", (2, 2)).save(tmp_path / "a.png")
    with pytest.raises(CanvasError):
        Canvas().read_png(str(tmp_path / "a.png"))
