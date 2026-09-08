"""Единый источник списка поддерживаемых форматов.

И таблица README «Поддерживаемые форматы», и диалог «О программе» строятся из
:data:`FORMAT_GROUPS` — так они не могут разойтись. Каждая группа ссылается на
реальный зарегистрированный класс просмотрщика; тест :mod:`tests.test_format_catalog`
сверяет каталог с :data:`omniviewer.registry.default_registry` и с самим README.md.
"""

from __future__ import annotations

from dataclasses import dataclass

from omniviewer.viewers.archive import ArchiveViewer
from omniviewer.viewers.base import BaseViewer
from omniviewer.viewers.document import DocumentViewer
from omniviewer.viewers.fallback import FallbackViewer
from omniviewer.viewers.font import FontViewer
from omniviewer.viewers.image import ImageViewer
from omniviewer.viewers.ipynb import IpynbViewer
from omniviewer.viewers.mail import MailViewer
from omniviewer.viewers.markup import MarkupViewer
from omniviewer.viewers.media import MediaViewer
from omniviewer.viewers.pdf import PdfViewer
from omniviewer.viewers.presentation import PresentationViewer
from omniviewer.viewers.spreadsheet import SpreadsheetViewer
from omniviewer.viewers.structure import StructureViewer
from omniviewer.viewers.text import TextViewer


## @brief Одна строка таблицы форматов: группа, просмотрщик, который её обслуживает, и текст.
@dataclass(frozen=True)
class FormatGroup:
    title: str
    viewer: type[BaseViewer]
    formats: str


FORMAT_GROUPS: tuple[FormatGroup, ...] = (
    FormatGroup(
        "Текст / код",
        TextViewer,
        "txt, исходный код с подсветкой синтаксиса (py, c, cpp, h, js, html, css, sh, bat, "
        "ps1 и др. через Pygments), ini, log, md, csv, tsv — как текст",
    ),
    FormatGroup(
        "Структура",
        StructureViewer,
        "JSON, YAML, XML, TOML — сворачиваемое дерево «ключ → значение → тип» (ленивое "
        "построение узлов + лимит детей, большой файл не подвешивает GUI); кнопка "
        "«дерево ⇄ текст»",
    ),
    FormatGroup(
        "Разметка",
        MarkupViewer,
        "Markdown (markdown-it-py, подсветка кода pygments), HTML/HTM/XHTML, MHTML "
        "(ресурсы инлайнятся) — рендер в QTextBrowser (HTML4/CSS2.1), строго офлайн",
    ),
    FormatGroup(
        "Презентации",
        PresentationViewer,
        "PPTX (текст слайдов по порядку + вложенные изображения, python-pptx), ODP "
        "(текст слайдов, odfpy), legacy PPT (извлечённый текст) — слайды секциями в "
        "QTextBrowser, строго офлайн",
    ),
    FormatGroup(
        "Ноутбуки",
        IpynbViewer,
        "Jupyter `.ipynb` — nbconvert (шаблон basic) → HTML: ячейки по порядку, "
        "Markdown отрендерен, код подсвечен pygments, текстовый и графический вывод; "
        "строго офлайн",
    ),
    FormatGroup(
        "Документы и книги",
        PdfViewer,
        "PDF, EPUB, MOBI, FB2, CBZ, XPS/OXPS (постранично, PyMuPDF)",
    ),
    FormatGroup(
        "Таблицы",
        SpreadsheetViewer,
        "XLSX, XLSM, XLS, ODS, CSV, TSV",
    ),
    FormatGroup(
        "Офисные документы",
        DocumentViewer,
        "DOCX (mammoth → HTML, заголовки/списки/изображения), DOC (olefile — "
        "извлечённый текст), ODT (odfpy — структура), RTF (striprtf — текст)",
    ),
    FormatGroup(
        "Изображения",
        ImageViewer,
        "PNG, JPEG, GIF, BMP, WebP, TIFF (многостраничный — листание кадров), ICO, "
        "SVG, HEIC/HEIF, AVIF, RAW (CR2/CR3/NEF/ARW/DNG/RAF/ORF/RW2 — по встроенному "
        "превью-JPEG)",
    ),
    FormatGroup("Аудио", MediaViewer, "MP3, FLAC, WAV, OGG, M4A, Opus — теги и обложка"),
    FormatGroup("Видео", MediaViewer, "MP4, MKV, AVI, WebM, MOV"),
    FormatGroup(
        "Шрифты",
        FontViewer,
        "TTF, OTF, WOFF, WOFF2 — образец начертания (панграммы и алфавит в нескольких "
        "кеглях этим шрифтом) + метаданные fontTools (семейство, начертание, версия, "
        "число глифов, состав таблиц); WOFF/WOFF2 распаковываются",
    ),
    FormatGroup(
        "Почта",
        MailViewer,
        "EML (stdlib email), MSG (Outlook, extract-msg) — заголовки From/To/Cc/Subject/Date, "
        "тело (HTML-часть в QTextBrowser строго офлайн, иначе text/plain), список вложений "
        "с открытием тем же приложением",
    ),
    FormatGroup(
        "Архивы",
        ArchiveViewer,
        "ZIP, TAR(.gz/.bz2/.xz), 7Z, RAR, ISO, CAB, LHA, AR — дерево содержимого; двойной "
        "клик открывает вложенный файл тем же приложением; вложенные архивы — рекурсивно "
        "(с лимитами глубины и суммарного размера, защита от Zip Slip)",
    ),
    FormatGroup(
        "Любой другой файл",
        FallbackViewer,
        "fallback: текст → hex-дамп + базовые метаданные (размер, MIME, даты); для "
        "форматов, которые разбирает hachoir, — ещё и дерево полей (десятки экзотических "
        "бинарных типов)",
    ),
)


## @brief Markdown-таблица «Группа | Форматы», байт-в-байт совпадающая с блоком в README.md.
def render_markdown_table() -> str:
    lines = ["| Группа | Форматы |", "|---|---|"]
    lines.extend(f"| {g.title} | {g.formats} |" for g in FORMAT_GROUPS)
    return "\n".join(lines)
