"""Просмотрщик структуры: JSON / YAML / XML / TOML сворачиваемым деревом.

Разбирает документ (``json`` / :mod:`yaml` / ``defusedxml`` / ``tomllib``) и
показывает его деревом «ключ → значение → тип». Узлы-контейнеры строятся
**лениво** — дети создаются только при разворачивании узла, и не больше
``MAX_CHILDREN`` на узел (остальное — строкой «… ещё N»), поэтому большой файл
не подвешивает GUI. Кнопка переключает дерево и исходный текст. Битый документ
валит разбор — ``BaseViewer`` отдаёт «ошибочный» виджет.
"""

from __future__ import annotations

import json
from pathlib import Path
from xml.etree.ElementTree import Element

from defusedxml.ElementTree import fromstring as _xml_fromstring
from PyQt6.QtCore import QMimeType, Qt
from PyQt6.QtWidgets import QPlainTextEdit, QPushButton, QTreeWidget, QTreeWidgetItem

from omniviewer.viewers.base import BaseViewer

_JSON_SUFFIXES = (".json",)
_YAML_SUFFIXES = (".yaml", ".yml")
_XML_SUFFIXES = (".xml",)
_TOML_SUFFIXES = (".toml",)

_JSON_MIMES = frozenset({"application/json", "text/json"})
_YAML_MIMES = frozenset(
    {"application/x-yaml", "application/yaml", "text/yaml", "text/x-yaml"}
)
_XML_MIMES = frozenset({"application/xml", "text/xml"})
_TOML_MIMES = frozenset({"application/toml", "text/x-toml"})

_ROLE_OBJ = Qt.ItemDataRole.UserRole
_ROLE_PENDING = Qt.ItemDataRole.UserRole + 1


def _typename(value: object) -> str:
    if isinstance(value, Element):
        return "element"
    if isinstance(value, bool):
        return "bool"
    if value is None:
        return "null"
    return type(value).__name__


def _is_container(value: object) -> bool:
    if isinstance(value, dict):
        return bool(value)
    if isinstance(value, (list, tuple)):
        return bool(value)
    if isinstance(value, Element):
        return bool(value.attrib) or bool((value.text or "").strip()) or len(value) > 0
    return False


def _iter_children(value: object):
    """Выдаёт ``(ключ, значение, тип)`` для узла-контейнера (без создания виджетов)."""
    if isinstance(value, dict):
        for key, sub in value.items():
            yield str(key), sub, _typename(sub)
    elif isinstance(value, (list, tuple)):
        for index, sub in enumerate(value):
            yield f"[{index}]", sub, _typename(sub)
    elif isinstance(value, Element):
        for name, attr_value in value.attrib.items():
            yield f"@{name}", attr_value, "attr"
        text = (value.text or "").strip()
        if text:
            yield "#text", text, "text"
        for child in value:
            yield child.tag, child, "element"


def _summary(value: object) -> str:
    if isinstance(value, dict):
        return f"{{{len(value)}}}"
    if isinstance(value, (list, tuple)):
        return f"[{len(value)}]"
    if isinstance(value, Element):
        return f"<{value.tag}> ({len(value)})"
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, bytes):
        return value.hex(" ")[:200]
    text = str(value)
    return text if len(text) <= 200 else text[:200] + "…"


## @brief Просмотрщик JSON / YAML / XML / TOML в виде сворачиваемого дерева.
#
# Дерево строится лениво (дети — по событию разворачивания) с пределом
# ``MAX_CHILDREN`` детей на узел, что защищает GUI от зависания на больших
# документах. Кнопка переключает представление «дерево ⇄ исходный текст».
class StructureViewer(BaseViewer):
    mime_types = tuple(_JSON_MIMES | _YAML_MIMES | _XML_MIMES | _TOML_MIMES)
    extensions = _JSON_SUFFIXES + _YAML_SUFFIXES + _XML_SUFFIXES + _TOML_SUFFIXES
    priority = 20

    ## @brief Максимум детей, строящихся под одним узлом (остальное — «… ещё N»).
    MAX_CHILDREN = 1000
    ## @brief Порог показа исходного текста в режиме «Текст».
    MAX_TEXT_BYTES = 4 * 1024 * 1024

    def __init__(self):
        super().__init__()
        self._layout.setContentsMargins(0, 0, 0, 0)

        self._toggle = QPushButton("Показать текст")
        self._toggle.clicked.connect(self._on_toggle)
        self._layout.addWidget(self._toggle)

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Ключ", "Значение", "Тип"])
        self._tree.setColumnCount(3)
        self._tree.itemExpanded.connect(self._on_expanded)
        self._layout.addWidget(self._tree)

        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._text.hide()
        self._layout.addWidget(self._text)

        self._raw_text: str = ""
        self._text_mode = False
        self.kind: str = ""
        self.data: object = None

    # ------------------------------------------------------------------ #
    # Диспетчеризация                                                    #
    # ------------------------------------------------------------------ #

    @classmethod
    def can_handle(cls, path: Path, mime: QMimeType | str) -> bool:
        if path.suffix.lower() in cls.extensions:
            return True
        mime_name = mime.name() if isinstance(mime, QMimeType) else str(mime)
        return mime_name in cls.mime_types

    # ------------------------------------------------------------------ #
    # Загрузка                                                           #
    # ------------------------------------------------------------------ #

    def load(self, path: Path) -> None:
        raw = path.read_bytes()
        self.kind = self._detect_kind(path.suffix.lower(), raw)
        self.data = self._parse(self.kind, raw)

        self._raw_text = (
            raw.decode("utf-8", errors="replace")
            if len(raw) <= self.MAX_TEXT_BYTES
            else f"[файл {len(raw)} Б — слишком большой для текстового режима]"
        )

        self._tree.clear()
        root = QTreeWidgetItem([path.name, _summary(self.data), _typename(self.data)])
        self._tree.addTopLevelItem(root)
        if _is_container(self.data):
            root.setData(0, _ROLE_OBJ, self.data)
            root.setData(0, _ROLE_PENDING, True)
            root.addChild(QTreeWidgetItem(["…", "", ""]))
            root.setExpanded(True)

    @staticmethod
    def _detect_kind(suffix: str, raw: bytes) -> str:
        if suffix in _JSON_SUFFIXES:
            return "json"
        if suffix in _YAML_SUFFIXES:
            return "yaml"
        if suffix in _XML_SUFFIXES:
            return "xml"
        if suffix in _TOML_SUFFIXES:
            return "toml"
        head = raw.lstrip()[:1]
        if head == b"<":
            return "xml"
        if head in (b"{", b"["):
            return "json"
        return "yaml"

    @staticmethod
    def _parse(kind: str, raw: bytes) -> object:
        if kind == "json":
            return json.loads(raw.decode("utf-8"))
        if kind == "toml":
            try:
                import tomllib  # Python 3.11+
            except ModuleNotFoundError:  # pragma: no cover - для 3.10
                import tomli as tomllib
            return tomllib.loads(raw.decode("utf-8"))
        if kind == "xml":
            return _xml_fromstring(raw.decode("utf-8", errors="replace"))
        import yaml

        return yaml.safe_load(raw.decode("utf-8", errors="replace"))

    # ------------------------------------------------------------------ #
    # Ленивое построение дерева                                          #
    # ------------------------------------------------------------------ #

    def _on_expanded(self, item: QTreeWidgetItem) -> None:
        if not item.data(0, _ROLE_PENDING):
            return
        item.setData(0, _ROLE_PENDING, False)
        item.takeChildren()

        value = item.data(0, _ROLE_OBJ)
        shown = 0
        total = 0
        for key, sub, typ in _iter_children(value):
            total += 1
            if shown >= self.MAX_CHILDREN:
                continue
            child = QTreeWidgetItem([key, _summary(sub), typ])
            if _is_container(sub):
                child.setData(0, _ROLE_OBJ, sub)
                child.setData(0, _ROLE_PENDING, True)
                child.addChild(QTreeWidgetItem(["…", "", ""]))
            item.addChild(child)
            shown += 1
        if total > shown:
            item.addChild(QTreeWidgetItem([f"… ещё {total - shown}", "", ""]))

    # ------------------------------------------------------------------ #
    # Переключатель                                                      #
    # ------------------------------------------------------------------ #

    def _on_toggle(self) -> None:
        self._text_mode = not self._text_mode
        if self._text_mode and not self._text.toPlainText():
            self._text.setPlainText(self._raw_text)
        self._tree.setVisible(not self._text_mode)
        self._text.setVisible(self._text_mode)
        self._toggle.setText("Показать дерево" if self._text_mode else "Показать текст")
