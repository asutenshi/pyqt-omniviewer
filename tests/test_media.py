"""Регрессия для просмотрщика медиа (:mod:`omniviewer.viewers.media`).

Главный шов — ``ViewerRegistry`` и жизненный цикл просмотрщика как в
``MainWindow.on_file_selected`` (load → cancel → deleteLater). Проверяется, что
переключение с активного видео и уничтожение ``MediaViewer`` не вешают GUI-поток:
деструктор ``~QVideoWidget`` бэкенда Qt FFmpeg делает join своих рабочих потоков
прямо в GUI-потоке, и раньше приложение намертво зависало (в логе — «Killed»).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PyQt6.QtCore import QThreadPool
from PyQt6.QtWidgets import QApplication

from omniviewer.registry import ViewerRegistry
from omniviewer.viewers.media import MediaViewer, _SharedPlayer

_MEDIA = Path(__file__).parent.parent / "demo" / "media"


@pytest.fixture(scope="session", autouse=True)
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture
def registry() -> ViewerRegistry:
    return ViewerRegistry()


def _pump(ms: int = 300) -> None:
    """Прокрутить цикл событий: сработает отложенный ``_init_player`` и сигналы плеера."""
    QThreadPool.globalInstance().waitForDone(ms)
    QApplication.processEvents()


def test_registry_selects_media_viewer_for_video(registry: ViewerRegistry) -> None:
    assert isinstance(registry.viewer_for(_MEDIA / "sample.mp4"), MediaViewer)


def test_switching_away_from_active_video_does_not_hang(registry: ViewerRegistry) -> None:
    """Открыть видео, дождаться поднятия плеера, переключиться и уничтожить.

    До фикса тут намертво зависал GUI-поток. Успех теста = он просто завершается.
    """
    v1 = registry.viewer_for(_MEDIA / "sample.mp4")
    v1.safe_load(_MEDIA / "sample.mp4")
    _pump()
    assert v1.player is not None  # отложенный _init_player действительно отработал

    # как в MainWindow.on_file_selected
    v1.cancel()
    v1.deleteLater()
    _pump()

    v2 = registry.viewer_for(_MEDIA / "sample.avi")
    v2.safe_load(_MEDIA / "sample.avi")
    _pump()
    v2.cancel()
    _pump()

    assert not v2.is_error_widget


def test_cancel_parks_shared_video_widget_without_destroying_it(registry: ViewerRegistry) -> None:
    """``cancel()`` должен выцепить общий видеовиджет в «домик», а не дать снести
    его вместе с деревом просмотрщика."""
    v = registry.viewer_for(_MEDIA / "sample.mkv")
    v.safe_load(_MEDIA / "sample.mkv")
    _pump()

    _, _, shared_video = _SharedPlayer.acquire()
    assert shared_video.parent() is v.video_widget  # во время показа — в дереве просмотрщика

    v.cancel()
    assert shared_video.parent() is _SharedPlayer._keeper  # после cancel — припаркован


def test_destroy_without_cancel_is_still_safe(registry: ViewerRegistry) -> None:
    """Даже если ``cancel()`` не вызвали (как в смоук-тестах), уничтожение
    ``MediaViewer`` не должно вешать поток — страхует ``__del__``."""
    v = registry.viewer_for(_MEDIA / "sample.webm")
    v.safe_load(_MEDIA / "sample.webm")
    _pump()

    v.deleteLater()
    del v
    _pump()

    # общий плеер остался жив и пригоден для следующего просмотрщика
    player, _, _ = _SharedPlayer.acquire()
    assert player is not None
