"""Диалог «О программе»: описание приложения + список поддерживаемых форматов."""

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from omniviewer.format_catalog import FORMAT_GROUPS

_DESCRIPTION = (
    "Двухпанельный десктоп-просмотрщик максимального числа типов файлов. "
    "Всё рендерится программно, без запуска сторонних приложений."
)


## @brief Диалог «О программе»: версия и список поддерживаемых форматов/групп.
#
# Список строится из :data:`omniviewer.format_catalog.FORMAT_GROUPS` — того же
# источника, что и таблица «Поддерживаемые форматы» в README.md, поэтому два
# списка не могут разойтись. Материал для демонстрации охвата форматов жюри.
class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("О программе")
        self.resize(560, 480)

        layout = QVBoxLayout(self)

        title = QLabel("<h2>OmniViewer</h2>")
        layout.addWidget(title)

        description = QLabel(_DESCRIPTION)
        description.setWordWrap(True)
        layout.addWidget(description)

        layout.addWidget(QLabel(f"<b>Поддерживаемые форматы ({len(FORMAT_GROUPS)} групп):</b>"))

        self.formats_tree = QTreeWidget()
        self.formats_tree.setHeaderLabels(["Группа", "Форматы"])
        self.formats_tree.setColumnCount(2)
        self.formats_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.formats_tree.header().setStretchLastSection(True)
        for group in FORMAT_GROUPS:
            item = QTreeWidgetItem([group.title, group.formats])
            item.setToolTip(1, group.formats)
            self.formats_tree.addTopLevelItem(item)
        layout.addWidget(self.formats_tree, stretch=1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
