import sys

import pytest
from PyQt6.QtWidgets import QApplication

from omniviewer.about_dialog import AboutDialog
from omniviewer.format_catalog import FORMAT_GROUPS


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_window_title(qapp):
    dialog = AboutDialog()
    assert dialog.windowTitle() == "О программе"


def test_lists_every_format_group(qapp):
    dialog = AboutDialog()
    assert dialog.formats_tree.topLevelItemCount() == len(FORMAT_GROUPS)
    titles = {
        dialog.formats_tree.topLevelItem(i).text(0)
        for i in range(dialog.formats_tree.topLevelItemCount())
    }
    assert titles == {g.title for g in FORMAT_GROUPS}
