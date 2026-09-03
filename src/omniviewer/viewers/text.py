# ruff: noqa: BLE001
import os
from pathlib import Path

import charset_normalizer
from pygments import lex
from pygments.lexers import get_lexer_for_filename, get_lexer_for_mimetype
from pygments.lexers.special import TextLexer
from pygments.styles import get_style_by_name
from PyQt6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat, QTextDocument
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QWidget

from omniviewer.viewers.base import BaseViewer


class PygmentsHighlighter(QSyntaxHighlighter):
    """Highlighter bridging pygments with QSyntaxHighlighter."""
    def __init__(self, document: QTextDocument, lexer):
        super().__init__(document)
        self.lexer = lexer
        self.style = get_style_by_name("default")
        self.formats = {}
        for token, style_data in self.style:
            fmt = QTextCharFormat()
            if style_data['color']:
                fmt.setForeground(QColor('#' + style_data['color']))
            if style_data['bgcolor']:
                fmt.setBackground(QColor('#' + style_data['bgcolor']))
            if style_data['bold']:
                fmt.setFontWeight(QFont.Weight.Bold)
            if style_data['italic']:
                fmt.setFontItalic(True)
            if style_data['underline']:
                fmt.setFontUnderline(True)
            self.formats[token] = fmt

    def highlightBlock(self, text: str):
        # We lex just the block. For a simple viewer this is usually acceptable, 
        # though multiline constructs (like multiline strings) might lose highlight across lines.
        # But this fits the "ширина охвата важнее полировки" principle.
        if isinstance(self.lexer, TextLexer):
            return
            
        try:
            tokens = lex(text, self.lexer)
            current_pos = 0
            for token, t_text in tokens:
                t_len = len(t_text)
                fmt = self.formats.get(token)
                if not fmt:
                    # Try parent token types
                    parent = token.parent
                    while parent:
                        if parent in self.formats:
                            fmt = self.formats[parent]
                            break
                        parent = parent.parent
                if fmt:
                    self.setFormat(current_pos, t_len, fmt)
                current_pos += t_len
        except Exception:  # noqa: S110
            pass

## @brief Просмотрщик обычного текста и исходного кода.
#
# Особенности:
# - Определение кодировки через charset_normalizer.
# - Подсветка синтаксиса через pygments + QSyntaxHighlighter.
# - Чтение больших файлов по частям (оконное чтение).
class TextViewer(BaseViewer):
    mime_types = (
        "text/plain", 
        "application/json", 
        "application/xml", 
        "text/xml", 
        "application/x-yaml", 
        "application/yaml", 
        "text/yaml", 
        "application/x-shellscript"
    )
    extensions = (
        ".txt", ".py", ".c", ".cpp", ".h", ".js", ".html", ".css", 
        ".json", ".yaml", ".yml", ".xml", ".toml", ".ini", ".log", 
        ".sh", ".bat", ".ps1", ".md", ".csv", ".tsv"
    )
    priority = 10
    
    WINDOW_READ_THRESHOLD = 256 * 1024

    def __init__(self):
        super().__init__()
        
        self._text_edit = QPlainTextEdit()
        self._text_edit.setReadOnly(True)
        self._text_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        
        # Pager UI for windowed reading
        self._pager_widget = QWidget()
        pager_layout = QHBoxLayout(self._pager_widget)
        pager_layout.setContentsMargins(0, 0, 0, 0)
        
        self._btn_prev = QPushButton("Пред. часть")
        self._btn_next = QPushButton("След. часть")
        self._lbl_status = QLabel("")
        
        self._btn_prev.clicked.connect(self._on_prev)
        self._btn_next.clicked.connect(self._on_next)
        
        pager_layout.addWidget(self._btn_prev)
        pager_layout.addWidget(self._lbl_status)
        pager_layout.addWidget(self._btn_next)
        
        self._pager_widget.setVisible(False)
        
        self._layout.addWidget(self._text_edit)
        self._layout.addWidget(self._pager_widget)
        
        self._file_path = None
        self._file_size = 0
        self._offset = 0
        self._highlighter = None

    def load(self, path: Path):
        self._file_path = path
        self._file_size = os.path.getsize(path)
        self._offset = 0
        self._load_chunk()
        
    def _load_chunk(self):
        if self._file_size == 0:
            self._text_edit.setPlainText("")
            self._pager_widget.setVisible(False)
            return

        with open(self._file_path, "rb") as f:
            f.seek(self._offset)
            raw_data = f.read(self.WINDOW_READ_THRESHOLD)
            
        if not raw_data:
            return
            
        res = charset_normalizer.from_bytes(raw_data).best()
        encoding = res.encoding if res else "utf-8"
        
        text = raw_data.decode(encoding, errors="replace")
        
        self._text_edit.setPlainText(text)
        
        if self._file_size > self.WINDOW_READ_THRESHOLD:
            self._pager_widget.setVisible(True)
            self._lbl_status.setText(f"Часть: {self._offset} - {self._offset + len(raw_data)} / {self._file_size}")
            self._btn_prev.setEnabled(self._offset > 0)
            self._btn_next.setEnabled(self._offset + len(raw_data) < self._file_size)
        else:
            self._pager_widget.setVisible(False)
            
        self._apply_highlighter()
        
    def _apply_highlighter(self):
        # Determine lexer
        from PyQt6.QtCore import QMimeDatabase
        mime_type = QMimeDatabase().mimeTypeForFile(str(self._file_path)).name()
        
        try:
            lexer = get_lexer_for_filename(self._file_path.name)
        except Exception:
            try:
                lexer = get_lexer_for_mimetype(mime_type)
            except Exception:
                lexer = TextLexer()
                
        # If still text lexer, try some explicit mapping for known configs
        if isinstance(lexer, TextLexer):
            name = self._file_path.name.lower()
            if name.endswith(('.ini', '.log', '.toml')):
                # Try getting it by name
                from pygments.lexers import get_lexer_by_name
                try:
                    if name.endswith(('.ini', '.toml')):
                        lexer = get_lexer_by_name("ini")
                    else:
                        lexer = TextLexer()
                except Exception:  # noqa: S110
                    pass
        
        # Remove old highlighter
        if self._highlighter:
            self._highlighter.setDocument(None)
            
        if not isinstance(lexer, TextLexer):
            self._highlighter = PygmentsHighlighter(self._text_edit.document(), lexer)
        else:
            self._highlighter = None

    def _on_prev(self):
        self._offset = max(0, self._offset - self.WINDOW_READ_THRESHOLD)
        self._load_chunk()
        
    def _on_next(self):
        self._offset = min(self._file_size, self._offset + self.WINDOW_READ_THRESHOLD)
        self._load_chunk()
