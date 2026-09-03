from pathlib import Path

import fitz  # type: ignore
from PyQt6.QtCore import QEvent, QObject, QRunnable, Qt, QThreadPool, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from omniviewer.viewers.base import BaseViewer


## @brief Рабочий для рендеринга страниц в фоне.
class RenderWorkerSignals(QObject):
    page_rendered = pyqtSignal(int, QImage)
    error_occurred = pyqtSignal(str)


## @brief Задача рендеринга страницы.
class RenderPageTask(QRunnable):
    def __init__(self, path: Path, page_num: int, zoom: float):
        super().__init__()
        self.path = path
        self.page_num = page_num
        self.zoom = zoom
        self.signals = RenderWorkerSignals()
        self.is_cancelled = False

    def run(self):
        if self.is_cancelled:
            return
        try:
            doc = fitz.open(self.path)
            if self.is_cancelled:
                doc.close()
                return
            page = doc.load_page(self.page_num)
            matrix = fitz.Matrix(self.zoom, self.zoom)
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            
            if self.is_cancelled:
                doc.close()
                return

            # Convert fitz.Pixmap to QImage
            qimg = QImage(
                pix.samples,
                pix.width,
                pix.height,
                pix.stride,
                QImage.Format.Format_RGB888,
            ).copy()
            
            doc.close()

            if not self.is_cancelled:
                self.signals.page_rendered.emit(self.page_num, qimg)
        except Exception as e:  # noqa: BLE001
            if not self.is_cancelled:
                self.signals.error_occurred.emit(str(e))


## @brief Просмотрщик для PDF и электронных книг через PyMuPDF (fitz).
#
# Поддерживает форматы: pdf, epub, mobi, fb2, cbz, xps.
# Выполняет постраничную прокрутку и зум. Рендер страниц в фоне с отменой.
class PdfViewer(BaseViewer):
    priority = 20  # Выше, чем fallback и текст

    def __init__(self):
        super().__init__()
        self.doc: fitz.Document | None = None
        self._path: Path | None = None
        self._zoom = 1.0
        self._tasks: list[RenderPageTask] = []
        
        # UI
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        
        # Zoom toolbar
        toolbar = QWidget()
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(8, 4, 8, 4)
        tb_layout.setSpacing(6)
        
        self.btn_zoom_out = QPushButton("Зум −")
        self.btn_zoom_out.clicked.connect(self.zoom_out)
        self.btn_zoom_reset = QPushButton("100%")
        self.btn_zoom_reset.clicked.connect(self.zoom_reset)
        self.btn_zoom_in = QPushButton("Зум +")
        self.btn_zoom_in.clicked.connect(self.zoom_in)
        self.lbl_zoom = QLabel("100%")
        
        tb_layout.addWidget(QLabel("Масштаб:"))
        tb_layout.addWidget(self.btn_zoom_out)
        tb_layout.addWidget(self.btn_zoom_reset)
        tb_layout.addWidget(self.btn_zoom_in)
        tb_layout.addWidget(self.lbl_zoom)
        tb_layout.addStretch(1)
        layout.addWidget(toolbar)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.viewport().installEventFilter(self)
        
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(10)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        
        self.scroll_area.setWidget(self.content_widget)
        layout.addWidget(self.scroll_area, stretch=1)
        
        self._page_labels: list[QLabel] = []

    def eventFilter(self, obj, event):
        if (
            obj == self.scroll_area.viewport()
            and event.type() == QEvent.Type.Wheel
            and event.modifiers() == Qt.KeyboardModifier.ControlModifier
        ):
            if event.angleDelta().y() > 0:
                self.zoom_in()
            else:
                self.zoom_out()
            return True
        return super().eventFilter(obj, event)

    @classmethod
    def can_handle(cls, path: Path, mime_type) -> bool:
        ext = path.suffix.lower()
        if mime_type.name() in (
            "application/pdf",
            "application/epub+zip",
            "application/x-mobipocket-ebook",
            "application/vnd.comicbook+zip",
            "application/vnd.ms-xpsdocument",
            "application/oxps",
            "application/x-fictionbook+xml",
        ):
            return True
        return ext in (".pdf", ".epub", ".mobi", ".fb2", ".cbz", ".xps", ".oxps")

    def load(self, path: Path) -> None:
        self._cancel_all_tasks()
        self._path = path
        self.doc = fitz.open(path)
        
        # Clear UI
        self._clear_layout()
        self._page_labels.clear()
        
        # Extract properties
        props = self.doc.metadata
        self.properties = {
            "title": props.get("title", ""),
            "author": props.get("author", ""),
            "pages": str(len(self.doc)),
        }
        
        # Create placeholders for pages
        for i in range(len(self.doc)):
            lbl = QLabel()
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            
            # Temporary size based on page unzoomed rect if possible
            try:
                rect = self.doc[i].rect
                lbl.setFixedSize(int(rect.width * self._zoom), int(rect.height * self._zoom))
                lbl.setStyleSheet("background-color: white; border: 1px solid #ccc;")
            except Exception:  # noqa: BLE001
                lbl.setFixedSize(400, 600)
                
            self.content_layout.addWidget(lbl)
            self._page_labels.append(lbl)
            
        self.load_async()

    def load_async(self) -> None:
        """Запускает рендеринг страниц в фоне."""
        if not self.doc or not self._path:
            return
            
        for i in range(len(self.doc)):
            task = RenderPageTask(self._path, i, self._zoom)
            task.signals.page_rendered.connect(self._on_page_rendered)
            self._tasks.append(task)
            QThreadPool.globalInstance().start(task)

    def _on_page_rendered(self, page_num: int, qimg: QImage):
        if page_num < len(self._page_labels):
            lbl = self._page_labels[page_num]
            pix = QPixmap.fromImage(qimg)
            lbl.setPixmap(pix)
            lbl.setFixedSize(pix.size())

    def _cancel_all_tasks(self):
        for task in self._tasks:
            task.is_cancelled = True
        self._tasks.clear()

    def _clear_layout(self):
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def zoom_in(self) -> None:
        self._zoom = min(10.0, self._zoom * 1.2)
        self._rerender()

    def zoom_out(self) -> None:
        self._zoom = max(0.1, self._zoom / 1.2)
        self._rerender()

    def zoom_reset(self) -> None:
        self._zoom = 1.0
        self._rerender()
        
    def _rerender(self):
        if not self._path or not self.doc:
            return
        self.lbl_zoom.setText(f"{int(self._zoom * 100)}%")
        self._cancel_all_tasks()
        # Resize labels to new expected sizes and clear pixmaps
        for i, lbl in enumerate(self._page_labels):
            lbl.clear()
            try:
                rect = self.doc[i].rect
                lbl.setFixedSize(int(rect.width * self._zoom), int(rect.height * self._zoom))
            except Exception:  # noqa: BLE001, S110
                pass
        self.load_async()

    def unload(self) -> None:
        self._cancel_all_tasks()
        if self.doc:
            self.doc.close()
            self.doc = None
        self._path = None
        self._clear_layout()
        self._page_labels.clear()
        super().unload()
