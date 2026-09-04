"""Тесты «разобрать структуру»: StructureViewer (JSON/YAML/XML/TOML) и
дерево полей hachoir в FallbackViewer.

Поведение проверяется через главный шов ``ViewerRegistry`` и публичный API:

* реестр отдаёт ``StructureViewer`` по json/yaml/xml/toml (приоритет выше текста);
* документ показывается деревом «ключ → значение → тип»;
* большой файл строится лениво и с пределом детей на узел — GUI не виснет;
* переключатель «дерево ⇄ текст»;
* битый документ → «ошибочный» виджет;
* FallbackViewer показывает дерево полей hachoir для разбираемого бинарника и
  спокойно обходится без него для непрозрачного.
"""

from __future__ import annotations

import struct
import sys
import time
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

from omniviewer.registry import ViewerRegistry
from omniviewer.viewers.fallback import FallbackViewer
from omniviewer.viewers.structure import StructureViewer


@pytest.fixture(scope="session", autouse=True)
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture
def registry() -> ViewerRegistry:
    return ViewerRegistry()


def _root(viewer: StructureViewer):
    return viewer._tree.topLevelItem(0)


def _child_by_key(item, key: str):
    for i in range(item.childCount()):
        if item.child(i).text(0) == key:
            return item.child(i)
    return None


def _midi_bytes() -> bytes:
    track = b"\x00\xff\x03\x03mid\x00\x90\x3c\x40\x60\x80\x3c\x40\x00\xff\x2f\x00"
    return b"MThd" + struct.pack(">IHHH", 6, 0, 1, 96) + b"MTrk" + struct.pack(">I", len(track)) + track


# --------------------------------------------------------------------------- #
# Диспетчеризация                                                             #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("a.json", b'{"k": 1}'),
        ("a.yaml", b"k: 1\n"),
        ("a.yml", b"k: 1\n"),
        ("a.xml", b"<root><k>1</k></root>"),
        ("a.toml", b'k = 1\n'),
    ],
)
def test_registry_selects_structure_viewer(registry, tmp_path: Path, name, content) -> None:
    p = tmp_path / name
    p.write_bytes(content)
    assert isinstance(registry.viewer_for(p), StructureViewer)


def test_structure_viewer_outranks_text_for_json(registry, tmp_path: Path) -> None:
    p = tmp_path / "x.json"
    p.write_bytes(b'{"a": 1}')
    viewer = registry.viewer_for(p)
    assert type(viewer).__name__ == "StructureViewer"


# --------------------------------------------------------------------------- #
# Дерево структуры                                                            #
# --------------------------------------------------------------------------- #


def test_json_tree_key_value(tmp_path: Path) -> None:
    p = tmp_path / "d.json"
    p.write_bytes(b'{"name": "demo", "count": 3, "nested": {"inner": 7}, "list": [10, 20]}')
    viewer = StructureViewer()
    viewer.safe_load(p)

    assert not viewer.is_error_widget
    root = _root(viewer)
    assert root.isExpanded()

    name_item = _child_by_key(root, "name")
    assert name_item is not None and name_item.text(1) == "demo" and name_item.text(2) == "str"

    count_item = _child_by_key(root, "count")
    assert count_item.text(1) == "3" and count_item.text(2) == "int"

    nested = _child_by_key(root, "nested")
    assert nested.text(1) == "{1}"
    nested.setExpanded(True)  # ленивое достроение по разворачиванию
    inner = _child_by_key(nested, "inner")
    assert inner is not None and inner.text(1) == "7"

    lst = _child_by_key(root, "list")
    assert lst.text(1) == "[2]"
    lst.setExpanded(True)
    assert _child_by_key(lst, "[0]").text(1) == "10"
    assert _child_by_key(lst, "[1]").text(1) == "20"


def test_yaml_tree(tmp_path: Path) -> None:
    p = tmp_path / "d.yaml"
    p.write_bytes(b"name: demo\ntags:\n  - a\n  - b\n")
    viewer = StructureViewer()
    viewer.safe_load(p)
    assert not viewer.is_error_widget
    root = _root(viewer)
    assert _child_by_key(root, "name").text(1) == "demo"
    tags = _child_by_key(root, "tags")
    tags.setExpanded(True)
    assert tags.childCount() == 2


def test_toml_tree(tmp_path: Path) -> None:
    p = tmp_path / "d.toml"
    p.write_bytes(b'title = "demo"\n[owner]\nname = "me"\n')
    viewer = StructureViewer()
    viewer.safe_load(p)
    assert not viewer.is_error_widget
    root = _root(viewer)
    assert _child_by_key(root, "title").text(1) == "demo"
    owner = _child_by_key(root, "owner")
    owner.setExpanded(True)
    assert _child_by_key(owner, "name").text(1) == "me"


def test_xml_tree_with_attributes_and_text(tmp_path: Path) -> None:
    p = tmp_path / "d.xml"
    p.write_bytes(b'<catalog name="demo"><item id="1">first</item></catalog>')
    viewer = StructureViewer()
    viewer.safe_load(p)
    assert not viewer.is_error_widget
    root = _root(viewer)

    assert _child_by_key(root, "@name").text(1) == "demo"
    item = _child_by_key(root, "item")
    assert item is not None
    item.setExpanded(True)
    assert _child_by_key(item, "@id").text(1) == "1"
    assert _child_by_key(item, "#text").text(1) == "first"


# --------------------------------------------------------------------------- #
# Большой файл: ленивое построение + лимит                                     #
# --------------------------------------------------------------------------- #


def test_large_file_is_lazy_and_capped(tmp_path: Path) -> None:
    import json

    big = {f"key_{i:05d}": {"i": i, "sq": i * i} for i in range(5000)}
    p = tmp_path / "big.json"
    p.write_bytes(json.dumps(big).encode())

    viewer = StructureViewer()
    start = time.monotonic()
    viewer.safe_load(p)
    elapsed = time.monotonic() - start

    assert not viewer.is_error_widget
    assert elapsed < 5.0  # не подвешивает

    root = _root(viewer)
    # первый уровень построен, но не больше лимита (+1 маркер «… ещё N»)
    assert root.childCount() <= viewer.MAX_CHILDREN + 1
    assert root.child(root.childCount() - 1).text(0).startswith("… ещё")

    # вложенный узел не достроен, пока его не развернули
    first_container = None
    for i in range(root.childCount()):
        if root.child(i).text(1) == "{2}":
            first_container = root.child(i)
            break
    assert first_container is not None
    assert first_container.childCount() == 1
    assert first_container.child(0).text(0) == "…"


def test_deep_nodes_build_only_on_expand(tmp_path: Path) -> None:
    p = tmp_path / "deep.json"
    p.write_bytes(b'{"outer": {"inner": {"x": 1}}}')
    viewer = StructureViewer()
    viewer.safe_load(p)

    root = _root(viewer)
    outer = _child_by_key(root, "outer")
    assert outer.childCount() == 1 and outer.child(0).text(0) == "…"

    outer.setExpanded(True)
    inner = _child_by_key(outer, "inner")
    assert inner.childCount() == 1 and inner.child(0).text(0) == "…"

    inner.setExpanded(True)
    assert _child_by_key(inner, "x").text(1) == "1"


# --------------------------------------------------------------------------- #
# Переключатель и ошибки                                                      #
# --------------------------------------------------------------------------- #


def test_toggle_between_tree_and_text(tmp_path: Path) -> None:
    p = tmp_path / "t.json"
    p.write_bytes(b'{"hello": "world"}')
    viewer = StructureViewer()
    viewer.safe_load(p)

    assert viewer._tree.isVisibleTo(viewer)
    viewer._toggle.click()
    assert not viewer._tree.isVisibleTo(viewer)
    assert viewer._text.isVisibleTo(viewer)
    assert '"hello"' in viewer._text.toPlainText()

    viewer._toggle.click()
    assert viewer._tree.isVisibleTo(viewer)
    assert not viewer._text.isVisibleTo(viewer)


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("bad.json", b'{"a": 1, '),
        ("bad.xml", b"<root><unclosed>"),
        ("bad.toml", b'name = "demo\nversion = [1, 2'),
    ],
)
def test_broken_document_yields_error_widget(tmp_path: Path, name, content) -> None:
    p = tmp_path / name
    p.write_bytes(content)
    viewer = StructureViewer()
    viewer.safe_load(p)
    assert viewer.is_error_widget


def test_empty_yaml_is_not_an_error(tmp_path: Path) -> None:
    p = tmp_path / "empty.yaml"
    p.write_bytes(b"")
    viewer = StructureViewer()
    viewer.safe_load(p)
    assert not viewer.is_error_widget


# --------------------------------------------------------------------------- #
# hachoir-дерево в FallbackViewer                                             #
# --------------------------------------------------------------------------- #


def test_fallback_shows_hachoir_tree_for_parsable_binary(registry, tmp_path: Path) -> None:
    p = tmp_path / "exotic.mid"
    p.write_bytes(_midi_bytes())

    viewer = registry.viewer_for(p)
    assert isinstance(viewer, FallbackViewer)
    viewer.safe_load(p)

    assert not viewer.is_error_widget
    assert not viewer.hachoir_widget.isHidden()
    assert viewer.hachoir_tree.topLevelItemCount() == 1
    assert viewer.hachoir_tree.topLevelItem(0).childCount() > 0
    # hex-дамп по-прежнему на месте
    assert viewer.hex_dump.toPlainText().strip()


def test_fallback_opaque_binary_has_no_tree_but_no_error(tmp_path: Path) -> None:
    p = tmp_path / "opaque.bin"
    p.write_bytes(b"OPAQUE\x00\x01\x02\x03" * 32)

    viewer = FallbackViewer()
    viewer.safe_load(p)

    assert not viewer.is_error_widget
    assert viewer.hachoir_widget.isHidden()
    assert viewer.hachoir_tree.topLevelItemCount() == 0
    assert viewer.hex_dump.toPlainText().strip()
    assert viewer.metadata_table.model() is not None


def test_fallback_hachoir_node_budget_is_respected(tmp_path: Path) -> None:
    p = tmp_path / "exotic.mid"
    p.write_bytes(_midi_bytes())
    viewer = FallbackViewer()
    viewer.safe_load(p)
    assert viewer._hachoir_nodes <= viewer.MAX_HACHOIR_NODES
