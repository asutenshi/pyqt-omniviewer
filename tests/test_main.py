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
    yield app

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
