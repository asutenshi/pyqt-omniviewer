from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QImageReader


def load_scaled_image(path: str, max_dim: int) -> QImage:
    """
    Загружает изображение, уменьшая его, если одна из сторон больше max_dim.
    """
    reader = QImageReader(path)
    size = reader.size()
    if size.isValid() and (size.width() > max_dim or size.height() > max_dim):
        new_size = size.scaled(max_dim, max_dim, Qt.AspectRatioMode.KeepAspectRatio)
        reader.setScaledSize(new_size)
    return reader.read()
