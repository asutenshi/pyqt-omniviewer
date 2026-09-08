import sys
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

from omniviewer.main import MainWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    app.setOrganizationName("asutenshi")
    app.setApplicationName("OmniViewerTest")
    yield app

@pytest.fixture(autouse=True)
def clean_settings():
    from omniviewer.settings import AppSettings
    AppSettings()._settings.clear()

def test_main_window_initialization(qapp):
    path = Path.home()
    window = MainWindow(path)
    
    # Check that splitter exists
    assert window.splitter is not None
    
    # Check that it has two widgets
    assert window.splitter.count() == 2
    
    # Check order: Viewer first, Tree second
    assert window.splitter.widget(0) == window.viewer_panel
    assert window.splitter.widget(1) == window.tree_panel
    
    # Status bar exists
    assert window.status_bar is not None
    assert str(path) in window.status_bar.currentMessage()

def test_swap_panels(qapp):
    path = Path.home()
    window = MainWindow(path)
    
    # Initial: Viewer(0), Tree(1)
    assert window.splitter.widget(0) == window.viewer_panel
    assert window.splitter.widget(1) == window.tree_panel
    
    # Swap
    window.swap_panels()
    
    # After swap: Tree(0), Viewer(1)
    assert window.splitter.widget(0) == window.tree_panel
    assert window.splitter.widget(1) == window.viewer_panel
    
    # Swap back
    window.swap_panels()
    
    # After second swap: Viewer(0), Tree(1)
    assert window.splitter.widget(0) == window.viewer_panel
    assert window.splitter.widget(1) == window.tree_panel


def test_cli_help(monkeypatch, capsys):
    from omniviewer.main import main
    monkeypatch.setattr("sys.argv", ["omniviewer", "-h"])
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 0
    out, _ = capsys.readouterr()
    assert "OmniViewer" in out

def test_about_action_opens_about_dialog(qapp, monkeypatch):
    from omniviewer.about_dialog import AboutDialog

    opened = {}

    def fake_exec(self):
        opened["dialog"] = self
        return 0

    monkeypatch.setattr(AboutDialog, "exec", fake_exec)

    window = MainWindow(Path.home())
    assert window.about_action is not None

    window.about_action.trigger()

    assert isinstance(opened.get("dialog"), AboutDialog)


def test_close_saves_settings(qapp):

    from omniviewer.settings import AppSettings
    
    path = Path("/tmp/test_dir")
    window = MainWindow(path)
    window.resize(100, 100)
    window.swap_panels()
    
    window.close()
    
    settings = AppSettings()
    assert settings.last_opened_dir == path
    assert settings.tree_on_left is True
    assert not settings.window_geometry.isEmpty()
