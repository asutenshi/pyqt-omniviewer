#!/usr/bin/env python3
"""Генератор скриптуемых демонстрационных образцов для ``demo/``.

Наполняет каталог ``demo/`` файлами, которые можно воспроизвести из кода:
тексты, исходники, ``csv``/``tsv``, ``json``/``yaml``/``xml``/``ini``, простые
растровые изображения, большой текстовый файл для проверки оконного чтения,
набор «битых» (обрезанных) образцов и файл без расширения с распознаваемым
содержимым.

Запуск идемпотентен: повторный вызов не меняет уже созданные файлы. Каждый
последующий тикет-просмотрщик добавляет сюда свою ветку генерации и/или
готовый бинарный образец (происхождение — в ``demo/CREDITS.md``).

Модуль не тянет сторонних зависимостей — только стандартная библиотека, чтобы
генератор работал на «голом» окружении без установленных пакетов проекта.

Использование::

    python demo/generate.py            # наполнить каталог demo/
    python demo/generate.py --dest DIR # наполнить произвольный каталог
"""

from __future__ import annotations

import argparse
import base64
import struct
import sys
import zlib
from collections.abc import Callable
from pathlib import Path

## @brief Ориентир порога «оконного» чтения текста для демо-набора.
#  Продуктовое значение по умолчанию задаётся отдельно (через ``QSettings``) и
#  крупнее; здесь порог намеренно небольшой, чтобы большой образец укладывался в
#  бюджет размера каталога ``demo/`` (< 5 МБ суммарно).
WINDOW_READ_THRESHOLD_BYTES: int = 256 * 1024

## @brief Бюджет суммарного размера каталога ``demo/`` (см. SPEC).
SIZE_BUDGET_BYTES: int = 5 * 1024 * 1024

# Каталог demo/ рядом с этим скриптом — цель генерации по умолчанию.
DEMO_DIR: Path = Path(__file__).resolve().parent


# --------------------------------------------------------------------------- #
# Низкоуровневые помощники                                                     #
# --------------------------------------------------------------------------- #


def _write(path: Path, data: bytes | str) -> Path:
    """Записать файл, создав родительские каталоги.

    Если содержимое не изменилось — файл не трогаем, чтобы повторный запуск был
    идемпотентным и не порождал лишних изменений mtime.
    """
    payload = data.encode("utf-8") if isinstance(data, str) else data
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() == payload:
        return path
    path.write_bytes(payload)
    return path


def _png(width: int, height: int, pixel: Callable[[int, int], tuple[int, int, int]]) -> bytes:
    """Собрать минимальный валидный PNG (truecolor, 8 бит) стандартной библиотекой."""

    def chunk(tag: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + tag + body + struct.pack(
            ">I", zlib.crc32(tag + body) & 0xFFFFFFFF
        )

    raw = bytearray()
    for y in range(height):
        raw.append(0)  # тип фильтра строки: None
        for x in range(width):
            raw.extend(pixel(x, y))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"".join(
        (
            b"\x89PNG\r\n\x1a\n",
            chunk(b"IHDR", ihdr),
            chunk(b"IDAT", zlib.compress(bytes(raw), 9)),
            chunk(b"IEND", b""),
        )
    )


# Крошечный (16×16) JPEG, сгенерированный один раз и вкладываемый как константа,
# чтобы не тянуть JPEG-кодировщик. CC0 — создан скриптом проекта.
_JPEG_16 = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAoHBwgHBgoICAgLCgoLDhgQDg0NDh0VFhEYIx8lJCIf"
    "IiEmKzcvJik0KSEiMEExNDk7Pj4+JS5ESUM8SDc9Pjv/2wBDAQoLCw4NDhwQEBw7KCIoOzs7Ozs7"
    "Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozv/wAARCAAQABADASIA"
    "AhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAABQb/xAAXEAADAQAAAAAAAAAAAAAAAAAAAgQx/8QA"
    "FAEBAAAAAAAAAAAAAAAAAAAABf/EABoRAAEFAQAAAAAAAAAAAAAAAAACAwQFMWH/2gAMAwEAAhED"
    "EQA/AJiZsF5mwCmbBeZsFn5vRKrTh//Z"
)


# --------------------------------------------------------------------------- #
# Содержимое образцов                                                          #
# --------------------------------------------------------------------------- #

_PLAIN_EN = """\
pyqt-omniviewer demo sample: plain text
=======================================

This file is UTF-8 encoded plain text with a few short paragraphs. It exists so
the registry smoke test has a trivial text/plain fixture to hand to the text
viewer.

Lines stay under eighty columns. No tabs, no trailing whitespace, single blank
line between paragraphs.
"""

_NOTES_RU = """\
Демонстрационный образец: текст на русском языке
===============================================

Файл в кодировке UTF-8. Нужен, чтобы проверять определение кодировки и вывод
кириллицы в просмотрщике текста.

Съешь же ещё этих мягких французских булок да выпей чаю.
"""

_EXAMPLE_PY = '''\
"""Небольшой модуль-образец исходного кода Python для подсветки синтаксиса."""

from __future__ import annotations

import sys


def greet(name: str) -> str:
    """Вернуть приветствие."""
    return f"Hello, {name}!"


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    print(greet(args[0] if args else "world"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

_EXAMPLE_C = """\
/* Образец исходного кода C для подсветки синтаксиса. */
#include <stdio.h>

int main(void)
{
    for (int i = 0; i < 3; ++i) {
        printf("hello %d\\n", i);
    }
    return 0;
}
"""

_TABLE_ROWS = [
    ("id", "name", "role", "score"),
    ("1", "Alice", "developer", "42"),
    ("2", "Bob", "designer", "37"),
    ("3", "Carol", "manager", "58"),
    ("4", "Dave", "qa", "45"),
]

_RECORD_JSON = """\
{
  "name": "demo",
  "version": 1,
  "enabled": true,
  "tags": ["text", "json", "sample"],
  "author": {
    "name": "pyqt-omniviewer",
    "url": "https://github.com/asutenshi/pyqt-omniviewer"
  },
  "items": [
    {"id": 1, "title": "first"},
    {"id": 2, "title": "second"}
  ]
}
"""

_CONFIG_YAML = """\
# Демонстрационный YAML-образец.
name: demo
version: 1
enabled: true
tags:
  - text
  - yaml
  - sample
author:
  name: pyqt-omniviewer
  url: https://github.com/asutenshi/pyqt-omniviewer
items:
  - id: 1
    title: first
  - id: 2
    title: second
"""

_CATALOG_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<catalog name="demo" version="1">
  <item id="1">
    <title>first</title>
    <tags>
      <tag>text</tag>
      <tag>xml</tag>
    </tags>
  </item>
  <item id="2">
    <title>second</title>
    <tags>
      <tag>sample</tag>
    </tags>
  </item>
</catalog>
"""

_SETTINGS_INI = """\
; Демонстрационный INI-образец.
[general]
name = demo
version = 1
enabled = true

[window]
width = 1024
height = 768

[paths]
last_dir = ~/Documents
"""

_SHEBANG_SCRIPT = """\
#!/bin/sh
# Файл без расширения с распознаваемым содержимым (shebang -> shell script).
echo "pyqt-omniviewer demo: extensionless shell script"
exit 0
"""


def _csv_bytes(delimiter: str) -> bytes:
    lines = [delimiter.join(row) for row in _TABLE_ROWS]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _big_text_bytes() -> bytes:
    """Детерминированный текстовый файл заведомо крупнее порога оконного чтения."""
    target = WINDOW_READ_THRESHOLD_BYTES + 128 * 1024
    template = (
        "Съешь же ещё этих мягких французских булок да выпей чаю. "
        "The quick brown fox jumps over the lazy dog. "
    )
    out = bytearray()
    line_no = 0
    while len(out) < target:
        out += f"{line_no:07d}  {template}\n".encode()
        line_no += 1
    return bytes(out)


def _swatch_png() -> bytes:
    return _png(32, 32, lambda x, y: (8 * x, 8 * y, 128))


# --------------------------------------------------------------------------- #
# Точка сборки                                                                 #
# --------------------------------------------------------------------------- #


_PDF_BYTES = None
def _write_minimal_pdf() -> bytes:
    global _PDF_BYTES
    if _PDF_BYTES is not None:
        return _PDF_BYTES
    import fitz  # type: ignore
    doc = fitz.open()
    page = doc.new_page(width=400, height=400)
    page.insert_text((50, 50), "pyqt-omniviewer PDF sample", fontsize=14)
    page = doc.new_page(width=400, height=400)
    page.insert_text((50, 50), "Page 2", fontsize=14)
    res = doc.write()
    doc.close()
    _PDF_BYTES = res
    return res

def _write_minimal_cbz() -> bytes:
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("page1.png", _swatch_png())
        z.writestr("page2.jpg", _JPEG_16)
    return buf.getvalue()

def _write_minimal_epub() -> bytes:
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml", '<?xml version="1.0"?>\n<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
        z.writestr("content.opf", '<?xml version="1.0"?><package version="2.0" xmlns="http://www.idpf.org/2007/opf"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Sample EPUB</dc:title></metadata><manifest><item id="item1" href="index.html" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="item1"/></spine></package>')
        z.writestr("index.html", '<html xmlns="http://www.w3.org/1999/xhtml"><body><h1>Sample EPUB</h1></body></html>')
    return buf.getvalue()

def _write_minimal_fb2() -> bytes:
    return b'<?xml version="1.0" encoding="utf-8"?><FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0"><description><title-info><book-title>Sample FB2</book-title><author><first-name>Test</first-name><last-name>Author</last-name></author></title-info></description><body><title><p>Sample FB2</p></title><p>Test content</p></body></FictionBook>'

def _write_minimal_xps() -> bytes:
    # XPS is essentially a zip with specific FixedDocument sequences.
    # PyMuPDF can also open basic empty zip? No, it needs valid XPS.
    # Actually, we can just use a dummy text file renamed to XPS if PyMuPDF falls back to text,
    # but let's just make a very basic empty XPS structure.
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="utf-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="fdoc" ContentType="application/vnd.ms-package.xps-fixeddocument+xml" /><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml" /></Types>')
        z.writestr("_rels/.rels", '<?xml version="1.0" encoding="utf-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Type="http://schemas.microsoft.com/xps/2005/06/fixedrepresentation" Target="/FixedDocumentSequence.fdseq" Id="R1" /></Relationships>')
        z.writestr("FixedDocumentSequence.fdseq", '<FixedDocumentSequence xmlns="http://schemas.microsoft.com/xps/2005/06"><DocumentReference Source="Documents/1/FixedDocument.fdoc" /></FixedDocumentSequence>')
        z.writestr("Documents/1/FixedDocument.fdoc", '<FixedDocument xmlns="http://schemas.microsoft.com/xps/2005/06"><PageContent Source="Pages/1.fpage" /></FixedDocument>')
        z.writestr("Documents/1/Pages/1.fpage", '<FixedPage Width="793.76" Height="1122.56" xmlns="http://schemas.microsoft.com/xps/2005/06" xml:lang="en-US"></FixedPage>')
        z.writestr("Documents/1/_rels/FixedDocument.fdoc.rels", '<?xml version="1.0" encoding="utf-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Type="http://schemas.microsoft.com/xps/2005/06/required-resource" Target="/Documents/1/Pages/1.fpage" Id="R1" /></Relationships>')
    return buf.getvalue()

def build(dest: Path) -> list[Path]:
    """Наполнить ``dest`` всеми скриптуемыми образцами. Идемпотентно.

    Возвращает отсортированный список записанных путей.
    """
    dest = Path(dest)
    png = _swatch_png()
    jpeg = _JPEG_16
    record_json = _RECORD_JSON
    catalog_xml = _CATALOG_XML
    pdf = _write_minimal_pdf()

    written = [
        _write(dest / "text/plain-en.txt", _PLAIN_EN),
        _write(dest / "text/notes-ru.txt", _NOTES_RU),
        _write(dest / "code/example.py", _EXAMPLE_PY),
        _write(dest / "code/example.c", _EXAMPLE_C),
        _write(dest / "data/table.csv", _csv_bytes(",")),
        _write(dest / "data/table.tsv", _csv_bytes("\t")),
        _write(dest / "data/record.json", record_json),
        _write(dest / "data/config.yaml", _CONFIG_YAML),
        _write(dest / "data/catalog.xml", catalog_xml),
        _write(dest / "data/settings.ini", _SETTINGS_INI),
        _write(dest / "images/swatch.png", png),
        _write(dest / "images/swatch.jpg", jpeg),
        _write(dest / "books/sample.pdf", pdf),
        _write(dest / "books/sample.cbz", _write_minimal_cbz()),
        _write(dest / "books/sample.epub", _write_minimal_epub()),
        _write(dest / "books/sample.fb2", _write_minimal_fb2()),
        _write(dest / "books/sample.xps", _write_minimal_xps()),
        _write(dest / "large/big-lines.txt", _big_text_bytes()),
        _write(dest / "noext/hello-script", _SHEBANG_SCRIPT),
        # «Битые» образцы: обрезки валидных файлов — просмотрщик обязан отдать
        # аккуратный «ошибочный» виджет, а не упасть.
        _write(dest / "broken/truncated.png", png[: len(png) // 2]),
        _write(dest / "broken/truncated.jpg", jpeg[: len(jpeg) // 3]),
        _write(dest / "broken/truncated.json", record_json[:60]),
        _write(dest / "broken/truncated.xml", catalog_xml[:80]),
        _write(dest / "broken/truncated.pdf", pdf[: 10]),
    ]
    return sorted(written)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Сгенерировать демонстрационные образцы demo/.")
    parser.add_argument(
        "--dest",
        type=Path,
        default=DEMO_DIR,
        help="каталог назначения (по умолчанию — каталог самого скрипта)",
    )
    args = parser.parse_args(argv)

    written = build(args.dest)
    total = sum(p.stat().st_size for p in written)
    print(f"demo/generate: {len(written)} файлов, {total / 1024:.1f} КБ -> {args.dest}")
    if total >= SIZE_BUDGET_BYTES:
        print("ВНИМАНИЕ: превышен бюджет размера demo/ (< 5 МБ)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
