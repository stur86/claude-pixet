"""Stateful indexed-color pixel canvas.

All drawing uses palette indices. Shapes are clipped to the canvas bounds.
"""

from __future__ import annotations

import io
from collections import deque
from collections.abc import Iterable

from PIL import Image as PILImage

RGBA = tuple[int, int, int, int]

MAX_SIZE = 1024
MAX_PALETTE = 256
MAX_UNDO = 50

# PICO-8 palette, with index 0 made transparent.
DEFAULT_PALETTE = [
    "#00000000", "#1d2b53", "#7e2553", "#008751",
    "#ab5236", "#5f574f", "#c2c3c7", "#fff1e8",
    "#ff004d", "#ffa300", "#ffec27", "#00e436",
    "#29adff", "#83769c", "#ff77a8", "#ffccaa",
    "#000000",
]

BAYER4 = [
    [0, 8, 2, 10],
    [12, 4, 14, 6],
    [3, 11, 1, 9],
    [15, 7, 13, 5],
]

DITHER_MODES = ("none", "checker", "bayer", "hlines", "vlines", "diagonal")


class CanvasError(ValueError):
    """Bad input from the caller."""


def parse_color(value: str) -> RGBA:
    """Parse '#RGB', '#RGBA', '#RRGGBB' or '#RRGGBBAA' into an RGBA tuple."""
    s = value.strip().lstrip("#")
    if len(s) in (3, 4):
        s = "".join(c * 2 for c in s)
    if len(s) == 6:
        s += "ff"
    if len(s) != 8:
        raise CanvasError(f"Bad color {value!r}: use #RRGGBB or #RRGGBBAA")
    try:
        r, g, b, a = (int(s[i : i + 2], 16) for i in range(0, 8, 2))
    except ValueError:
        raise CanvasError(f"Bad color {value!r}: not hex") from None
    return (r, g, b, a)


def format_color(c: RGBA) -> str:
    r, g, b, a = c
    return f"#{r:02x}{g:02x}{b:02x}" + ("" if a == 255 else f"{a:02x}")


def dither_mask(mode: str, x: int, y: int, density: float) -> bool:
    """True where the primary color goes, False where the secondary color goes.

    Uses absolute coordinates, so patterns line up across separate fills.
    """
    if mode == "none":
        return True
    if mode == "checker":
        return (x + y) % 2 == 0
    if mode == "bayer":
        return (BAYER4[y % 4][x % 4] + 0.5) / 16 < density
    if mode == "hlines":
        return y % 2 == 0
    if mode == "vlines":
        return x % 2 == 0
    if mode == "diagonal":
        return (x + y) % 4 == 0
    raise CanvasError(f"Unknown dither {mode!r}; use one of {', '.join(DITHER_MODES)}")


class Canvas:
    def __init__(self, width: int = 16, height: int = 16, background: int = 0):
        self.palette: list[RGBA] = [parse_color(c) for c in DEFAULT_PALETTE]
        self._history: list[tuple[bytearray, list[RGBA], int, int]] = []
        self._reset(width, height, background)

    # ---- state -----------------------------------------------------------

    def _reset(self, width: int, height: int, background: int) -> None:
        if not (1 <= width <= MAX_SIZE and 1 <= height <= MAX_SIZE):
            raise CanvasError(f"Size must be 1..{MAX_SIZE} on each side")
        self._check_index(background)
        self.width = width
        self.height = height
        self.pixels = bytearray([background]) * (width * height)

    def _snapshot(self) -> None:
        self._history.append((self.pixels[:], self.palette[:], self.width, self.height))
        if len(self._history) > MAX_UNDO:
            self._history.pop(0)

    def undo(self) -> bool:
        if not self._history:
            return False
        self.pixels, self.palette, self.width, self.height = self._history.pop()
        return True

    def clear_history(self) -> None:
        self._history.clear()

    def _check_index(self, index: int) -> None:
        if not 0 <= index < len(self.palette):
            raise CanvasError(
                f"Color index {index} is not in the palette (0..{len(self.palette) - 1})"
            )

    def _in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def get(self, x: int, y: int) -> int:
        if not self._in_bounds(x, y):
            raise CanvasError(f"({x}, {y}) is outside the {self.width}x{self.height} image")
        return self.pixels[y * self.width + x]

    def _plot(self, points: Iterable[tuple[int, int]], color: int) -> int:
        """Write color to the in-bounds points. Returns how many were written."""
        n = 0
        w = self.width
        for x, y in points:
            if 0 <= x < w and 0 <= y < self.height:
                self.pixels[y * w + x] = color
                n += 1
        return n

    # ---- operations ------------------------------------------------------

    def new_image(self, width: int, height: int, background: int = 0) -> None:
        self._check_index(background)
        self._snapshot()
        self._reset(width, height, background)

    def set_palette(self, colors: list[str]) -> None:
        if not 1 <= len(colors) <= MAX_PALETTE:
            raise CanvasError(f"Palette must have 1..{MAX_PALETTE} colors")
        parsed = [parse_color(c) for c in colors]
        used = max(self.pixels) if self.pixels else 0
        if used >= len(parsed):
            raise CanvasError(
                f"The image uses index {used}, but the new palette has only "
                f"{len(parsed)} colors. Add more colors or redraw first."
            )
        self._snapshot()
        self.palette = parsed

    def set_pixels(self, points: list[tuple[int, int]], color: int) -> int:
        self._check_index(color)
        self._snapshot()
        return self._plot(points, color)

    def draw_line(self, x0: int, y0: int, x1: int, y1: int, color: int) -> int:
        self._check_index(color)
        self._snapshot()
        return self._plot(line_points(x0, y0, x1, y1), color)

    def draw_rect(
        self, x: int, y: int, width: int, height: int, color: int, filled: bool = False
    ) -> int:
        self._check_index(color)
        if width < 1 or height < 1:
            raise CanvasError("Rect width and height must be at least 1")
        x1, y1 = x + width - 1, y + height - 1
        if filled:
            pts = ((px, py) for py in range(y, y1 + 1) for px in range(x, x1 + 1))
        else:
            pts = {
                *((px, y) for px in range(x, x1 + 1)),
                *((px, y1) for px in range(x, x1 + 1)),
                *((x, py) for py in range(y, y1 + 1)),
                *((x1, py) for py in range(y, y1 + 1)),
            }
        self._snapshot()
        return self._plot(pts, color)

    def draw_circle(
        self, cx: int, cy: int, radius: int, color: int, filled: bool = False
    ) -> int:
        self._check_index(color)
        if radius < 0:
            raise CanvasError("Radius must be 0 or more")
        outline = circle_points(cx, cy, radius)
        if filled:
            rows: dict[int, list[int]] = {}
            for px, py in outline:
                span = rows.setdefault(py, [px, px])
                span[0] = min(span[0], px)
                span[1] = max(span[1], px)
            pts = {(px, py) for py, (a, b) in rows.items() for px in range(a, b + 1)}
        else:
            pts = outline
        self._snapshot()
        return self._plot(pts, color)

    def flood_fill(
        self,
        x: int,
        y: int,
        color: int,
        dither: str = "none",
        color2: int | None = None,
        density: float = 0.5,
    ) -> int:
        """4-connected fill of the region that has the same index as (x, y)."""
        self._check_index(color)
        if dither not in DITHER_MODES:
            raise CanvasError(f"Unknown dither {dither!r}; use one of {', '.join(DITHER_MODES)}")
        if dither != "none":
            if color2 is None:
                raise CanvasError("Dithered fill needs color2")
            self._check_index(color2)
        if not 0.0 <= density <= 1.0:
            raise CanvasError("Density must be in 0..1")
        target = self.get(x, y)

        region = []
        seen = {(x, y)}
        queue = deque([(x, y)])
        w = self.width
        while queue:
            px, py = queue.popleft()
            region.append((px, py))
            for nx, ny in ((px + 1, py), (px - 1, py), (px, py + 1), (px, py - 1)):
                if (
                    (nx, ny) not in seen
                    and self._in_bounds(nx, ny)
                    and self.pixels[ny * w + nx] == target
                ):
                    seen.add((nx, ny))
                    queue.append((nx, ny))

        self._snapshot()
        for px, py in region:
            use_primary = dither_mask(dither, px, py, density)
            self.pixels[py * w + px] = color if use_primary else color2
        return len(region)

    # ---- output ----------------------------------------------------------

    def to_pil(self) -> PILImage.Image:
        """True-color RGBA image at 1:1 scale."""
        lut = self.palette
        raw = bytearray()
        for i in self.pixels:
            raw.extend(lut[i])
        return PILImage.frombytes("RGBA", (self.width, self.height), bytes(raw))

    def render_preview(self, scale: int | None = None, grid: bool = False) -> bytes:
        """PNG for visual inspection: scaled up, transparency shown as a checkerboard."""
        if scale is None:
            scale = max(1, min(32, 512 // max(self.width, self.height)))
        if not 1 <= scale <= 64:
            raise CanvasError("Scale must be 1..64")
        img = self.to_pil().resize(
            (self.width * scale, self.height * scale), PILImage.Resampling.NEAREST
        )
        # 2x2 checker cells per canvas pixel, so the pattern lines up with pixels.
        light, dark = (204, 204, 204, 255), (153, 153, 153, 255)
        cw, ch = self.width * 2, self.height * 2
        checker = bytearray()
        for cy in range(ch):
            for cx in range(cw):
                checker.extend(dark if (cx + cy) % 2 else light)
        bg = PILImage.frombytes("RGBA", (cw, ch), bytes(checker)).resize(
            img.size, PILImage.Resampling.NEAREST
        )
        out = PILImage.alpha_composite(bg, img)
        if grid and scale >= 4:
            px = out.load()
            line = (0, 0, 0, 255)
            for gx in range(0, out.width, scale):
                major = (gx // scale) % 8 == 0
                for gy in range(out.height):
                    if major or gy % 2 == 0:
                        px[gx, gy] = line
            for gy in range(0, out.height, scale):
                major = (gy // scale) % 8 == 0
                for gx in range(out.width):
                    if major or gx % 2 == 0:
                        px[gx, gy] = line
        buf = io.BytesIO()
        out.convert("RGB").save(buf, "PNG")
        return buf.getvalue()

    def write_png(self, path: str) -> None:
        """Save as an indexed PNG. Keeps the exact indices and the full palette,
        including entries that no pixel uses yet."""
        img = PILImage.frombytes("P", (self.width, self.height), bytes(self.pixels))
        img.putpalette(b"".join(bytes(c) for c in self.palette), rawmode="RGBA")
        img.save(path, format="PNG")

    def read_png(self, path: str) -> None:
        """Load pixels and palette from an indexed PNG. The undo history stays."""
        with PILImage.open(path) as img:
            if img.mode != "P":
                raise CanvasError(f"{path} is not an indexed (palette) PNG")
            img.load()
            size = img.size
            pixels = bytearray(img.tobytes())
            rgb = img.getpalette("RGB") or []
            trns = img.info.get("transparency")
        n = len(rgb) // 3
        if isinstance(trns, bytes):
            alpha = list(trns[:n]) + [255] * (n - len(trns))
        elif isinstance(trns, int):
            alpha = [0 if i == trns else 255 for i in range(n)]
        else:
            alpha = [255] * n
        if pixels and max(pixels) >= n:
            raise CanvasError(f"{path} uses a color index that is not in its palette")
        self.width, self.height = size
        self.pixels = pixels
        self.palette = [(rgb[3 * i], rgb[3 * i + 1], rgb[3 * i + 2], alpha[i]) for i in range(n)]

    def save(self, path: str, scale: int = 1) -> None:
        if not 1 <= scale <= 64:
            raise CanvasError("Scale must be 1..64")
        img = self.to_pil()
        if scale > 1:
            img = img.resize((self.width * scale, self.height * scale), PILImage.Resampling.NEAREST)
        img.save(path)


def line_points(x0: int, y0: int, x1: int, y1: int) -> list[tuple[int, int]]:
    """Bresenham line, both ends included."""
    pts = []
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        pts.append((x0, y0))
        if x0 == x1 and y0 == y1:
            return pts
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def circle_points(cx: int, cy: int, r: int) -> set[tuple[int, int]]:
    """Midpoint circle outline."""
    pts: set[tuple[int, int]] = set()
    x, y, d = r, 0, 1 - r
    while x >= y:
        for px, py in ((x, y), (y, x), (-y, x), (-x, y), (-x, -y), (-y, -x), (y, -x), (x, -y)):
            pts.add((cx + px, cy + py))
        y += 1
        if d < 0:
            d += 2 * y + 1
        else:
            x -= 1
            d += 2 * (y - x) + 1
    return pts
