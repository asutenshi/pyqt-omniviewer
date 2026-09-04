# ruff: noqa: BLE001
"""Просмотрщик изображений: растр, SVG, современные и профессиональные форматы."""

from pathlib import Path

from PyQt6.QtCore import QEvent, QPoint, QSize, Qt
from PyQt6.QtGui import QImage, QImageReader, QMovie, QPixmap
from PyQt6.QtSvgWidgets import QSvgWidget
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QScrollArea, QWidget

from omniviewer.viewers.base import BaseViewer

# --- Опциональные плагины Pillow. Их отсутствие не должно ломать остальные форматы. ---
try:
    import pillow_heif

    pillow_heif.register_heif_opener()
    _HEIF_OK = True
except Exception:  # pragma: no cover - зависит от окружения
    _HEIF_OK = False

try:
    import pillow_avif  # noqa: F401 — импорт регистрирует AVIF-плагин Pillow

    _AVIF_OK = True
except Exception:  # pragma: no cover - зависит от окружения
    _AVIF_OK = False

_HEIF_SUFFIXES = (".heic", ".heif", ".hif")
_AVIF_SUFFIXES = (".avif",)
_RAW_SUFFIXES = (".cr2", ".cr3", ".nef", ".arw", ".dng", ".raf", ".orf", ".rw2")
_TIFF_SUFFIXES = (".tif", ".tiff")


## @brief Просмотрщик изображений (растр, SVG, современные и профессиональные форматы).
#
# Отображает растровые изображения (PNG, JPEG, GIF, BMP, WebP, TIFF, ICO), векторные (SVG,
# SVGZ), современные HEIC/HEIF и AVIF (через Pillow → QImage), а также RAW-фото
# (CR2/CR3/NEF/ARW/DNG/RAF/ORF/RW2) — по встроенному превью-JPEG. Многостраничный TIFF
# позволяет листать кадры. Поддерживает панорамирование (перетаскивание мышью) и зум
# (Ctrl+Wheel). Анимированные изображения проигрываются автоматически. Большие изображения
# масштабируются при загрузке для экономии памяти.
class ImageViewer(BaseViewer):
    mime_types = (
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/bmp",
        "image/webp",
        "image/tiff",
        "image/vnd.microsoft.icon",
        "image/x-icon",
        "image/svg+xml",
        "image/svg+xml-compressed",
        # современные форматы
        "image/heic",
        "image/heif",
        "image/heic-sequence",
        "image/heif-sequence",
        "image/avif",
        # RAW-фото
        "image/x-canon-cr2",
        "image/x-canon-cr3",
        "image/x-nikon-nef",
        "image/x-sony-arw",
        "image/x-adobe-dng",
        "image/x-raw-adobe",
        "image/x-fuji-raf",
        "image/x-olympus-orf",
        "image/x-panasonic-rw2",
        "image/x-dcraw",
    )
    extensions = (
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp",
        ".tiff", ".tif", ".ico", ".svg", ".svgz",
        *_HEIF_SUFFIXES, *_AVIF_SUFFIXES, *_RAW_SUFFIXES,
    )
    priority = 20

    # Порог размера, свыше которого изображение уменьшается при загрузке
    MAX_IMAGE_SIDE = 4096

    def __init__(self):
        super().__init__()
        self.scroll_area = QScrollArea()
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")

        self.content_widget = None
        self.movie = None
        self._layout.addWidget(self.scroll_area)

        # Пейджер для многостраничного TIFF
        self._pager = QWidget()
        pager_layout = QHBoxLayout(self._pager)
        pager_layout.setContentsMargins(0, 0, 0, 0)
        self._btn_prev_frame = QPushButton("◀ Кадр")
        self._btn_next_frame = QPushButton("Кадр ▶")
        self._lbl_frame = QLabel("")
        self._btn_prev_frame.clicked.connect(self._prev_frame)
        self._btn_next_frame.clicked.connect(self._next_frame)
        pager_layout.addWidget(self._btn_prev_frame)
        pager_layout.addWidget(self._lbl_frame)
        pager_layout.addWidget(self._btn_next_frame)
        self._pager.setVisible(False)
        self._layout.addWidget(self._pager)

        self._tiff_path = None
        self._frame_index = 0
        self._frame_count = 0

        self.zoom = 1.0
        self.base_size = QSize()

        self.pan_active = False
        self.pan_start = QPoint()

        self.scroll_area.viewport().installEventFilter(self)

    def load(self, path: Path):
        self.cancel()  # Отменяем любые асинхронные задачи если есть
        path_str = str(path)
        suffix = path.suffix.lower()

        # Очистка предыдущего виджета
        if self.content_widget:
            self.scroll_area.takeWidget()
            self.content_widget.deleteLater()
            self.content_widget = None
        if self.movie:
            self.movie.deleteLater()
            self.movie = None
        self._pager.setVisible(False)
        self._tiff_path = None
        self._frame_index = 0
        self._frame_count = 0

        if suffix in (".svg", ".svgz"):
            self._load_svg(path_str)
        elif suffix in _RAW_SUFFIXES:
            self._load_raw(path_str)
        elif suffix in _HEIF_SUFFIXES:
            self._load_pillow(path_str, "pillow-heif" if not _HEIF_OK else None)
        elif suffix in _AVIF_SUFFIXES:
            self._load_pillow(path_str, "pillow-avif-plugin" if not _AVIF_OK else None)
        else:
            self._load_raster(path_str, suffix)

        self._fit_to_window()

    def _new_label(self):
        """Свежий QLabel как содержимое области прокрутки (для растровых путей)."""
        self.content_widget = QLabel()
        self.content_widget.setScaledContents(True)
        self.scroll_area.setWidget(self.content_widget)

    def _display_qimage(self, img: QImage):
        """Показать QImage: при необходимости уменьшить, вписать в QLabel."""
        if img.isNull():
            raise ValueError("Не удалось декодировать изображение")
        if img.width() > self.MAX_IMAGE_SIDE or img.height() > self.MAX_IMAGE_SIDE:
            img = img.scaled(
                self.MAX_IMAGE_SIDE, self.MAX_IMAGE_SIDE,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        pixmap = QPixmap.fromImage(img)
        self.content_widget.setPixmap(pixmap)
        self.base_size = pixmap.size()
        self.content_widget.resize(self.base_size)

    def _load_svg(self, path_str: str):
        self.content_widget = QSvgWidget(path_str)
        if not self.content_widget.renderer().isValid():
            raise ValueError("Недопустимый или поврежденный SVG файл")
        self.base_size = self.content_widget.sizeHint()
        if self.base_size.isEmpty():
            self.base_size = QSize(800, 600)  # Fallback size
        self.content_widget.resize(self.base_size)
        self.scroll_area.setWidget(self.content_widget)

    def _load_pillow(self, path_str: str, missing_plugin: str | None):
        """HEIC/HEIF/AVIF через Pillow → QImage."""
        if missing_plugin:
            raise ValueError(f"Формат недоступен: не установлен плагин {missing_plugin}")
        from PIL import Image

        with Image.open(path_str) as im:
            im.load()
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGBA")
            fmt = (
                QImage.Format.Format_RGBA8888
                if im.mode == "RGBA"
                else QImage.Format.Format_RGB888
            )
            channels = len(im.mode)
            data = im.tobytes("raw", im.mode)
            qimg = QImage(data, im.width, im.height, im.width * channels, fmt).copy()
        self._new_label()
        self._display_qimage(qimg)

    def _load_raw(self, path_str: str):
        """RAW-фото: встроенное превью-JPEG (быстро); запасной путь — half-size демозаик."""
        import rawpy

        with rawpy.imread(path_str) as raw:
            qimg = None
            try:
                thumb = raw.extract_thumb()
            except rawpy.LibRawError:
                thumb = None

            if thumb is not None and thumb.format == rawpy.ThumbFormat.JPEG:
                qimg = QImage.fromData(thumb.data, "JPEG")
            elif thumb is not None and thumb.format == rawpy.ThumbFormat.BITMAP:
                try:
                    h, w = thumb.data.shape[:2]
                    qimg = QImage(
                        thumb.data.tobytes(), w, h, w * 3, QImage.Format.Format_RGB888
                    ).copy()
                except Exception:
                    qimg = None

            if qimg is None or qimg.isNull():
                rgb = raw.postprocess(half_size=True, no_auto_bright=True, use_camera_wb=True)
                h, w = rgb.shape[:2]
                qimg = QImage(rgb.tobytes(), w, h, w * 3, QImage.Format.Format_RGB888).copy()

        self._new_label()
        self._display_qimage(qimg)

    def _load_raster(self, path_str: str, suffix: str):
        self._new_label()

        reader = QImageReader(path_str)
        if not reader.canRead():
            raise ValueError(f"Невозможно прочитать изображение: {reader.errorString()}")

        # Проверка на анимацию
        if reader.supportsAnimation() and reader.imageCount() > 1:
            self.movie = QMovie(path_str)
            if not self.movie.isValid():
                raise ValueError("Недопустимый файл анимации")
            self.content_widget.setMovie(self.movie)
            self.movie.start()

            # Ждем первый кадр для определения размера
            self.movie.jumpToFrame(0)
            orig_size = self.movie.currentImage().size()

            if orig_size.width() > self.MAX_IMAGE_SIDE or orig_size.height() > self.MAX_IMAGE_SIDE:
                orig_size.scale(self.MAX_IMAGE_SIDE, self.MAX_IMAGE_SIDE, Qt.AspectRatioMode.KeepAspectRatio)
                self.movie.setScaledSize(orig_size)

            self.base_size = orig_size
            self.content_widget.resize(self.base_size)
        elif suffix in _TIFF_SUFFIXES and reader.imageCount() > 1:
            # Многостраничный TIFF — листаем кадры пейджером
            self._tiff_path = path_str
            self._frame_count = reader.imageCount()
            self._frame_index = 0
            self._pager.setVisible(True)
            self._show_tiff_frame()
        else:
            orig_size = reader.size()
            if orig_size.width() > self.MAX_IMAGE_SIDE or orig_size.height() > self.MAX_IMAGE_SIDE:
                reader.setScaledSize(orig_size.scaled(self.MAX_IMAGE_SIDE, self.MAX_IMAGE_SIDE, Qt.AspectRatioMode.KeepAspectRatio))

            img = reader.read()
            if img.isNull():
                raise ValueError(f"Ошибка декодирования изображения: {reader.errorString()}")

            pixmap = QPixmap.fromImage(img)
            self.content_widget.setPixmap(pixmap)
            self.base_size = pixmap.size()
            self.content_widget.resize(self.base_size)

    def _show_tiff_frame(self):
        reader = QImageReader(self._tiff_path)
        reader.jumpToImage(self._frame_index)
        size = reader.size()
        if size.width() > self.MAX_IMAGE_SIDE or size.height() > self.MAX_IMAGE_SIDE:
            reader.setScaledSize(
                size.scaled(self.MAX_IMAGE_SIDE, self.MAX_IMAGE_SIDE, Qt.AspectRatioMode.KeepAspectRatio)
            )
        img = reader.read()
        if img.isNull():
            raise ValueError(f"Ошибка чтения кадра TIFF: {reader.errorString()}")
        pixmap = QPixmap.fromImage(img)
        self.content_widget.setPixmap(pixmap)
        self.base_size = pixmap.size()
        self.content_widget.resize(self.base_size)
        self._lbl_frame.setText(f"Кадр {self._frame_index + 1} / {self._frame_count}")
        self._btn_prev_frame.setEnabled(self._frame_index > 0)
        self._btn_next_frame.setEnabled(self._frame_index < self._frame_count - 1)

    def _prev_frame(self):
        if self._tiff_path and self._frame_index > 0:
            self._frame_index -= 1
            self._show_tiff_frame()
            self._fit_to_window()

    def _next_frame(self):
        if self._tiff_path and self._frame_index < self._frame_count - 1:
            self._frame_index += 1
            self._show_tiff_frame()
            self._fit_to_window()

    def _fit_to_window(self):
        """Вписывает изображение в окно по умолчанию"""
        viewport_size = self.scroll_area.viewport().size()
        if viewport_size.isEmpty() or self.base_size.isEmpty():
            self.zoom = 1.0
            return

        w_ratio = viewport_size.width() / self.base_size.width()
        h_ratio = viewport_size.height() / self.base_size.height()

        # Если изображение меньше окна, не увеличиваем его по умолчанию
        self.zoom = min(1.0, min(w_ratio, h_ratio))
        self._apply_zoom()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # При первом показе (когда размер окна меняется с 0 на реальный) вписываем
        if getattr(self, '_first_resize', True):
            self._fit_to_window()
            self._first_resize = False

    def _apply_zoom(self):
        if self.content_widget and not self.base_size.isEmpty():
            new_size = self.base_size * self.zoom
            self.content_widget.resize(new_size)

    def eventFilter(self, obj, event):
        if obj == self.scroll_area.viewport():
            if event.type() == QEvent.Type.Wheel:
                if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                    # Zoom in/out
                    delta = event.angleDelta().y()
                    old_zoom = self.zoom
                    if delta > 0:
                        self.zoom *= 1.2
                    else:
                        self.zoom /= 1.2

                    self.zoom = max(0.05, min(50.0, self.zoom))

                    if old_zoom != self.zoom:
                        # Centering zoom logic (approximation)
                        hbar = self.scroll_area.horizontalScrollBar()
                        vbar = self.scroll_area.verticalScrollBar()

                        hx = hbar.value() + event.position().x()
                        hy = vbar.value() + event.position().y()

                        self._apply_zoom()

                        ratio = self.zoom / old_zoom
                        hbar.setValue(int(hx * ratio - event.position().x()))
                        vbar.setValue(int(hy * ratio - event.position().y()))

                    return True

            elif event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self.pan_active = True
                self.pan_start = event.pos()
                self.scroll_area.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
                return True

            elif event.type() == QEvent.Type.MouseMove:
                if self.pan_active:
                    delta = event.pos() - self.pan_start
                    hbar = self.scroll_area.horizontalScrollBar()
                    vbar = self.scroll_area.verticalScrollBar()
                    hbar.setValue(hbar.value() - delta.x())
                    vbar.setValue(vbar.value() - delta.y())
                    self.pan_start = event.pos()
                    return True

            elif event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                self.pan_active = False
                self.scroll_area.viewport().setCursor(Qt.CursorShape.ArrowCursor)
                return True

        return super().eventFilter(obj, event)
