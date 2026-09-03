import sys
import time

import pytest
from PyQt6.QtCore import QThreadPool
from PyQt6.QtWidgets import QApplication

from omniviewer.settings import AppSettings
from omniviewer.utils.io import WindowedReader
from omniviewer.viewers.base import BaseViewer


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app

class DummyViewer(BaseViewer):
    def __init__(self):
        super().__init__()
        self.result = None

    def load(self, path):
        pass
        
    def do_heavy_work(self):
        time.sleep(0.1)
        return "success"
        
    def apply_result(self, result):
        self.result = result

    def do_failing_work(self):
        raise ValueError("Something went wrong")

def test_base_viewer_async_success(qapp, qtbot):
    viewer = DummyViewer()
    viewer._start_async(viewer.do_heavy_work, viewer.apply_result)
    
    # Wait for the thread pool to finish
    QThreadPool.globalInstance().waitForDone(1000)
    # The application of the result is in the GUI thread, so wait for it
    QApplication.processEvents()
    
    assert viewer.result == "success"
    assert not viewer.is_error_widget

def test_base_viewer_async_cancel(qapp, qtbot):
    viewer = DummyViewer()
    viewer._start_async(viewer.do_heavy_work, viewer.apply_result)
    viewer.cancel()
    
    QThreadPool.globalInstance().waitForDone(1000)
    QApplication.processEvents()
    
    assert viewer.result is None

def test_base_viewer_async_error(qapp, qtbot):
    viewer = DummyViewer()
    viewer._start_async(viewer.do_failing_work, viewer.apply_result)
    
    QThreadPool.globalInstance().waitForDone(1000)
    QApplication.processEvents()
    
    assert viewer.is_error_widget
    assert "Something went wrong" in viewer.error_message

def test_base_viewer_safe_load_error(qapp, qtbot):
    class FailingSyncViewer(BaseViewer):
        def load(self, path):
            raise RuntimeError("Sync fail")
            
    viewer = FailingSyncViewer()
    viewer.safe_load("dummy.txt")
    
    assert viewer.is_error_widget
    assert "Sync fail" in viewer.error_message

def test_base_viewer_safe_load_async_error(qapp, qtbot):
    class FailingAsyncViewer(BaseViewer):
        def load_async(self):
            raise RuntimeError("Async start fail")
            
    viewer = FailingAsyncViewer()
    viewer.safe_load_async()
    
    assert viewer.is_error_widget
    assert "Async start fail" in viewer.error_message

def test_windowed_reader(tmp_path):
    f_path = tmp_path / "large.txt"
    f_path.write_bytes(b"A" * 1024 + b"B" * 1024)
    
    reader = WindowedReader(str(f_path), chunk_size=1024)
    chunk1 = reader.read_chunk(0)
    chunk2 = reader.read_chunk(1024)
    
    assert chunk1 == b"A" * 1024
    assert chunk2 == b"B" * 1024
    assert len(chunk1) <= 1024

def test_settings_thresholds():
    settings = AppSettings()
    settings.max_text_read_bytes = 1000
    settings.max_image_dimension = 2000
    
    assert settings.max_text_read_bytes == 1000
    assert settings.max_image_dimension == 2000
