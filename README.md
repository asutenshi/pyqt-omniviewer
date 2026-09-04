# pyqt-omniviewer

Двухпанельный десктоп-просмотрщик для **максимального числа типов файлов**.
Python + PyQt6. Всё рендерится программно, **без запуска сторонних приложений**.

> Проект разрабатывается в рамках хакатона: побеждает тот, чьё приложение
> отобразит больше типов файлов. Поэтому каждый отдельный просмотрщик —
> минимальный: задача «показать содержимое», без редакторов и лишнего UX.
> Полное техзадание и решения — в [SPEC.md](SPEC.md).

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

| Группа | Форматы |
|---|---|
| Текст / код | txt, любой исходный код (подсветка), json, yaml, xml, toml, ini, log |
| Разметка | Markdown, HTML, MHTML, XHTML (базовый HTML4/CSS2.1 движком Qt) |
| Документы | PDF, EPUB, MOBI, FB2, CBZ, XPS, DOCX, DOC, ODT, RTF |
| Таблицы | XLSX, XLS, ODS, CSV, TSV |
| Презентации | PPTX, PPT, ODP |
| Ноутбуки | ipynb |
| Изображения | PNG, JPEG, GIF, BMP, WebP, TIFF, ICO, SVG, HEIC/HEIF, AVIF, RAW (CR2/CR3/NEF/ARW/DNG…) |
| Аудио | MP3, FLAC, WAV, OGG, M4A, Opus (+ теги и обложка) |
| Видео | MP4, MKV, AVI, WebM, MOV |
| Архивы | ZIP, TAR(.gz/.bz2/.xz), 7Z, RAR, ISO, CAB, LHA — просмотр содержимого и вложенных файлов |
| Шрифты | TTF, OTF, WOFF, WOFF2 (образец начертания) |
| Почта | EML, MSG |
| Прочее | любой бинарный формат — дерево полей (hachoir) + hex + метаданные |

Актуальный список пополняется по мере разработки — см. [SPEC.md](SPEC.md).

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
