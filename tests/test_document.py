import pytest

from pixet.canvas import Canvas, CanvasError
from pixet.document import Document


def test_needs_new_image_first():
    with pytest.raises(CanvasError):
        Document().load()


def test_changes_go_to_disk(tmp_path):
    doc = Document()
    path = doc.new(str(tmp_path / "sub" / "a.png"), 4, 4)
    assert path.exists()
    doc.load().draw_line(0, 0, 3, 0, 8)
    doc.commit()
    c = Canvas()
    c.read_png(str(path))
    assert [c.get(x, 0) for x in range(4)] == [8] * 4
    assert list(tmp_path.glob("sub/a_*.png")) == []  # no frames unless asked


def test_reads_external_edits(tmp_path):
    doc = Document()
    path = doc.new(str(tmp_path / "a.png"), 2, 2)
    other = Canvas(2, 2)
    other.set_pixels([(1, 1)], 3)
    other.write_png(str(path))
    assert doc.load().get(1, 1) == 3


def test_record_frames(tmp_path):
    stale = tmp_path / "a_0009.png"
    stale.write_bytes(b"old")
    keep = tmp_path / "a_notes.png"
    keep.write_bytes(b"keep")
    doc = Document()
    doc.new(str(tmp_path / "a.png"), 2, 2, record=True)
    doc.load().set_pixels([(0, 0)], 1)
    doc.commit()
    doc.load().undo()
    doc.commit()
    assert [p.name for p in doc.frame_paths()] == ["a_0001.png", "a_0002.png", "a_0003.png"]
    assert keep.exists()
    frames = []
    for p in doc.frame_paths():
        c = Canvas()
        c.read_png(str(p))
        frames.append(c.get(0, 0))
    assert frames == [0, 1, 0]


def test_new_clears_undo_and_checks_suffix(tmp_path):
    doc = Document()
    doc.new(str(tmp_path / "a.png"), 2, 2)
    assert not doc.load().undo()
    with pytest.raises(CanvasError):
        doc.new(str(tmp_path / "a.gif"), 2, 2)
