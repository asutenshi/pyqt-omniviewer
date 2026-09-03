from PyQt6.QtWidgets import QLabel

from .base import BaseViewer


## @brief Fallback-просмотрщик для нераспознанных файлов.
#
# Загружается, когда ни один другой просмотрщик не подошел по типу файла.
class FallbackViewer(BaseViewer):
    priority = -100

    @classmethod
    def can_handle(cls, path: str, mime: str) -> bool:
        return True

    def load(self, path: str):
        label = QLabel("Отображение не поддерживается (Fallback Viewer)")
        self._layout.addWidget(label)
