from pathlib import Path

from PyQt6.QtCore import QFileInfo, QMimeDatabase, Qt
from PyQt6.QtGui import QFont, QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QHeaderView,
    QLabel,
    QSplitter,
    QTableView,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from omniviewer.viewers.base import BaseViewer


## @brief Fallback-просмотрщик для любых типов файлов.
#
# Показывает окно первых N КБ текстом, hex-дамп с ASCII-колонкой
# и таблицу базовых метаданных (размер, MIME, даты).
class FallbackViewer(BaseViewer):
    mime_types: tuple[str, ...] = ("*/*",)
    extensions: tuple[str, ...] = ()
    priority: int = -100

    def __init__(self, parent=None, max_preview_bytes: int = 16 * 1024):
        super().__init__(parent)
        self.max_preview_bytes = max_preview_bytes

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self.splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(self.splitter)

        # 1. Текстовое превью
        text_widget = QWidget()
        text_layout = QVBoxLayout(text_widget)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.addWidget(QLabel("Текстовый предпросмотр (первые КБ):"))
        self.text_preview = QTextEdit()
        self.text_preview.setReadOnly(True)
        self.text_preview.setFontFamily("monospace")
        text_layout.addWidget(self.text_preview)
        self.splitter.addWidget(text_widget)

        # 2. Hex-дамп с ASCII
        hex_widget = QWidget()
        hex_layout = QVBoxLayout(hex_widget)
        hex_layout.setContentsMargins(0, 0, 0, 0)
        hex_layout.addWidget(QLabel("Hex-дамп:"))
        self.hex_dump = QTextEdit()
        self.hex_dump.setReadOnly(True)
        font = QFont("monospace")
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.hex_dump.setFont(font)
        hex_layout.addWidget(self.hex_dump)
        self.splitter.addWidget(hex_widget)

        # 3. Метаданные (таблица)
        meta_widget = QWidget()
        meta_layout = QVBoxLayout(meta_widget)
        meta_layout.setContentsMargins(0, 0, 0, 0)
        meta_layout.addWidget(QLabel("Метаданные файла:"))
        self.metadata_table = QTableView()
        self.metadata_table.setAlternatingRowColors(True)
        self.metadata_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        meta_layout.addWidget(self.metadata_table)
        self.splitter.addWidget(meta_widget)

        self.splitter.setSizes([150, 200, 150])

    def load(self, path: Path) -> None:
        raw_bytes = b""
        if path.is_file():
            try:
                with open(path, "rb") as f:
                    raw_bytes = f.read(self.max_preview_bytes)
            except OSError as e:
                raw_bytes = f"Ошибка чтения: {e}".encode("utf-8", errors="replace")

        # 1. Текст
        try:
            text_content = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text_content = raw_bytes.decode("latin-1", errors="replace")
        self.text_preview.setPlainText(text_content)

        # 2. Hex-дамп
        hex_lines = []
        for offset in range(0, len(raw_bytes), 16):
            chunk = raw_bytes[offset : offset + 16]
            hex_part = " ".join(f"{b:02x}" for b in chunk)
            ascii_part = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
            hex_lines.append(f"{offset:08x}  {hex_part:<48}  |{ascii_part}|")
        self.hex_dump.setPlainText("\n".join(hex_lines))

        # 3. Метаданные
        info = QFileInfo(str(path))
        mime_db = QMimeDatabase()
        mime_type = mime_db.mimeTypeForFile(str(path), QMimeDatabase.MatchMode.MatchDefault)

        model = QStandardItemModel(self)
        model.setHorizontalHeaderLabels(["Свойство", "Значение"])

        props = [
            ("Имя", info.fileName()),
            ("Путь", info.absoluteFilePath()),
            ("Размер", f"{info.size()} байт"),
            ("MIME-тип", mime_type.name()),
            (
                "Создан",
                info.birthTime().toString(Qt.DateFormat.ISODate)
                if info.birthTime().isValid()
                else "-",
            ),
            (
                "Изменен",
                info.lastModified().toString(Qt.DateFormat.ISODate)
                if info.lastModified().isValid()
                else "-",
            ),
            (
                "Прочитан",
                info.lastRead().toString(Qt.DateFormat.ISODate)
                if info.lastRead().isValid()
                else "-",
            ),
        ]

        for prop_name, prop_val in props:
            item_key = QStandardItem(prop_name)
            item_key.setEditable(False)
            item_val = QStandardItem(str(prop_val))
            item_val.setEditable(False)
            model.appendRow([item_key, item_val])

        self.metadata_table.setModel(model)
