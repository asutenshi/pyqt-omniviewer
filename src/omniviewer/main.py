import argparse
import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from omniviewer.properties import PropertyPanel
from omniviewer.registry import default_registry
from omniviewer.settings import AppSettings
from omniviewer.tree import FileTreePanel
from omniviewer.viewers.base import BaseViewer


## @brief Главное окно приложения.
#
# Реализует двухпанельный интерфейс с перетаскиваемым сплиттером.
# Слева располагается область просмотра, справа — дерево файлов.
class MainWindow(QMainWindow):
    """
    Главное окно приложения OmniViewer.
    Инициализируется с начальным путем (initial_path), который отображается в статус-баре.
    """

    def __init__(self, initial_path: Path):
        super().__init__()
        self.settings = AppSettings()
        
        self.setWindowTitle("OmniViewer")

        # Main splitter
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(self.splitter)

        # Viewer panel
        self.viewer_panel = QWidget()
        self.viewer_layout = QVBoxLayout(self.viewer_panel)
        self.viewer_layout.setContentsMargins(4, 4, 4, 4)
        self.viewer_layout.setSpacing(4)

        # Header above viewer area: file name and full path
        self.header_widget = QWidget()
        header_layout = QVBoxLayout(self.header_widget)
        header_layout.setContentsMargins(4, 4, 4, 4)
        header_layout.setSpacing(2)

        name_row = QHBoxLayout()
        name_title = QLabel("Файл:")
        name_title.setStyleSheet("font-weight: bold;")
        self.file_name_label = QLabel("Не выбран")
        self.file_name_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        name_row.addWidget(name_title)
        name_row.addWidget(self.file_name_label, stretch=1)
        header_layout.addLayout(name_row)

        path_row = QHBoxLayout()
        path_title = QLabel("Путь:")
        path_title.setStyleSheet("font-weight: bold;")
        self.file_path_label = QLabel("—")
        self.file_path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        path_row.addWidget(path_title)
        path_row.addWidget(self.file_path_label, stretch=1)
        header_layout.addLayout(path_row)

        # Separator line
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        header_layout.addWidget(line)

        self.viewer_layout.addWidget(self.header_widget)

        self.viewer_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.viewer_layout.addWidget(self.viewer_splitter, stretch=1)

        # Viewer container
        self.viewer_container = QWidget()
        self.viewer_container_layout = QVBoxLayout(self.viewer_container)
        self.viewer_container_layout.setContentsMargins(0, 0, 0, 0)
        self.placeholder_label = QLabel("Выберите файл в дереве для просмотра")
        self.placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.viewer_container_layout.addWidget(self.placeholder_label)

        self.viewer_splitter.addWidget(self.viewer_container)

        # Property Panel
        self.property_panel = PropertyPanel()
        self.viewer_splitter.addWidget(self.property_panel)
        self.viewer_splitter.setSizes([600, 200])

        self.current_viewer: BaseViewer | None = None

        # Tree panel
        self.tree_panel = QWidget()
        tree_layout = QVBoxLayout(self.tree_panel)

        self.tree_widget = FileTreePanel(initial_path)
        self.tree_widget.file_selected.connect(self.on_file_selected)
        tree_layout.addWidget(self.tree_widget)

        # Swap button
        self.swap_button = QPushButton("Swap Panels")
        self.swap_button.clicked.connect(self.swap_panels)
        tree_layout.addWidget(self.swap_button)
        self.tree_panel.setLayout(tree_layout)

        # Order based on settings
        if self.settings.tree_on_left:
            self.splitter.addWidget(self.tree_panel)
            self.splitter.addWidget(self.viewer_panel)
        else:
            self.splitter.addWidget(self.viewer_panel)
            self.splitter.addWidget(self.tree_panel)
        
        # Set splitter sizes evenly
        self.splitter.setSizes([400, 400])
        
        # Restore geometry
        geom = self.settings.window_geometry
        if not geom.isEmpty():
            self.restoreGeometry(geom)
        else:
            self.resize(800, 600)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage(f"Opened: {initial_path}")
        
        self.current_path = initial_path

    ## @brief Обработчик выбора файла в дереве.
    #
    # Отображает имя и полный путь над областью просмотра,
    # запрашивает подходящий просмотрщик из реестра и загружает файл.
    def on_file_selected(self, path: Path):
        """Отображает выбранный файл соответствующим просмотрщиком."""
        self.file_name_label.setText(path.name)
        self.file_path_label.setText(str(path))

        if self.current_viewer is not None:
            self.current_viewer.cancel()
            self.viewer_container_layout.removeWidget(self.current_viewer)
            self.current_viewer.deleteLater()
            self.current_viewer = None

        if self.placeholder_label is not None:
            self.viewer_container_layout.removeWidget(self.placeholder_label)
            self.placeholder_label.deleteLater()
            self.placeholder_label = None

        viewer = default_registry.viewer_for(path)
        try:
            viewer.load(path)
        except Exception:  # noqa: BLE001
            from omniviewer.viewers.fallback import FallbackViewer
            viewer = FallbackViewer()
            viewer.load(path)

        self.current_viewer = viewer
        self.viewer_container_layout.addWidget(viewer)
        
        self.property_panel.update_for_file(path)

    ## @brief Поменять панели местами.
    #
    # Меняет порядок панелей просмотра и дерева файлов в главном сплиттере.
    def swap_panels(self):
        """Переставляет панели в сплиттере местами."""
        idx0 = self.splitter.widget(0)

        if idx0 == self.viewer_panel:
            self.splitter.insertWidget(1, self.viewer_panel)
        else:
            self.splitter.insertWidget(1, self.tree_panel)
            
    def closeEvent(self, event):
        """Сохранение настроек при закрытии."""
        self.settings.window_geometry = self.saveGeometry()
        self.settings.tree_on_left = self.splitter.widget(0) == self.tree_panel
        if self.current_path:
            self.settings.last_opened_dir = self.current_path
        super().closeEvent(event)


def main():
    """Точка входа приложения."""
    parser = argparse.ArgumentParser(description="OmniViewer")
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Path to file or directory to open"
    )
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setOrganizationName("asutenshi")
    app.setApplicationName("OmniViewer")
    
    settings = AppSettings()
    
    if args.path is not None:
        path = Path(args.path)
    else:
        path = settings.last_opened_dir
        if not path.exists():
            path = Path.home()
    
    window = MainWindow(path)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
