# ruff: noqa: BLE001
"""Тесты для просмотрщика офисных документов (DOCX, DOC, ODT, RTF).

Проверяем:
- диспетчеризацию реестра (правильный класс по расширению/MIME);
- загрузку каждого формата без ошибок;
- сохранение базовой структуры (заголовки, списки) в DOCX/ODT;
- извлечение читаемого текста из DOC/RTF;
- метаданные документов (автор, заголовок);
- корректную обработку битых образцов (is_error_widget, не падает).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

DEMO_DIR = Path(__file__).parent.parent / "demo"


@pytest.fixture(scope="session", autouse=True)
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


@pytest.fixture
def registry():
    from omniviewer.registry import ViewerRegistry

    return ViewerRegistry()


# --------------------------------------------------------------------------- #
# Диспетчеризация реестра: формат → правильный класс просмотрщика             #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "rel_path",
    [
        "documents/sample.docx",
        "documents/sample.doc",
        "documents/sample.odt",
        "documents/sample.rtf",
    ],
)
def test_registry_returns_document_viewer(registry, rel_path):
    """Реестр для каждого офисного формата возвращает DocumentViewer."""
    from omniviewer.viewers.document import DocumentViewer

    full = DEMO_DIR / rel_path
    viewer = registry.viewer_for(full)
    assert isinstance(viewer, DocumentViewer), (
        f"Ожидался DocumentViewer для {rel_path}, получен {type(viewer).__name__}"
    )


# --------------------------------------------------------------------------- #
# Загрузка: содержимое без ошибок                                              #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "rel_path",
    [
        "documents/sample.docx",
        "documents/sample.doc",
        "documents/sample.odt",
        "documents/sample.rtf",
    ],
)
def test_smoke_load_document(qapp, registry, rel_path):
    """Загрузка каждого формата проходит без ошибки."""
    full = DEMO_DIR / rel_path
    viewer = registry.viewer_for(full)
    viewer.safe_load(full)
    assert not viewer.is_error_widget, (
        f"Ошибка при загрузке {rel_path}: {viewer.error_message}"
    )


# --------------------------------------------------------------------------- #
# Структура DOCX: заголовки, списки                                            #
# --------------------------------------------------------------------------- #


def test_docx_has_heading(qapp, registry):
    """DOCX содержит заголовок документа в отрендеренном HTML."""
    from omniviewer.viewers.document import DocumentViewer

    viewer = DocumentViewer()
    viewer.load(DEMO_DIR / "documents/sample.docx")
    assert not viewer.is_error_widget
    html = viewer.rendered_html.lower()
    assert "заголовок документа" in html or "заголовок" in html


def test_docx_has_list_items(qapp, registry):
    """DOCX содержит элементы списка."""
    from omniviewer.viewers.document import DocumentViewer

    viewer = DocumentViewer()
    viewer.load(DEMO_DIR / "documents/sample.docx")
    html = viewer.rendered_html.lower()
    assert "первый пункт" in html
    assert "второй пункт" in html


def test_docx_has_embedded_image(qapp, registry):
    """DOCX содержит встроенные изображения (img tag с data:-URI)."""
    from omniviewer.viewers.document import DocumentViewer

    viewer = DocumentViewer()
    viewer.load(DEMO_DIR / "documents/sample.docx")
    assert "<img" in viewer.rendered_html
    assert "data:image/" in viewer.rendered_html


# --------------------------------------------------------------------------- #
# Извлечение текста из DOC                                                     #
# --------------------------------------------------------------------------- #


def test_doc_has_readable_text(qapp, registry):
    """Legacy .doc содержит читаемый извлечённый текст."""
    from omniviewer.viewers.document import DocumentViewer

    viewer = DocumentViewer()
    viewer.load(DEMO_DIR / "documents/sample.doc")
    assert not viewer.is_error_widget
    html = viewer.rendered_html.lower()
    assert "заголовок" in html or "doc" in html


# --------------------------------------------------------------------------- #
# ODT: текст с абзацами/списками                                              #
# --------------------------------------------------------------------------- #


def test_odt_has_heading(qapp, registry):
    """ODT содержит заголовок."""
    from omniviewer.viewers.document import DocumentViewer

    viewer = DocumentViewer()
    viewer.load(DEMO_DIR / "documents/sample.odt")
    assert not viewer.is_error_widget
    html = viewer.rendered_html.lower()
    assert "заголовок" in html


def test_odt_has_list_items(qapp, registry):
    """ODT содержит элементы списка."""
    from omniviewer.viewers.document import DocumentViewer

    viewer = DocumentViewer()
    viewer.load(DEMO_DIR / "documents/sample.odt")
    html = viewer.rendered_html.lower()
    assert "первый пункт" in html


# --------------------------------------------------------------------------- #
# RTF: читаемый текст                                                         #
# --------------------------------------------------------------------------- #


def test_rtf_has_readable_text(qapp, registry):
    """RTF открывается как читаемый текст."""
    from omniviewer.viewers.document import DocumentViewer

    viewer = DocumentViewer()
    viewer.load(DEMO_DIR / "documents/sample.rtf")
    assert not viewer.is_error_widget
    html = viewer.rendered_html.lower()
    assert "заголовок" in html or "rtf" in html


# --------------------------------------------------------------------------- #
# Метаданные документов                                                        #
# --------------------------------------------------------------------------- #


def test_docx_metadata():
    """Метаданные DOCX: автор и заголовок."""
    from omniviewer.metadata import metadata_for

    meta = metadata_for(str(DEMO_DIR / "documents/sample.docx"))
    # python-docx заполняет title/author
    assert any("omniviewer" in str(v).lower() or "demo" in str(v).lower() for v in meta.values()), (
        f"Ожидались метаданные с 'omniviewer' или 'demo', получены: {meta}"
    )


def test_odt_metadata():
    """Метаданные ODT: автор."""
    from omniviewer.metadata import metadata_for

    meta = metadata_for(str(DEMO_DIR / "documents/sample.odt"))
    assert meta.get("Author") == "Omniviewer Demo"


def test_rtf_metadata():
    """Метаданные RTF: заголовок и автор."""
    from omniviewer.metadata import metadata_for

    meta = metadata_for(str(DEMO_DIR / "documents/sample.rtf"))
    assert meta.get("Title") == "Демонстрационный RTF"
    assert meta.get("Author") == "Omniviewer Demo"


# --------------------------------------------------------------------------- #
# Битые образцы → ошибочный виджет, не падает                                  #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "rel_path",
    [
        "broken/truncated.docx",
        "broken/truncated.doc",
        "broken/truncated.odt",
    ],
)
def test_broken_document_shows_error(qapp, registry, rel_path):
    """Битый образец DOCX/DOC/ODT → ошибочный виджет, без исключения."""
    full = DEMO_DIR / rel_path
    viewer = registry.viewer_for(full)
    try:
        viewer.safe_load(full)
        assert viewer.is_error_widget, (
            f"Ожидался ошибочный виджет для {rel_path}"
        )
    except Exception as e:
        pytest.fail(f"Просмотрщик упал на битом файле {rel_path}: {e}")


def test_broken_rtf_does_not_crash(qapp, registry):
    """Битый RTF не падает (striprtf извлекает что может, как TextViewer)."""
    full = DEMO_DIR / "broken/truncated.rtf"
    viewer = registry.viewer_for(full)
    try:
        viewer.safe_load(full)
        # striprtf не бросает на обрезанном RTF — это нормально
    except Exception as e:
        pytest.fail(f"Просмотрщик упал на битом RTF: {e}")
