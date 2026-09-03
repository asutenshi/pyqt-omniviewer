from pathlib import Path

import pytest

from omniviewer.metadata import metadata_for

DEMO_DIR = Path("demo")

def test_basic_metadata():
    txt_path = DEMO_DIR / "text" / "plain-en.txt"
    if not txt_path.exists():
        pytest.skip("Run demo/generate.py first")
        
    meta = metadata_for(str(txt_path))
    assert meta
    assert "File Name" in meta
    assert "Size" in meta
    assert "MIME Type" in meta
    assert "Created" in meta
    assert "Modified" in meta
    
def test_image_metadata():
    img_path = DEMO_DIR / "images" / "swatch.jpg"
    if not img_path.exists():
        pytest.skip("Run demo/generate.py first")
        
    meta = metadata_for(str(img_path))
    assert meta
    assert "Resolution" in meta

def test_hachoir_fallback(tmp_path):
    # create a dummy wav file with minimal header to trick hachoir
    wav_path = tmp_path / "dummy.wav"
    # RIFF(4) size(4) WAVE(4) fmt (4) size(4) format(2) channels(2) rate(4) byte_rate(4) align(2) bits(2) data(4) size(4)
    # just write enough for hachoir to see it as something
    wav_path.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00")
    
    meta = metadata_for(str(wav_path))
    assert meta
    assert "MIME Type" in meta

def test_gui_doesnt_hang_on_large_file():
    large_path = DEMO_DIR / "large" / "big-lines.txt"
    if not large_path.exists():
        pytest.skip("Run demo/generate.py first")
        
    meta = metadata_for(str(large_path))
    assert meta
    assert "Size" in meta
