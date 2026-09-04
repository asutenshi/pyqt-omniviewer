"""Тесты просмотрщика шрифтов: TTF / OTF / WOFF / WOFF2.

Проверяется через главный шов ``ViewerRegistry`` и публичный API ``FontViewer``:

* реестр отдаёт ``FontViewer`` по ``ttf`` / ``otf`` / ``woff`` / ``woff2``;
* образец нарисован именно загруженным семейством, в нескольких кеглях, с
  панграммой и алфавитом;
* показаны метаданные из fontTools (семейство, начертание, версия, число глифов);
* WOFF/WOFF2 распаковываются и грузятся;
* OTF опознаётся как PostScript/CFF;
* битый файл → «ошибочный» виджет.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from PyQt6.QtWidgets import QApplication, QLabel

from omniviewer.registry import ViewerRegistry
from omniviewer.viewers.font import FontViewer

_CHARS = list(" ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.,:;!?")
_ORDER = [".notdef"] + [f"g{ord(c):04X}" for c in _CHARS]
_ADV = 600


@pytest.fixture(scope="session", autouse=True)
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture
def registry() -> ViewerRegistry:
    return ViewerRegistry()


# --------------------------------------------------------------------------- #
# Мини-конструктор шрифтов (без зависимости от demo/)                          #
# --------------------------------------------------------------------------- #


def _names(fb: FontBuilder, family: str, style: str) -> None:
    fb.setupHorizontalMetrics({g: (_ADV, 60) for g in _ORDER})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable(
        {
            "familyName": family,
            "styleName": style,
            "uniqueFontIdentifier": f"test;{family}-{style};1.0",
            "fullName": f"{family} {style}",
            "psName": f"{family}-{style}".replace(" ", ""),
            "version": "Version 2.500",
        }
    )
    fb.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    fb.setupPost()
    fb.font["head"].created = fb.font["head"].modified = 3800000000


def make_ttf(family: str = "Testish Sans", style: str = "Regular") -> bytes:
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(_ORDER)
    fb.setupCharacterMap({ord(c): f"g{ord(c):04X}" for c in _CHARS})
    glyphs = {}
    for g in _ORDER:
        pen = TTGlyphPen(None)
        if g != ".notdef" and g != f"g{ord(' '):04X}":
            pen.moveTo((80, 0))
            pen.lineTo((80, 640))
            pen.lineTo((_ADV - 80, 640))
            pen.lineTo((_ADV - 80, 0))
            pen.closePath()
        glyphs[g] = pen.glyph()
    fb.setupGlyf(glyphs)
    _names(fb, family, style)
    buf = io.BytesIO()
    fb.save(buf)
    return buf.getvalue()


def make_otf(family: str = "Testish Serif", style: str = "Regular") -> bytes:
    fb = FontBuilder(1000, isTTF=False)
    fb.setupGlyphOrder(_ORDER)
    fb.setupCharacterMap({ord(c): f"g{ord(c):04X}" for c in _CHARS})
    cs = {}
    for g in _ORDER:
        pen = T2CharStringPen(_ADV, None)
        if g != ".notdef" and g != f"g{ord(' '):04X}":
            pen.moveTo((80, 0))
            pen.lineTo((80, 640))
            pen.lineTo((_ADV - 80, 640))
            pen.lineTo((_ADV - 80, 0))
            pen.closePath()
        cs[g] = pen.getCharString()
    fb.setupCFF(
        psName=f"{family}-{style}".replace(" ", ""),
        fontInfo={"FamilyName": family, "FullName": f"{family} {style}", "version": "2.500"},
        charStringsDict=cs,
        privateDict={},
    )
    _names(fb, family, style)
    buf = io.BytesIO()
    fb.save(buf)
    return buf.getvalue()


def reflavor(sfnt: bytes, flavor: str) -> bytes:
    f = TTFont(io.BytesIO(sfnt))
    f.flavor = flavor
    buf = io.BytesIO()
    f.save(buf)
    return buf.getvalue()


def _write(tmp_path: Path, name: str, data: bytes) -> Path:
    p = tmp_path / name
    p.write_bytes(data)
    return p


def _sample_labels(viewer: FontViewer) -> list[QLabel]:
    page = viewer._scroll.widget()
    assert page is not None
    return page.findChildren(QLabel)


# --------------------------------------------------------------------------- #
# Диспетчеризация                                                             #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("suffix", [".ttf", ".otf", ".woff", ".woff2"])
def test_registry_selects_font_viewer(registry, tmp_path, suffix: str) -> None:
    ttf = make_ttf()
    data = make_otf() if suffix == ".otf" else (ttf if suffix == ".ttf" else reflavor(ttf, suffix.lstrip(".")))
    p = _write(tmp_path, f"sample{suffix}", data)
    assert isinstance(registry.viewer_for(p), FontViewer)


def test_font_viewer_ignores_plain_binary(registry, tmp_path) -> None:
    p = _write(tmp_path, "blob.bin", b"\x00\x01\x02not a font\xff")
    assert not isinstance(registry.viewer_for(p), FontViewer)


# --------------------------------------------------------------------------- #
# Образец начертания                                                          #
# --------------------------------------------------------------------------- #


def test_sample_is_drawn_with_loaded_family(tmp_path) -> None:
    p = _write(tmp_path, "s.ttf", make_ttf(family="Testish Sans"))
    viewer = FontViewer()
    viewer.safe_load(p)

    assert not viewer.is_error_widget
    assert viewer.font_family == "Testish Sans"

    labels = _sample_labels(viewer)
    using_family = [lbl for lbl in labels if lbl.font().family() == "Testish Sans"]
    assert len(using_family) >= len(viewer.sample_sizes)
    assert any("quick brown fox" in lbl.text() for lbl in labels)
    assert any("ABCDEFGHIJKLMNOPQRSTUVWXYZ" in lbl.text() for lbl in labels)
    assert any("0123456789" in lbl.text() for lbl in labels)


def test_sample_shown_in_several_sizes(tmp_path) -> None:
    p = _write(tmp_path, "s.ttf", make_ttf())
    viewer = FontViewer()
    viewer.safe_load(p)

    sizes = {
        lbl.font().pointSize()
        for lbl in _sample_labels(viewer)
        if lbl.font().family() == viewer.font_family and lbl.font().pointSize() > 0
    }
    assert sizes.issuperset(set(viewer.sample_sizes))
    assert len(sizes) >= 4


# --------------------------------------------------------------------------- #
# Метаданные                                                                  #
# --------------------------------------------------------------------------- #


def test_metadata_from_fonttools(tmp_path) -> None:
    p = _write(tmp_path, "s.ttf", make_ttf(family="Testish Sans", style="Regular"))
    viewer = FontViewer()
    viewer.safe_load(p)

    md = viewer.metadata
    assert md["Семейство"] == "Testish Sans"
    assert md["Начертание"] == "Regular"
    assert "2.500" in md["Версия"]
    assert md["Тип контуров"] == "TrueType"
    assert md["Формат файла"] == "TTF"
    assert "cmap" in md["Таблицы"] and "glyf" in md["Таблицы"]

    expected = TTFont(str(p))["maxp"].numGlyphs
    assert viewer.glyph_count == expected
    assert md["Число глифов"] == str(expected)


def test_otf_reports_cff_outlines(tmp_path) -> None:
    p = _write(tmp_path, "s.otf", make_otf())
    viewer = FontViewer()
    viewer.safe_load(p)

    assert not viewer.is_error_widget
    assert viewer.metadata["Тип контуров"] == "PostScript / CFF"
    assert viewer.metadata["Формат файла"] == "OTF"
    assert "CFF" in viewer.metadata["Таблицы"]


# --------------------------------------------------------------------------- #
# WOFF / WOFF2                                                                #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("flavor", ["woff", "woff2"])
def test_web_font_is_decompressed_and_loaded(tmp_path, flavor: str) -> None:
    ttf = make_ttf(family="Testish Sans")
    p = _write(tmp_path, f"s.{flavor}", reflavor(ttf, flavor))
    viewer = FontViewer()
    viewer.safe_load(p)

    assert not viewer.is_error_widget
    assert viewer.font_family == "Testish Sans"
    assert viewer.glyph_count == TTFont(io.BytesIO(ttf))["maxp"].numGlyphs
    assert viewer.metadata["Формат файла"] == flavor.upper()
    assert any(
        lbl.font().family() == "Testish Sans" for lbl in _sample_labels(viewer)
    )


# --------------------------------------------------------------------------- #
# Битый образец                                                               #
# --------------------------------------------------------------------------- #


def test_broken_font_yields_error_widget(tmp_path) -> None:
    full = make_ttf()
    p = _write(tmp_path, "broken.ttf", full[: len(full) // 3])
    viewer = FontViewer()
    viewer.safe_load(p)
    assert viewer.is_error_widget


def test_not_a_font_yields_error_widget(tmp_path) -> None:
    p = _write(tmp_path, "fake.otf", b"OTTO" + b"\x00" * 200)
    viewer = FontViewer()
    viewer.safe_load(p)
    assert viewer.is_error_widget
