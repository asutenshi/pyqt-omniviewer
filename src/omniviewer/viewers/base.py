# ruff: noqa: BLE001
import traceback
from collections.abc import Callable

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal
from PyQt6.QtWidgets import QLabel, QTextBrowser, QVBoxLayout, QWidget


class WorkerSignals(QObject):
    """Signals for the background worker."""
    finished = pyqtSignal(object)
    error = pyqtSignal(Exception, str)

class Worker(QRunnable):
    """Worker for executing heavy render tasks in a QThreadPool."""
    def __init__(self, fn: Callable, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self.is_cancelled = False
        # QRunnable has autoDelete True by default.
        self.setAutoDelete(True)

    def run(self):
        try:
            if self.is_cancelled:
                return
            result = self.fn(*self.args, **self.kwargs)
            if self.is_cancelled:
                return
            self.signals.finished.emit(result)
        except Exception as e:
            if self.is_cancelled:
                return
            tb = traceback.format_exc()
            try:
                self.signals.error.emit(e, tb)
            except RuntimeError:
                pass

## @brief Базовый класс для всех просмотрщиков.
#
# Предоставляет инфраструктуру асинхронной загрузки через QThreadPool
# и универсальный механизм отображения ошибок при сбоях загрузки.
class BaseViewer(QWidget):
    mime_types: tuple[str, ...] = ()
    extensions: tuple[str, ...] = ()
    priority: int = 0

    @classmethod
    def can_handle(cls, path: str, mime: str) -> bool:
        """Определяет, может ли просмотрщик открыть данный файл."""
        from pathlib import Path
        ext = Path(path).suffix.lower()
        if mime and mime in cls.mime_types:
            return True
        return bool(ext and ext in cls.extensions)

    def __init__(self):
        super().__init__()
        self.is_error_widget = False
        self.error_message = ""
        self._current_worker: Worker | None = None
        self._active_workers: set[Worker] = set()
        self._layout = QVBoxLayout(self)

    def safe_load(self, path: str):
        """Безопасная обертка для load, перехватывающая исключения."""
        try:
            self.load(path)
        except Exception as e:
            self._show_error(e, traceback.format_exc())

    def load(self, path: str):
        """Синхронная загрузка, переопределяемая в наследниках."""

    def safe_load_async(self):
        """Безопасная обертка для load_async, перехватывающая исключения до запуска потока."""
        try:
            self.load_async()
        except Exception as e:
            self._show_error(e, traceback.format_exc())

    def load_async(self):
        """Тяжелый рендер, переопределяемый в наследниках (должен вызывать _start_async)."""

    def _start_async(self, fn: Callable, on_success: Callable):
        """
        Запускает функцию fn в QThreadPool. При успехе результат передается в on_success
        (выполняется в GUI-потоке). При исключении - виджет переводится в состояние ошибки.
        """
        self.cancel()
        worker = Worker(fn)
        self._current_worker = worker
        self._active_workers.add(worker)

        def _on_finished(result):
            self._active_workers.discard(worker)
            if worker is self._current_worker and not worker.is_cancelled:
                on_success(result)

        def _on_error(e, tb):
            self._active_workers.discard(worker)
            if worker is self._current_worker and not worker.is_cancelled:
                self._show_error(e, tb)

        worker.signals.finished.connect(_on_finished)
        worker.signals.error.connect(_on_error)
        QThreadPool.globalInstance().start(worker)

    def cancel(self):
        """Отменяет текущую асинхронную задачу."""
        if self._current_worker:
            self._current_worker.is_cancelled = True
            self._current_worker = None

    def _show_error(self, e: Exception, tb: str):
        """Отображает сообщение об ошибке с разворачиваемой трассировкой."""
        self.is_error_widget = True
        self.error_message = str(e)
        
        # Очищаем текущий макет
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        error_label = QLabel(f"<b>Ошибка загрузки:</b> {e}")
        error_label.setWordWrap(True)
        self._layout.addWidget(error_label)
        
        trace = QTextBrowser()
        trace.setText(tb)
        self._layout.addWidget(trace)
