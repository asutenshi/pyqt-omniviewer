"""Тесты просмотрщика архивов (issue #16).

Поведение проверяется через главный шов ``ViewerRegistry`` и публичный API
``ArchiveViewer``: дерево содержимого, безопасная распаковка одного файла
(Zip Slip), лимиты рекурсии по глубине и суммарному размеру, рекурсивное
открытие вложенного архива, «ошибочный» виджет на битом архиве.
"""

from __future__ import annotations

import io
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

from omniviewer.registry import ViewerRegistry
from omniviewer.viewers.archive import ArchiveSecurityError, ArchiveViewer
from omniviewer.viewers.fallback import FallbackViewer
from omniviewer.viewers.text import TextViewer


@pytest.fixture(scope="session", autouse=True)
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture
def registry() -> ViewerRegistry:
    return ViewerRegistry()


# --------------------------------------------------------------------------- #
# Помощники — сборка архивов только стандартной библиотекой                    #
# --------------------------------------------------------------------------- #


def make_zip(path: Path, entries: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return path


def make_tar_gz(path: Path, entries: dict[str, bytes]) -> Path:
    with tarfile.open(path, "w:gz") as t:
        for name, data in entries.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
    return path


def make_zip_with_raw_name(path: Path, arcname: str, data: bytes) -> Path:
    """ZIP с произвольным (в т.ч. вредоносным) именем записи — для теста Zip Slip."""
    with zipfile.ZipFile(path, "w") as z:
        zi = zipfile.ZipInfo(arcname)
        z.writestr(zi, data)
    return path


# --------------------------------------------------------------------------- #
# Диспетчеризация                                                             #
# --------------------------------------------------------------------------- #


def test_registry_selects_archive_viewer_for_zip(registry: ViewerRegistry, tmp_path: Path) -> None:
    z = make_zip(tmp_path / "sample.zip", {"a.txt": b"hi"})
    assert isinstance(registry.viewer_for(z), ArchiveViewer)


def test_registry_selects_archive_viewer_for_tar_gz(
    registry: ViewerRegistry, tmp_path: Path
) -> None:
    t = make_tar_gz(tmp_path / "sample.tar.gz", {"a.txt": b"hi"})
    assert isinstance(registry.viewer_for(t), ArchiveViewer)


def test_archive_viewer_does_not_steal_comicbook_and_office(tmp_path: Path) -> None:
    """cbz/epub/xlsx — зип-контейнеры, но их берут другие просмотрщики, не архивный."""
    from PyQt6.QtCore import QMimeDatabase

    db = QMimeDatabase()
    for name in ("book.cbz", "book.epub", "table.xlsx", "doc.docx"):
        p = make_zip(tmp_path / name, {"x": b"y"})
        mime = db.mimeTypeForFile(str(p), QMimeDatabase.MatchMode.MatchDefault)
        assert ArchiveViewer.can_handle(p, mime) is False, name


# --------------------------------------------------------------------------- #
# Дерево содержимого                                                          #
# --------------------------------------------------------------------------- #


def test_lists_entries_with_names_and_sizes(tmp_path: Path) -> None:
    z = make_zip(
        tmp_path / "a.zip",
        {"readme.txt": b"hello", "src/main.py": b"print(1)\n", "src/lib/util.py": b"x = 2\n"},
    )
    viewer = ArchiveViewer()
    viewer.safe_load(z)
    assert not viewer.is_error_widget

    by_name = {e.name: e for e in viewer.entries if not e.is_dir}
    assert set(by_name) == {"readme.txt", "src/main.py", "src/lib/util.py"}
    assert by_name["readme.txt"].size == 5
    assert by_name["src/main.py"].size == len(b"print(1)\n")

    # дерево отражает иерархию каталогов
    assert viewer.tree_widget.topLevelItemCount() >= 1


# --------------------------------------------------------------------------- #
# Безопасная распаковка одного файла                                          #
# --------------------------------------------------------------------------- #


def test_extract_member_returns_file_inside_tmpdir(tmp_path: Path) -> None:
    z = make_zip(tmp_path / "a.zip", {"dir/f.txt": b"content-here"})
    viewer = ArchiveViewer()
    viewer.safe_load(z)

    out = viewer.extract_member("dir/f.txt")
    assert out.is_file()
    assert out.read_bytes() == b"content-here"
    assert out.resolve().is_relative_to(Path(viewer.temp_root).resolve())


@pytest.mark.parametrize("evil", ["../evil.txt", "../../evil.txt", "/abs/evil.txt", "a/../../evil"])
def test_zip_slip_is_rejected(tmp_path: Path, evil: str) -> None:
    z = make_zip_with_raw_name(tmp_path / "evil.zip", evil, b"pwned")
    viewer = ArchiveViewer()
    viewer.safe_load(z)

    with pytest.raises(ArchiveSecurityError):
        viewer.extract_member(evil)

    # ничего не создано за пределами временной папки
    assert not (tmp_path.parent / "evil.txt").exists()
    assert not Path("/abs/evil.txt").exists()


# --------------------------------------------------------------------------- #
# Лимиты рекурсии                                                             #
# --------------------------------------------------------------------------- #


def _nested_zip_bytes(depth: int) -> bytes:
    """ZIP, вложенный сам в себя `depth` раз, самый внутренний — с text-файлом."""
    inner = b"deepest payload\n"
    name = "payload.txt"
    for _ in range(depth):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr(name, inner)
        inner = buf.getvalue()
        name = "inner.zip"
    return inner


def test_recursion_depth_limit(tmp_path: Path) -> None:
    z = tmp_path / "n.zip"
    z.write_bytes(_nested_zip_bytes(4))

    viewer = ArchiveViewer(max_depth=2)
    viewer.safe_load(z)

    # глубина 0 -> открываем inner.zip (глубина 1) -> ok
    v1 = viewer.open_member("inner.zip")
    assert isinstance(v1, ArchiveViewer)
    # глубина 1 -> inner.zip (глубина 2) -> ok
    v2 = v1.open_member("inner.zip")
    assert isinstance(v2, ArchiveViewer)
    # глубина 2 -> превышение -> ошибочный виджет / исключение
    v3 = v2.open_member("inner.zip")
    assert v3.is_error_widget


def test_total_extract_size_budget(tmp_path: Path) -> None:
    z = make_zip(tmp_path / "big.zip", {"big.bin": b"x" * 5000})
    viewer = ArchiveViewer(max_total_bytes=1000)
    viewer.safe_load(z)

    with pytest.raises(ArchiveSecurityError):
        viewer.extract_member("big.bin")


# --------------------------------------------------------------------------- #
# Рекурсивное открытие вложенного архива                                      #
# --------------------------------------------------------------------------- #


def test_nested_archive_opens_through_registry(tmp_path: Path) -> None:
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as z:
        z.writestr("hello.txt", b"from inner archive")
    outer = make_zip(tmp_path / "outer.zip", {"inner.zip": inner.getvalue()})

    viewer = ArchiveViewer()
    viewer.safe_load(outer)

    inner_viewer = viewer.open_member("inner.zip")
    assert isinstance(inner_viewer, ArchiveViewer)
    assert not inner_viewer.is_error_widget

    text_viewer = inner_viewer.open_member("hello.txt")
    assert isinstance(text_viewer, (TextViewer, FallbackViewer))
    assert not text_viewer.is_error_widget


# --------------------------------------------------------------------------- #
# Битый архив                                                                 #
# --------------------------------------------------------------------------- #


def test_truncated_archive_yields_error_widget(tmp_path: Path) -> None:
    full = make_zip(tmp_path / "full.zip", {"a.txt": b"a" * 400, "b.txt": b"b" * 400}).read_bytes()
    broken = tmp_path / "broken.zip"
    broken.write_bytes(full[: len(full) // 2])

    viewer = ArchiveViewer()
    viewer.safe_load(broken)
    viewer.safe_load_async()
    QApplication.processEvents()

    assert viewer.is_error_widget
