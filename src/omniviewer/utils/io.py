import os


class WindowedReader:
    """Утилита для оконного чтения больших файлов."""
    def __init__(self, path: str, chunk_size: int = 5 * 1024 * 1024):
        self.path = path
        self.chunk_size = chunk_size
        self.file_size = os.path.getsize(path)

    def read_chunk(self, offset: int) -> bytes:
        """Читает блок данных размером chunk_size начиная с offset."""
        with open(self.path, 'rb') as f:
            f.seek(offset)
            return f.read(self.chunk_size)
