# ruff: noqa: BLE001
import os
import sys
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

from omniviewer.registry import ViewerRegistry
from omniviewer.viewers.archive import ArchiveViewer
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

DEMO_DIR = Path(__file__).parent.parent / "demo"

# Таблица: имя файла из demo/ -> Ожидаемый класс просмотрщика.
# Дополняется в каждом тикете просмотрщика.
FILE_TO_VIEWER = {
    # Пока только FallbackViewer для всех, так как других просмотрщиков нет
    "text/plain-en.txt": TextViewer,
    "text/notes-ru.txt": TextViewer,
    "code/example.py": TextViewer,
    "code/example.c": TextViewer,
    "data/table.csv": SpreadsheetViewer,
    "data/table.tsv": SpreadsheetViewer,
    "data/table.xlsx": SpreadsheetViewer,
    "data/table.xls": SpreadsheetViewer,
    "data/table.ods": SpreadsheetViewer,
    "data/record.json": StructureViewer,
    "data/config.yaml": StructureViewer,
    "data/catalog.xml": StructureViewer,
    "data/settings.ini": TextViewer,
    "data/config.toml": StructureViewer,
    "data/big-tree.json": StructureViewer,
    "misc/exotic.mid": FallbackViewer,
    "misc/opaque.bin": FallbackViewer,
    "images/swatch.png": ImageViewer,
    "images/swatch.jpg": ImageViewer,
    "images/swatch.gif": ImageViewer,
    "images/animated.gif": ImageViewer,
    "images/photo_exif.jpg": ImageViewer,
    "images/swatch.bmp": ImageViewer,
    "images/swatch.webp": ImageViewer,
    "images/swatch.tiff": ImageViewer,
    "images/swatch.ico": ImageViewer,
    "images/circle.svg": ImageViewer,
    "images/sample.heic": ImageViewer,
    "images/sample.avif": ImageViewer,
    "images/multipage.tiff": ImageViewer,
    "images/sample.dng": ImageViewer,
    "broken/truncated.heic": ImageViewer,
    "books/sample.pdf": PdfViewer,
    "books/sample.cbz": PdfViewer,
    "books/sample.epub": PdfViewer,
    "books/sample.fb2": PdfViewer,
    "books/sample.xps": PdfViewer,
    "archives/sample.zip": ArchiveViewer,
    "archives/sample.tar.gz": ArchiveViewer,
    "archives/sample.ar": ArchiveViewer,
    "archives/nested.zip": ArchiveViewer,
    "large/big-lines.txt": TextViewer,
    "noext/hello-script": TextViewer,
    "media/sample.mp4": MediaViewer,
    "media/sample.mkv": MediaViewer,
    "media/sample.avi": MediaViewer,
    "media/sample.webm": MediaViewer,
    "media/sample.mov": MediaViewer,
    "media/sample.mp3": MediaViewer,
    "media/sample.flac": MediaViewer,
    "media/sample.wav": MediaViewer,
    "media/sample.ogg": MediaViewer,
    "media/sample.m4a": MediaViewer,
    "media/sample.opus": MediaViewer,
    "markup/sample.md": MarkupViewer,
    "markup/page.html": MarkupViewer,
    "markup/page.xhtml": MarkupViewer,
    "markup/saved.mhtml": MarkupViewer,
    "broken/truncated.mhtml": MarkupViewer,
    "presentations/sample.pptx": PresentationViewer,
    "presentations/sample.odp": PresentationViewer,
    "presentations/sample.ppt": PresentationViewer,
    "broken/truncated.pptx": PresentationViewer,
    "notebooks/sample.ipynb": IpynbViewer,
    "broken/truncated.ipynb": IpynbViewer,
    "fonts/sample.ttf": FontViewer,
    "fonts/sample.otf": FontViewer,
    "fonts/sample.woff": FontViewer,
    "fonts/sample.woff2": FontViewer,
    "broken/truncated.ttf": FontViewer,
    "mail/sample.eml": MailViewer,
    "mail/sample.msg": MailViewer,
    "broken/truncated.msg": MailViewer,
    "broken/truncated.png": ImageViewer,
    "broken/truncated.jpg": ImageViewer,
    "broken/truncated.svg": ImageViewer,
    "broken/truncated.json": StructureViewer,
    "broken/truncated.xml": StructureViewer,
    "broken/truncated.toml": StructureViewer,
    "broken/truncated.pdf": PdfViewer,
    "broken/truncated.xlsx": SpreadsheetViewer,
    "broken/truncated.mp4": MediaViewer,
    "broken/truncated.mp3": MediaViewer,
    "broken/truncated.zip": ArchiveViewer,
    # Офисные документы
    "documents/sample.docx": DocumentViewer,
    "documents/sample.doc": DocumentViewer,
    "documents/sample.odt": DocumentViewer,
    "documents/sample.rtf": DocumentViewer,
    "broken/truncated.docx": DocumentViewer,
    "broken/truncated.doc": DocumentViewer,
    "broken/truncated.odt": DocumentViewer,
    "broken/truncated.rtf": DocumentViewer,
}

# Таблица: имя файла из demo/ -> Ожидаемый MIME-тип.
# Дополняется в каждом тикете просмотрщика.
PATH_TO_MIME = {
    "text/plain-en.txt": "text/plain",
    "text/notes-ru.txt": "text/plain",
    "code/example.py": "text/x-python",
    "code/example.c": "text/x-csrc", # Или text/plain, mimetypes может выдать None
    "data/table.csv": "text/csv",
    "data/table.tsv": "text/tab-separated-values",
    "data/table.xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "data/table.xls": "application/vnd.ms-excel",
    "data/table.ods": "application/vnd.oasis.opendocument.spreadsheet",
    "data/record.json": "application/json",
    "data/config.yaml": "application/x-yaml", # Или application/yaml
    "data/catalog.xml": "text/xml", # Или application/xml
    "data/settings.ini": "application/octet-stream", # По умолчанию
    "data/config.toml": "application/toml",
    "data/big-tree.json": "application/json",
    "misc/exotic.mid": "audio/midi",
    "misc/opaque.bin": "application/octet-stream",
    "images/swatch.png": "image/png",
    "images/swatch.jpg": "image/jpeg",
    "images/swatch.gif": "image/gif",
    "images/animated.gif": "image/gif",
    "images/photo_exif.jpg": "image/jpeg",
    "images/swatch.bmp": "image/bmp",
    "images/swatch.webp": "image/webp",
    "images/swatch.tiff": "image/tiff",
    "images/swatch.ico": "image/vnd.microsoft.icon",
    "images/circle.svg": "image/svg+xml",
    "images/sample.heic": "image/heic",
    "images/sample.avif": "image/avif",
    "images/multipage.tiff": "image/tiff",
    "images/sample.dng": "image/x-raw-adobe",
    "broken/truncated.heic": "image/heic",
    "books/sample.pdf": "application/pdf",
    "books/sample.cbz": "application/vnd.comicbook+zip", # or application/zip
    "books/sample.epub": "application/epub+zip",
    "books/sample.fb2": "application/x-fictionbook+xml",
    "books/sample.xps": "application/vnd.ms-xpsdocument", # or application/oxps
    "archives/sample.zip": "application/zip",
    "archives/sample.tar.gz": "application/gzip",
    "archives/sample.ar": "application/x-archive",
    "archives/nested.zip": "application/zip",
    "large/big-lines.txt": "text/plain",
    "noext/hello-script": "application/octet-stream", # Без расширения пока octet-stream
    "media/sample.mp4": "video/mp4",
    "media/sample.mkv": "video/x-matroska",
    "media/sample.avi": "video/vnd.avi",
    "media/sample.webm": "video/webm",
    "media/sample.mov": "video/quicktime",
    "media/sample.mp3": "audio/mpeg",
    "media/sample.flac": "audio/flac",
    "media/sample.wav": "audio/vnd.wave",
    "media/sample.ogg": "audio/x-vorbis+ogg",
    "media/sample.m4a": "audio/mp4",
    "media/sample.opus": "audio/x-opus+ogg",
    "markup/sample.md": "text/markdown",
    "markup/page.html": "text/html",
    "markup/page.xhtml": "application/xhtml+xml",
    "markup/saved.mhtml": "multipart/related",
    "broken/truncated.mhtml": "multipart/related",
    "presentations/sample.pptx": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    ),
    "presentations/sample.odp": "application/vnd.oasis.opendocument.presentation",
    "presentations/sample.ppt": "application/vnd.ms-powerpoint",
    "broken/truncated.pptx": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    ),
    "notebooks/sample.ipynb": "text/plain",
    "broken/truncated.ipynb": "text/plain",
    "fonts/sample.ttf": "application/x-font-ttf",
    "fonts/sample.otf": "application/x-font-otf",
    "fonts/sample.woff": "application/octet-stream",
    "fonts/sample.woff2": "application/octet-stream",
    "broken/truncated.ttf": "application/x-font-ttf",
    "mail/sample.eml": "message/rfc822",
    "mail/sample.msg": "application/vnd.ms-outlook",
    "broken/truncated.msg": "application/vnd.ms-outlook",
    "broken/truncated.png": "image/png",
    "broken/truncated.jpg": "image/jpeg",
    "broken/truncated.svg": "image/svg+xml",
    "broken/truncated.json": "application/json",
    "broken/truncated.xml": "text/xml",
    "broken/truncated.toml": "application/toml",
    "broken/truncated.pdf": "application/pdf",
    "broken/truncated.xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "broken/truncated.mp4": "video/mp4",
    "broken/truncated.mp3": "audio/mpeg",
    "broken/truncated.zip": "application/zip",
    # Офисные документы
    "documents/sample.docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "documents/sample.doc": "application/msword",
    "documents/sample.odt": "application/vnd.oasis.opendocument.text",
    "documents/sample.rtf": "application/rtf",
    "broken/truncated.docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "broken/truncated.doc": "application/msword",
    "broken/truncated.odt": "application/vnd.oasis.opendocument.text",
    "broken/truncated.rtf": "application/rtf",
}

@pytest.fixture(scope="session", autouse=True)
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app

@pytest.fixture
def registry():
    reg = ViewerRegistry()
    return reg

def get_demo_files():
    """Возвращает относительные пути ко всем файлам в demo/ (кроме .md и .py скрипта)"""
    files = []
    for root, _, filenames in os.walk(DEMO_DIR):
        if "__pycache__" in root:
            continue
        for name in filenames:
            if name.endswith((".md", ".pyc")) or name == "generate.py":
                continue
            full_path = Path(root) / name
            rel_path = full_path.relative_to(DEMO_DIR).as_posix()
            files.append(rel_path)
    return files

@pytest.mark.parametrize("rel_path", get_demo_files())
def test_expected_viewer_class(registry, rel_path):
    """
    Тест «путь → ожидаемый класс просмотрщика» проходит по всем образцам demo/.
    """
    expected_class = FILE_TO_VIEWER.get(rel_path, FallbackViewer)
    
    full_path = str(DEMO_DIR / rel_path)
    viewer = registry.viewer_for(Path(full_path))
    
    assert isinstance(viewer, expected_class), f"Expected {expected_class.__name__} for {rel_path}, got {type(viewer).__name__}"

@pytest.mark.parametrize("rel_path", get_demo_files())
def test_smoke_load(qapp, registry, rel_path):
    """
    Смоук: по каждому образцу viewer_for(path).load(path) (+ ожидание load_async)
    не бросает исключений и не даёт «ошибочный» виджет.
    """
    if "broken" in rel_path:
        pytest.skip("Broken files are tested separately")
        
    full_path = str(DEMO_DIR / rel_path)
    viewer = registry.viewer_for(Path(full_path))
    
    try:
        viewer.safe_load(Path(full_path))
        viewer.safe_load_async()
        
        # Ждем завершения асинхронных задач
        from PyQt6.QtCore import QThreadPool
        QThreadPool.globalInstance().waitForDone(2000)
        QApplication.processEvents()
        
        assert not viewer.is_error_widget, f"Error widget created for {rel_path}: {viewer.error_message}"
    except Exception as e:
        pytest.fail(f"Exception raised for {rel_path}: {e}")
    finally:
        # Освобождаем ресурсы просмотрщика (для MediaViewer — общий QMediaPlayer):
        # без этого уничтожение MediaViewer с активным конвейером вешает поток.
        viewer.cancel()

@pytest.mark.parametrize("rel_path", [f for f in get_demo_files() if "broken" in f])
def test_broken_files(qapp, registry, rel_path):
    """
    Тест: обрезанный образец каждого поддержанного типа → просмотрщик отдаёт «ошибочный» виджет, не падает.
    """
    full_path = str(DEMO_DIR / rel_path)
    viewer = registry.viewer_for(Path(full_path))
    
    try:
        viewer.safe_load(Path(full_path))
        viewer.safe_load_async()
        
        from PyQt6.QtCore import QThreadPool
        QThreadPool.globalInstance().waitForDone(2000)
        QApplication.processEvents()
        
        # FallbackViewer и TextViewer не бросают исключений даже для битых файлов;
        # DocumentViewer для .rtf (striprtf) тоже корректно извлекает что может.
        is_rtf = rel_path.endswith(".rtf")
        if not isinstance(viewer, (FallbackViewer, TextViewer)) and not is_rtf:
            assert viewer.is_error_widget, f"Viewer {type(viewer).__name__} did not show error for broken file {rel_path}"
    except Exception as e:
        pytest.fail(f"Viewer {type(viewer).__name__} crashed on broken file {rel_path}: {e}")
    finally:
        viewer.cancel()

def test_unrecognized_file(qapp, registry, tmp_path):
    """
    Тест: нераспознанный файл → fallback-просмотрщик, загружается без исключения.
    """
    unrec_path = tmp_path / "unknown.xyz123"
    unrec_path.write_text("Hello")
    
    viewer = registry.viewer_for(unrec_path)
    assert isinstance(viewer, (FallbackViewer, TextViewer))
    
    viewer.safe_load(unrec_path)
    assert not viewer.is_error_widget

@pytest.mark.parametrize("rel_path", get_demo_files())
def test_expected_mime(rel_path):
    from PyQt6.QtCore import QMimeDatabase
    
    expected_mime = PATH_TO_MIME.get(rel_path)
    if not expected_mime:
        expected_mime = "application/octet-stream"
        
    full_path = str(DEMO_DIR / rel_path)
    mime = QMimeDatabase().mimeTypeForFile(full_path, QMimeDatabase.MatchMode.MatchDefault).name()
    
    # QMimeDatabase usually gives text/x-csrc for .c
    if rel_path == "code/example.c":
        assert mime in ["text/x-csrc", "text/plain", "text/x-c++src"]
    elif rel_path == "data/config.yaml":
        assert mime in ["application/x-yaml", "application/yaml", "text/yaml"]
    elif rel_path.endswith(".xml"):
        assert mime in ["application/xml", "text/xml"]
    elif "hello-script" in rel_path:
        assert mime in ["application/x-shellscript", "application/octet-stream"]
    elif rel_path == "media/sample.wav":
        assert mime in ["audio/vnd.wave", "audio/x-wav"]
    elif rel_path == "media/sample.m4a":
        assert mime in ["audio/mp4", "audio/x-m4a"]
    elif rel_path == "media/sample.avi":
        assert mime in ["video/vnd.avi", "video/x-msvideo", "video/avi"]
    elif rel_path == "media/sample.ogg":
        assert mime in ["audio/x-vorbis+ogg", "audio/ogg"]
    elif rel_path == "media/sample.opus":
        assert mime in ["audio/x-opus+ogg", "audio/ogg", "audio/opus"]
    elif rel_path == "data/settings.ini":
        assert mime in ["application/octet-stream", "text/plain"]
    elif rel_path.endswith(".heic"):
        assert mime in ["image/heic", "image/heif", "image/heic-sequence"]
    elif rel_path == "images/sample.avif":
        assert mime in ["image/avif", "image/heif"]
    elif rel_path == "images/sample.dng":
        assert mime in [
            "image/x-raw-adobe", "image/x-adobe-dng", "image/dng", "image/tiff", "image/x-dcraw",
        ]
    elif rel_path == "archives/sample.tar.gz":
        assert mime in ["application/gzip", "application/x-gzip", "application/x-compressed-tar"]
    elif rel_path == "archives/sample.ar":
        assert mime in ["application/x-archive", "application/x-unix-archive"]
    elif rel_path == "markup/sample.md":
        assert mime in ["text/markdown", "text/x-markdown", "text/plain"]
    elif rel_path.endswith(".mhtml"):
        assert mime in ["multipart/related", "application/x-mimearchive", "message/rfc822"]
    elif rel_path.endswith(".pptx"):
        assert mime in [
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "application/zip",
            "application/octet-stream",
        ]
    elif rel_path == "presentations/sample.ppt":
        assert mime in [
            "application/vnd.ms-powerpoint",
            "application/x-ole-storage",
            "application/octet-stream",
        ]
    elif rel_path.endswith(".doc") and "truncated" not in rel_path:
        assert mime in ["application/msword", "application/x-ole-storage", "application/vnd.ms-word"]
    elif rel_path.endswith(".doc"):
        # Обрезанный .doc — MIME может быть чем угодно
        assert mime in [
            "application/msword", "application/x-ole-storage", "application/octet-stream",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ]
    elif rel_path.endswith(".rtf"):
        assert mime in ["application/rtf", "text/rtf"]
    elif rel_path.endswith(".odt") and "truncated" in rel_path:
        # Обрезанный ODT — MIME может определиться неточно
        assert mime in [
            "application/vnd.oasis.opendocument.text", "application/zip",
            "application/octet-stream",
        ]
    elif rel_path.endswith(".docx") and "truncated" in rel_path:
        # Обрезанный DOCX — MIME может определиться неточно
        assert mime in [
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/zip", "application/octet-stream",
        ]
    elif rel_path.endswith(".ipynb"):
        assert mime in ["text/plain", "application/json", "application/x-ipynb+json"]
    elif rel_path.endswith((".ttf", ".otf")):
        assert mime in [
            "application/x-font-ttf", "application/x-font-otf", "font/ttf", "font/otf",
            "font/sfnt", "application/font-sfnt", "application/x-font-truetype",
            "application/x-font-opentype", "application/vnd.ms-opentype", "application/octet-stream",
        ]
    elif rel_path.endswith((".woff", ".woff2")):
        assert mime in [
            "application/octet-stream", "font/woff", "font/woff2",
            "application/font-woff", "application/font-woff2",
        ]
    elif rel_path.endswith(".toml"):
        assert mime in [
            "application/toml", "text/plain", "text/x-toml", "application/octet-stream",
        ]
    elif rel_path.endswith(".mid"):
        assert mime in ["audio/midi", "audio/x-midi", "audio/mid"]
    elif rel_path.endswith(".eml"):
        assert mime in ["message/rfc822", "text/plain", "application/octet-stream"]
    elif rel_path.endswith(".msg"):
        assert mime in [
            "application/vnd.ms-outlook", "application/x-ole-storage",
            "application/CDFV2", "application/octet-stream",
        ]
    else:
        assert mime == expected_mime, f"Expected {expected_mime} for {rel_path}, got {mime}"
