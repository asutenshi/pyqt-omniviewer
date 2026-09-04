"""Тесты просмотрщика Jupyter-ноутбуков (.ipynb).

Поведение проверяется через главный шов ``ViewerRegistry`` и публичный API
``IpynbViewer``:

* реестр отдаёт ``IpynbViewer`` по ``.ipynb`` и не трогает обычный JSON;
* ячейки рендерятся в порядке следования, счётчик ячеек верен;
* Markdown-ячейки отрендерены, ячейки кода подсвечены pygments;
* текстовый вывод (stream, execute_result) и вывод-картинка (data:-URI) видны;
* внешние сетевые ресурсы не загружаются;
* битый / не-ноутбучный JSON → «ошибочный» виджет.
"""

from __future__ import annotations

import base64
import re
import sys
from pathlib import Path

import nbformat
import pytest
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QColor, QPalette, QTextDocument
from PyQt6.QtWidgets import QApplication

from omniviewer.registry import ViewerRegistry
from omniviewer.viewers.ipynb import IpynbViewer

_IMG_RESOURCE = QTextDocument.ResourceType.ImageResource.value

_PNG_1X1 = base64.b64decode(
    b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


@pytest.fixture(scope="session", autouse=True)
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture
def registry() -> ViewerRegistry:
    return ViewerRegistry()


@pytest.fixture
def dark_qt_theme(qapp):
    """Форсировать тёмную палитру Qt на время теста (тёмный QPalette.Base)."""
    old = qapp.palette()
    dark = QPalette(old)
    dark.setColor(QPalette.ColorRole.Base, QColor("#1e1e1e"))
    dark.setColor(QPalette.ColorRole.Text, QColor("#e0e0e0"))
    dark.setColor(QPalette.ColorRole.Window, QColor("#2b2b2b"))
    qapp.setPalette(dark)
    yield
    qapp.setPalette(old)


# --------------------------------------------------------------------------- #
# Помощники                                                                   #
# --------------------------------------------------------------------------- #


def _notebook(*, with_image: bool = True, with_remote_img: bool = False) -> nbformat.NotebookNode:
    nb = nbformat.v4.new_notebook()
    md_src = "# Заголовок ноутбука\n\nАбзац с **жирным** и `инлайн-кодом`.\n\n- пункт один\n- пункт два"
    if with_remote_img:
        md_src += '\n\n<img src="http://example.invalid/tracker.png">'
    nb.cells.append(nbformat.v4.new_markdown_cell(md_src))

    code = nbformat.v4.new_code_cell("import math\n\n\ndef area(r):\n    return math.pi * r * r\n\n\nprint(round(area(2), 3))")
    code.execution_count = 1
    code.outputs = [
        nbformat.v4.new_output("stream", name="stdout", text="12.566\n"),
        nbformat.v4.new_output(
            "execute_result", data={"text/plain": "'готово'"}, execution_count=1
        ),
    ]
    nb.cells.append(code)

    if with_image:
        img_cell = nbformat.v4.new_code_cell("show_chart()")
        img_cell.execution_count = 2
        img_cell.outputs = [
            nbformat.v4.new_output(
                "display_data",
                data={"image/png": base64.b64encode(_PNG_1X1).decode("ascii")},
            )
        ]
        nb.cells.append(img_cell)
    return nb


def _write_ipynb(path: Path, nb: nbformat.NotebookNode) -> Path:
    path.write_text(nbformat.writes(nb), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# Диспетчеризация                                                             #
# --------------------------------------------------------------------------- #


def test_registry_selects_ipynb_viewer(registry: ViewerRegistry, tmp_path: Path) -> None:
    p = _write_ipynb(tmp_path / "analysis.ipynb", _notebook())
    assert isinstance(registry.viewer_for(p), IpynbViewer)


def test_ipynb_viewer_does_not_steal_plain_json(registry: ViewerRegistry, tmp_path: Path) -> None:
    p = tmp_path / "data.json"
    p.write_text('{"a": 1, "b": [2, 3]}', encoding="utf-8")
    assert not isinstance(registry.viewer_for(p), IpynbViewer)


# --------------------------------------------------------------------------- #
# Рендер ячеек                                                                #
# --------------------------------------------------------------------------- #


def test_cells_render_in_order(tmp_path: Path) -> None:
    viewer = IpynbViewer()
    viewer.safe_load(_write_ipynb(tmp_path / "nb.ipynb", _notebook()))

    assert not viewer.is_error_widget
    assert viewer.cell_count == 3

    plain = viewer._browser.toPlainText()
    assert "Заголовок ноутбука" in plain
    assert "def area" in plain
    # Markdown-ячейка идёт раньше ячейки кода
    assert plain.index("Заголовок ноутбука") < plain.index("def area")
    # вывод идёт после исходника ячейки
    assert plain.index("def area") < plain.index("12.566")


def test_markdown_cell_is_rendered(tmp_path: Path) -> None:
    viewer = IpynbViewer()
    viewer.safe_load(_write_ipynb(tmp_path / "nb.ipynb", _notebook(with_image=False)))

    assert not viewer.is_error_widget
    assert "<h1" in viewer.rendered_html
    assert "<li" in viewer.rendered_html
    plain = viewer._browser.toPlainText()
    assert "Заголовок ноутбука" in plain
    assert "# Заголовок" not in plain  # markdown отрендерен, а не показан как текст


def test_code_cell_is_highlighted(tmp_path: Path) -> None:
    viewer = IpynbViewer()
    viewer.safe_load(_write_ipynb(tmp_path / "nb.ipynb", _notebook(with_image=False)))

    assert not viewer.is_error_widget
    # nbconvert разметил токены классами, а мы подложили таблицу стилей pygments
    assert 'class="highlight' in viewer.rendered_html
    assert ".highlight .k" in viewer.rendered_html  # стиль ключевого слова
    # Qt применил класс: ключевое слово получило цвет
    html = viewer._browser.toHtml()
    idx = html.find("import")
    assert idx != -1
    assert "color:#" in html[idx - 220 : idx]


def test_dark_theme_code_cell_has_dark_bg_and_readable_text(tmp_path: Path, dark_qt_theme) -> None:
    """На тёмной теме блок кода ноутбука: тёмный фон + светлый цвет текста, при
    этом stderr/error-вывод остаётся визуально отличимым от обычного кода."""
    viewer = IpynbViewer()
    viewer.safe_load(_write_ipynb(tmp_path / "nb.ipynb", _notebook(with_image=False)))

    assert not viewer.is_error_widget
    html = viewer.rendered_html
    assert ".highlight, .highlight pre { background:#1e1e1e; color:#d4d4d4; }" in html
    # плейн-токены/неизвестный язык наследуют цвет .highlight — он светлый
    idx = html.find("import")
    assert idx != -1
    # stderr-вывод отличается фоном от обычного блока кода
    assert "background:#3a1f1f" in html


def test_light_theme_code_cell_keeps_previous_look(tmp_path: Path) -> None:
    """На светлой (дефолтной offscreen) палитре — прежнее поведение."""
    viewer = IpynbViewer()
    viewer.safe_load(_write_ipynb(tmp_path / "nb.ipynb", _notebook(with_image=False)))

    assert not viewer.is_error_widget
    html = viewer.rendered_html
    assert "background:#f5f5f5" in html
    assert "background:#ffe6e6" in html


# --------------------------------------------------------------------------- #
# Вывод ячеек                                                                 #
# --------------------------------------------------------------------------- #


def test_text_outputs_are_shown(tmp_path: Path) -> None:
    viewer = IpynbViewer()
    viewer.safe_load(_write_ipynb(tmp_path / "nb.ipynb", _notebook()))

    plain = viewer._browser.toPlainText()
    assert "12.566" in plain  # stream stdout
    assert "готово" in plain  # execute_result text/plain


def test_image_output_is_embedded_offline(tmp_path: Path) -> None:
    viewer = IpynbViewer()
    viewer.safe_load(_write_ipynb(tmp_path / "nb.ipynb", _notebook(with_image=True)))

    assert not viewer.is_error_widget
    m = re.search(r'src="(data:image/png;base64,[^"]+)"', viewer.rendered_html)
    assert m, "картинка вывода не инлайнена как data:-URI"
    data = viewer._browser.loadResource(_IMG_RESOURCE, QUrl(m.group(1)))
    assert data is not None and bytes(data) == _PNG_1X1


def test_external_network_resource_is_not_loaded(tmp_path: Path) -> None:
    viewer = IpynbViewer()
    viewer.safe_load(
        _write_ipynb(tmp_path / "nb.ipynb", _notebook(with_image=False, with_remote_img=True))
    )

    assert not viewer.is_error_widget
    data = viewer._browser.loadResource(
        _IMG_RESOURCE, QUrl("http://example.invalid/tracker.png")
    )
    assert bytes(data) == b""


# --------------------------------------------------------------------------- #
# Битые образцы                                                               #
# --------------------------------------------------------------------------- #


def test_truncated_ipynb_yields_error_widget(tmp_path: Path) -> None:
    full = nbformat.writes(_notebook())
    p = tmp_path / "broken.ipynb"
    p.write_text(full[: len(full) // 3], encoding="utf-8")
    viewer = IpynbViewer()
    viewer.safe_load(p)
    assert viewer.is_error_widget


def test_valid_json_that_is_not_a_notebook_yields_error_widget(tmp_path: Path) -> None:
    p = tmp_path / "notnb.ipynb"
    p.write_text('{"totally": "valid json", "but": ["not", "a", "notebook"]}', encoding="utf-8")
    viewer = IpynbViewer()
    viewer.safe_load(p)
    assert viewer.is_error_widget
