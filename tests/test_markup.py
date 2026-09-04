"""Тесты просмотрщика разметки (issue #17).

Поведение проверяется через главный шов ``ViewerRegistry`` и публичный API
``MarkupViewer``: рендер Markdown (заголовки, списки, таблицы, подсветка кода),
показ HTML/XHTML, распаковка MHTML с инлайном ресурсов, офлайн-политика (внешние
ресурсы не грузятся), «ошибочный» виджет на битом MHTML. Отдельно — переиспользуемый
хелпер «HTML-строка → QTextBrowser».
"""

from __future__ import annotations

import base64
import sys
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import pytest
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QTextDocument
from PyQt6.QtWidgets import QApplication, QTextBrowser

from omniviewer.registry import ViewerRegistry
from omniviewer.viewers.html_render import build_html_browser
from omniviewer.viewers.markup import MarkupViewer

# PNG 1×1 (прозрачный) — CC0, для инлайна в MHTML.
_PNG_1X1 = base64.b64decode(
    b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

_IMG_RESOURCE = QTextDocument.ResourceType.ImageResource.value


@pytest.fixture(scope="session", autouse=True)
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture
def registry() -> ViewerRegistry:
    return ViewerRegistry()


# --------------------------------------------------------------------------- #
# Помощники                                                                   #
# --------------------------------------------------------------------------- #


def _make_mhtml(html: str, image_name: str | None = None) -> bytes:
    root = MIMEMultipart("related", boundary="----=_omniviewer_test")
    root.attach(MIMEText(html, "html", "utf-8"))
    if image_name:
        img = MIMEImage(_PNG_1X1, "png")
        img.add_header("Content-Location", image_name)
        root.attach(img)
    return root.as_bytes()


# --------------------------------------------------------------------------- #
# Диспетчеризация                                                             #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "name",
    ["a.md", "a.markdown", "page.html", "page.htm", "page.xhtml", "archive.mhtml", "archive.mht"],
)
def test_registry_selects_markup_viewer(registry: ViewerRegistry, tmp_path: Path, name: str) -> None:
    p = tmp_path / name
    p.write_bytes(b"# hi\n" if name.endswith((".md", ".markdown")) else b"<html><body>hi</body></html>")
    assert isinstance(registry.viewer_for(p), MarkupViewer)


def test_markup_viewer_does_not_steal_plain_text_or_xml(registry: ViewerRegistry, tmp_path: Path) -> None:
    for name, body in (("notes.txt", b"just text"), ("data.xml", b"<?xml version='1.0'?><r/>")):
        p = tmp_path / name
        p.write_bytes(body)
        assert not isinstance(registry.viewer_for(p), MarkupViewer), name


# --------------------------------------------------------------------------- #
# Markdown                                                                    #
# --------------------------------------------------------------------------- #


def test_markdown_renders_structure(tmp_path: Path) -> None:
    md = tmp_path / "doc.md"
    md.write_text(
        "# Заголовок\n\n"
        "- пункт один\n- пункт два\n\n"
        "| столбец | значение |\n|---|---|\n| a | 1 |\n\n"
        "```python\ndef foo():\n    return 42\n```\n",
        encoding="utf-8",
    )
    viewer = MarkupViewer()
    viewer.safe_load(md)

    assert not viewer.is_error_widget
    html = viewer.rendered_html
    assert "<h1" in html
    assert "<ul" in html and "<li" in html
    assert "<table" in html and "<td" in html
    # текст реально дошёл до виджета
    plain = viewer._browser.toPlainText()
    assert "Заголовок" in plain and "пункт один" in plain


def test_markdown_code_block_is_highlighted(tmp_path: Path) -> None:
    md = tmp_path / "code.md"
    md.write_text("```python\ndef foo():\n    return 42\n```\n", encoding="utf-8")
    viewer = MarkupViewer()
    viewer.safe_load(md)

    assert not viewer.is_error_widget
    # pygments c noclasses=True встраивает цвета инлайном
    assert '<span style="color' in viewer.rendered_html


def test_code_block_sets_explicit_text_colour_for_dark_theme(tmp_path: Path) -> None:
    """Регрессия: на тёмной теме QTextBrowser блок кода красил бы текст в белый
    поверх светлого фона (pygments с noclasses красит только распознанные токены).
    Обёртка <pre> должна задавать цвет текста явно."""
    md = tmp_path / "code.md"
    md.write_text("```python\nx = 1\n```\n", encoding="utf-8")
    viewer = MarkupViewer()
    viewer.safe_load(md)

    assert not viewer.is_error_widget
    assert "color:#1a1a1a" in viewer.rendered_html


def test_fenced_block_with_unknown_language_is_wrapped_and_escaped(tmp_path: Path) -> None:
    """Блок с неизвестным языком тоже оборачивается в стилизованный <pre> (а не
    отдаётся сырым) и экранируется."""
    md = tmp_path / "u.md"
    md.write_text("```nosuchlang-xyz\n<b> & </b>\n```\n", encoding="utf-8")
    viewer = MarkupViewer()
    viewer.safe_load(md)

    assert not viewer.is_error_widget
    html = viewer.rendered_html
    assert "color:#1a1a1a" in html
    assert "&lt;b&gt;" in html and "&amp;" in html


# --------------------------------------------------------------------------- #
# HTML / XHTML                                                                #
# --------------------------------------------------------------------------- #


def test_html_file_is_displayed(tmp_path: Path) -> None:
    p = tmp_path / "page.html"
    p.write_text(
        "<html><head><title>t</title></head><body><h2>Ключевой текст</h2></body></html>",
        encoding="utf-8",
    )
    viewer = MarkupViewer()
    viewer.safe_load(p)

    assert not viewer.is_error_widget
    assert "Ключевой текст" in viewer._browser.toPlainText()


def test_xhtml_file_is_displayed(tmp_path: Path) -> None:
    p = tmp_path / "page.xhtml"
    p.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml"><body><p>XHTML абзац</p></body></html>',
        encoding="utf-8",
    )
    viewer = MarkupViewer()
    viewer.safe_load(p)

    assert not viewer.is_error_widget
    assert "XHTML абзац" in viewer._browser.toPlainText()


# --------------------------------------------------------------------------- #
# MHTML                                                                       #
# --------------------------------------------------------------------------- #


def test_mhtml_inlines_embedded_resource(tmp_path: Path) -> None:
    p = tmp_path / "saved.mhtml"
    p.write_bytes(
        _make_mhtml(
            '<html><body><h3>Сохранённая страница</h3><img src="pic.png"></body></html>',
            image_name="pic.png",
        )
    )
    viewer = MarkupViewer()
    viewer.safe_load(p)

    assert not viewer.is_error_widget
    assert "Сохранённая страница" in viewer._browser.toPlainText()
    # ресурс кадра MHTML доступен браузеру по имени из src=
    data = viewer._browser.loadResource(_IMG_RESOURCE, QUrl("pic.png"))
    assert bytes(data) == _PNG_1X1


def test_broken_mhtml_yields_error_widget(tmp_path: Path) -> None:
    p = tmp_path / "broken.mhtml"
    # обрезано по заголовкам — HTML-части нет
    p.write_bytes(_make_mhtml("<html><body>x</body></html>", image_name="x.png")[:90])
    viewer = MarkupViewer()
    viewer.safe_load(p)

    assert viewer.is_error_widget


# --------------------------------------------------------------------------- #
# Офлайн-политика                                                             #
# --------------------------------------------------------------------------- #


def test_external_network_resource_is_not_loaded(tmp_path: Path) -> None:
    p = tmp_path / "remote.html"
    p.write_text(
        '<html><body><img src="http://example.invalid/tracker.png"></body></html>',
        encoding="utf-8",
    )
    viewer = MarkupViewer()
    viewer.safe_load(p)

    assert not viewer.is_error_widget
    data = viewer._browser.loadResource(_IMG_RESOURCE, QUrl("http://example.invalid/tracker.png"))
    assert bytes(data) == b""


# --------------------------------------------------------------------------- #
# Переиспользуемый хелпер «HTML → QTextBrowser»                               #
# --------------------------------------------------------------------------- #


def test_build_html_browser_returns_readonly_offline_widget() -> None:
    browser = build_html_browser("<h1>Привет</h1><p>тело</p>")
    assert isinstance(browser, QTextBrowser)
    assert browser.isReadOnly()
    assert browser.openExternalLinks() is False
    assert "Привет" in browser.toPlainText()


def test_build_html_browser_serves_local_resources_only() -> None:
    browser = build_html_browser("<img src='logo.png'>", resources={"logo.png": _PNG_1X1})
    assert bytes(browser.loadResource(_IMG_RESOURCE, QUrl("logo.png"))) == _PNG_1X1
    assert bytes(browser.loadResource(_IMG_RESOURCE, QUrl("https://cdn.example/logo.png"))) == b""


def test_build_html_browser_decodes_data_uri() -> None:
    b64 = base64.b64encode(_PNG_1X1).decode("ascii")
    browser = build_html_browser(f'<img src="data:image/png;base64,{b64}">')
    got = browser.loadResource(_IMG_RESOURCE, QUrl(f"data:image/png;base64,{b64}"))
    assert bytes(got) == _PNG_1X1
