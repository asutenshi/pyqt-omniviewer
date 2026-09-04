# ruff: noqa: BLE001
"""Просмотрщик почты: EML (stdlib :mod:`email`) и MSG (Outlook, ``extract_msg``).

Показывает заголовки From/To/Cc/Subject/Date и тело письма: HTML-часть — через
общий шов :mod:`omniviewer.viewers.html_render` (строго офлайн, сетевые ресурсы
не грузятся), иначе ``text/plain`` как есть. Вложения перечислены отдельным
списком; двойной клик распаковывает вложение во временную папку и открывает его
тем же ``ViewerRegistry``. Битый образец валит разбор — ``BaseViewer`` отдаёт
«ошибочный» виджет.
"""

from __future__ import annotations

import contextlib
import datetime
import email
import email.header
import email.message
import email.policy
import email.utils
import html as _html
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QMimeType, Qt, pyqtSignal
from PyQt6.QtWidgets import QListWidget, QListWidgetItem, QSplitter

from omniviewer.viewers.base import BaseViewer
from omniviewer.viewers.html_render import build_html_browser

_EML_SUFFIXES = (".eml",)
_MSG_SUFFIXES = (".msg",)
_EML_MIMES = frozenset({"message/rfc822", "text/rfc822-headers"})
_MSG_MIMES = frozenset({"application/vnd.ms-outlook", "application/x-msg"})

_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

## @brief Порядок и русские подписи отображаемых заголовков письма.
_HEADER_LABELS = (
    ("From", "От"),
    ("To", "Кому"),
    ("Cc", "Копия"),
    ("Subject", "Тема"),
    ("Date", "Дата"),
)


@dataclass(frozen=True)
class MailAttachment:
    """Одно вложение письма: имя файла и его содержимое."""

    name: str
    data: bytes


def _safe_name(name: str) -> str:
    """Обеззаразить имя вложения: только basename, без ведущих точек и пустот."""
    base = Path(str(name).replace("\\", "/")).name
    base = base.strip().lstrip(".").strip()
    return base or "attachment"


def _human_size(nbytes: int) -> str:
    size = float(nbytes)
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if size < 1024 or unit == "ГБ":
            return f"{size:.0f} {unit}" if unit == "Б" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{nbytes} Б"


## @brief Просмотрщик писем EML / MSG.
#
# EML разбирается стандартной библиотекой :mod:`email` (политика
# ``email.policy.default``), MSG — библиотекой ``extract_msg``. Заголовки
# и тело сводятся в одну строку HTML и показываются в офлайновом
# ``QTextBrowser``; вложения открываются во временной копии через
# ``ViewerRegistry``.
class MailViewer(BaseViewer):
    mime_types = tuple(_EML_MIMES | _MSG_MIMES)
    extensions = _EML_SUFFIXES + _MSG_SUFFIXES
    # Выше DocumentViewer(30): .msg — OLE-контейнер, как и legacy .doc, и на
    # Linux content-sniffing (shared-mime-info) распознаёт его только как общий
    # родитель `application/x-ole-storage` — тот же MIME, что ловит DocumentViewer
    # для .doc. При равном приоритете и совпадении по этому MIME побеждал бы
    # DocumentViewer (регистрируется раньше). Расширение .msg/.eml — однозначный
    # сигнал, поэтому MailViewer должен выигрывать этот тай-брейк.
    priority = 31

    ## @brief Испущен при двойном клике по вложению — имя вложения.
    attachment_activated = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._layout.setContentsMargins(0, 0, 0, 0)

        self._browser = build_html_browser("")
        self._attach_list = QListWidget()
        self._attach_list.itemDoubleClicked.connect(self._on_attach_double_clicked)
        self._attach_list.setMaximumHeight(140)
        self._attach_list.hide()

        self._splitter = QSplitter(Qt.Orientation.Vertical)
        self._splitter.addWidget(self._browser)
        self._splitter.addWidget(self._attach_list)
        self._splitter.setStretchFactor(0, 1)
        self._layout.addWidget(self._splitter)

        self.headers: dict[str, str] = {}
        self.attachments: list[MailAttachment] = []
        self.rendered_html: str = ""

        self._temp_root: str | None = None
        self._child_viewers: list[BaseViewer] = []

    # ------------------------------------------------------------------ #
    # Диспетчеризация                                                    #
    # ------------------------------------------------------------------ #

    @classmethod
    def can_handle(cls, path: Path, mime: QMimeType | str) -> bool:
        if path.suffix.lower() in cls.extensions:
            return True
        mime_name = mime.name() if isinstance(mime, QMimeType) else str(mime)
        return mime_name in _EML_MIMES or mime_name in _MSG_MIMES

    # ------------------------------------------------------------------ #
    # Загрузка                                                           #
    # ------------------------------------------------------------------ #

    def load(self, path: Path) -> None:
        path = Path(path)
        if self._detect_kind(path) == "msg":
            headers, body_html, body_text, atts, resources = self._parse_msg(path)
        else:
            headers, body_html, body_text, atts, resources = self._parse_eml(path)

        self.headers = headers
        self.attachments = atts

        html = self._compose(headers, body_html, body_text)
        self.rendered_html = html
        self._browser.set_resources(resources)
        self._browser.setHtml(html)
        self._populate_attachments()

    @staticmethod
    def _detect_kind(path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix in _MSG_SUFFIXES:
            return "msg"
        if suffix in _EML_SUFFIXES:
            return "eml"
        with contextlib.suppress(OSError), open(path, "rb") as fh:
            if fh.read(8) == _OLE_MAGIC:
                return "msg"
        return "eml"

    # ------------------------------------------------------------------ #
    # EML                                                                #
    # ------------------------------------------------------------------ #

    def _parse_eml(self, path: Path):
        raw = path.read_bytes()
        msg = email.message_from_bytes(raw, policy=email.policy.default)

        headers = {
            key: self._decode_header(msg.get(key))
            for key, _label in _HEADER_LABELS
        }

        body_html: str | None = None
        body_text = ""
        resources: dict[str, bytes] = {}

        try:
            html_part = msg.get_body(preferencelist=("html",))
        except Exception:
            html_part = None
        try:
            text_part = msg.get_body(preferencelist=("plain",))
        except Exception:
            text_part = None

        if html_part is not None:
            body_html = html_part.get_content()
        if text_part is not None:
            body_text = text_part.get_content()

        body_ids = {id(p) for p in (html_part, text_part) if p is not None}

        atts: list[MailAttachment] = []
        for part in msg.walk():
            if part.is_multipart() or id(part) in body_ids:
                continue
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            cid = part.get("Content-ID")
            disposition = (part.get_content_disposition() or "").lower()
            if cid and disposition != "attachment":
                key = cid.strip().strip("<>")
                resources[f"cid:{key}"] = payload
                continue
            if disposition != "attachment" and not part.get_filename():
                continue
            name = part.get_filename() or f"attachment-{len(atts) + 1}"
            atts.append(MailAttachment(_safe_name(name), payload))

        if not any(headers.values()) and body_html is None and not body_text and not atts:
            raise ValueError("Не удалось разобрать письмо: нет заголовков, тела и вложений")

        return headers, body_html, body_text, atts, resources

    @staticmethod
    def _decode_header(value) -> str:
        if not value:
            return ""
        try:
            return str(email.header.make_header(email.header.decode_header(str(value))))
        except Exception:
            return str(value)

    # ------------------------------------------------------------------ #
    # MSG                                                                #
    # ------------------------------------------------------------------ #

    def _parse_msg(self, path: Path):
        import extract_msg

        m = extract_msg.Message(str(path))
        try:
            headers = {
                "From": m.sender or "",
                "To": m.to or "",
                "Cc": m.cc or "",
                "Subject": m.subject or "",
                "Date": self._fmt_msg_date(m.date),
            }
            html_bytes = m.htmlBody
            body_html = None
            if html_bytes:
                body_html = html_bytes.decode("utf-8", errors="replace")
            body_text = m.body or ""

            atts: list[MailAttachment] = []
            for att in m.attachments:
                data = att.data
                if not isinstance(data, (bytes, bytearray)):
                    continue
                name = att.longFilename or att.shortFilename or f"attachment-{len(atts) + 1}"
                atts.append(MailAttachment(_safe_name(name), bytes(data)))
        finally:
            with contextlib.suppress(Exception):
                m.close()

        return headers, body_html, body_text, atts, {}

    @staticmethod
    def _fmt_msg_date(value) -> str:
        if not value:
            return ""
        try:
            if value.tzinfo is not None:
                value = value.astimezone(datetime.timezone.utc)
            return email.utils.format_datetime(value)
        except Exception:
            return str(value)

    # ------------------------------------------------------------------ #
    # Сборка HTML                                                        #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _compose(headers: dict[str, str], body_html: str | None, body_text: str) -> str:
        rows = []
        for key, label in _HEADER_LABELS:
            value = headers.get(key, "")
            if not value:
                continue
            rows.append(
                f'<tr><td class="k">{_html.escape(label)}:</td>'
                f"<td>{_html.escape(value)}</td></tr>"
            )
        header_table = f'<table class="hdr">{"".join(rows)}</table>'

        if body_html is not None:
            body = f'<div class="msgbody">{body_html}</div>'
        else:
            body = f'<pre class="body">{_html.escape(body_text)}</pre>'

        return (
            "<html><head><meta charset=\"utf-8\"><style>"
            "body{font-family:sans-serif;font-size:13px}"
            "table.hdr{border-collapse:collapse;margin-bottom:6px}"
            "table.hdr td{padding:1px 8px;vertical-align:top}"
            "td.k{color:#666;white-space:nowrap;text-align:right}"
            "pre.body{white-space:pre-wrap;word-wrap:break-word;"
            "font-family:sans-serif;margin:0}"
            "</style></head><body>"
            f"{header_table}<hr>{body}"
            "</body></html>"
        )

    # ------------------------------------------------------------------ #
    # Вложения                                                           #
    # ------------------------------------------------------------------ #

    def _populate_attachments(self) -> None:
        self._attach_list.clear()
        for index, att in enumerate(self.attachments):
            item = QListWidgetItem(f"{att.name}  ({_human_size(len(att.data))})")
            item.setData(Qt.ItemDataRole.UserRole, index)
            self._attach_list.addItem(item)
        self._attach_list.setVisible(bool(self.attachments))

    @property
    def _temp_dir(self) -> str:
        if self._temp_root is None:
            self._temp_root = tempfile.mkdtemp(prefix="omniviewer-mail-")
        return self._temp_root

    def open_attachment(self, index: int) -> BaseViewer:
        """Записать вложение во временный файл и вернуть просмотрщик из реестра."""
        from omniviewer.registry import default_registry

        att = self.attachments[index]
        target = Path(self._temp_dir) / _safe_name(att.name)
        target.write_bytes(att.data)

        viewer = default_registry.viewer_for(target)
        viewer.safe_load(target)
        self._child_viewers.append(viewer)
        return viewer

    def _on_attach_double_clicked(self, item: QListWidgetItem) -> None:
        index = item.data(Qt.ItemDataRole.UserRole)
        if index is None:
            return
        att = self.attachments[index]
        viewer = self.open_attachment(index)
        viewer.setWindowTitle(att.name)
        viewer.resize(900, 700)
        viewer.show()
        self.attachment_activated.emit(att.name)

    # ------------------------------------------------------------------ #
    # Очистка                                                            #
    # ------------------------------------------------------------------ #

    def unload(self) -> None:
        for child in self._child_viewers:
            if hasattr(child, "unload"):
                with contextlib.suppress(Exception):
                    child.unload()
        self._child_viewers.clear()
        if self._temp_root:
            shutil.rmtree(self._temp_root, ignore_errors=True)
            self._temp_root = None

    def closeEvent(self, event):
        self.unload()
        super().closeEvent(event)
