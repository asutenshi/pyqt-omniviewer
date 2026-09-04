## @brief Сборщик метаданных для файлов
# Использует QFileInfo, hachoir, Pillow (EXIF), mutagen и PyMuPDF.

import os
from datetime import datetime

from PyQt6.QtCore import QFileInfo

from .mime import detect_mime


def format_size(size_bytes: int) -> str:
    """Форматирует размер в байтах в человекочитаемый вид."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"

def _get_basic_metadata(path: str) -> dict:
    info = QFileInfo(path)
    if not info.exists():
        return {}
    
    if info.isDir():
        mime = "inode/directory"
        size_str = ""
    else:
        mime = detect_mime(path)
        size_str = format_size(info.size())
    
    created = info.birthTime().toSecsSinceEpoch()
    modified = info.lastModified().toSecsSinceEpoch()
    
    if created <= 0 or modified <= 0:
        try:
            stat = os.stat(path)
            created = stat.st_ctime
            modified = stat.st_mtime
        except Exception:  # noqa: BLE001, S110
            pass
            
    meta = {
        "File Name": info.fileName(),
        "MIME Type": mime,
        "Created": datetime.fromtimestamp(created).strftime('%Y-%m-%d %H:%M:%S'),
        "Modified": datetime.fromtimestamp(modified).strftime('%Y-%m-%d %H:%M:%S'),
    }
    if size_str:
        meta["Size"] = size_str
    return meta

def _get_hachoir_metadata(path: str, meta: dict):
    try:
        from hachoir.metadata import extractMetadata
        from hachoir.parser import createParser
        
        parser = createParser(path)
        if parser:
            extracted = extractMetadata(parser)
            if extracted:
                for k, v in extracted.exportPlaintext():
                    # k is like "Duration:", "Image width:"
                    key = k.strip(':')
                    meta[key] = v
    except Exception:  # noqa: BLE001, S110
        pass

def _register_optional_image_plugins():
    """HEIC/HEIF и AVIF читаются Pillow только после регистрации плагинов."""
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except Exception:  # noqa: BLE001, S110
        pass
    try:
        import pillow_avif  # noqa: F401
    except Exception:  # noqa: BLE001, S110
        pass


def _get_image_metadata(path: str, meta: dict):
    _register_optional_image_plugins()
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS
        with Image.open(path) as img:
            meta["Resolution"] = f"{img.width}x{img.height}"
            
            exif = img.getexif()
            if exif:
                for tag_id, data in exif.items():
                    tag = TAGS.get(tag_id, tag_id)
                    if tag in ('Model', 'ExposureTime', 'ISOSpeedRatings', 'FNumber', 'Make', 'Software'):
                        meta[tag] = str(data)
    except Exception:  # noqa: BLE001, S110
        pass

def _get_raw_metadata(path: str, meta: dict):
    """RAW-фото: размер кадра через rawpy, EXIF-подобные поля — через hachoir."""
    try:
        import rawpy
        with rawpy.imread(path) as raw:
            meta["Resolution"] = f"{raw.sizes.width}x{raw.sizes.height}"
    except Exception:  # noqa: BLE001, S110
        pass
    _get_hachoir_metadata(path, meta)

def _get_audio_metadata(path: str, meta: dict):
    try:
        import mutagen
        audio = mutagen.File(path)
        if audio is not None:
            if audio.info:
                if hasattr(audio.info, 'length'):
                    mins = int(audio.info.length // 60)
                    secs = int(audio.info.length % 60)
                    meta["Duration"] = f"{mins}:{secs:02d}"
            
            if audio.tags:
                for key in ['artist', 'title', 'album']:
                    if key in audio.tags:
                        meta[key.capitalize()] = str(audio.tags[key][0])
                    elif key == 'artist' and 'TPE1' in audio.tags:
                        meta['Artist'] = str(audio.tags['TPE1'].text[0])
                    elif key == 'title' and 'TIT2' in audio.tags:
                        meta['Title'] = str(audio.tags['TIT2'].text[0])
                    elif key == 'album' and 'TALB' in audio.tags:
                        meta['Album'] = str(audio.tags['TALB'].text[0])
    except Exception:  # noqa: BLE001, S110
        pass

def _get_pdf_metadata(path: str, meta: dict):
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(path)
        if doc.metadata:
            for k, v in doc.metadata.items():
                if v:
                    meta[k.capitalize()] = v
        meta["Pages"] = str(len(doc))
        doc.close()
    except Exception:  # noqa: BLE001, S110
        pass

def metadata_for(path: str) -> dict:
    """Единая точка входа для сбора метаданных файла."""
    meta = _get_basic_metadata(path)
    if not meta:
        return {}
        
    mime = meta.get("MIME Type", "")
    lower = path.lower()

    _IMG_EXT = (
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff", ".ico",
        ".heic", ".heif", ".hif", ".avif",
    )
    _RAW_EXT = (".cr2", ".cr3", ".nef", ".arw", ".dng", ".raf", ".orf", ".rw2")

    if lower.endswith(_RAW_EXT):
        _get_raw_metadata(path, meta)
    elif mime.startswith("image/") or lower.endswith(_IMG_EXT):
        _get_image_metadata(path, meta)
    elif mime.startswith(("audio/", "video/")):
        _get_audio_metadata(path, meta)
    elif mime in (
        "application/pdf",
        "application/epub+zip",
        "application/x-mobipocket-ebook",
        "application/vnd.comicbook+zip",
        "application/vnd.ms-xpsdocument",
        "application/oxps",
        "application/x-fictionbook+xml",
    ) or path.lower().endswith(('.pdf', '.epub', '.mobi', '.fb2', '.cbz', '.xps', '.oxps')):
        _get_pdf_metadata(path, meta)
        
    if (mime.startswith(("image/", "video/"))) and "Resolution" not in meta:
        _get_hachoir_metadata(path, meta)
        
    if (mime.startswith(("audio/", "video/"))) and "Duration" not in meta:
        _get_hachoir_metadata(path, meta)
        
    return meta
    # ruff: noqa: DTZ006, SIM102
