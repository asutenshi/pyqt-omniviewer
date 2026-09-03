from pathlib import Path

from PyQt6.QtWidgets import QTableView, QTextEdit, QWidget

from omniviewer.main import MainWindow
from omniviewer.registry import ViewerRegistry
from omniviewer.viewers.base import BaseViewer
from omniviewer.viewers.fallback import FallbackViewer


class DummyImageViewer(BaseViewer):
    mime_types = ("image/png", "image/jpeg")
    extensions = (".png", ".jpg", ".jpeg")
    priority = 10

    def __init__(self, parent=None):
        super().__init__(parent)
        self.loaded_path = None

    def load(self, path: Path) -> None:
        self.loaded_path = path


class DummyHighPriorityFallback(BaseViewer):
    mime_types = ("*/*",)
    priority = 100


def test_base_viewer_interface():
    assert hasattr(BaseViewer, "mime_types")
    assert hasattr(BaseViewer, "extensions")
    assert hasattr(BaseViewer, "priority")
    assert hasattr(BaseViewer, "can_handle")
    assert hasattr(BaseViewer, "load")
    assert hasattr(BaseViewer, "load_async")
    assert hasattr(BaseViewer, "cancel")

    viewer = BaseViewer()
    assert isinstance(viewer, QWidget)
    assert viewer.can_handle(Path("test.txt"), "text/plain") is False
    viewer.load(Path("test.txt"))
    viewer.load_async()
    viewer.cancel()


def test_registry_registration_and_fallback(tmp_path):
    registry = ViewerRegistry()
    registry.register(FallbackViewer)
    registry.register(DummyImageViewer)

    # Known image
    png_file = tmp_path / "sample.png"
    # Write PNG signature
    png_file.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01")
    viewer = registry.viewer_for(png_file)
    assert isinstance(viewer, DummyImageViewer)

    # Unknown binary / text without specific handler -> FallbackViewer
    bin_file = tmp_path / "random.unknown_ext_123"
    bin_file.write_bytes(b"\x00\x01\x02\x03\x04\x05")
    viewer = registry.viewer_for(bin_file)
    assert isinstance(viewer, FallbackViewer)


def test_file_without_extension_content_sniffing(tmp_path):
    registry = ViewerRegistry()
    registry.register(FallbackViewer)
    registry.register(DummyImageViewer)

    # File without extension but with PNG magic bytes
    no_ext_png = tmp_path / "image_no_ext"
    no_ext_png.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01")

    viewer = registry.viewer_for(no_ext_png)
    assert isinstance(viewer, DummyImageViewer)


def test_fallback_by_extension_when_sniffing_ambiguous(tmp_path):
    registry = ViewerRegistry()
    registry.register(FallbackViewer)
    registry.register(DummyImageViewer)

    # Empty file named sample.png
    empty_png = tmp_path / "sample.png"
    empty_png.touch()

    viewer = registry.viewer_for(empty_png)
    assert isinstance(viewer, DummyImageViewer)


def test_handler_priority_resolves_conflicts(tmp_path):
    registry = ViewerRegistry()
    registry.register(FallbackViewer)
    registry.register(DummyImageViewer)
    registry.register(DummyHighPriorityFallback)

    sample = tmp_path / "sample.png"
    sample.write_bytes(b"\x89PNG\r\n\x1a\n")

    viewer = registry.viewer_for(sample)
    # DummyHighPriorityFallback has priority 100 > DummyImageViewer (10)
    assert isinstance(viewer, DummyHighPriorityFallback)


def test_fallback_viewer_ui_components(qapp, tmp_path):
    sample = tmp_path / "test.bin"
    content = b"Hello World!\x00\x01\x02\x03Testing hex dump"
    sample.write_bytes(content)

    viewer = FallbackViewer()
    viewer.load(sample)

    # Should contain text preview, hex dump, metadata table
    assert hasattr(viewer, "text_preview")
    assert hasattr(viewer, "hex_dump")
    assert hasattr(viewer, "metadata_table")

    assert isinstance(viewer.text_preview, QTextEdit)
    assert isinstance(viewer.hex_dump, QTextEdit)
    assert isinstance(viewer.metadata_table, QTableView)

    # Verify content in text preview and hex dump
    assert "Hello World!" in viewer.text_preview.toPlainText()
    hex_text = viewer.hex_dump.toPlainText()
    assert "48 65 6c 6c 6f" in hex_text.lower() or "48 65 6C 6C 6F" in hex_text
    assert "Hello" in hex_text  # ASCII column

    # Metadata table checks
    model = viewer.metadata_table.model()
    assert model is not None
    props = {}
    for r in range(model.rowCount()):
        key = model.data(model.index(r, 0))
        val = model.data(model.index(r, 1))
        props[key] = val

    assert "Size" in props or "Размер" in props
    assert "MIME" in props or "MIME-тип" in props


def test_main_window_tree_click_updates_viewer(qapp, tmp_path):
    test_file = tmp_path / "test.txt"
    test_file.write_text("File content")

    window = MainWindow(tmp_path)
    # Check header labels above viewer area
    assert hasattr(window, "file_name_label")
    assert hasattr(window, "file_path_label")

    # Simulate file selection signal from tree
    window.tree_widget.file_selected.emit(test_file)

    assert window.file_name_label.text() == "test.txt"
    assert window.file_path_label.text() == str(test_file)
    assert window.current_viewer is not None
    assert isinstance(window.current_viewer, FallbackViewer)
