import mimetypes


def detect_mime(path: str) -> str:
    """
    Определяет MIME-тип файла.
    """
    mime, _ = mimetypes.guess_type(path)
    if mime:
        return mime
    
    return "application/octet-stream"
