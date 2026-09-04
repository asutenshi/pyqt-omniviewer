"""Просмотрщик шрифтов: TTF / OTF / WOFF / WOFF2.

Показывает образец начертания (панграммы и набор букв/цифр в нескольких кеглях
выбранным шрифтом) и таблицу метаданных из :mod:`fontTools` (семейство,
начертание, версия, число глифов, единицы на em, тип контуров, состав таблиц).

Загрузка в Qt: TTF/OTF отдаются в ``QFontDatabase.addApplicationFont`` напрямую;
WOFF/WOFF2 (и всё, что Qt не принял) пересобираются :mod:`fontTools` во временный
sfnt (``.ttf``/``.otf``) и грузятся уже из него. Битый файл валит ``TTFont`` —
``BaseViewer`` отдаёт «ошибочный» виджет.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path

from PyQt6.QtCore import QMimeType, Qt
from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from omniviewer.viewers.base import BaseViewer

_FONT_SUFFIXES = (".ttf", ".otf", ".ttc", ".otc", ".woff", ".woff2")
_WEB_FONT_SUFFIXES = (".woff", ".woff2")
_FONT_MIMES = frozenset(
    {
        "font/ttf",
        "font/otf",
        "font/woff",
        "font/woff2",
        "font/sfnt",
        "font/collection",
        "application/font-woff",
        "application/font-woff2",
        "application/font-sfnt",
        "application/x-font-ttf",
        "application/x-font-otf",
        "application/x-font-truetype",
        "application/x-font-opentype",
        "application/vnd.ms-opentype",
        "application/vnd.ms-fontobject",
    }
)

_PANGRAMS = (
    "The quick brown fox jumps over the lazy dog",
    "Съешь же ещё этих мягких французских булок, да выпей чаю",
)
_ALPHABET = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "abcdefghijklmnopqrstuvwxyz",
    "0123456789   .,:;!?()[]{}/&@#$%",
)
_SAMPLE_SIZES = (12, 16, 20, 28, 40, 56)


## @brief Просмотрщик образца начертания шрифта и его метаданных.
#
# Регистрирует шрифт в QFontDatabase (WOFF/WOFF2 предварительно распаковываются
# fontTools во временный sfnt), рисует панграммы и алфавит несколькими кеглями
# этим шрифтом и выводит таблицу метаданных из fontTools.
class FontViewer(BaseViewer):
    mime_types = tuple(_FONT_MIMES)
    extensions = _FONT_SUFFIXES
    priority = 30

    def __init__(self):
        super().__init__()
        self._layout.setContentsMargins(0, 0, 0, 0)

        self._font_id: int = -1
        self._tmp_path: str | None = None

        self.font_family: str = ""
        self.metadata: dict[str, str] = {}
        self.glyph_count: int = 0
        self.sample_sizes: tuple[int, ...] = _SAMPLE_SIZES

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._layout.addWidget(self._scroll)

    # ------------------------------------------------------------------ #
    # Диспетчеризация                                                    #
    # ------------------------------------------------------------------ #

    @classmethod
    def can_handle(cls, path: Path, mime: QMimeType | str) -> bool:
        if path.suffix.lower() in cls.extensions:
            return True
        mime_name = mime.name() if isinstance(mime, QMimeType) else str(mime)
        return mime_name in _FONT_MIMES

    # ------------------------------------------------------------------ #
    # Загрузка                                                           #
    # ------------------------------------------------------------------ #

    def load(self, path: Path) -> None:
        from fontTools.ttLib import TTFont

        font = TTFont(str(path), fontNumber=0, lazy=True)
        try:
            self.metadata = self._extract_metadata(font, path)
            self.glyph_count = int(font["maxp"].numGlyphs)
        finally:
            font.close()

        self.font_family = self._register_with_qt(path)
        self._build_ui()

    def _extract_metadata(self, font, path: Path) -> dict[str, str]:
        name = font["name"]

        def nm(*ids: int) -> str:
            for i in ids:
                value = name.getDebugName(i)
                if value:
                    return value
            return ""

        is_cff = "CFF " in font or "CFF2" in font
        upm = int(font["head"].unitsPerEm) if "head" in font else 0
        tags = [tag.strip() for tag in sorted(font.keys()) if tag.strip() != "GlyphOrder"]
        tables = ", ".join(tags)

        meta: dict[str, str] = {
            "Семейство": nm(16, 1),
            "Начертание": nm(17, 2) or "Regular",
            "Полное имя": nm(4),
            "Версия": nm(5) or (f"{font['head'].fontRevision:.3f}" if "head" in font else ""),
            "Число глифов": str(int(font["maxp"].numGlyphs)),
            "Единиц на em": str(upm),
            "Тип контуров": "PostScript / CFF" if is_cff else "TrueType",
            "Формат файла": path.suffix.lower().lstrip(".").upper() or "SFNT",
            "Таблицы": tables,
        }
        for label, name_id in (("Производитель", 8), ("Копирайт", 0), ("Лицензия", 13)):
            value = nm(name_id)
            if value:
                meta[label] = value
        return {k: v for k, v in meta.items() if v}

    def _register_with_qt(self, path: Path) -> str:
        suffix = path.suffix.lower()
        font_id = -1
        if suffix not in _WEB_FONT_SUFFIXES:
            font_id = QFontDatabase.addApplicationFont(str(path))

        if font_id == -1:
            self._tmp_path = self._to_sfnt(path)
            font_id = QFontDatabase.addApplicationFont(self._tmp_path)

        if font_id == -1:
            raise ValueError("Qt не смог загрузить шрифт")

        self._font_id = font_id
        families = QFontDatabase.applicationFontFamilies(font_id)
        if not families:
            raise ValueError("В шрифте не найдено семейство")
        return families[0]

    @staticmethod
    def _to_sfnt(path: Path) -> str:
        """Пересобрать шрифт в несжатый sfnt во временный файл, вернуть путь."""
        from fontTools.ttLib import TTFont

        font = TTFont(str(path), fontNumber=0)
        font.flavor = None
        suffix = ".otf" if ("CFF " in font or "CFF2" in font) else ".ttf"
        fd, tmp = tempfile.mkstemp(prefix="omniviewer-font-", suffix=suffix)
        os.close(fd)
        font.save(tmp)
        font.close()
        return tmp

    # ------------------------------------------------------------------ #
    # UI                                                                 #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(14)

        title = QLabel(self.font_family or "Шрифт")
        title.setFont(QFont(self.font_family, 40))
        title.setWordWrap(True)
        outer.addWidget(title)

        outer.addWidget(self._metadata_widget())
        outer.addWidget(self._separator())

        for size in self.sample_sizes:
            row = QLabel(f"{size}px  ·  {_PANGRAMS[0]}")
            row.setFont(QFont(self.font_family, size))
            row.setWordWrap(True)
            row.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            outer.addWidget(row)

        outer.addWidget(self._separator())

        ru = QLabel(_PANGRAMS[1])
        ru.setFont(QFont(self.font_family, 24))
        ru.setWordWrap(True)
        outer.addWidget(ru)

        for line in _ALPHABET:
            lbl = QLabel(line)
            lbl.setFont(QFont(self.font_family, 22))
            lbl.setWordWrap(True)
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            outer.addWidget(lbl)

        outer.addStretch(1)
        self._scroll.setWidget(page)

    def _metadata_widget(self) -> QWidget:
        box = QWidget()
        grid = QGridLayout(box)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(4)
        for r, (key, value) in enumerate(self.metadata.items()):
            k = QLabel(f"{key}:")
            k.setStyleSheet("color:#666")
            v = QLabel(value)
            v.setWordWrap(True)
            v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            grid.addWidget(k, r, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
            grid.addWidget(v, r, 1)
        grid.setColumnStretch(1, 1)
        return box

    @staticmethod
    def _separator() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        return line

    # ------------------------------------------------------------------ #
    # Очистка                                                            #
    # ------------------------------------------------------------------ #

    def _release(self) -> None:
        if self._font_id != -1:
            QFontDatabase.removeApplicationFont(self._font_id)
            self._font_id = -1
        if self._tmp_path:
            with contextlib.suppress(OSError):
                os.unlink(self._tmp_path)
            self._tmp_path = None

    def closeEvent(self, event):
        self._release()
        super().closeEvent(event)

    def __del__(self):
        with contextlib.suppress(Exception):
            self._release()
