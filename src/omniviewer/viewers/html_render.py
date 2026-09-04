# ruff: noqa: BLE001
"""Общий шов «HTML-строка → виджет QTextBrowser».

Переиспользуемый хелпер для просмотрщиков разметки (Markdown / HTML / MHTML) и
последующих тикетов — DOCX, презентаций, ноутбуков: все они приводят документ к
строке HTML4/CSS2.1 и отдают её сюда.

Гарантии:
- рендер строго офлайн: любые внешние ресурсы (``http``/``https``/``ftp`` …) не
  загружаются, ``loadResource`` для них возвращает пустой ``QByteArray``;
- локально известные ресурсы (кадры MHTML, картинки DOCX) отдаются из словаря
  ``resources`` по URL/``cid:``-ключу;
- ``data:``-URI декодируются на месте, без обращения к сети;
- виджет только для чтения, внешние ссылки не открываются.
"""

from __future__ import annotations

import base64
from collections.abc import Mapping

from PyQt6.QtCore import QByteArray, QUrl
from PyQt6.QtWidgets import QTextBrowser


def _decode_data_uri(url: QUrl) -> QByteArray | None:
    """Декодировать ``data:``-URI в байты (или ``None``, если это не он)."""
    if url.scheme().lower() != "data":
        return None
    raw = url.toString()[len("data:") :]
    head, sep, payload = raw.partition(",")
    if not sep:
        return QByteArray()
    try:
        if head.strip().lower().endswith("base64"):
            return QByteArray(base64.b64decode(payload))
        return QByteArray(QByteArray.fromPercentEncoding(payload.encode("latin-1")))
    except Exception:
        return QByteArray()


## @brief QTextBrowser с офлайн-политикой загрузки ресурсов.
#
# Ресурсы берутся только из локального словаря, ``data:``-URI и локальных файлов;
# сетевые схемы блокируются (возвращается пустой QByteArray).
class OfflineTextBrowser(QTextBrowser):
    _LOCAL_SCHEMES = frozenset({"", "file", "qrc", "about"})

    def __init__(self, parent=None):
        super().__init__(parent)
        self._resources: dict[str, QByteArray] = {}
        self.setReadOnly(True)
        self.setOpenExternalLinks(False)
        self.setOpenLinks(False)

    def set_resources(self, resources: Mapping[str, bytes | QByteArray] | None) -> None:
        """Задать карту «URL/cid → байты» для инлайн-ресурсов документа."""
        self._resources = {
            str(key): value if isinstance(value, QByteArray) else QByteArray(bytes(value))
            for key, value in (resources or {}).items()
        }

    def loadResource(self, resource_type: int, url: QUrl):
        key = url.toString()
        if key in self._resources:
            return self._resources[key]

        stripped = key.split("#", 1)[0]
        if stripped in self._resources:
            return self._resources[stripped]

        data = _decode_data_uri(url)
        if data is not None:
            return data

        if url.scheme().lower() in self._LOCAL_SCHEMES:
            return super().loadResource(resource_type, url)

        # Внешняя сеть — офлайн-режим, ничего не грузим.
        return QByteArray()


def build_html_browser(
    html: str,
    *,
    resources: Mapping[str, bytes | QByteArray] | None = None,
    base_url: QUrl | str | None = None,
) -> OfflineTextBrowser:
    """Собрать готовый к показу ``OfflineTextBrowser`` из строки HTML.

    :param html: разметка HTML4/CSS2.1.
    :param resources: карта «URL или ``cid:``-ключ → байты» для встроенных
        ресурсов (кадры MHTML, картинки офисных документов).
    :param base_url: база для разрешения относительных ссылок (необязательно).
    """
    browser = OfflineTextBrowser()
    browser.set_resources(resources)
    if base_url is not None:
        browser.document().setBaseUrl(QUrl(base_url) if isinstance(base_url, str) else base_url)
    browser.setHtml(html)
    return browser
