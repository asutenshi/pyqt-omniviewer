from pathlib import Path

from PyQt6.QtCore import QMimeType
from PyQt6.QtWidgets import QWidget


## @brief Базовый класс для всех просмотрщиков файлов.
#
# Определяет интерфейс: поддерживаемые MIME-типы, расширения, приоритет,
# методы can_handle, load, load_async и cancel.
class BaseViewer(QWidget):
    mime_types: tuple[str, ...] = ()
    extensions: tuple[str, ...] = ()
    priority: int = 0

    @classmethod
    def can_handle(cls, path: Path, mime: QMimeType | str) -> bool:
        """
        Проверяет, может ли просмотрщик обработать файл с заданным путем и MIME-типом.
        Учитывает наследование MIME-типов и расширения файлов.
        """
        mime_name = mime.name() if isinstance(mime, QMimeType) else str(mime)

        # 1. Точное совпадение MIME или поддержка всех типов
        if "*/*" in cls.mime_types or mime_name in cls.mime_types:
            return True

        # 2. Проверка наследования MIME (если передан QMimeType)
        if isinstance(mime, QMimeType):
            for t in cls.mime_types:
                if mime.inherits(t):
                    return True

        # 3. Запасной матч по расширению
        suffix = path.suffix.lower()
        return bool(suffix and suffix in cls.extensions)

    def load(self, path: Path) -> None:
        """Синхронная лёгкая подготовка / загрузка файла."""

    def load_async(self) -> None:
        """Тяжёлый рендер в QThreadPool (опционально)."""

    def cancel(self) -> None:
        """Отмена фоновых операций при смене выбора."""
