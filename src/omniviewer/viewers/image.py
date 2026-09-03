## @brief Просмотрщик изображений (растр и SVG).
#
# Отображает растровые изображения (PNG, JPEG, GIF, BMP, WebP, TIFF, ICO) и векторные (SVG, SVGZ).
# Поддерживает панорамирование (перетаскивание мышью) и зум (Ctrl+Wheel).
# Анимированные изображения проигрываются автоматически.
# Большие изображения масштабируются при загрузке для экономии памяти.

from pathlib import Path

from PyQt6.QtCore import QEvent, QPoint, QSize, Qt
from PyQt6.QtGui import QImageReader, QMovie, QPixmap
from PyQt6.QtSvgWidgets import QSvgWidget
from PyQt6.QtWidgets import QLabel, QScrollArea

from omniviewer.viewers.base import BaseViewer


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
    )
    extensions = (
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", 
        ".tiff", ".tif", ".ico", ".svg", ".svgz"
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
        
        self.zoom = 1.0
        self.base_size = QSize()

        self.pan_active = False
        self.pan_start = QPoint()

        self.scroll_area.viewport().installEventFilter(self)

    def load(self, path: Path):
        self.cancel() # Отменяем любые асинхронные задачи если есть
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

        if suffix in (".svg", ".svgz"):
            self._load_svg(path_str)
        else:
            self._load_raster(path_str)

        self._fit_to_window()

    def _load_svg(self, path_str: str):
        self.content_widget = QSvgWidget(path_str)
        if not self.content_widget.renderer().isValid():
            raise ValueError("Недопустимый или поврежденный SVG файл")
        self.base_size = self.content_widget.sizeHint()
        if self.base_size.isEmpty():
            self.base_size = QSize(800, 600) # Fallback size
        self.content_widget.resize(self.base_size)
        self.scroll_area.setWidget(self.content_widget)

    def _load_raster(self, path_str: str):
        self.content_widget = QLabel()
        self.content_widget.setScaledContents(True)
        self.scroll_area.setWidget(self.content_widget)

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

