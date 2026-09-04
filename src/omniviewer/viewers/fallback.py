from pathlib import Path

from PyQt6.QtCore import QFileInfo, QMimeDatabase, Qt
from PyQt6.QtGui import QFont, QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QHeaderView,
    QLabel,
    QSplitter,
    QTableView,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from omniviewer.viewers.base import BaseViewer


## @brief Fallback-просмотрщик для любых типов файлов.
#
# Показывает окно первых N КБ текстом, hex-дамп с ASCII-колонкой,
# таблицу базовых метаданных (размер, MIME, даты) и — для бинарных форматов,
# которые распознаёт hachoir — разобранное дерево полей. Нераспознанный формат
# просто не получает дерева: hex и метаданные остаются.
class FallbackViewer(BaseViewer):
    mime_types: tuple[str, ...] = ("*/*",)
    extensions: tuple[str, ...] = ()
    priority: int = -100

    ## @brief Файлы крупнее этого не отдаём в hachoir (защита от долгого разбора).
    MAX_HACHOIR_BYTES = 64 * 1024 * 1024
    ## @brief Совокупный предел числа узлов дерева полей.
    MAX_HACHOIR_NODES = 4000
    ## @brief Предел детей одного узла дерева полей.
    MAX_HACHOIR_SIBLINGS = 512
    ## @brief Предел глубины дерева полей.
    MAX_HACHOIR_DEPTH = 8

    def __init__(self, parent=None, max_preview_bytes: int = 16 * 1024):
        super().__init__()
        self.max_preview_bytes = max_preview_bytes
        self._hachoir_nodes = 0

        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(4)

        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self._layout.addWidget(self.splitter)

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

        # 4. Дерево полей hachoir (только если формат распознан)
        self.hachoir_widget = QWidget()
        hachoir_layout = QVBoxLayout(self.hachoir_widget)
        hachoir_layout.setContentsMargins(0, 0, 0, 0)
        hachoir_layout.addWidget(QLabel("Дерево полей (hachoir):"))
        self.hachoir_tree = QTreeWidget()
        self.hachoir_tree.setHeaderLabels(["Поле", "Значение", "Описание"])
        self.hachoir_tree.setColumnCount(3)
        hachoir_layout.addWidget(self.hachoir_tree)
        self.splitter.addWidget(self.hachoir_widget)
        self.hachoir_widget.hide()

        self.splitter.setSizes([150, 200, 150, 200])

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

        # 4. Дерево полей hachoir
        self._populate_hachoir(path)

    def _populate_hachoir(self, path: Path) -> None:
        """Разобрать файл hachoir'ом и показать дерево полей; при неудаче — скрыть.

        Никогда не бросает: нераспознанный или проблемный формат просто остаётся
        без дерева (hex + метаданные уже показаны).
        """
        self.hachoir_tree.clear()
        self.hachoir_widget.hide()
        self._hachoir_nodes = 0
        try:
            if not path.is_file() or path.stat().st_size > self.MAX_HACHOIR_BYTES:
                return
            from hachoir.core import config as hachoir_config
            from hachoir.field import FieldSet
            from hachoir.parser import createParser

            hachoir_config.quiet = True
            parser = createParser(str(path))
            if parser is None:
                return
            with parser:
                root = QTreeWidgetItem([
                    getattr(parser, "description", None) or path.name, "", ""
                ])
                self.hachoir_tree.addTopLevelItem(root)
                self._fill_hachoir(root, parser, FieldSet, depth=0)
                root.setExpanded(True)
            if root.childCount() > 0:
                self.hachoir_widget.show()
        except Exception:  # noqa: BLE001 - hachoir не должен ронять fallback
            self.hachoir_tree.clear()
            self.hachoir_widget.hide()

    def _fill_hachoir(self, parent_item, fieldset, field_set_cls, depth: int) -> None:
        if depth > self.MAX_HACHOIR_DEPTH:
            return
        for siblings, field in enumerate(fieldset):
            if self._hachoir_nodes >= self.MAX_HACHOIR_NODES:
                return
            if siblings >= self.MAX_HACHOIR_SIBLINGS:
                parent_item.addChild(QTreeWidgetItem(["…", "", ""]))
                return
            self._hachoir_nodes += 1

            is_set = isinstance(field, field_set_cls)
            try:
                value = "" if is_set else str(field.display)
            except Exception:  # noqa: BLE001
                value = "?"
            node = QTreeWidgetItem([
                field.name, value, getattr(field, "description", "") or ""
            ])
            parent_item.addChild(node)

            if is_set:
                try:
                    self._fill_hachoir(node, field, field_set_cls, depth + 1)
                except Exception:  # noqa: BLE001
                    node.addChild(QTreeWidgetItem(["[ошибка разбора]", "", ""]))
