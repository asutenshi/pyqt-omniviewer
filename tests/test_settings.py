from pathlib import Path

from PyQt6.QtCore import QByteArray

from omniviewer.settings import AppSettings


def test_app_settings_defaults(tmp_path, monkeypatch):
    # Mock config location
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    
    settings = AppSettings()
    settings._settings.clear()
    
    # Check default values
    assert settings.last_opened_dir == Path.home()
    assert settings.sort_field == "name"
    assert settings.sort_direction == 0  # 0 for Ascending
    assert settings.folders_on_top is True
    assert settings.tree_on_left is False
    assert settings.thumbnail_mode is False
    assert settings.window_geometry == QByteArray()
    
    # Check large file limits
    assert settings.max_text_read_bytes == 5 * 1024 * 1024
    assert settings.max_image_dimension == 8000

def test_app_settings_persistence(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    
    settings = AppSettings()
    settings._settings.clear()
    settings.last_opened_dir = Path("/tmp")
    settings.sort_field = "size"
    settings.sort_direction = 1
    settings.folders_on_top = False
    settings.tree_on_left = True
    settings.thumbnail_mode = True
    settings.window_geometry = QByteArray(b"geometry")
    
    settings.max_text_read_bytes = 1000
    settings.max_image_dimension = 2000
    
    # Force sync
    settings._settings.sync()
    
    # Recreate settings to read from file
    settings_new = AppSettings()
    assert settings_new.last_opened_dir == Path("/tmp")
    assert settings_new.sort_field == "size"
    assert settings_new.sort_direction == 1
    assert settings_new.folders_on_top is False
    assert settings_new.tree_on_left is True
    assert settings_new.thumbnail_mode is True
    assert settings_new.window_geometry == QByteArray(b"geometry")
    assert settings_new.max_text_read_bytes == 1000
    assert settings_new.max_image_dimension == 2000

