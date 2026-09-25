"""MCP server that exposes a stateful indexed-color pixel art editor."""

from __future__ import annotations

from pathlib import Path

from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from .canvas import CanvasError, format_color
from .document import Document

mcp = MCPServer(
    "pixet",
    instructions=(
        "Pixel art editor that works on one PNG file on disk. All colors are palette "
        "indices. Coordinates start at (0, 0) in the top-left corner. "
        "Typical flow: new_image(path) -> set_palette -> draw -> get_image to look at "
        "the result -> fix and repeat. Every change is saved to the file at once; "
        "save_image only exports a scaled copy. Shapes are clipped to the canvas. "
        "Use undo to revert the last change."
    ),
)

doc = Document()


def _run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except CanvasError as e:
        raise ToolError(str(e)) from None


def _edit(method: str, *args):
    """Read the file, apply a canvas method, write the file back."""
    canvas = _run(doc.load)
    result = _run(getattr(canvas, method), *args)
    doc.commit()
    return result


def _palette_text() -> str:
    return ", ".join(f"{i}={format_color(c)}" for i, c in enumerate(doc.canvas.palette))


def _frame_text() -> str:
    return f" Frame {doc.frame_path(doc.frame).name}." if doc.record else ""


@mcp.tool()
def new_image(
    path: str, width: int, height: int, background: int = 0, record_frames: bool = False
) -> str:
    """Start a new blank image at `path` (a .png file), filled with palette index `background`.

    The file is overwritten if it exists. From now on, every change is written to
    this file at once, so it can be watched in an image viewer.
    If `record_frames` is true, every change also saves a numbered copy next to
    the file (name_0001.png, name_0002.png, ...) to replay the process. Old
    frames with the same name are deleted first.
    The palette stays the same. The default palette is PICO-8 with index 0
    transparent and index 16 black.
    """
    p = _run(doc.new, path, width, height, background, record_frames)
    return f"New {width}x{height} image at {p}.{_frame_text()} Palette: {_palette_text()}"


@mcp.tool()
def set_palette(colors: list[str]) -> str:
    """Replace the palette. `colors` is a list of hex strings.

    Formats: '#RRGGBB', '#RRGGBBAA', '#RGB' or '#RGBA'. Use alpha 00 for
    transparent (for example '#00000000'). Index i in the list is color index i.
    Existing pixels keep their indices, so they change color to match.
    """
    _edit("set_palette", colors)
    return f"Palette set: {_palette_text()}"


@mcp.tool()
def get_palette() -> str:
    """Show the current palette as index=color pairs."""
    _run(doc.load)
    return _palette_text()


@mcp.tool()
def set_pixel(x: int, y: int, color: int) -> str:
    """Set one pixel to palette index `color`."""
    _run(_run(doc.load).get, x, y)  # bounds check
    _edit("set_pixels", [(x, y)], color)
    return f"Set ({x}, {y}) to {color}"


@mcp.tool()
def set_pixels(points: list[tuple[int, int]], color: int) -> str:
    """Set many pixels to palette index `color`. `points` is a list of [x, y] pairs.

    Use this instead of many set_pixel calls. Out-of-bounds points are skipped.
    """
    n = _edit("set_pixels", [tuple(p) for p in points], color)
    return f"Set {n} pixels to {color}"


@mcp.tool()
def draw_line(x0: int, y0: int, x1: int, y1: int, color: int) -> str:
    """Draw a 1-pixel line from (x0, y0) to (x1, y1), both ends included."""
    n = _edit("draw_line", x0, y0, x1, y1, color)
    return f"Line drew {n} pixels"


@mcp.tool()
def draw_rect(
    x: int, y: int, width: int, height: int, color: int, filled: bool = False
) -> str:
    """Draw a rectangle with its top-left corner at (x, y).

    If `filled` is false, only the 1-pixel border is drawn.
    """
    n = _edit("draw_rect", x, y, width, height, color, filled)
    return f"Rect drew {n} pixels"


@mcp.tool()
def draw_circle(cx: int, cy: int, radius: int, color: int, filled: bool = False) -> str:
    """Draw a circle centered on (cx, cy). Diameter is 2*radius + 1 pixels.

    If `filled` is false, only the 1-pixel outline is drawn.
    """
    n = _edit("draw_circle", cx, cy, radius, color, filled)
    return f"Circle drew {n} pixels"


@mcp.tool()
def flood_fill(
    x: int,
    y: int,
    color: int,
    dither: str = "none",
    color2: int | None = None,
    density: float = 0.5,
) -> str:
    """Fill the 4-connected area that has the same color as (x, y).

    Dither options (all need `color2`, the second color):
    - "none": solid fill with `color`.
    - "checker": 50/50 checkerboard of `color` and `color2`.
    - "bayer": ordered 4x4 Bayer dither. `density` (0..1) is the fraction
      of `color`; the rest is `color2`. Good for gradients made of bands.
    - "hlines" / "vlines": alternating horizontal / vertical lines.
    - "diagonal": sparse diagonal lines of `color` on `color2`.
    Patterns use absolute coordinates, so adjacent fills line up.
    """
    n = _edit("flood_fill", x, y, color, dither, color2, density)
    return f"Filled {n} pixels"


@mcp.tool()
def undo() -> str:
    """Revert the last change (up to 50 steps)."""
    if not _run(doc.load).undo():
        return "Nothing to undo"
    doc.commit()
    return "Undone"


@mcp.tool()
def get_image(scale: int | None = None, grid: bool = False) -> list:
    """Return the image as a PNG so you can look at it.

    The preview is scaled up with nearest-neighbor (auto: about 512 px on
    the long side). Transparent pixels show as a gray checkerboard.
    Set `grid` to true to draw pixel grid lines (solid every 8 pixels),
    which helps to read coordinates.
    """
    canvas = _run(doc.load)
    png = _run(canvas.render_preview, scale, grid)
    return [
        Image(data=png, format="png"),
        f"{canvas.width}x{canvas.height}. Palette: {_palette_text()}",
    ]


@mcp.tool()
def save_image(path: str, scale: int = 1) -> str:
    """Export a copy of the image as a true-color PNG with real transparency.

    The working file is already saved after every change; use this for a
    scaled-up copy or a copy at another path. `scale` multiplies the size with
    nearest-neighbor scaling.
    """
    p = Path(path).expanduser().resolve()
    if p.suffix.lower() != ".png":
        raise ToolError("Path must end in .png")
    p.parent.mkdir(parents=True, exist_ok=True)
    _run(_run(doc.load).save, str(p), scale)
    return f"Saved {p}"


def main() -> None:
    mcp.run()
