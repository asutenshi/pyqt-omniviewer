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

This file is UTF-8 encoded plain text with a few short paragraphs. It exists so
the registry smoke test has a trivial text/plain fixture to hand to the text
viewer.

Lines stay under eighty columns. No tabs, no trailing whitespace, single blank
line between paragraphs.
"""

_NOTES_RU = """\
Демонстрационный образец: текст на русском языке

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

_XLSX = base64.b64decode("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")
_ODS = base64.b64decode("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")
_XLS = base64.b64decode("0M8R4KGxGuEAAAAAAAAAAAAAAAAAAAAAPgADAP7/CQAGAAAAAAAAAAAAAAABAAAACQAAAAAAAAAAEAAA/v///wAAAAD+////AAAAAAgAAAD///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////8JCBAAAAYFALsNzAcAAAAABgAAAOEAAgCwBMEAAgAAAOIAAABcAHAATm9uZSAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIEIAAgCwBGEBAgAAAD0BAgABAJwAAgAOABkAAgAAABIAAgAAAGMAAgAAABMAAgAAAK8BAgAAALwBAgAAAEAAAgAAAI0AAgAAAD0AEgDgAVoAzz9OKjgAAAAAAAEAWAIiAAIAAAAOAAIAAQC3AQIAAADaAAIAAAAxABUAyAAAAP9/kAEAAAAAAQAFAEFyaWFsMQAVAMgAAAD/f5ABAAAAAAEABQBBcmlhbDEAFQDIAAAA/3+QAQAAAAABAAUAQXJpYWwxABUAyAAAAP9/kAEAAAAAAQAFAEFyaWFsMQAVAMgAAAD/f5ABAAAAAAEABQBBcmlhbDEAFQDIAAAA/3+QAQAAAAABAAUAQXJpYWwxABUAyAAAAP9/kAEAAAAAAQAFAEFyaWFsHgQMAKQABwAAR2VuZXJhbOAAFAAGAKQA9f8gAAD0AAAAAAAAAADAIOAAFAAGAKQA9f8gAAD0AAAAAAAAAADAIOAAFAAGAKQA9f8gAAD0AAAAAAAAAADAIOAAFAAGAKQA9f8gAAD0AAAAAAAAAADAIOAAFAAGAKQA9f8gAAD0AAAAAAAAAADAIOAAFAAGAKQA9f8gAAD0AAAAAAAAAADAIOAAFAAGAKQA9f8gAAD0AAAAAAAAAADAIOAAFAAGAKQA9f8gAAD0AAAAAAAAAADAIOAAFAAGAKQA9f8gAAD0AAAAAAAAAADAIOAAFAAGAKQA9f8gAAD0AAAAAAAAAADAIOAAFAAGAKQA9f8gAAD0AAAAAAAAAADAIOAAFAAGAKQA9f8gAAD0AAAAAAAAAADAIOAAFAAGAKQA9f8gAAD0AAAAAAAAAADAIOAAFAAGAKQA9f8gAAD0AAAAAAAAAADAIOAAFAAGAKQA9f8gAAD0AAAAAAAAAADAIOAAFAAGAKQA9f8gAAD0AAAAAAAAAADAIOAAFAAGAKQAAQAgAAD4AAAAAAAAAADAIOAAFAAHAKQAAQAgAAD4AAAAAAAAAADAIJMCBAAAgAD/YAECAAEAhQAPAO4DAAAAAAcAU2hlZXQgMfwASAAKAAAACQAAAAIAAGlkBAAAbmFtZQUAAEFsaWNlAwAAQm9iBwAAQ2hhcmxpZQUAAHNjb3JlBgAAYWN0aXZlAwAAeWVzAgAAbm8KAAAACQgQAAAGEAC7DcwHAAAAAAYAAAANAAIAAQAMAAIAZAAPAAIAAQARAAIAAAAQAAgA/Knx0k1iUD9fAAIAAACAAAgAAAAAAAEAAAAlAgQAAAD/AIEAAgABDAACDgAAAAAABAAAAAAABAAAACoAAgAAACsAAgAAAIIAAgABABsAAgAAABoAAgAAABQABQACAAAmUBUABQACAAAmRoMAAgABAIQAAgAAACYACAAzMzMzMzPTPycACAAzMzMzMzPTPygACACF61G4HoXjPykACACuR+F6FK7XP6EAIgAJAGQAAQABAAEAgwAsASwBmpmZmZmZuT+amZmZmZm5PwEAEgACAAAA3QACAAAAGQACAAAAYwACAAAAEwACAAAACAIQAAAAAAAEAP8AAAAAAAABDwD9AAoAAAAAABEAAAAAAP0ACgAAAAEAEQABAAAA/QAKAAAAAgARAAUAAAD9AAoAAAADABEABgAAAAgCEAABAAAABAD/AAAAAAAAAQ8AfgIKAAEAAAARAAYAAAD9AAoAAQABABEAAgAAAH4CCgABAAIAEQBrQgAA/QAKAAEAAwARAAcAAAAIAhAAAgAAAAQA/wAAAAAAAAEPAH4CCgACAAAAEQAKAAAA/QAKAAIAAQARAAMAAAB+AgoAAgACABEAmgAAAP0ACgACAAMAEQAIAAAACAIQAAMAAAAEAP8AAAAAAAABDwB+AgoAAwAAABEADgAAAP0ACgADAAEAEQAEAAAAfgIKAAMAAgARABucAAD9AAoAAwADABEABwAAAD4CEgC2AgAAAABAAAAAAAAAAAAAAAAKAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAQAAAAIAAAADAAAABAAAAAUAAAAGAAAABwAAAP7////9/////v////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////9SAG8AbwB0ACAARQBuAHQAcgB5AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAFgAFAf//////////AQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAP7///8AAAAAAAAAAFcAbwByAGsAYgBvAG8AawAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAASAAIB////////////////AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAH///////////////8AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD+////AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAf///////////////wAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAP7///8AAAAAAAAAAA==")

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
        _write(dest / "data/table.xlsx", _XLSX),
        _write(dest / "data/table.ods", _ODS),
        _write(dest / "data/table.xls", _XLS),

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
        _write(dest / "broken/truncated.xlsx", _XLSX[:10]),
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
