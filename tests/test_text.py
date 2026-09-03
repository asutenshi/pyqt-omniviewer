from omniviewer.viewers.text import TextViewer


def test_text_viewer_basic(tmp_path):
    viewer = TextViewer()
    p = tmp_path / "test.txt"
    p.write_text("hello", encoding="utf-8")
    viewer.load(p)
    assert viewer._text_edit.toPlainText() == "hello"
