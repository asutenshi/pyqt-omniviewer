from PyQt6.QtCore import QSettings


class AppSettings:
    """Управление настройками приложения через QSettings."""
    def __init__(self):
        self._settings = QSettings("OmniViewer", "OmniViewerApp")

    @property
    def max_text_read_bytes(self) -> int:
        return int(self._settings.value("limits/max_text_read_bytes", 5 * 1024 * 1024))

    @max_text_read_bytes.setter
    def max_text_read_bytes(self, val: int):
        self._settings.setValue("limits/max_text_read_bytes", val)

    @property
    def max_image_dimension(self) -> int:
        return int(self._settings.value("limits/max_image_dimension", 8000))

    @max_image_dimension.setter
    def max_image_dimension(self, val: int):
        self._settings.setValue("limits/max_image_dimension", val)
