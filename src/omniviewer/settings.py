from pathlib import Path

from PyQt6.QtCore import QByteArray, QSettings


class AppSettings:
    """Управление настройками приложения через QSettings."""
    def __init__(self):
        # Хранение — QSettings (INI в ~/.config)
        self._settings = QSettings(
            QSettings.Format.IniFormat,
            QSettings.Scope.UserScope,
            "OmniViewer",
            "OmniViewerApp"
        )

    @property
    def window_geometry(self) -> QByteArray:
        return self._settings.value("ui/window_geometry", QByteArray())

    @window_geometry.setter
    def window_geometry(self, val: QByteArray):
        self._settings.setValue("ui/window_geometry", val)

    @property
    def last_opened_dir(self) -> Path:
        val = self._settings.value("state/last_opened_dir", str(Path.home()))
        return Path(val)

    @last_opened_dir.setter
    def last_opened_dir(self, val: Path):
        self._settings.setValue("state/last_opened_dir", str(val))

    @property
    def sort_field(self) -> str:
        return self._settings.value("tree/sort_field", "name")

    @sort_field.setter
    def sort_field(self, val: str):
        self._settings.setValue("tree/sort_field", val)

    @property
    def sort_direction(self) -> int:
        return int(self._settings.value("tree/sort_direction", 0))

    @sort_direction.setter
    def sort_direction(self, val: int):
        self._settings.setValue("tree/sort_direction", int(val))

    @property
    def folders_on_top(self) -> bool:
        return str(self._settings.value("tree/folders_on_top", "true")).lower() == "true"

    @folders_on_top.setter
    def folders_on_top(self, val: bool):
        self._settings.setValue("tree/folders_on_top", val)

    @property
    def tree_on_left(self) -> bool:
        return str(self._settings.value("ui/tree_on_left", "false")).lower() == "true"

    @tree_on_left.setter
    def tree_on_left(self, val: bool):
        self._settings.setValue("ui/tree_on_left", val)

    @property
    def thumbnail_mode(self) -> bool:
        return str(self._settings.value("ui/thumbnail_mode", "false")).lower() == "true"

    @thumbnail_mode.setter
    def thumbnail_mode(self, val: bool):
        self._settings.setValue("ui/thumbnail_mode", val)

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
