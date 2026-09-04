"""Просмотрщик Jupyter-ноутбуков (``.ipynb``).

``nbconvert`` с шаблоном ``basic`` превращает ноутбук во фрагмент HTML: ячейки
Markdown и кода в порядке следования, текстовый и графический вывод. Подсветка
кода — ``pygments`` (классы ``.highlight`` + инлайн-таблица стилей, потому что
шаблон ``basic`` свой CSS не включает). Рендер через общий офлайн-хелпер
:mod:`omniviewer.viewers.html_render` (QTextBrowser).

Офлайн: внешние ресурсы не грузятся; картинки вывода ``nbconvert`` уже
инлайнит как ``data:``-URI, их декодирует :class:`OfflineTextBrowser`.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QMimeType

from omniviewer.viewers.base import BaseViewer
from omniviewer.viewers.html_render import build_html_browser

_IPYNB_SUFFIXES = (".ipynb",)
_IPYNB_MIMES = frozenset(
    {
        "application/x-ipynb+json",
        "application/ipynb+json",
        "application/x-jupyter",
    }
)


def _style_block() -> str:
    """Таблица стилей pygments для классов ``.highlight`` + мелкие правки под Qt."""
    from pygments.formatters import HtmlFormatter

    css = HtmlFormatter().get_style_defs(".highlight")
    return (
        "<style>\n"
        f"{css}\n"
        ".highlight, .highlight pre { background:#f8f8f8; }\n"
        "pre { white-space: pre-wrap; word-wrap: break-word; }\n"
        ".output_stderr pre, .output_error pre { background:#ffe6e6; }\n"
        ".anchor-link { display: none; }\n"
        ".prompt, .input_prompt, .output_prompt { color:#888; font-family:monospace; }\n"
        "</style>\n"
    )


## @brief Просмотрщик Jupyter-ноутбуков (.ipynb).
#
# Приводит ноутбук к строке HTML через nbconvert (шаблон basic) и показывает во
# встроенном движке rich text Qt (QTextBrowser). Ячейки идут по порядку: Markdown
# отрендерен, код подсвечен pygments, текстовый и графический (data:-URI) вывод
# показан. Внешняя сеть не используется.
class IpynbViewer(BaseViewer):
    mime_types = tuple(_IPYNB_MIMES)
    extensions = _IPYNB_SUFFIXES
    priority = 30

    def __init__(self):
        super().__init__()
        self._browser = build_html_browser("")
        self._layout.addWidget(self._browser)
        self.rendered_html: str = ""
        self.cell_count: int = 0

    @classmethod
    def can_handle(cls, path: Path, mime: QMimeType | str) -> bool:
        if path.suffix.lower() in cls.extensions:
            return True
        mime_name = mime.name() if isinstance(mime, QMimeType) else str(mime)
        return mime_name in _IPYNB_MIMES

    def load(self, path: Path) -> None:
        import nbformat
        from nbconvert import HTMLExporter

        nb = nbformat.read(str(path), as_version=4)
        self.cell_count = len(nb.get("cells", []))

        exporter = HTMLExporter(template_name="basic")
        exporter.exclude_anchor_links = True
        body, _resources = exporter.from_notebook_node(nb)

        html = _style_block() + body
        self.rendered_html = html
        self._browser.setHtml(html)
