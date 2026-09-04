# ruff: noqa: BLE001
"""Просмотрщик офисных текстовых документов: DOCX, DOC, ODT, RTF.

Единый конвейер «документ → строка HTML → QTextBrowser» (см.
:mod:`omniviewer.viewers.html_render`). Пиксельная точность не требуется —
показываем содержание: заголовки, абзацы, списки, встроенные изображения.

Библиотеки:
- DOCX: ``mammoth`` → HTML, метаданные через ``python-docx``
- DOC (legacy): ``olefile`` — извлечённый текст из OLE-потока WordDocument
- ODT: ``odfpy`` — текст со структурой (заголовки, абзацы, списки)
- RTF: ``striprtf`` — извлечённый чистый текст
"""

from __future__ import annotations

import base64
from pathlib import Path

from PyQt6.QtCore import QMimeType

from omniviewer.viewers.base import BaseViewer
from omniviewer.viewers.html_render import build_html_browser

# ─── Расширения и MIME ──────────────────────────────────────────────────────

_DOCX_EXTS = (".docx",)
_DOC_EXTS = (".doc",)
_ODT_EXTS = (".odt",)
_RTF_EXTS = (".rtf",)

_DOCX_MIMES = frozenset({
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
})
_DOC_MIMES = frozenset({
    "application/msword",
    "application/x-ole-storage",
})
_ODT_MIMES = frozenset({
    "application/vnd.oasis.opendocument.text",
})
_RTF_MIMES = frozenset({
    "application/rtf",
    "text/rtf",
})

_ALL_EXTS = _DOCX_EXTS + _DOC_EXTS + _ODT_EXTS + _RTF_EXTS
_ALL_MIMES = _DOCX_MIMES | _DOC_MIMES | _ODT_MIMES | _RTF_MIMES


# ─── Конвертеры отдельных форматов ──────────────────────────────────────────

def _docx_to_html(path: Path) -> tuple[str, dict[str, bytes]]:
    """DOCX → HTML через mammoth; встроенные изображения инлайнятся в ``data:`` URI."""
    import mammoth

    resources: dict[str, bytes] = {}

    def convert_image(image):
        """Конвертер изображений mammoth → data URI для QTextBrowser."""
        with image.open() as img_stream:
            img_bytes = img_stream.read()
        content_type = image.content_type or "image/png"
        b64 = base64.b64encode(img_bytes).decode("ascii")
        src = f"data:{content_type};base64,{b64}"
        return {"src": src}

    with open(path, "rb") as f:
        result = mammoth.convert_to_html(f, convert_image=mammoth.images.img_element(convert_image))

    return result.value, resources


def _doc_to_html(path: Path) -> str:
    """Legacy .doc (OLE2) → HTML; извлекаем текст из потока WordDocument."""
    import olefile

    ole = olefile.OleFileIO(str(path))
    try:
        # Ищем поток с текстом
        text = ""
        for stream_name in ("WordDocument", "Word Document"):
            if ole.exists(stream_name):
                raw = ole.openstream(stream_name).read()
                # Убираем нулевые байты в конце
                raw = raw.rstrip(b"\x00")
                # Пробуем декодировать
                for enc in ("utf-8", "cp1251", "cp1252", "latin-1"):
                    try:
                        text = raw.decode(enc)
                        break
                    except (UnicodeDecodeError, ValueError):
                        continue
                if text:
                    break

        if not text:
            # Fallback: пробуем извлечь любой текстовый поток
            for entry in ole.listdir():
                stream_path = "/".join(entry)
                try:
                    raw = ole.openstream(stream_path).read().rstrip(b"\x00")
                    text = raw.decode("utf-8", errors="replace")
                    if len(text) > 10:
                        break
                except Exception:  # noqa: S112
                    continue

        if not text:
            raise ValueError("Не удалось извлечь текст из .doc файла")
    finally:
        ole.close()

    # Форматируем абзацы
    paragraphs = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    html_parts = ["<h3>Извлечённый текст (legacy .doc)</h3>"]
    for para in paragraphs:
        para = para.strip()
        if para:
            html_parts.append(f"<p>{_escape_html(para)}</p>")

    return "\n".join(html_parts)


def _odt_to_html(path: Path) -> str:
    """ODT → HTML; извлекаем заголовки, абзацы и списки через odfpy."""
    from odf.opendocument import load as odf_load

    # Пространство имён ODF text
    _TEXT_NS = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"

    doc = odf_load(str(path))
    html_parts: list[str] = []

    def _get_text(element) -> str:
        """Рекурсивно извлечь текстовое содержимое элемента."""
        parts = []
        if hasattr(element, "childNodes"):
            for child in element.childNodes:
                if hasattr(child, "data"):
                    parts.append(str(child))
                elif hasattr(child, "childNodes"):
                    parts.append(_get_text(child))
        return "".join(parts)

    def _tag(element) -> str:
        """Локальное имя тега элемента ODF."""
        if hasattr(element, "qname") and isinstance(element.qname, tuple):
            return element.qname[1]
        return ""

    def _process_element(element):
        """Обработать элемент ODF и добавить в html_parts."""
        tag = _tag(element)

        if tag == "h":
            level = element.getAttribute("outlinelevel") or "1"
            try:
                lvl = min(int(level), 6)
            except (ValueError, TypeError):
                lvl = 1
            text = _escape_html(_get_text(element))
            html_parts.append(f"<h{lvl}>{text}</h{lvl}>")
        elif tag == "p":
            text = _get_text(element).strip()
            if text:
                html_parts.append(f"<p>{_escape_html(text)}</p>")
        elif tag == "list":
            html_parts.append("<ul>")
            if hasattr(element, "childNodes"):
                for child in element.childNodes:
                    if _tag(child) == "list-item":
                        li_text = _get_text(child).strip()
                        if li_text:
                            html_parts.append(f"<li>{_escape_html(li_text)}</li>")
            html_parts.append("</ul>")
        elif hasattr(element, "childNodes"):
            for child in element.childNodes:
                if hasattr(child, "qname"):
                    _process_element(child)

    # Обрабатываем body текста
    if doc.text and hasattr(doc.text, "childNodes"):
        for child in doc.text.childNodes:
            if hasattr(child, "qname"):
                _process_element(child)

    return "\n".join(html_parts) if html_parts else "<p><i>Пустой документ</i></p>"


def _rtf_to_html(path: Path) -> str:
    """RTF → HTML; извлекаем чистый текст через striprtf."""
    from striprtf.striprtf import rtf_to_text

    raw = path.read_bytes()
    # Пробуем разные кодировки
    for enc in ("utf-8", "cp1251", "cp1252", "latin-1"):
        try:
            rtf_str = raw.decode(enc)
            break
        except (UnicodeDecodeError, ValueError):
            continue
    else:
        rtf_str = raw.decode("utf-8", errors="replace")

    text = rtf_to_text(rtf_str, errors="replace")

    # Форматируем абзацы
    paragraphs = text.split("\n")
    html_parts: list[str] = []
    for para in paragraphs:
        para = para.strip()
        if para:
            html_parts.append(f"<p>{_escape_html(para)}</p>")

    return "\n".join(html_parts) if html_parts else "<p><i>Пустой документ</i></p>"


def _escape_html(text: str) -> str:
    """Минимальное экранирование HTML-сущностей."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# ─── Класс просмотрщика ────────────────────────────────────────────────────


## @brief Просмотрщик офисных текстовых документов (DOCX / DOC / ODT / RTF).
#
# Приводит документ к строке HTML и показывает во встроенном движке rich text Qt
# (QTextBrowser). DOCX рендерится через mammoth, встроенные изображения
# инлайнятся как data-URI. Legacy .doc парсится olefile (извлечение текста).
# ODT разбирается odfpy (заголовки, абзацы, списки). RTF — через striprtf.
class DocumentViewer(BaseViewer):
    mime_types = tuple(_ALL_MIMES)
    extensions = _ALL_EXTS
    priority = 30

    def __init__(self):
        super().__init__()
        self._browser = build_html_browser("")
        self._layout.addWidget(self._browser)
        self.rendered_html: str = ""

    @classmethod
    def can_handle(cls, path: Path, mime: QMimeType | str) -> bool:
        """Проверка по расширению и MIME-типу."""
        suffix = path.suffix.lower()
        if suffix in _ALL_EXTS:
            return True
        mime_name = mime.name() if isinstance(mime, QMimeType) else str(mime)
        return mime_name in _ALL_MIMES

    def load(self, path: Path) -> None:
        """Синхронная загрузка документа."""
        suffix = path.suffix.lower()
        resources: dict[str, bytes] = {}

        if suffix in _DOCX_EXTS:
            html, resources = _docx_to_html(path)
        elif suffix in _DOC_EXTS:
            html = _doc_to_html(path)
        elif suffix in _ODT_EXTS:
            html = _odt_to_html(path)
        elif suffix in _RTF_EXTS:
            html = _rtf_to_html(path)
        else:
            raise ValueError(f"Неподдерживаемое расширение: {suffix}")

        self.rendered_html = html
        self._browser.set_resources(resources)
        self._browser.setHtml(html)
