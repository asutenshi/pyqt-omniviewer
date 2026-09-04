from pathlib import Path

from PyQt6.QtCore import Qt

from omniviewer.tree import FileTreePanel


def test_tree_initialization(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))
    from omniviewer.settings import AppSettings
    AppSettings()._settings.clear()
    panel = FileTreePanel(tmp_path)
    
    # Check widgets
    assert panel.address_bar is not None
    assert panel.address_bar.text() == str(tmp_path)
    assert panel.filter_input is not None
    assert panel.tree_view is not None
    
    # Models
    assert panel.source_model is not None
    assert panel.proxy_model is not None
    
    # Buttons
    assert panel.btn_back is not None
    assert panel.btn_forward is not None
    assert panel.btn_up is not None
    assert panel.btn_home is not None

def test_navigation_history(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))
    from omniviewer.settings import AppSettings
    AppSettings()._settings.clear()
    d1 = tmp_path / "d1"
    d2 = tmp_path / "d2"
    d1.mkdir()
    d2.mkdir()
    
    panel = FileTreePanel(tmp_path)
    assert panel.current_path == tmp_path
    
    panel.set_root_path(d1)
    assert panel.current_path == d1
    
    panel.set_root_path(d2)
    assert panel.current_path == d2
    
    panel.go_back()
    assert panel.current_path == d1
    
    panel.go_forward()
    assert panel.current_path == d2
    
    panel.go_up()
    assert panel.current_path == tmp_path
    
    panel.go_home()
    assert panel.current_path == Path.home()

def test_sorting_and_menu_sync(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))
    from omniviewer.settings import AppSettings
    AppSettings()._settings.clear()
    panel = FileTreePanel(tmp_path)
    
    # Check default menu state
    assert panel.action_sort_name.isChecked()
    assert panel.action_sort_asc.isChecked()
    assert panel.action_folders_first.isChecked()
    
    # Sort via header
    panel.tree_view.header().sortIndicatorChanged.emit(1, Qt.SortOrder.DescendingOrder)
    
    # Ensure menu is updated
    assert panel.action_sort_size.isChecked()
    assert panel.action_sort_desc.isChecked()
    
    # Sort via menu
    panel.action_sort_date.setChecked(True)
    panel.action_sort_asc.setChecked(True)
    panel._apply_sorting()
    
    # Ensure header is updated
    assert panel.tree_view.header().sortIndicatorSection() == 3
    assert panel.tree_view.header().sortIndicatorOrder() == Qt.SortOrder.AscendingOrder

def test_columns(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))
    from omniviewer.settings import AppSettings
    AppSettings()._settings.clear()
    panel = FileTreePanel(tmp_path)
    model = panel.proxy_model
    
    assert model.columnCount() == 4
    assert model.headerData(0, Qt.Orientation.Horizontal) == "Name"
    assert model.headerData(1, Qt.Orientation.Horizontal) == "Size"
    assert model.headerData(2, Qt.Orientation.Horizontal) == "Type"
    # Note: 3 could be "Date Modified" depending on locale/system. Let's just check count for now or avoid strict string matching on Qt defaults.

def test_filtering(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))
    from omniviewer.settings import AppSettings
    AppSettings()._settings.clear()
    (tmp_path / "file_abc.txt").touch()
    (tmp_path / "file_def.txt").touch()
    (tmp_path / "dir_abc").mkdir()
    
    panel = FileTreePanel(tmp_path)
    
    # Needs to wait for QFileSystemModel to populate
    import time

    from PyQt6.QtCore import QCoreApplication
    
    for _ in range(50):
        QCoreApplication.processEvents()
        time.sleep(0.01)
        if panel.source_model.rowCount(panel.source_model.index(str(tmp_path))) >= 3:
            break
            
    panel.filter_input.setText("abc")
    
    # Wait for proxy model to update
    QCoreApplication.processEvents()
    
    root_idx = panel.tree_view.rootIndex()
    rows = panel.proxy_model.rowCount(root_idx)
    
    names = []
    for i in range(rows):
        idx = panel.proxy_model.index(i, 0, root_idx)
        names.append(panel.proxy_model.data(idx))
        
    assert "file_abc.txt" in names
    assert "file_def.txt" not in names
    assert "dir_abc" in names  # Directories are always accepted


def test_current_changed_emits_file_selected(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))
    from omniviewer.settings import AppSettings
    AppSettings()._settings.clear()
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "sub").mkdir()

    panel = FileTreePanel(tmp_path)

    import time

    from PyQt6.QtCore import QCoreApplication, QItemSelectionModel

    for _ in range(50):
        QCoreApplication.processEvents()
        time.sleep(0.01)
        if panel.source_model.rowCount(panel.source_model.index(str(tmp_path))) >= 2:
            break

    received: list[Path] = []
    panel.file_selected.connect(received.append)

    root_idx = panel.tree_view.rootIndex()
    # Находим строку с файлом a.txt и делаем её текущей — как при навигации стрелками.
    file_idx = None
    for i in range(panel.proxy_model.rowCount(root_idx)):
        idx = panel.proxy_model.index(i, 0, root_idx)
        if panel.proxy_model.data(idx) == "a.txt":
            file_idx = idx
            break
    assert file_idx is not None

    panel.tree_view.selectionModel().setCurrentIndex(
        file_idx, QItemSelectionModel.SelectionFlag.SelectCurrent
    )

    assert received == [tmp_path / "a.txt"]

    # Переход на папку не должен эмитить file_selected.
    dir_idx = None
    for i in range(panel.proxy_model.rowCount(root_idx)):
        idx = panel.proxy_model.index(i, 0, root_idx)
        if panel.proxy_model.data(idx) == "sub":
            dir_idx = idx
            break
    assert dir_idx is not None
    panel.tree_view.selectionModel().setCurrentIndex(
        dir_idx, QItemSelectionModel.SelectionFlag.SelectCurrent
    )
    assert received == [tmp_path / "a.txt"]

