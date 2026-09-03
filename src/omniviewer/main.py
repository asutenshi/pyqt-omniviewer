import argparse
import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)


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
        self.setWindowTitle("OmniViewer")
        self.resize(800, 600)

        # Main splitter
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(self.splitter)

        # Viewer panel
        self.viewer_panel = QWidget()
        viewer_layout = QVBoxLayout(self.viewer_panel)
        viewer_layout.addWidget(QLabel("Viewer Area"))
        self.viewer_panel.setLayout(viewer_layout)

        # Tree panel
        self.tree_panel = QWidget()
        tree_layout = QVBoxLayout(self.tree_panel)
        tree_layout.addWidget(QLabel("Tree Area"))
        
        # Swap button
        self.swap_button = QPushButton("Swap Panels")
        self.swap_button.clicked.connect(self.swap_panels)
        tree_layout.addWidget(self.swap_button)
        self.tree_panel.setLayout(tree_layout)

        # Initial order: Viewer (Left), Tree (Right)
        # Based on SPEC: Слева — область просмотра, Справа — дерево файлов
        self.splitter.addWidget(self.viewer_panel)
        self.splitter.addWidget(self.tree_panel)
        
        # Set splitter sizes evenly
        self.splitter.setSizes([400, 400])

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage(f"Opened: {initial_path}")

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


def main():
    """Точка входа приложения."""
    parser = argparse.ArgumentParser(description="OmniViewer")
    parser.add_argument(
        "path",
        nargs="?",
        default=str(Path.home()),
        help="Path to file or directory to open"
    )
    args = parser.parse_args()

    app = QApplication(sys.argv)
    
    path = Path(args.path)
    
    window = MainWindow(path)
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
