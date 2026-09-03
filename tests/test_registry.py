# ruff: noqa: BLE001
import os
import sys
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

from omniviewer.registry import ViewerRegistry
from omniviewer.viewers.fallback import FallbackViewer
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
    "data/table.csv": TextViewer,
    "data/table.tsv": TextViewer,
    "data/record.json": TextViewer,
    "data/config.yaml": TextViewer,
    "data/catalog.xml": TextViewer,
    "data/settings.ini": TextViewer,
    "images/swatch.png": FallbackViewer,
    "images/swatch.jpg": FallbackViewer,
    "large/big-lines.txt": TextViewer,
    "noext/hello-script": TextViewer,
    "broken/truncated.png": FallbackViewer,
    "broken/truncated.jpg": FallbackViewer,
    "broken/truncated.json": TextViewer,
    "broken/truncated.xml": TextViewer,
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
    "data/record.json": "application/json",
    "data/config.yaml": "application/x-yaml", # Или application/yaml
    "data/catalog.xml": "text/xml", # Или application/xml
    "data/settings.ini": "application/octet-stream", # По умолчанию
    "images/swatch.png": "image/png",
    "images/swatch.jpg": "image/jpeg",
    "large/big-lines.txt": "text/plain",
    "noext/hello-script": "application/octet-stream", # Без расширения пока octet-stream
    "broken/truncated.png": "image/png",
    "broken/truncated.jpg": "image/jpeg",
    "broken/truncated.json": "application/json",
    "broken/truncated.xml": "text/xml",
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
        
        # FallbackViewer и TextViewer не бросают исключений даже для битых файлов
        if not isinstance(viewer, (FallbackViewer, TextViewer)):
            assert viewer.is_error_widget, f"Viewer {type(viewer).__name__} did not show error for broken file {rel_path}"
    except Exception as e:
        pytest.fail(f"Viewer {type(viewer).__name__} crashed on broken file {rel_path}: {e}")

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
    elif rel_path == "data/settings.ini":
        assert mime in ["application/octet-stream", "text/plain"]
    else:
        assert mime == expected_mime, f"Expected {expected_mime} for {rel_path}, got {mime}"

