from pathlib import Path

from PyQt6.QtCore import QMimeDatabase

from omniviewer.viewers.archive import ArchiveViewer
from omniviewer.viewers.base import BaseViewer
from omniviewer.viewers.fallback import FallbackViewer
from omniviewer.viewers.image import ImageViewer
from omniviewer.viewers.markup import MarkupViewer
from omniviewer.viewers.media import MediaViewer
from omniviewer.viewers.pdf import PdfViewer
from omniviewer.viewers.spreadsheet import SpreadsheetViewer
from omniviewer.viewers.text import TextViewer


## @brief Реестр просмотрщиков файлов.
#
# Отвечает за сопоставление файлов с соответствующими классами просмотрщиков
# на основе MIME-типа (с контентным сниффингом и наследованием), расширения и приоритета.
class ViewerRegistry:
    def __init__(self):
        self._viewers: list[type[BaseViewer]] = []
        self._mime_db = QMimeDatabase()
        # Регистрируем FallbackViewer по умолчанию
        self.register(FallbackViewer)
        self.register(TextViewer)
        self.register(ImageViewer)
        self.register(PdfViewer)
        self.register(SpreadsheetViewer)
        self.register(MediaViewer)
        self.register(ArchiveViewer)
        self.register(MarkupViewer)

    def register(self, viewer_cls: type[BaseViewer]) -> None:
        """Регистрирует класс просмотрщика в реестре."""
        if viewer_cls not in self._viewers:
            self._viewers.append(viewer_cls)

    def viewer_for(self, path: Path) -> BaseViewer:
        """
        Возвращает экземпляр подходящего BaseViewer для заданного пути.
        При ошибке или нераспознанном типе возвращается FallbackViewer.
        """
        viewer_cls = self.find_viewer_class(path)
        if viewer_cls is None:
            return FallbackViewer()
        try:
            return viewer_cls()
        except Exception:  # noqa: BLE001
            return FallbackViewer()

    def find_viewer_class(self, path: Path) -> type[BaseViewer]:
        """
        Находит класс просмотрщика с наивысшим приоритетом для заданного пути.
        Определяет MIME-тип с помощью контентного сниффинга (QMimeDatabase.MatchDefault).
        При неоднозначности используется запасной поиск по расширению.
        """
        path_str = str(path)
        mime_type = self._mime_db.mimeTypeForFile(path_str, QMimeDatabase.MatchMode.MatchDefault)

        # Кандидаты, удовлетворяющие can_handle
        candidates: list[type[BaseViewer]] = []

        for cls in self._viewers:
            if cls.can_handle(path, mime_type):
                candidates.append(cls)

        if not candidates:
            # Запасная проверка чисто по расширению (MatchExtension) если контент дал неизвестно
            ext_mime = self._mime_db.mimeTypeForFile(
                path_str, QMimeDatabase.MatchMode.MatchExtension
            )
            for cls in self._viewers:
                if cls.can_handle(path, ext_mime):
                    candidates.append(cls)

        if not candidates:
            return FallbackViewer

        # Выбираем обработчик с максимальным приоритетом
        candidates.sort(key=lambda c: c.priority, reverse=True)
        return candidates[0]


# Глобальный синглтон реестра
default_registry = ViewerRegistry()
