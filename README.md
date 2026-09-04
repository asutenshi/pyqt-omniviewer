# pyqt-omniviewer

[![CI](https://github.com/asutenshi/pyqt-omniviewer/actions/workflows/ci.yml/badge.svg)](https://github.com/asutenshi/pyqt-omniviewer/actions/workflows/ci.yml)

Двухпанельный десктоп-просмотрщик для **максимального числа типов файлов**.
Python + PyQt6. Всё рендерится программно, **без запуска сторонних приложений**.

> Проект разрабатывается в рамках хакатона: побеждает тот, чьё приложение
> отобразит больше типов файлов. Поэтому каждый отдельный просмотрщик —
> минимальный: задача «показать содержимое», без редакторов и лишнего UX.
> Полное техзадание и решения — в [SPEC.md](SPEC.md).

## Демо

https://github.com/user-attachments/assets/325a28d6-c7b4-4216-9489-264fbeeb61fc

## Возможности

- Две панели в перетаскиваемом сплиттере: **просмотр слева, дерево файлов справа**
  (по ТЗ), кнопка «поменять местами».
- Дерево выбранной папки: адресная строка, Назад/Вперёд/Вверх/Домой, фильтр по
  имени, авто-обновление при изменениях на диске.
- Сортировка по имени / размеру / типу / дате — клик по заголовку колонки или меню
  сортировки; «папки сверху».
- Тип файла определяется по содержимому (`QMimeDatabase`), а не только по
  расширению.
- Панель свойств: размер, MIME, даты, EXIF/теги/разрешение/длительность.
- Любой нераспознанный файл всё равно отображается: текст → hex-дамп + метаданные.

## Поддерживаемые форматы

### Работают сейчас

| Группа | Форматы |
|---|---|
| Текст / код | txt, исходный код с подсветкой синтаксиса (py, c, cpp, h, js, html, css, sh, bat, ps1 и др. через Pygments), json, yaml, xml, toml, ini, log, md, csv, tsv — как текст |
| Разметка | Markdown (markdown-it-py, подсветка кода pygments), HTML/HTM/XHTML, MHTML (ресурсы инлайнятся) — рендер в QTextBrowser (HTML4/CSS2.1), строго офлайн |
| Презентации | PPTX (текст слайдов по порядку + вложенные изображения, python-pptx), ODP (текст слайдов, odfpy), legacy PPT (извлечённый текст) — слайды секциями в QTextBrowser, строго офлайн |
| Ноутбуки | Jupyter `.ipynb` — nbconvert (шаблон basic) → HTML: ячейки по порядку, Markdown отрендерен, код подсвечен pygments, текстовый и графический вывод; строго офлайн |
| Документы и книги | PDF, EPUB, MOBI, FB2, CBZ, XPS/OXPS (постранично, PyMuPDF) |
| Таблицы | XLSX, XLSM, XLS, ODS, CSV, TSV |
| Офисные документы | DOCX (mammoth → HTML, заголовки/списки/изображения), DOC (olefile — извлечённый текст), ODT (odfpy — структура), RTF (striprtf — текст) |
| Изображения | PNG, JPEG, GIF, BMP, WebP, TIFF (многостраничный — листание кадров), ICO, SVG, HEIC/HEIF, AVIF, RAW (CR2/CR3/NEF/ARW/DNG/RAF/ORF/RW2 — по встроенному превью-JPEG) |
| Аудио | MP3, FLAC, WAV, OGG, M4A, Opus |
| Видео | MP4, MKV, AVI, WebM, MOV |
| Шрифты | TTF, OTF, WOFF, WOFF2 — образец начертания (панграммы и алфавит в нескольких кеглях этим шрифтом) + метаданные fontTools (семейство, начертание, версия, число глифов, состав таблиц); WOFF/WOFF2 распаковываются |
| Почта | EML (stdlib email), MSG (Outlook, extract-msg) — заголовки From/To/Cc/Subject/Date, тело (HTML-часть в QTextBrowser строго офлайн, иначе text/plain), список вложений с открытием тем же приложением |
| Архивы | ZIP, TAR(.gz/.bz2/.xz), 7Z, RAR, ISO, CAB, LHA, AR — дерево содержимого; двойной клик открывает вложенный файл тем же приложением; вложенные архивы — рекурсивно (с лимитами глубины и суммарного размера, защита от Zip Slip) |
| Любой другой файл | fallback: текст → hex-дамп + базовые метаданные (размер, MIME, даты) |

### В планах

| Группа | Форматы |
|---|---|
| Аудио | теги и обложка в панели свойств |
| Прочее | дерево полей произвольного бинарного формата (hachoir) |

Список пополняется по мере разработки — полный план см. в [SPEC.md](SPEC.md).

## Установка

Эталон — чистая Ubuntu 24.04; также поддержана Fedora/RHEL.

```bash
git clone https://github.com/asutenshi/pyqt-omniviewer.git
cd pyqt-omniviewer
bash install.sh
```

`install.sh` сам выбирает пакетный менеджер (`apt` или `dnf`), ставит системные
пакеты и Python-зависимости в `.venv`. Список pip-пакетов —
[requirements.txt](requirements.txt); системные пакеты перечислены внутри `install.sh`.

## Запуск

```bash
source .venv/bin/activate
omniviewer [путь-к-папке-или-файлу]
```

Без аргумента открывается домашняя папка.

## Документация (Doxygen)

```bash
sudo apt-get install -y doxygen   # Fedora: sudo dnf install -y doxygen
doxygen Doxyfile
xdg-open docs/html/index.html
```

## Стек и ключевые решения

- **PyQt6** (только ядро Qt). `PyQt6-WebEngine` не используется — он многопроцессный
  (Chromium), что противоречит требованию «без сторонних процессов». HTML / Markdown /
  DOCX / ipynb рендерятся через `QTextBrowser`, SVG — через `QtSvg`.
- **PyMuPDF** — PDF и электронные книги одной библиотекой (проект под **AGPL-3.0**).
- **QtMultimedia** (FFmpeg-бэкенд) — аудио/видео; опциональный запасной движок — `python-mpv`.
- Строго in-process: никаких вызовов `soffice`, `pdftoppm`, `ffmpeg`-CLI, `unrar`.
  Офисные документы показываются как текст + структура + вложенные изображения.
- Архитектура: `ViewerRegistry` + `BaseViewer`, выбор просмотрщика по MIME,
  тяжёлый рендер в фоновом потоке с отменой.

Полное обоснование — [SPEC.md](SPEC.md).

## Лицензия

[AGPL-3.0-or-later](LICENSE) (обусловлено использованием PyMuPDF).

## About

`pyqt-omniviewer` is a two-pane desktop file viewer (PyQt6) aiming to preview as
many file types as possible, rendering everything in-process without launching
external applications. Built for a hackathon scored by format coverage. See
[SPEC.md](SPEC.md) for the full specification.
