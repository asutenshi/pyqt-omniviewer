from pathlib import Path

from PyQt6.QtCore import QModelIndex, QSortFilterProxyModel, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QActionGroup, QFileSystemModel
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QPushButton,
    QToolButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from omniviewer.settings import AppSettings


## @brief Прокси-модель для дерева файлов.
#
# Обеспечивает фильтрацию по подстроке имени (без учета регистра)
# и гарантирует, что папки всегда отображаются сверху независимо от сортировки.
class TreeProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.folders_first = True
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        # We want to filter by the first column (Name)
        self.setFilterKeyColumn(0)

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        source_model = self.sourceModel()
        if isinstance(source_model, QFileSystemModel):
            index = source_model.index(source_row, self.filterKeyColumn(), source_parent)
            if source_model.isDir(index):
                return True
        return super().filterAcceptsRow(source_row, source_parent)

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        source_model = self.sourceModel()
        if not isinstance(source_model, QFileSystemModel):
            return super().lessThan(left, right)

        if self.folders_first:
            left_is_dir = source_model.isDir(left)
            right_is_dir = source_model.isDir(right)
            if left_is_dir and not right_is_dir:
                return self.sortOrder() == Qt.SortOrder.AscendingOrder
            if not left_is_dir and right_is_dir:
                return self.sortOrder() == Qt.SortOrder.DescendingOrder

        return super().lessThan(left, right)


## @brief Панель дерева файлов.
#
# Реализует файловый менеджер: навигация, фильтрация, сортировка.
class FileTreePanel(QWidget):
    # Signal emitted when a file is selected (for the viewer panel)
    file_selected = pyqtSignal(Path)

    def __init__(self, initial_path: Path, parent=None):
        super().__init__(parent)
        self.settings = AppSettings()
        self.current_path = initial_path
        self.history_back = []
        self.history_forward = []

        self.setup_ui()
        self.set_root_path(self.current_path, record_history=False)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # 1. Address bar and navigation buttons
        nav_layout = QHBoxLayout()
        
        self.btn_back = QToolButton()
        self.btn_back.setText("<-")
        self.btn_back.clicked.connect(self.go_back)
        nav_layout.addWidget(self.btn_back)

        self.btn_forward = QToolButton()
        self.btn_forward.setText("->")
        self.btn_forward.clicked.connect(self.go_forward)
        nav_layout.addWidget(self.btn_forward)

        self.btn_up = QToolButton()
        self.btn_up.setText("^")
        self.btn_up.clicked.connect(self.go_up)
        nav_layout.addWidget(self.btn_up)

        self.btn_home = QToolButton()
        self.btn_home.setText("~")
        self.btn_home.clicked.connect(self.go_home)
        nav_layout.addWidget(self.btn_home)

        self.address_bar = QLineEdit()
        self.address_bar.returnPressed.connect(self._on_address_entered)
        nav_layout.addWidget(self.address_bar)

        layout.addLayout(nav_layout)

        # 2. Filter and options
        filter_layout = QHBoxLayout()
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Filter by name...")
        self.filter_input.textChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.filter_input)

        self.btn_sort = QPushButton("Sort")
        self.btn_sort.setMenu(self._create_sort_menu())
        filter_layout.addWidget(self.btn_sort)

        layout.addLayout(filter_layout)

        # 3. Tree View
        self.tree_view = QTreeView()
        self.tree_view.setSortingEnabled(True)
        self.tree_view.setSelectionMode(QTreeView.SelectionMode.SingleSelection)
        self.tree_view.doubleClicked.connect(self._on_tree_double_clicked)
        self.tree_view.clicked.connect(self._on_tree_clicked)
        
        # Models
        self.source_model = QFileSystemModel()
        self.source_model.setReadOnly(True)
        # Watcher should be active. QFileSystemModel automatically uses QFileSystemWatcher.
        
        self.proxy_model = TreeProxyModel(self)
        self.proxy_model.setSourceModel(self.source_model)
        
        self.tree_view.setModel(self.proxy_model)
        self.tree_view.header().sortIndicatorChanged.connect(self._on_header_sort_changed)
        
        layout.addWidget(self.tree_view)
        self._apply_sorting()

    def _create_sort_menu(self) -> QMenu:
        menu = QMenu(self)
        
        # Columns
        col_group = QActionGroup(self)
        col_group.setExclusive(True)
        
        sf = self.settings.sort_field
        self.action_sort_name = QAction("Name", self, checkable=True, checked=(sf == "name"))
        self.action_sort_size = QAction("Size", self, checkable=True, checked=(sf == "size"))
        self.action_sort_type = QAction("Type", self, checkable=True, checked=(sf == "type"))
        self.action_sort_date = QAction("Date Modified", self, checkable=True, checked=(sf == "date"))
        
        for a in (self.action_sort_name, self.action_sort_size, self.action_sort_type, self.action_sort_date):
            col_group.addAction(a)
            menu.addAction(a)
            a.triggered.connect(self._apply_sorting)
            
        menu.addSeparator()
        
        # Order
        order_group = QActionGroup(self)
        order_group.setExclusive(True)
        
        sd = self.settings.sort_direction
        self.action_sort_asc = QAction("Ascending", self, checkable=True, checked=(sd == 0))
        self.action_sort_desc = QAction("Descending", self, checkable=True, checked=(sd == 1))
        
        for a in (self.action_sort_asc, self.action_sort_desc):
            order_group.addAction(a)
            menu.addAction(a)
            a.triggered.connect(self._apply_sorting)
            
        menu.addSeparator()
        
        # Folders first
        ft = self.settings.folders_on_top
        self.action_folders_first = QAction("Folders First", self, checkable=True, checked=ft)
        self.action_folders_first.triggered.connect(self._apply_sorting)
        menu.addAction(self.action_folders_first)

        return menu

    def _apply_sorting(self):
        col = 0
        field = "name"
        if self.action_sort_size.isChecked():
            col = 1
            field = "size"
        elif self.action_sort_type.isChecked():
            col = 2
            field = "type"
        elif self.action_sort_date.isChecked():
            col = 3
            field = "date"
        
        order = Qt.SortOrder.AscendingOrder
        direction = 0
        if self.action_sort_desc.isChecked():
            order = Qt.SortOrder.DescendingOrder
            direction = 1
            
        self.proxy_model.folders_first = self.action_folders_first.isChecked()
        
        self.settings.sort_field = field
        self.settings.sort_direction = direction
        self.settings.folders_on_top = self.proxy_model.folders_first
        
        self.tree_view.sortByColumn(col, order)

    def set_root_path(self, path: Path, record_history: bool = True):
        path_str = str(path)
        
        if record_history and self.current_path != path:
            self.history_back.append(self.current_path)
            self.history_forward.clear()
            self._update_nav_buttons()
            
        self.current_path = path
        self.address_bar.setText(path_str)
        
        idx = self.source_model.setRootPath(path_str)
        proxy_idx = self.proxy_model.mapFromSource(idx)
        self.tree_view.setRootIndex(proxy_idx)

    def _update_nav_buttons(self):
        self.btn_back.setEnabled(bool(self.history_back))
        self.btn_forward.setEnabled(bool(self.history_forward))

    def go_back(self):
        if self.history_back:
            self.history_forward.append(self.current_path)
            prev = self.history_back.pop()
            self.set_root_path(prev, record_history=False)
            self._update_nav_buttons()

    def go_forward(self):
        if self.history_forward:
            self.history_back.append(self.current_path)
            nxt = self.history_forward.pop()
            self.set_root_path(nxt, record_history=False)
            self._update_nav_buttons()

    def go_up(self):
        parent = self.current_path.parent
        if parent != self.current_path:
            self.set_root_path(parent)

    def go_home(self):
        self.set_root_path(Path.home())

    def _on_address_entered(self):
        path = Path(self.address_bar.text())
        if path.exists() and path.is_dir():
            self.set_root_path(path)
        else:
            # Revert
            self.address_bar.setText(str(self.current_path))

    def _on_filter_changed(self, text: str):
        self.proxy_model.setFilterFixedString(text)

    def _on_tree_double_clicked(self, index: QModelIndex):
        source_index = self.proxy_model.mapToSource(index)
        if self.source_model.isDir(source_index):
            path = Path(self.source_model.filePath(source_index))
            self.set_root_path(path)

    def _on_tree_clicked(self, index: QModelIndex):
        source_index = self.proxy_model.mapToSource(index)
        if not self.source_model.isDir(source_index):
            path = Path(self.source_model.filePath(source_index))
            self.file_selected.emit(path)

    def _on_header_sort_changed(self, logicalIndex: int, order: Qt.SortOrder):
        field = "name"
        if logicalIndex == 0:
            self.action_sort_name.setChecked(True)
        elif logicalIndex == 1:
            self.action_sort_size.setChecked(True)
            field = "size"
        elif logicalIndex == 2:
            self.action_sort_type.setChecked(True)
            field = "type"
        elif logicalIndex == 3:
            self.action_sort_date.setChecked(True)
            field = "date"
        
        direction = 0
        if order == Qt.SortOrder.AscendingOrder:
            self.action_sort_asc.setChecked(True)
        else:
            self.action_sort_desc.setChecked(True)
            direction = 1
            
        self.proxy_model.folders_first = self.action_folders_first.isChecked()
        
        self.settings.sort_field = field
        self.settings.sort_direction = direction
        self.settings.folders_on_top = self.proxy_model.folders_first