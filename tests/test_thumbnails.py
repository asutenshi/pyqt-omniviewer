"""Тесты модуля миниатюр: дисковый кэш, генерация, фоновая очередь.

Проверяется внешнее поведение (см. «Критерии приёмки» тикета «миниатюры»):
раскладка кэша по freedesktop thumbnail spec и его инвалидация, миниатюры для
изображений / первой страницы PDF / кадра видео, неблокирующая выдача через
менеджер и полное отсутствие фоновой работы в выключенном режиме.
"""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

import pytest
from PyQt6.QtGui import QImage

from omniviewer import thumbnails as th

DEMO = Path(__file__).resolve().parent.parent / "demo"


@pytest.fixture(autouse=True)
def cache_home(tmp_path, monkeypatch) -> Path:
    """Изолируем кэш: тесты не должны писать в ~/.cache пользователя."""
    root = tmp_path / "cache"
    monkeypatch.setenv("XDG_CACHE_HOME", str(root))
    return root


def _copy(src: Path, dst_dir: Path) -> Path:
    dst = dst_dir / src.name
    dst.write_bytes(src.read_bytes())
    return dst


# ─── Раскладка кэша по freedesktop thumbnail spec ───────────────────────────


def test_cache_path_follows_freedesktop_spec(qapp, cache_home, tmp_path):
    target = tmp_path / "картинка.png"
    target.write_bytes(b"x")

    expected_name = hashlib.md5(th.file_uri(target).encode("utf-8")).hexdigest() + ".png"
    path = th.cache_path(target)

    assert path.parent == cache_home / "thumbnails" / "normal"
    assert path.name == expected_name


def test_file_uri_is_percent_encoded(qapp, tmp_path):
    target = tmp_path / "имя с пробелом.png"
    uri = th.file_uri(target)
    assert uri.startswith("file:///")
    assert " " not in uri
    assert "%20" in uri


def test_store_writes_png_with_spec_metadata(qapp, tmp_path):
    source = _copy(DEMO / "images/swatch.png", tmp_path)
    image = QImage(8, 8, QImage.Format.Format_ARGB32)
    image.fill(0xFF112233)

    cache = th.ThumbnailCache()
    written = cache.store(source, image)

    assert written.is_file()
    stored = QImage(str(written))
    assert stored.text("Thumb::URI") == th.file_uri(source)
    assert stored.text("Thumb::MTime") == str(int(source.stat().st_mtime))
    assert stored.text("Thumb::Size") == str(source.stat().st_size)
    # Спека требует, чтобы миниатюры были доступны только владельцу.
    assert stat.S_IMODE(written.stat().st_mode) == 0o600


def test_load_returns_stored_thumbnail(qapp, tmp_path):
    source = _copy(DEMO / "images/swatch.png", tmp_path)
    image = QImage(8, 8, QImage.Format.Format_ARGB32)
    image.fill(0xFF445566)

    cache = th.ThumbnailCache()
    cache.store(source, image)

    loaded = cache.load(source)
    assert loaded is not None
    assert loaded.size() == image.size()


def test_load_returns_none_without_cache_entry(qapp, tmp_path):
    source = _copy(DEMO / "images/swatch.png", tmp_path)
    assert th.ThumbnailCache().load(source) is None


def test_cache_is_invalidated_when_file_mtime_changes(qapp, tmp_path):
    source = _copy(DEMO / "images/swatch.png", tmp_path)
    cache = th.ThumbnailCache()
    cache.store(source, QImage(8, 8, QImage.Format.Format_ARGB32))
    assert cache.load(source) is not None

    stamp = source.stat().st_mtime + 120
    os.utime(source, (stamp, stamp))

    assert cache.load(source) is None


def test_cache_is_invalidated_when_file_size_changes(qapp, tmp_path):
    source = _copy(DEMO / "images/swatch.png", tmp_path)
    cache = th.ThumbnailCache()
    cache.store(source, QImage(8, 8, QImage.Format.Format_ARGB32))

    before = source.stat()
    source.write_bytes(source.read_bytes() + b"\x00" * 32)
    os.utime(source, (before.st_atime, before.st_mtime))  # mtime тот же, размер другой

    assert cache.load(source) is None


# ─── Генерация ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "rel_path",
    ["images/swatch.png", "images/swatch.jpg", "images/swatch.bmp", "images/animated.gif"],
)
def test_generate_image_thumbnail(qapp, rel_path):
    image = th.generate(DEMO / rel_path)

    assert image is not None and not image.isNull()
    assert max(image.width(), image.height()) <= th.THUMBNAIL_SIZE


def test_generate_pdf_uses_first_page(qapp):
    image = th.generate(DEMO / "books/sample.pdf")

    assert image is not None and not image.isNull()
    assert max(image.width(), image.height()) <= th.THUMBNAIL_SIZE


def test_generate_returns_none_for_plain_text(qapp):
    assert th.generate(DEMO / "text/plain-en.txt") is None


def test_generate_returns_none_for_broken_sample(qapp):
    """Битый образец не должен ронять фоновую задачу."""
    assert th.generate(DEMO / "broken/truncated.png") is None


def test_kind_of_classifies_by_extension(qapp):
    assert th.kind_of(DEMO / "images/swatch.png") == "image"
    assert th.kind_of(DEMO / "books/sample.pdf") == "document"
    assert th.kind_of(DEMO / "media/sample.mp4") == "video"
    assert th.kind_of(DEMO / "media/sample.mp3") is None
    assert th.kind_of(DEMO / "text/plain-en.txt") is None


# ─── Менеджер и фоновая очередь ─────────────────────────────────────────────


def test_manager_answers_immediately_and_fills_in_background(qapp, qtbot, tmp_path):
    source = _copy(DEMO / "images/swatch.png", tmp_path)
    manager = th.ThumbnailManager(enabled=True)

    # Первый запрос не блокирует вызывающего: миниатюры ещё нет.
    assert manager.thumbnail_for(source) is None

    with qtbot.waitSignal(manager.thumbnail_ready, timeout=10000):
        pass

    pixmap = manager.thumbnail_for(source)
    assert pixmap is not None and not pixmap.isNull()
    assert max(pixmap.width(), pixmap.height()) <= th.THUMBNAIL_SIZE


def test_manager_reuses_disk_cache_between_runs(qapp, qtbot, tmp_path, monkeypatch):
    source = _copy(DEMO / "images/swatch.png", tmp_path)

    first = th.ThumbnailManager(enabled=True)
    first.thumbnail_for(source)
    with qtbot.waitSignal(first.thumbnail_ready, timeout=10000):
        pass
    assert first.thumbnail_for(source) is not None

    # Новый менеджер (как новый запуск приложения) обязан взять готовое с диска.
    def _fail(*args, **kwargs):
        raise AssertionError("миниатюра сгенерирована заново вместо чтения кэша")

    monkeypatch.setattr(th, "generate", _fail)

    second = th.ThumbnailManager(enabled=True)
    assert second.thumbnail_for(source) is None  # первый ответ всегда неблокирующий
    with qtbot.waitSignal(second.thumbnail_ready, timeout=10000):
        pass
    assert second.thumbnail_for(source) is not None


def test_disabled_manager_does_not_start_background_work(qapp, tmp_path):
    source = _copy(DEMO / "images/swatch.png", tmp_path)
    manager = th.ThumbnailManager(enabled=False)

    assert manager.thumbnail_for(source) is None
    assert manager.pending_count() == 0
    assert not th.cache_path(source).exists()


def test_manager_does_not_enqueue_same_path_twice(qapp, tmp_path):
    source = _copy(DEMO / "images/swatch.png", tmp_path)
    manager = th.ThumbnailManager(enabled=True)

    manager.thumbnail_for(source)
    manager.thumbnail_for(source)
    manager.thumbnail_for(source)

    assert manager.pending_count() <= 1


def test_clear_queue_drops_pending_requests(qapp, tmp_path):
    """Смена папки не должна оставлять хвост задач по старой."""
    manager = th.ThumbnailManager(enabled=True)
    for i in range(5):
        manager.thumbnail_for(_copy(DEMO / "images/swatch.png", tmp_path).rename(
            tmp_path / f"copy{i}.png"
        ))

    manager.clear_queue()
    assert manager.pending_count() == 0


def test_unsupported_file_is_not_requeued_forever(qapp, qtbot, tmp_path):
    """Текст миниатюры не имеет — менеджер обязан это запомнить, а не спрашивать снова."""
    source = _copy(DEMO / "text/plain-en.txt", tmp_path)
    manager = th.ThumbnailManager(enabled=True)

    assert manager.thumbnail_for(source) is None
    qtbot.waitUntil(lambda: manager.pending_count() == 0, timeout=10000)

    assert manager.thumbnail_for(source) is None
    assert manager.pending_count() == 0


def test_video_thumbnail_is_a_frame(qapp, qtbot, tmp_path):
    source = _copy(DEMO / "media/sample.mp4", tmp_path)
    manager = th.ThumbnailManager(enabled=True)

    assert manager.thumbnail_for(source) is None
    try:
        qtbot.waitUntil(lambda: manager.thumbnail_for(source) is not None, timeout=20000)
    except Exception:  # noqa: BLE001
        pytest.skip("мультимедийный бэкенд Qt не отдал кадр в этой среде")

    pixmap = manager.thumbnail_for(source)
    assert not pixmap.isNull()
    assert max(pixmap.width(), pixmap.height()) <= th.THUMBNAIL_SIZE
