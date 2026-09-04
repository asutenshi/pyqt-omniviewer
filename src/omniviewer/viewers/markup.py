"""Просмотрщик разметки: Markdown, HTML/HTM/XHTML, MHTML.

Единый конвейер «документ → строка HTML → QTextBrowser» (см.
:mod:`omniviewer.viewers.html_render`). Рендер строго офлайн.
"""

from __future__ import annotations

import email
import email.policy
import html as _html
from pathlib import Path

import charset_normalizer
from markdown_it import MarkdownIt
from pygments import highlight as _pyg_highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name, guess_lexer
from pygments.util import ClassNotFound
from PyQt6.QtCore import QMimeType

from omniviewer.viewers.base import BaseViewer
from omniviewer.viewers.html_render import build_html_browser

_MARKDOWN_SUFFIXES = (".md", ".markdown", ".mdown", ".mkd", ".mdwn")
_HTML_SUFFIXES = (".html", ".htm", ".xhtml", ".xht")
_MHTML_SUFFIXES = (".mhtml", ".mht")
_MARKDOWN_MIMES = frozenset({"text/markdown", "text/x-markdown"})
_HTML_MIMES = frozenset({"text/html", "application/xhtml+xml"})
_MHTML_MIMES = frozenset({"application/x-mimearchive", "multipart/related"})


def _decode(raw: bytes) -> str:
    """Декодировать байты в текст по определённой кодировке (fallback — utf-8)."""
    match = charset_normalizer.from_bytes(raw).best()
    if match is not None:
        return str(match)
    return raw.decode("utf-8", errors="replace")


# Обёртка блока кода задаёт цвет текста явно: pygments с ``noclasses`` красит
# только распознанные токены, а остальное (и весь блок, если язык неизвестен)
# наследовало бы цвет темы QTextBrowser и на тёмной теме сливалось бы со
# светлым фоном — блок выглядел бы пустым белым прямоугольником.
_CODE_BLOCK_STYLE = "background:#f5f5f5;color:#1a1a1a;padding:8px;white-space:pre-wrap"


def _highlight_code(code: str, lang: str, _attrs) -> str:
    """Подсветка блока кода pygments'ом со встроенными стилями (без внешнего CSS)."""
    try:
        lexer = get_lexer_by_name(lang, stripnl=False) if lang else guess_lexer(code)
    except (ClassNotFound, ValueError):
        inner = _html.escape(code, quote=False)
    else:
        inner = _pyg_highlight(code, lexer, HtmlFormatter(noclasses=True, nowrap=True))
    return f'<pre style="{_CODE_BLOCK_STYLE}"><code>{inner}</code></pre>'


_MD = MarkdownIt("commonmark", {"html": False, "linkify": False, "highlight": _highlight_code})
_MD.enable("table")


def _markdown_to_html(text: str) -> str:
    return _MD.render(text)


def _mhtml_to_html(raw: bytes) -> tuple[str, dict[str, bytes]]:
    """Разобрать MHTML: вернуть HTML-часть и карту «ключ → байты» её ресурсов.

    Ресурсы регистрируются под несколькими псевдонимами (Content-Location целиком
    и его basename, ``cid:<Content-ID>``), чтобы совпасть с тем, как на них
    ссылается HTML.
    """
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    html_text: str | None = None
    resources: dict[str, bytes] = {}

    for part in msg.walk():
        ctype = part.get_content_type()
        if ctype.startswith("multipart/"):
            continue
        payload = part.get_payload(decode=True)
        if ctype in ("text/html", "application/xhtml+xml") and html_text is None:
            charset = part.get_content_charset() or "utf-8"
            html_text = (payload or b"").decode(charset, errors="replace")
            continue
        if not payload:
            continue
        location = part.get("Content-Location")
        cid = part.get("Content-ID")
        if location:
            resources[location] = payload
            resources[location.rsplit("/", 1)[-1]] = payload
        if cid:
            resources[f"cid:{cid.strip('<>')}"] = payload

    if html_text is None:
        raise ValueError("MHTML не содержит HTML-части")
    return html_text, resources


## @brief Просмотрщик разметки (Markdown / HTML / XHTML / MHTML).
#
# Приводит документ к строке HTML и показывает во встроенном движке rich text Qt
# (QTextBrowser). Markdown рендерится markdown-it-py, блоки кода подсвечиваются
# pygments. MHTML распаковывается стандартной библиотекой email, встроенные
# ресурсы инлайнятся. Внешние сетевые ресурсы не загружаются.
class MarkupViewer(BaseViewer):
    mime_types = tuple(_MARKDOWN_MIMES | _HTML_MIMES | _MHTML_MIMES)
    extensions = _MARKDOWN_SUFFIXES + _HTML_SUFFIXES + _MHTML_SUFFIXES
    priority = 30

    def __init__(self):
        super().__init__()
        self._browser = build_html_browser("")
        self._layout.addWidget(self._browser)
        self.rendered_html: str = ""

    @classmethod
    def can_handle(cls, path: Path, mime: QMimeType | str) -> bool:
        suffix = path.suffix.lower()
        if suffix in cls.extensions:
            return True
        mime_name = mime.name() if isinstance(mime, QMimeType) else str(mime)
        return mime_name in _MARKDOWN_MIMES or mime_name in _HTML_MIMES or mime_name in _MHTML_MIMES

    def load(self, path: Path) -> None:
        raw = path.read_bytes()
        kind = self._detect_kind(path.suffix.lower(), raw)
        resources: dict[str, bytes] = {}

        if kind == "mhtml":
            html, resources = _mhtml_to_html(raw)
        elif kind == "html":
            html = _decode(raw)
        else:
            html = _markdown_to_html(_decode(raw))

        self.rendered_html = html
        self._browser.set_resources(resources)
        self._browser.setHtml(html)

    @staticmethod
    def _detect_kind(suffix: str, raw: bytes) -> str:
        """Определить тип разметки: ``mhtml`` / ``html`` / ``markdown``."""
        if suffix in _MHTML_SUFFIXES:
            return "mhtml"
        if suffix in _HTML_SUFFIXES:
            return "html"
        if suffix in _MARKDOWN_SUFFIXES:
            return "markdown"
        # Расширение не помогло (файл пришёл по MIME-снифферу) — смотрим содержимое.
        head = raw[:2048]
        if b"multipart/related" in head and b"MIME-Version" in head:
            return "mhtml"
        if raw.lstrip()[:1] == b"<":
            return "html"
        return "markdown"
