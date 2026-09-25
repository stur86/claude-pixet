"""A canvas bound to a PNG file on disk.

The file is the source of truth. Every operation reads it first and every
change writes it back, so an image viewer shows the edits live. With frame
recording on, each change also writes a numbered copy next to the file
(`name_0001.png`, `name_0002.png`, ...), so the whole process can be replayed.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from .canvas import Canvas, CanvasError


class Document:
    def __init__(self) -> None:
        self.canvas = Canvas()
        self.path: Path | None = None
        self.record = False
        self.frame = 0

    def new(
        self, path: str, width: int, height: int, background: int = 0, record: bool = False
    ) -> Path:
        """Start a blank image at `path` (overwritten if it exists).

        If `record` is true, old frames of the same name are deleted first.
        """
        p = Path(path).expanduser().resolve()
        if p.suffix.lower() != ".png":
            raise CanvasError("Path must end in .png")
        self.canvas.new_image(width, height, background)
        self.canvas.clear_history()
        p.parent.mkdir(parents=True, exist_ok=True)
        self.path, self.record, self.frame = p, record, 0
        if record:
            for old in self.frame_paths():
                old.unlink()
        self.commit()
        return p

    def load(self) -> Canvas:
        """Read the file into the canvas and return the canvas."""
        if self.path is None:
            raise CanvasError("No image yet. Call new_image first.")
        if not self.path.exists():
            raise CanvasError(f"{self.path} is missing. Call new_image again.")
        self.canvas.read_png(str(self.path))
        return self.canvas

    def commit(self) -> None:
        """Write the canvas to the file, plus a new frame if recording."""
        assert self.path is not None
        _write_atomic(self.canvas, self.path)
        if self.record:
            self.frame += 1
            _write_atomic(self.canvas, self.frame_path(self.frame))

    def frame_path(self, n: int) -> Path:
        assert self.path is not None
        return self.path.with_name(f"{self.path.stem}_{n:04d}.png")

    def frame_paths(self) -> list[Path]:
        """Existing frame files of the current image, in order."""
        assert self.path is not None
        pattern = re.compile(re.escape(self.path.stem) + r"_\d{4}\.png")
        return sorted(f for f in self.path.parent.iterdir() if pattern.fullmatch(f.name))


def _write_atomic(canvas: Canvas, path: Path) -> None:
    # Write then rename, so a viewer never reads a half-written file.
    tmp = path.with_name(f".{path.name}.tmp")
    canvas.write_png(str(tmp))
    os.replace(tmp, path)
