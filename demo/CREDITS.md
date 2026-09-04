# demo/ — происхождение и лицензии образцов

Все файлы в `demo/` — свободные образцы под **CC0 1.0 / public domain**, пригодные
для распространения вместе с проектом и использования в тестах.

## Скриптуемые образцы

Создаются `demo/generate.py` из кода (тексты, исходники, `csv`/`tsv`,
`json`/`yaml`/`xml`/`ini`, архивы `zip`/`tar.gz`/`ar`/вложенный `zip`, разметка
`md`/`html`/`xhtml`/`mhtml` с инлайновой картинкой, презентация `ppt`
(двоичный OLE/CFBF собран вручную из stdlib `struct`), большой текстовый файл,
«битые» обрезки, файл без расширения). Автор — этот репозиторий, лицензия
**CC0 1.0**. Воспроизводятся командой
`python demo/generate.py` и не требуют отдельной атрибуции.

## Бинарные образцы

| Файл | Тип | Происхождение | Лицензия |
|---|---|---|---|
| `images/swatch.png` | PNG 32×32 | сгенерирован `demo/generate.py` (stdlib `zlib`) | CC0 1.0 |
| `images/swatch.jpg` | JPEG 16×16 | сгенерирован однократно, вложён в `generate.py` как base64 | CC0 1.0 |
| `images/sample.heic` | HEIC 40×30 | сгенерирован однократно через `pillow-heif`, вложён в `generate.py` как base64 | CC0 1.0 |
| `images/sample.avif` | AVIF 40×30 | сгенерирован однократно через `pillow-avif-plugin`, вложён в `generate.py` как base64 | CC0 1.0 |
| `images/multipage.tiff` | TIFF, 3 кадра 40×30 | сгенерирован однократно через `Pillow`, вложён в `generate.py` как base64 | CC0 1.0 |
| `images/sample.dng` | DNG (CFA raw) 32×24 | минимальный валидный для LibRaw DNG собран вручную (stdlib `struct`), вложён в `generate.py` как base64 | CC0 1.0 |
| `archives/sample.zip` | ZIP | `demo/generate.py` (stdlib `zipfile`) | CC0 1.0 |
| `archives/sample.tar.gz` | TAR+GZIP | `demo/generate.py` (stdlib `tarfile`/`gzip`) | CC0 1.0 |
| `archives/sample.ar` | Unix `ar` | `demo/generate.py` (собран вручную, stdlib) | CC0 1.0 |
| `archives/nested.zip` | ZIP в ZIP | `demo/generate.py` (stdlib `zipfile`) | CC0 1.0 |
| `presentations/sample.pptx` | PPTX, 3 слайда (на 2-м картинка) | сгенерирован однократно через `python-pptx`, вложён в `generate.py` как base64 | CC0 1.0 |
| `presentations/sample.odp` | ODP, 3 слайда | сгенерирован однократно через `odfpy`, вложён в `generate.py` как base64 | CC0 1.0 |
| `presentations/sample.ppt` | PPT (двоичный OLE) | `demo/generate.py` — OLE/CFBF с потоком «PowerPoint Document» собран вручную (stdlib `struct`) | CC0 1.0 |
| `media/sample.{mp4,mkv,avi,webm,mov}` | короткие видео (~1 с) | синтетический тест-сигнал FFmpeg, сгенерированы однократно, вложены в `generate.py` как base64 | CC0 1.0 |
| `media/sample.{mp3,flac,wav,ogg,m4a,opus}` | короткое аудио (~1 с) | синтетический тон FFmpeg, сгенерированы однократно, вложены в `generate.py` как base64 | CC0 1.0 |

## Как добавлять новые образцы

Каждый тикет-просмотрщик кладёт свой образец в `demo/` (скриптуемое — веткой в
`demo/generate.py`, бинарное — готовым файлом). Любой **неигнорируемый бинарный**
образец обязан получить строку в таблице выше с указанием происхождения и
лицензии (только CC0 / public domain). Суммарный размер `demo/` — строго
меньше 5 МБ.
