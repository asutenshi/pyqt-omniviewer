# ruff: noqa: BLE001
"""Просмотрщик содержимого архивов."""

from __future__ import annotations

import contextlib
import shutil
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from PyQt6.QtCore import QMimeType, Qt, pyqtSignal
from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem

from omniviewer.viewers.base import BaseViewer

try:  # libarchive — необязательная зависимость (rar/iso/cab/lha/ar)
    import libarchive  # type: ignore

    _HAS_LIBARCHIVE = True
except Exception:  # pragma: no cover - зависит от системного libarchive
    _HAS_LIBARCHIVE = False

try:
    import py7zr  # type: ignore

    _HAS_PY7ZR = True
except Exception:  # pragma: no cover
    _HAS_PY7ZR = False


_SEVEN_ZIP_MAGIC = b"7z\xbc\xaf\x27\x1c"

## @brief Предел рекурсии по вложенным архивам (глубина).
DEFAULT_MAX_DEPTH = 3

## @brief Предел суммарного объёма распакованных данных за сессию просмотра, байт.
DEFAULT_MAX_TOTAL_BYTES = 256 * 1024 * 1024


class ArchiveSecurityError(Exception):
    """Запись архива выходит за пределы временной папки либо превышен лимит распаковки."""


@dataclass(frozen=True)
class ArchiveEntry:
    """Одна запись архива: POSIX-путь, размер в байтах, признак каталога."""

    name: str
    size: int
    is_dir: bool


class _Budget:
    """Разделяемый между вложенными архивами счётчик оставшегося объёма распаковки."""

    def __init__(self, limit: int) -> None:
        self.remaining = int(limit)

    def consume(self, nbytes: int) -> None:
        if nbytes > self.remaining:
            raise ArchiveSecurityError(
                f"Превышен лимит распаковки архива ({nbytes} Б запрошено, "
                f"{self.remaining} Б осталось)"
            )
        self.remaining -= nbytes


def _looks_like_7z(path: Path) -> bool:
    try:
        with open(path, "rb") as fh:
            return fh.read(6) == _SEVEN_ZIP_MAGIC
    except OSError:
        return False


## @brief Просмотрщик архивов: дерево содержимого + безопасное открытие вложенных файлов.
#
# Форматы: zip (zipfile), tar и tar.gz/bz2/xz (tarfile), 7z (py7zr),
# rar/iso/cab/lha/ar (libarchive-c). Содержимое показывается деревом.
# Двойной клик по вложенному файлу распаковывает его во временную папку и
# открывает тем же ``ViewerRegistry``; вложенные архивы открываются рекурсивно
# с ограничением по глубине и суммарному распакованному размеру. Пути записей
# проверяются на выход за пределы временной папки (Zip Slip).
class ArchiveViewer(BaseViewer):
    priority = 15  # ниже PdfViewer(20): cbz/epub остаются за ним

    _ARCHIVE_MIMES = frozenset(
        {
            "application/zip",
            "application/x-zip-compressed",
            "application/x-tar",
            "application/gzip",
            "application/x-gzip",
            "application/x-compressed-tar",
            "application/x-bzip2",
            "application/x-bzip-compressed-tar",
            "application/x-xz",
            "application/x-xz-compressed-tar",
            "application/x-7z-compressed",
            "application/vnd.rar",
            "application/x-rar",
            "application/x-rar-compressed",
            "application/x-cd-image",
            "application/x-iso9660-image",
            "application/vnd.ms-cab-compressed",
            "application/x-cpio",
            "application/x-lha",
            "application/x-lzh-compressed",
            "application/x-archive",
            "application/x-unix-archive",
        }
    )
    _ARCHIVE_SUFFIXES = (
        ".zip",
        ".tar",
        ".tar.gz",
        ".tgz",
        ".tar.bz2",
        ".tbz",
        ".tbz2",
        ".tar.xz",
        ".txz",
        ".7z",
        ".rar",
        ".iso",
        ".cab",
        ".lha",
        ".lzh",
        ".ar",
        ".cpio",
    )
    # Зип-контейнеры со своим просмотрщиком — архивным их не берём.
    _EXCLUDED_SUFFIXES = frozenset(
        {
            ".cbz",
            ".cbr",
            ".epub",
            ".mobi",
            ".fb2",
            ".xps",
            ".oxps",
            ".jar",
            ".war",
            ".apk",
            ".xpi",
            ".whl",
            ".xlsx",
            ".xlsm",
            ".docx",
            ".pptx",
            ".odt",
            ".ods",
            ".odp",
        }
    )

    ## @brief Испущен при двойном клике по вложенному файлу — путь распакованной копии.
    member_activated = pyqtSignal(object)

    def __init__(
        self,
        max_depth: int = DEFAULT_MAX_DEPTH,
        max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    ) -> None:
        super().__init__()
        self._max_depth = int(max_depth)
        self._depth = 0
        self._budget = _Budget(max_total_bytes)

        self._path: Path | None = None
        self._kind: str | None = None
        self.entries: list[ArchiveEntry] = []
        self._entry_map: dict[str, ArchiveEntry] = {}
        self._temp_root: str | None = None
        self._child_viewers: list[BaseViewer] = []

        self._layout.setContentsMargins(0, 0, 0, 0)
        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabels(["Имя", "Размер"])
        self.tree_widget.setColumnCount(2)
        self.tree_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._layout.addWidget(self.tree_widget)

    # ------------------------------------------------------------------ #
    # Диспетчеризация                                                    #
    # ------------------------------------------------------------------ #

    @classmethod
    def can_handle(cls, path: Path, mime: QMimeType | str) -> bool:
        name_lower = path.name.lower()
        if any(name_lower.endswith(s) for s in cls._EXCLUDED_SUFFIXES):
            return False

        mime_name = mime.name() if isinstance(mime, QMimeType) else str(mime)
        if mime_name in cls._ARCHIVE_MIMES:
            return True

        return any(name_lower.endswith(s) for s in cls._ARCHIVE_SUFFIXES)

    # ------------------------------------------------------------------ #
    # Загрузка                                                           #
    # ------------------------------------------------------------------ #

    def load(self, path: Path) -> None:
        path = Path(path)
        self._path = path
        self._kind = self._detect_kind(path)
        self.entries = self._read_index(path, self._kind)
        self._entry_map = {e.name: e for e in self.entries if not e.is_dir}
        self._populate_tree()

    def _detect_kind(self, path: Path) -> str:
        if zipfile.is_zipfile(path):
            return "zip"
        if tarfile.is_tarfile(path):
            return "tar"
        if _HAS_PY7ZR and (_looks_like_7z(path) or py7zr.is_7zfile(path)):
            return "7z"
        if _HAS_LIBARCHIVE:
            try:
                with libarchive.file_reader(str(path)) as arc:
                    for _ in arc:
                        break
                return "libarchive"
            except Exception as exc:  # битый/неизвестный контейнер
                raise ValueError(f"Не удалось открыть архив: {exc}") from exc
        raise ValueError("Формат архива не распознан (нет подходящей библиотеки)")

    def _read_index(self, path: Path, kind: str) -> list[ArchiveEntry]:
        if kind == "zip":
            with zipfile.ZipFile(path) as zf:
                return [
                    ArchiveEntry(i.filename.rstrip("/"), i.file_size, i.is_dir())
                    for i in zf.infolist()
                ]
        if kind == "tar":
            with tarfile.open(path) as tf:
                return [
                    ArchiveEntry(m.name, m.size, m.isdir())
                    for m in tf.getmembers()
                    if m.isdir() or m.isfile()
                ]
        if kind == "7z":
            with py7zr.SevenZipFile(path, "r") as zf:
                out: list[ArchiveEntry] = []
                for info in zf.list():
                    out.append(ArchiveEntry(info.filename, int(info.uncompressed or 0), info.is_directory))
                return out
        # libarchive
        out = []
        with libarchive.file_reader(str(path)) as arc:
            for entry in arc:
                out.append(
                    ArchiveEntry(str(entry.pathname).rstrip("/"), int(entry.size or 0), entry.isdir)
                )
        return out

    def _populate_tree(self) -> None:
        self.tree_widget.clear()
        nodes: dict[str, QTreeWidgetItem] = {}

        def ensure_dir(parts: tuple[str, ...]) -> QTreeWidgetItem | None:
            if not parts:
                return None
            key = "/".join(parts)
            if key in nodes:
                return nodes[key]
            parent = ensure_dir(parts[:-1])
            item = QTreeWidgetItem([parts[-1], ""])
            item.setData(0, Qt.ItemDataRole.UserRole, None)
            if parent is None:
                self.tree_widget.addTopLevelItem(item)
            else:
                parent.addChild(item)
            nodes[key] = item
            return item

        for entry in sorted(self.entries, key=lambda e: e.name):
            parts = tuple(p for p in PurePosixPath(entry.name).parts if p not in ("", "/"))
            if not parts:
                continue
            if entry.is_dir:
                ensure_dir(parts)
                continue
            parent = ensure_dir(parts[:-1])
            leaf = QTreeWidgetItem([parts[-1], _human_size(entry.size)])
            leaf.setData(0, Qt.ItemDataRole.UserRole, entry.name)
            if parent is None:
                self.tree_widget.addTopLevelItem(leaf)
            else:
                parent.addChild(leaf)

    # ------------------------------------------------------------------ #
    # Безопасная распаковка                                              #
    # ------------------------------------------------------------------ #

    @property
    def temp_root(self) -> str:
        if self._temp_root is None:
            self._temp_root = tempfile.mkdtemp(prefix="omniviewer-arc-")
        return self._temp_root

    def _safe_target(self, member_name: str) -> Path:
        pure = PurePosixPath(member_name)
        if pure.is_absolute() or member_name.startswith(("/", "\\")):
            raise ArchiveSecurityError(f"Абсолютный путь в архиве отклонён: {member_name!r}")
        if ".." in pure.parts:
            raise ArchiveSecurityError(f"Выход за пределы архива отклонён: {member_name!r}")
        root = Path(self.temp_root).resolve()
        target = (root / pure).resolve()
        if target != root and not target.is_relative_to(root):
            raise ArchiveSecurityError(f"Zip Slip отклонён: {member_name!r}")
        return target

    def extract_member(self, member_name: str) -> Path:
        """Распаковать один файл во временную папку и вернуть путь к копии."""
        entry = self._entry_map.get(member_name)
        if entry is None:
            raise ValueError(f"В архиве нет файла {member_name!r}")
        if entry.is_dir:
            raise ValueError(f"{member_name!r} — каталог, не файл")

        target = self._safe_target(member_name)
        self._budget.consume(entry.size)

        data = self._read_member_bytes(member_name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return target

    def _read_member_bytes(self, member_name: str) -> bytes:
        assert self._path is not None
        if self._kind == "zip":
            with zipfile.ZipFile(self._path) as zf:
                return zf.read(member_name)
        if self._kind == "tar":
            with tarfile.open(self._path) as tf:
                member = tf.getmember(member_name)
                if member.issym() or member.islnk():
                    raise ArchiveSecurityError(f"Ссылка в архиве отклонена: {member_name!r}")
                fobj = tf.extractfile(member)
                return fobj.read() if fobj else b""
        if self._kind == "7z":
            with py7zr.SevenZipFile(self._path, "r") as zf:
                extracted = zf.read([member_name])
                buf = extracted.get(member_name)
                return buf.read() if buf else b""
        # libarchive
        chunks: list[bytes] = []
        with libarchive.file_reader(str(self._path)) as arc:
            for entry in arc:
                if str(entry.pathname).rstrip("/") == member_name:
                    chunks.extend(entry.get_blocks())
                    break
        return b"".join(chunks)

    # ------------------------------------------------------------------ #
    # Рекурсивное открытие                                               #
    # ------------------------------------------------------------------ #

    def open_member(self, member_name: str) -> BaseViewer:
        """Распаковать вложенный файл и вернуть просмотрщик для него из реестра."""
        from omniviewer.registry import default_registry

        try:
            extracted = self.extract_member(member_name)
        except (ArchiveSecurityError, ValueError) as exc:
            return _error_widget(str(exc))

        viewer = default_registry.viewer_for(extracted)

        if isinstance(viewer, ArchiveViewer):
            if self._depth + 1 > self._max_depth:
                return _error_widget(
                    f"Достигнут предел вложенности архивов ({self._max_depth})"
                )
            viewer._depth = self._depth + 1
            viewer._max_depth = self._max_depth
            viewer._budget = self._budget

        viewer.safe_load(extracted)
        self._child_viewers.append(viewer)
        return viewer

    def _on_item_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        member_name = item.data(0, Qt.ItemDataRole.UserRole)
        if not member_name:
            return
        viewer = self.open_member(member_name)
        viewer.setWindowTitle(f"{Path(member_name).name} — {self._path.name if self._path else ''}")
        viewer.resize(900, 700)
        viewer.show()
        self.member_activated.emit(member_name)

    # ------------------------------------------------------------------ #
    # Очистка                                                            #
    # ------------------------------------------------------------------ #

    def unload(self) -> None:
        for child in self._child_viewers:
            if hasattr(child, "unload"):
                with contextlib.suppress(Exception):
                    child.unload()
        self._child_viewers.clear()
        if self._temp_root:
            shutil.rmtree(self._temp_root, ignore_errors=True)
            self._temp_root = None
        if hasattr(super(), "unload"):
            super().unload()


def _human_size(nbytes: int) -> str:
    size = float(nbytes)
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if size < 1024 or unit == "ГБ":
            return f"{size:.0f} {unit}" if unit == "Б" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{nbytes} Б"


def _error_widget(message: str) -> BaseViewer:
    widget = BaseViewer()
    widget._show_error(RuntimeError(message), "")
    return widget
