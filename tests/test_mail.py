"""Тесты просмотрщика почты: EML / MSG.

Поведение проверяется через главный шов ``ViewerRegistry`` и публичный API
``MailViewer``:

* реестр отдаёт ``MailViewer`` по ``.eml`` / ``.msg``;
* видны заголовки From/To/Cc/Subject/Date;
* HTML-тело рендерится, сетевые ресурсы не загружаются, инлайновые (``cid:``) —
  загружаются;
* тело ``text/plain`` показывается, когда HTML-части нет;
* вложения перечислены, открываются тем же реестром;
* битый образец → «ошибочный» виджет, без падения.
"""

from __future__ import annotations

import base64
import sys
import zlib
from pathlib import Path

import pytest
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QTextDocument
from PyQt6.QtWidgets import QApplication

from omniviewer.registry import ViewerRegistry
from omniviewer.viewers.mail import MailViewer

DEMO = Path(__file__).parent.parent / "demo"
_IMG_RESOURCE = QTextDocument.ResourceType.ImageResource.value


@pytest.fixture(scope="session", autouse=True)
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture
def registry() -> ViewerRegistry:
    return ViewerRegistry()


# --------------------------------------------------------------------------- #
# Помощники — строим EML прямо в тесте                                         #
# --------------------------------------------------------------------------- #


def _png(w: int = 8, h: int = 8) -> bytes:
    import struct

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    rows = bytearray()
    for _y in range(h):
        rows.append(0)
        rows += bytes((10, 120, 200)) * w
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(bytes(rows), 9))
        + chunk(b"IEND", b"")
    )


def _make_eml(*, html: bool = True, inline_image: bool = True, attachment: bool = True) -> bytes:
    png_b64 = "\r\n".join(base64.encodebytes(_png()).decode("ascii").splitlines())
    note_b64 = base64.b64encode("вложение\nстрока два\n".encode()).decode("ascii")
    subj = "=?utf-8?B?" + base64.b64encode("Проверка темы".encode()).decode("ascii") + "?="

    alt = (
        '--ALT\r\nContent-Type: text/plain; charset="utf-8"\r\n'
        "Content-Transfer-Encoding: 8bit\r\n\r\n"
        "Текстовое тело письма.\r\nВторая строка тела.\r\n\r\n"
    )
    if html:
        img_tag = '<img src="cid:pic@t">' if inline_image else ""
        alt += (
            '--ALT\r\nContent-Type: text/html; charset="utf-8"\r\n'
            "Content-Transfer-Encoding: 8bit\r\n\r\n"
            f"<html><body><p>HTML <b>тело</b> письма.</p>{img_tag}"
            '<p><a href="http://tracker.example/x.gif">внешняя</a></p>'
            '<img src="http://tracker.example/beacon.png"></body></html>\r\n\r\n'
        )
    alt += "--ALT--\r\n\r\n"

    related = (
        '--REL\r\nContent-Type: multipart/alternative; boundary="ALT"\r\n\r\n' + alt
    )
    if inline_image:
        related += (
            "--REL\r\nContent-Type: image/png\r\n"
            "Content-Transfer-Encoding: base64\r\n"
            "Content-ID: <pic@t>\r\nContent-Disposition: inline\r\n\r\n"
            f"{png_b64}\r\n\r\n"
        )
    related += "--REL--\r\n\r\n"

    head = (
        "From: Alice Example <alice@example.com>\r\n"
        "To: Bob Recipient <bob@example.com>\r\n"
        "Cc: carol@example.com\r\n"
        f"Subject: {subj}\r\n"
        "Date: Mon, 06 May 2024 09:30:00 +0000\r\n"
        "MIME-Version: 1.0\r\n"
        'Content-Type: multipart/mixed; boundary="MIX"\r\n\r\n'
        '--MIX\r\nContent-Type: multipart/related; boundary="REL"\r\n\r\n'
    )
    tail = ""
    if attachment:
        tail = (
            '--MIX\r\nContent-Type: text/plain; charset="utf-8"\r\n'
            "Content-Transfer-Encoding: base64\r\n"
            'Content-Disposition: attachment; filename="note.txt"\r\n\r\n'
            f"{note_b64}\r\n\r\n"
        )
    return (head + related + tail + "--MIX--\r\n").encode("utf-8")


def _make_plaintext_eml() -> bytes:
    return (
        "From: sender@example.com\r\n"
        "To: rcpt@example.com\r\n"
        "Subject: только текст\r\n"
        "Date: Tue, 07 May 2024 10:00:00 +0000\r\n"
        'Content-Type: text/plain; charset="utf-8"\r\n\r\n'
        "Единственная текстовая часть письма.\r\n"
    ).encode()


# --------------------------------------------------------------------------- #
# Диспетчеризация                                                             #
# --------------------------------------------------------------------------- #


def test_registry_selects_mail_viewer_eml(registry, tmp_path: Path) -> None:
    p = tmp_path / "letter.eml"
    p.write_bytes(_make_eml())
    assert isinstance(registry.viewer_for(p), MailViewer)


def test_registry_selects_mail_viewer_msg(registry) -> None:
    sample = DEMO / "mail/sample.msg"
    if not sample.exists():
        pytest.skip("demo/mail/sample.msg не сгенерирован")
    assert isinstance(registry.viewer_for(sample), MailViewer)


def test_mail_viewer_ignores_plain_text(registry, tmp_path: Path) -> None:
    t = tmp_path / "notes.txt"
    t.write_bytes(b"just text")
    assert not isinstance(registry.viewer_for(t), MailViewer)


# --------------------------------------------------------------------------- #
# EML                                                                         #
# --------------------------------------------------------------------------- #


def test_eml_headers_visible(tmp_path: Path) -> None:
    p = tmp_path / "letter.eml"
    p.write_bytes(_make_eml())
    viewer = MailViewer()
    viewer.safe_load(p)

    assert not viewer.is_error_widget
    assert viewer.headers["From"] == "Alice Example <alice@example.com>"
    assert viewer.headers["To"] == "Bob Recipient <bob@example.com>"
    assert viewer.headers["Cc"] == "carol@example.com"
    assert viewer.headers["Subject"] == "Проверка темы"
    assert "2024" in viewer.headers["Date"]

    plain = viewer._browser.toPlainText()
    for token in ("alice@example.com", "bob@example.com", "carol@example.com", "Проверка темы"):
        assert token in plain


def test_eml_html_body_rendered(tmp_path: Path) -> None:
    p = tmp_path / "letter.eml"
    p.write_bytes(_make_eml(html=True))
    viewer = MailViewer()
    viewer.safe_load(p)

    assert not viewer.is_error_widget
    assert "<b>тело</b>" in viewer.rendered_html
    assert "HTML" in viewer._browser.toPlainText()
    assert "тело" in viewer._browser.toPlainText()


def test_eml_inline_image_loads_but_network_does_not(tmp_path: Path) -> None:
    p = tmp_path / "letter.eml"
    p.write_bytes(_make_eml(html=True, inline_image=True))
    viewer = MailViewer()
    viewer.safe_load(p)

    assert not viewer.is_error_widget
    inline = viewer._browser.loadResource(_IMG_RESOURCE, QUrl("cid:pic@t"))
    assert inline is not None and len(bytes(inline)) > 0

    external = viewer._browser.loadResource(
        _IMG_RESOURCE, QUrl("http://tracker.example/beacon.png")
    )
    assert external is None or len(bytes(external)) == 0


def test_eml_plain_body_when_no_html(tmp_path: Path) -> None:
    p = tmp_path / "plain.eml"
    p.write_bytes(_make_plaintext_eml())
    viewer = MailViewer()
    viewer.safe_load(p)

    assert not viewer.is_error_widget
    assert "Единственная текстовая часть письма." in viewer._browser.toPlainText()


def test_eml_attachment_listed_and_opens_via_registry(tmp_path: Path) -> None:
    p = tmp_path / "letter.eml"
    p.write_bytes(_make_eml(attachment=True))
    viewer = MailViewer()
    viewer.safe_load(p)

    assert [a.name for a in viewer.attachments] == ["note.txt"]
    assert not viewer._attach_list.isHidden()
    assert viewer._attach_list.count() == 1

    child = viewer.open_attachment(0)
    assert not child.is_error_widget
    assert "строка два" in _text_of(child)


def test_eml_double_click_emits_signal(tmp_path: Path) -> None:
    p = tmp_path / "letter.eml"
    p.write_bytes(_make_eml(attachment=True))
    viewer = MailViewer()
    viewer.safe_load(p)

    seen: list[str] = []
    viewer.attachment_activated.connect(seen.append)
    viewer._attach_list.itemDoubleClicked.emit(viewer._attach_list.item(0))
    QApplication.processEvents()
    assert seen == ["note.txt"]


def test_eml_no_attachment_hides_list(tmp_path: Path) -> None:
    p = tmp_path / "letter.eml"
    p.write_bytes(_make_eml(attachment=False, inline_image=False))
    viewer = MailViewer()
    viewer.safe_load(p)

    assert viewer.attachments == []
    assert viewer._attach_list.isHidden()


def test_empty_eml_yields_error_widget(tmp_path: Path) -> None:
    p = tmp_path / "empty.eml"
    p.write_bytes(b"")
    viewer = MailViewer()
    viewer.safe_load(p)
    assert viewer.is_error_widget


# --------------------------------------------------------------------------- #
# MSG                                                                         #
# --------------------------------------------------------------------------- #


def test_msg_opens_with_same_fields() -> None:
    sample = DEMO / "mail/sample.msg"
    if not sample.exists():
        pytest.skip("demo/mail/sample.msg не сгенерирован")
    viewer = MailViewer()
    viewer.safe_load(sample)

    assert not viewer.is_error_widget
    assert viewer.headers["Subject"]
    assert "@" in viewer.headers["From"]
    assert "@" in viewer.headers["To"]
    assert viewer.headers["Cc"]
    assert viewer.headers["Date"]

    plain = viewer._browser.toPlainText()
    assert viewer.headers["Subject"] in plain


def test_msg_attachments_listed() -> None:
    sample = DEMO / "mail/sample.msg"
    if not sample.exists():
        pytest.skip("demo/mail/sample.msg не сгенерирован")
    viewer = MailViewer()
    viewer.safe_load(sample)

    assert len(viewer.attachments) >= 1
    child = viewer.open_attachment(0)
    assert not child.is_error_widget


def test_truncated_msg_yields_error_widget(tmp_path: Path) -> None:
    sample = DEMO / "mail/sample.msg"
    if not sample.exists():
        pytest.skip("demo/mail/sample.msg не сгенерирован")
    full = sample.read_bytes()
    p = tmp_path / "broken.msg"
    p.write_bytes(full[: len(full) // 3])
    viewer = MailViewer()
    viewer.safe_load(p)
    assert viewer.is_error_widget


def _text_of(viewer) -> str:
    from PyQt6.QtWidgets import QPlainTextEdit, QTextEdit

    for kind in (QTextEdit, QPlainTextEdit):
        for w in viewer.findChildren(kind):
            txt = w.toPlainText()
            if txt:
                return txt
    return ""
