"""Тесты генератора демонстрационных образцов ``demo/generate.py``.

Проверяется внешнее поведение генератора (см. «Критерии приёмки» issue #3):
идемпотентность, наличие обязательных скриптуемых типов, большой текстовый файл,
набор «битых» образцов, файл без расширения, ``demo/CREDITS.md`` и бюджет размера.
"""

from __future__ import annotations

import hashlib
import importlib.util
import struct
import zlib
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_DIR = REPO_ROOT / "demo"
GENERATE_PY = DEMO_DIR / "generate.py"
SIZE_BUDGET_BYTES = 5 * 1024 * 1024


def _load_generate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("demo_generate", GENERATE_PY)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def generate() -> ModuleType:
    assert GENERATE_PY.is_file(), "demo/generate.py отсутствует"
    return _load_generate()


@pytest.fixture
def built(generate: ModuleType, tmp_path: Path) -> Path:
    dest = tmp_path / "demo"
    generate.build(dest)
    return dest


def _tree_digest(root: Path) -> dict[str, str]:
    digest: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            digest[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest


def _dir_size(root: Path) -> int:
    return sum(p.stat().st_size for p in root.rglob("*") if p.is_file())


def test_build_is_idempotent(generate: ModuleType, tmp_path: Path) -> None:
    dest = tmp_path / "demo"

    generate.build(dest)
    first = _tree_digest(dest)

    generate.build(dest)
    second = _tree_digest(dest)

    assert first == second
    assert first, "генератор не создал ни одного файла"


def test_scriptable_samples_present(built: Path) -> None:
    files = {p.relative_to(built).as_posix() for p in built.rglob("*") if p.is_file()}
    suffixes = {Path(name).suffix.lower() for name in files}

    # обычный текст и файл исходного кода
    assert any(name.endswith(".txt") for name in files)
    assert any(name.endswith((".py", ".c", ".js", ".java")) for name in files)

    # табличные и конфигурационные форматы
    for required in (".csv", ".tsv", ".json", ".yaml", ".xml", ".ini"):
        assert required in suffixes, f"нет образца {required}"

    # простые растровые изображения
    assert suffixes >= {".png", ".jpg"}, "нет простых png/jpeg"

    for name in files:
        assert (built / name).stat().st_size > 0, f"{name} пуст"


def test_png_sample_is_structurally_valid(built: Path) -> None:
    png = next((built / "images").rglob("*.png"))
    data = png.read_bytes()

    assert data[:8] == b"\x89PNG\r\n\x1a\n", "нет PNG-сигнатуры"

    chunks: list[str] = []
    idat = b""
    offset = 8
    while offset < len(data):
        (length,) = struct.unpack(">I", data[offset : offset + 4])
        ctype = data[offset + 4 : offset + 8].decode("ascii")
        body = data[offset + 8 : offset + 8 + length]
        (stored_crc,) = struct.unpack(">I", data[offset + 8 + length : offset + 12 + length])
        assert zlib.crc32(data[offset + 4 : offset + 8 + length]) == stored_crc, f"битый CRC {ctype}"
        chunks.append(ctype)
        if ctype == "IDAT":
            idat += body
        offset += 12 + length

    assert chunks[0] == "IHDR"
    assert chunks[-1] == "IEND"
    assert "IDAT" in chunks
    zlib.decompress(idat)  # поднимет исключение, если данные пикселей повреждены


def test_jpeg_sample_has_valid_markers(built: Path) -> None:
    jpg = next((built / "images").rglob("*.jpg"))
    data = jpg.read_bytes()
    assert data[:2] == b"\xff\xd8", "нет JPEG SOI"
    assert data[-2:] == b"\xff\xd9", "нет JPEG EOI"


def test_extensionless_file_with_recognisable_content(built: Path) -> None:
    extensionless = [
        p for p in built.rglob("*") if p.is_file() and p.suffix == "" and "." not in p.name
    ]
    assert extensionless, "нет файла без расширения"

    assert any(p.read_bytes().startswith(b"#!") for p in extensionless), (
        "файл без расширения должен иметь распознаваемое содержимое (напр. shebang)"
    )


def test_large_text_file_over_window_threshold(generate: ModuleType, built: Path) -> None:
    threshold = generate.WINDOW_READ_THRESHOLD_BYTES
    assert isinstance(threshold, int) and threshold > 0

    big = [
        p
        for p in built.rglob("*.txt")
        if p.is_file() and p.stat().st_size > threshold
    ]
    assert big, f"нет текстового файла крупнее порога оконного чтения ({threshold} Б)"


def test_broken_samples_generated(built: Path) -> None:
    broken_dir = built / "broken"
    assert broken_dir.is_dir(), "нет каталога с «битыми» образцами"

    broken = [p for p in broken_dir.rglob("*") if p.is_file()]
    broken_suffixes = {p.suffix.lower() for p in broken}
    assert len(broken_suffixes) >= 3, "«битые» образцы нужны хотя бы для нескольких типов"

    # обрезанный PNG короче исходного и не содержит финального IEND
    truncated_png = broken_dir / "truncated.png"
    if truncated_png.exists():
        pristine_png = next(built.rglob("images/*.png"))
        assert truncated_png.stat().st_size < pristine_png.stat().st_size
        assert b"IEND" not in truncated_png.read_bytes()

    # обрезанный JSON не парсится
    truncated_json = broken_dir / "truncated.json"
    if truncated_json.exists():
        import json

        with pytest.raises(json.JSONDecodeError):
            json.loads(truncated_json.read_text("utf-8"))


def test_total_size_within_budget(built: Path) -> None:
    assert _dir_size(built) < SIZE_BUDGET_BYTES


def test_repo_demo_dir_within_budget() -> None:
    if DEMO_DIR.is_dir():
        assert _dir_size(DEMO_DIR) < SIZE_BUDGET_BYTES


def test_credits_file_describes_provenance() -> None:
    credits = DEMO_DIR / "CREDITS.md"
    assert credits.is_file(), "нет demo/CREDITS.md"
    text = credits.read_text("utf-8").lower()
    assert len(text) > 80
    assert "cc0" in text or "public domain" in text or "public-domain" in text
