"""Миниатюры для дерева файлов: дисковый кэш, генерация, фоновая очередь.

Кэш — по `freedesktop thumbnail spec
<https://specifications.freedesktop.org/thumbnail-spec/latest/>`_:
``$XDG_CACHE_HOME/thumbnails/normal/<md5 от file-URI>.png`` (128×128), метаданные
``Thumb::URI`` / ``Thumb::MTime`` / ``Thumb::Size`` в tEXt-чанках PNG. Благодаря
этому миниатюры переживают перезапуск и их видят другие приложения, а изменение
исходного файла (mtime или размер) автоматически делает запись недействительной.

Генерация идёт мимо GUI-потока: изображения и документы — в собственном
``QThreadPool``, кадр видео — последовательно на GUI-потоке через
:class:`_VideoFrameGrabber` (медиаконвейер Qt асинхронен, а его плеер нельзя
уничтожать — см. ``viewers/media.py``). Вызывающий никогда не ждёт: пока
миниатюры нет, :meth:`ThumbnailManager.thumbnail_for` отдаёт ``None``, и дерево
рисует системную иконку.
"""

from __future__ import annotations

import atexit
import contextlib
import hashlib
import os
import tempfile
import threading
from pathlib import Path

from PyQt6.QtCore import (
    QObject,
    QRunnable,
    QSize,
    Qt,
    QThreadPool,
    QTimer,
    QUrl,
    pyqtSignal,
)
from PyQt6.QtGui import QImage, QImageReader, QPixmap

## @brief Сторона миниатюры: размер «normal» из freedesktop thumbnail spec.
THUMBNAIL_SIZE = 128

## @brief Предельное время ожидания кадра одного видео, мс.
VIDEO_FRAME_TIMEOUT_MS = 10_000

# Набор форматов именно для миниатюр — он уже, чем у просмотрщиков: звук
# картинки не имеет, а HEIC/AVIF/RAW требуют тяжёлых декодеров, которых в
# фоновой очереди мы избегаем. Не покрытые здесь типы остаются с системной
# иконкой — это штатное поведение, а не ошибка.
_IMAGE_SUFFIXES = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff", ".tif", ".ico", ".svg", ".svgz"}
)
_DOCUMENT_SUFFIXES = frozenset({".pdf", ".epub", ".mobi", ".fb2", ".cbz", ".xps", ".oxps"})
_VIDEO_SUFFIXES = frozenset({".mp4", ".mkv", ".avi", ".webm", ".mov"})

# PyMuPDF не рассчитан на параллельное открытие документов из разных потоков.
_DOCUMENT_LOCK = threading.Lock()


## @brief Канонический file-URI для пути (RFC 2396, как у ``g_file_get_uri``).
def file_uri(path: Path | str) -> str:
    return Path(path).resolve().as_uri()


## @brief Каталог кэша миниатюр размера «normal».
def cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "thumbnails" / "normal"


## @brief Путь к файлу миниатюры: md5 от file-URI, как требует спека.
def cache_path(path: Path | str) -> Path:
    digest = hashlib.md5(file_uri(path).encode("utf-8")).hexdigest()
    return cache_dir() / f"{digest}.png"


## @brief К какому способу генерации относится файл: image / document / video / None.
def kind_of(path: Path | str) -> str | None:
    suffix = Path(path).suffix.lower()
    if suffix in _IMAGE_SUFFIXES:
        return "image"
    if suffix in _DOCUMENT_SUFFIXES:
        return "document"
    if suffix in _VIDEO_SUFFIXES:
        return "video"
    return None


def _fit(image: QImage, size: int) -> QImage:
    if image.isNull() or max(image.width(), image.height()) <= size:
        return image
    return image.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def _generate_image(path: Path, size: int) -> QImage | None:
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)  # учитываем EXIF-ориентацию
    if not reader.canRead():
        return None
    source_size = reader.size()
    if source_size.isValid() and (source_size.width() > size or source_size.height() > size):
        # Масштабируем силами декодера: полноразмерная картинка в память не попадает.
        reader.setScaledSize(source_size.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio))
    elif not source_size.isValid():
        reader.setScaledSize(QSize(size, size))  # векторные форматы размера не сообщают
    image = reader.read()
    if image.isNull():
        return None
    return _fit(image, size)


def _generate_document(path: Path, size: int) -> QImage | None:
    import pymupdf

    with _DOCUMENT_LOCK, pymupdf.open(str(path)) as doc:
        if doc.page_count < 1:
            return None
        page = doc.load_page(0)
        rect = page.rect
        longest = max(rect.width, rect.height)
        zoom = size / longest if longest > 0 else 1.0
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        image = QImage(
            pixmap.samples,
            pixmap.width,
            pixmap.height,
            pixmap.stride,
            QImage.Format.Format_RGB888,
        ).copy()  # копия: буфер pixmap живёт только внутри блока
    if image.isNull():
        return None
    return _fit(image, size)


## @brief Построить миниатюру синхронно; ``None``, если формат не поддержан или файл битый.
#
# Безопасна для вызова из фонового потока. Видео сюда не попадает: его кадр
# добывается на GUI-потоке (см. :class:`_VideoFrameGrabber`).
def generate(path: Path | str, size: int = THUMBNAIL_SIZE) -> QImage | None:
    path = Path(path)
    kind = kind_of(path)
    try:
        if kind == "image":
            return _generate_image(path, size)
        if kind == "document":
            return _generate_document(path, size)
    except Exception:  # noqa: BLE001 — битый файл не должен ронять фоновую задачу
        return None
    return None


## @brief Дисковый кэш миниатюр по freedesktop thumbnail spec.
#
# Запись атомарна (временный файл рядом + ``os.replace``) и доступна только
# владельцу (0600), как требует спека. Чтение проверяет актуальность записи по
# ``Thumb::MTime`` и ``Thumb::Size``: изменился файл — запись считается
# недействительной, и миниатюра будет построена заново.
class ThumbnailCache:
    def __init__(self, size: int = THUMBNAIL_SIZE) -> None:
        self._size = size

    def load(self, path: Path | str) -> QImage | None:
        """Готовая миниатюра из кэша либо ``None`` (нет записи или устарела)."""
        entry = cache_path(path)
        if not entry.is_file():
            return None
        try:
            stat_result = Path(path).stat()
        except OSError:
            return None
        image = QImage(str(entry))
        if image.isNull():
            return None
        if image.text("Thumb::MTime") != str(int(stat_result.st_mtime)):
            return None
        stored_size = image.text("Thumb::Size")
        if stored_size and stored_size != str(stat_result.st_size):
            return None
        return image

    def store(self, path: Path | str, image: QImage) -> Path:
        """Записать миниатюру в кэш; возвращает путь записи."""
        entry = cache_path(path)
        entry.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(entry.parent, 0o700)

        stat_result = Path(path).stat()
        tagged = image.copy()
        tagged.setText("Thumb::URI", file_uri(path))
        tagged.setText("Thumb::MTime", str(int(stat_result.st_mtime)))
        tagged.setText("Thumb::Size", str(stat_result.st_size))
        tagged.setText("Software", "omniviewer")

        handle, temp_name = tempfile.mkstemp(dir=str(entry.parent), suffix=".png")
        os.close(handle)
        try:
            if not tagged.save(temp_name, "PNG"):
                raise OSError(f"не удалось записать миниатюру: {entry}")
            os.chmod(temp_name, 0o600)
            os.replace(temp_name, entry)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(temp_name)
            raise
        return entry


class _TaskSignals(QObject):
    done = pyqtSignal(str, object, int)  # путь, QImage|None, поколение очереди


class _ThumbnailTask(QRunnable):
    """Фоновая задача: взять миниатюру из кэша, иначе построить и положить в кэш."""

    def __init__(self, path: str, cache: ThumbnailCache, size: int, generation: int) -> None:
        super().__init__()
        self._path = path
        self._cache = cache
        self._size = size
        self._generation = generation
        # Объект сигналов создаётся в GUI-потоке — доставка будет очередью.
        self.signals = _TaskSignals()
        self.setAutoDelete(True)

    def run(self) -> None:
        image: QImage | None = None
        try:
            image = self._cache.load(self._path)
            if image is None:
                image = generate(self._path, self._size)
                if image is not None and not image.isNull():
                    self._cache.store(self._path, image)
        except Exception:  # noqa: BLE001 — падение задачи не должно ронять пул
            image = None
        try:
            self.signals.done.emit(self._path, image, self._generation)
        except RuntimeError:  # менеджер уже уничтожен
            pass


## @brief Последовательный извлекатель кадра видео на GUI-потоке.
#
# Медиаконвейер Qt асинхронен, поэтому кадр нельзя получить внутри фоновой
# задачи. Плеер создаётся один раз и не уничтожается никогда: его разрушение при
# живом конвейере намертво вешает GUI-поток (подробности — в ``viewers/media.py``).
# Запросы обслуживаются по одному, зависший файл снимается по таймауту.
class _VideoFrameGrabber(QObject):
    frame_ready = pyqtSignal(str, object)  # путь, QImage|None

    def __init__(self, size: int = THUMBNAIL_SIZE) -> None:
        super().__init__()
        from PyQt6.QtMultimedia import QMediaPlayer, QVideoSink

        self._size = size
        self._queue: list[str] = []
        self._current: str | None = None

        self._sink = QVideoSink()
        self._player = QMediaPlayer()
        self._player.setVideoSink(self._sink)
        # Звуковой выход не подключаем — миниатюра не должна ничего проигрывать.
        self._sink.videoFrameChanged.connect(self._on_frame)
        self._player.errorOccurred.connect(self._on_error)

        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.setInterval(VIDEO_FRAME_TIMEOUT_MS)
        self._timeout.timeout.connect(self._on_timeout)

    def request(self, path: str) -> None:
        self._queue.append(path)
        if self._current is None:
            self._start_next()

    def clear(self) -> None:
        self._queue.clear()

    def _start_next(self) -> None:
        if not self._queue:
            self._current = None
            return
        self._current = self._queue.pop(0)
        self._player.setSource(QUrl.fromLocalFile(self._current))
        self._player.play()
        self._timeout.start()

    def _finish(self, image: QImage | None) -> None:
        path, self._current = self._current, None
        self._timeout.stop()
        self._player.stop()
        if path is not None:
            self.frame_ready.emit(path, image)
        # Следующий файл — через цикл событий, чтобы не рекурсировать в обработчике.
        QTimer.singleShot(0, self._start_next)

    def _on_frame(self, frame) -> None:
        if self._current is None or not frame.isValid():
            return
        image = frame.toImage()
        if image.isNull():
            return
        self._finish(_fit(image, self._size))

    def _on_error(self, *_args) -> None:
        if self._current is not None:
            self._finish(None)

    def _on_timeout(self) -> None:
        if self._current is not None:
            self._finish(None)


_POOL: QThreadPool | None = None


## @brief Общий на процесс пул под миниатюры.
#
# Пул намеренно живёт вне менеджера и не уничтожается: его разрушение из Python
# зовёт ``waitForDone()``, не отпуская GIL, а фоновой задаче GIL нужен, чтобы
# доложить о результате — получается взаимная блокировка. Отдельный от
# ``QThreadPool.globalInstance()`` пул нужен, чтобы очередь миниатюр не
# конкурировала с тяжёлым рендером просмотрщиков (``viewers/base.py``).
def thumbnail_pool() -> QThreadPool:
    global _POOL
    if _POOL is None:
        _POOL = QThreadPool()
        _POOL.setMaxThreadCount(max(1, min(4, os.cpu_count() or 2)))
        # На выходе гасим очередь явно: обычный вызов метода отпускает GIL, а
        # разрушение пула при живых задачах — нет (см. комментарий выше).
        atexit.register(shutdown_thumbnails)
    return _POOL


## @brief Снять очередь и дождаться фоновых задач (вызывать при закрытии окна).
def shutdown_thumbnails(timeout_ms: int = 3000) -> None:
    if _POOL is not None:
        _POOL.clear()
        _POOL.waitForDone(timeout_ms)


_VIDEO_GRABBER: _VideoFrameGrabber | None = None


def video_grabber() -> _VideoFrameGrabber:
    """Общий на процесс извлекатель кадров (плеер Qt создаётся ровно один раз)."""
    global _VIDEO_GRABBER
    if _VIDEO_GRABBER is None:
        _VIDEO_GRABBER = _VideoFrameGrabber()
    return _VIDEO_GRABBER


## @brief Менеджер миниатюр: неблокирующая выдача + фоновая очередь.
#
# :meth:`thumbnail_for` отвечает мгновенно: готовая миниатюра — ``QPixmap``,
# иначе ``None`` и постановка в очередь. Когда миниатюра построена, испускается
# :data:`thumbnail_ready` с путём — дерево по нему перерисовывает строку.
# Повторные запросы того же пути не плодят задач, файлы без миниатюры
# запоминаются и больше не опрашиваются, а :meth:`clear_queue` снимает хвост
# задач при смене папки.
class ThumbnailManager(QObject):
    thumbnail_ready = pyqtSignal(str)

    def __init__(self, enabled: bool = False, size: int = THUMBNAIL_SIZE, parent=None) -> None:
        super().__init__(parent)
        self._enabled = bool(enabled)
        self._size = size
        self._cache = ThumbnailCache(size)
        self._memory: dict[str, QPixmap] = {}
        self._unsupported: set[str] = set()
        self._pending: set[str] = set()
        self._generation = 0
        self._video_connected = False  # медиастек Qt поднимаем только под видео

    # ─── Состояние режима ───────────────────────────────────────────────── #

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, value: bool) -> None:
        """Включить/выключить режим; выключение снимает всю фоновую работу."""
        value = bool(value)
        if value == self._enabled:
            return
        self._enabled = value
        if not value:
            self.clear_queue()

    # ─── Выдача ─────────────────────────────────────────────────────────── #

    def thumbnail_for(self, path: Path | str) -> QPixmap | None:
        """Миниатюра, если она уже готова; иначе ``None`` и постановка в очередь."""
        if not self._enabled:
            return None
        key = str(path)
        ready = self._memory.get(key)
        if ready is not None:
            return ready
        if key in self._unsupported or key in self._pending:
            return None
        if kind_of(key) is None:
            self._unsupported.add(key)
            return None
        self._enqueue(key)
        return None

    def pending_count(self) -> int:
        """Сколько путей ждёт своей миниатюры."""
        return len(self._pending)

    def clear_queue(self) -> None:
        """Снять все незавершённые запросы (например, при смене папки)."""
        self._generation += 1
        self._pending.clear()
        thumbnail_pool().clear()
        if _VIDEO_GRABBER is not None:
            _VIDEO_GRABBER.clear()

    # ─── Внутреннее ─────────────────────────────────────────────────────── #

    def _enqueue(self, key: str) -> None:
        self._pending.add(key)
        if kind_of(key) == "video":
            grabber = video_grabber()
            if not self._video_connected:
                grabber.frame_ready.connect(self._on_video_frame)
                self._video_connected = True
            grabber.request(key)
            return
        task = _ThumbnailTask(key, self._cache, self._size, self._generation)
        task.signals.done.connect(self._on_task_done)
        thumbnail_pool().start(task)

    def _on_task_done(self, key: str, image, generation: int) -> None:
        if generation != self._generation:
            return  # очередь была сброшена — результат уже никому не нужен
        self._pending.discard(key)
        self._remember(key, image)

    def _on_video_frame(self, key: str, image) -> None:
        if key not in self._pending:
            return
        self._pending.discard(key)
        if image is not None and not image.isNull():
            try:
                self._cache.store(key, image)
            except OSError:
                pass
        self._remember(key, image)

    def _remember(self, key: str, image) -> None:
        if image is None or image.isNull():
            self._unsupported.add(key)
            return
        self._memory[key] = QPixmap.fromImage(image)
        self.thumbnail_ready.emit(key)
