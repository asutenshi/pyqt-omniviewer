"""Тесты расширения просмотрщика изображений (issue: современные + профессиональные форматы).

Поведение проверяется через главный шов ``ViewerRegistry`` и публичный API
``ImageViewer``: HEIC/HEIF и AVIF (Pillow → QImage), RAW-фото по встроенному
превью-JPEG, листание кадров многостраничного TIFF, изоляция отсутствия
опционального плагина, «ошибочный» виджет на битом образце, EXIF в метаданных.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest
import rawpy
from PIL import Image
from PyQt6.QtWidgets import QApplication

from omniviewer.registry import ViewerRegistry
from omniviewer.viewers import image as image_mod
from omniviewer.viewers.image import ImageViewer

DEMO = Path(__file__).parent.parent / "demo"


@pytest.fixture(scope="session", autouse=True)
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture
def registry() -> ViewerRegistry:
    return ViewerRegistry()


def _rgb(w=40, h=30) -> Image.Image:
    im = Image.new("RGB", (w, h))
    for y in range(h):
        for x in range(w):
            im.putpixel((x, y), ((x * 6) % 256, (y * 8) % 256, 140))
    return im


# --------------------------------------------------------------------------- #
# Диспетчеризация                                                             #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "name", ["sample.heic", "sample.avif", "multipage.tiff", "sample.dng"]
)
def test_registry_selects_image_viewer(registry: ViewerRegistry, name: str) -> None:
    assert isinstance(registry.viewer_for(DEMO / "images" / name), ImageViewer)


# --------------------------------------------------------------------------- #
# HEIC / AVIF                                                                 #
# --------------------------------------------------------------------------- #


def test_heic_loads_and_fits() -> None:
    viewer = ImageViewer()
    viewer.safe_load(DEMO / "images" / "sample.heic")
    assert not viewer.is_error_widget
    assert not viewer.base_size.isEmpty()
    assert viewer.zoom <= 1.0  # вписано в окно, не увеличено


def test_avif_loads() -> None:
    viewer = ImageViewer()
    viewer.safe_load(DEMO / "images" / "sample.avif")
    assert not viewer.is_error_widget
    assert not viewer.base_size.isEmpty()


def test_missing_avif_plugin_does_not_break_other_formats(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Отсутствие pillow-avif-plugin: PNG грузится, AVIF даёт аккуратную ошибку, не падение."""
    monkeypatch.setattr(image_mod, "_AVIF_OK", False)

    png = tmp_path / "ok.png"
    _rgb().save(png, "PNG")
    v_png = ImageViewer()
    v_png.safe_load(png)
    assert not v_png.is_error_widget

    avif = tmp_path / "x.avif"
    avif.write_bytes(b"not really avif")
    v_avif = ImageViewer()
    v_avif.safe_load(avif)  # не бросает
    assert v_avif.is_error_widget
    assert "плагин" in v_avif.error_message


# --------------------------------------------------------------------------- #
# RAW                                                                         #
# --------------------------------------------------------------------------- #


def test_raw_uses_embedded_jpeg_preview(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    buf = io.BytesIO()
    _rgb(64, 48).save(buf, "JPEG", quality=80)
    jpeg = buf.getvalue()

    class _Thumb:
        format = rawpy.ThumbFormat.JPEG
        data = jpeg

    class _FakeRaw:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_thumb(self):
            return _Thumb()

        def postprocess(self, **kw):  # pragma: no cover - не должно вызываться
            raise AssertionError("для RAW с превью-JPEG постпроцесс не нужен")

    monkeypatch.setattr(rawpy, "imread", lambda _path: _FakeRaw())

    raw_path = tmp_path / "shot.nef"
    raw_path.write_bytes(b"\x00" * 32)
    viewer = ImageViewer()
    viewer.safe_load(raw_path)

    assert not viewer.is_error_widget
    assert (viewer.base_size.width(), viewer.base_size.height()) == (64, 48)


def test_raw_demo_dng_loads() -> None:
    """Реальный демо-DNG: путь распаковки кадра целиком (запасной half-size демозаик)."""
    viewer = ImageViewer()
    viewer.safe_load(DEMO / "images" / "sample.dng")
    assert not viewer.is_error_widget
    assert not viewer.base_size.isEmpty()


# --------------------------------------------------------------------------- #
# Многостраничный TIFF                                                        #
# --------------------------------------------------------------------------- #


def test_multipage_tiff_frame_navigation() -> None:
    viewer = ImageViewer()
    viewer.safe_load(DEMO / "images" / "multipage.tiff")
    assert not viewer.is_error_widget
    assert not viewer._pager.isHidden()  # пейджер показан (isVisible требует show() предков)
    assert viewer._frame_count == 3
    assert viewer._frame_index == 0

    viewer._next_frame()
    assert viewer._frame_index == 1
    viewer._next_frame()
    assert viewer._frame_index == 2
    viewer._next_frame()  # дальше последнего — стоим на месте
    assert viewer._frame_index == 2
    viewer._prev_frame()
    assert viewer._frame_index == 1
    assert not viewer.is_error_widget
    assert not viewer.base_size.isEmpty()


def test_single_page_tiff_has_no_pager(tmp_path: Path) -> None:
    p = tmp_path / "one.tiff"
    _rgb().save(p, "TIFF")
    viewer = ImageViewer()
    viewer.safe_load(p)
    assert not viewer.is_error_widget
    assert viewer._pager.isHidden()


# --------------------------------------------------------------------------- #
# Битый образец                                                               #
# --------------------------------------------------------------------------- #


def test_truncated_heic_yields_error_widget(tmp_path: Path, registry: ViewerRegistry) -> None:
    full = (DEMO / "images" / "sample.heic").read_bytes()
    broken = tmp_path / "broken.heic"
    broken.write_bytes(full[: len(full) // 3])

    viewer = registry.viewer_for(broken)
    assert isinstance(viewer, ImageViewer)
    viewer.safe_load(broken)
    assert viewer.is_error_widget


# --------------------------------------------------------------------------- #
# EXIF в панель свойств                                                       #
# --------------------------------------------------------------------------- #


def test_exif_surfaced_for_heic(tmp_path: Path) -> None:
    from omniviewer.metadata import metadata_for

    exif = Image.Exif()
    exif[0x010F] = "OmniCam"       # Make
    exif[0x0110] = "Model-X"       # Model
    p = tmp_path / "with_exif.heic"
    _rgb().save(p, "HEIF", exif=exif)

    meta = metadata_for(str(p))
    assert meta.get("Resolution") == "40x30"
    assert meta.get("Make") == "OmniCam" or meta.get("Model") == "Model-X"
