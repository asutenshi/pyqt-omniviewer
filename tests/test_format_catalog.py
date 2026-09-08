import re
from pathlib import Path

from omniviewer.format_catalog import FORMAT_GROUPS, render_markdown_table
from omniviewer.registry import default_registry

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_every_registered_viewer_has_catalog_entry():
    """Каждый зарегистрированный просмотрщик покрыт хотя бы одной группой каталога."""
    catalog_viewers = {g.viewer for g in FORMAT_GROUPS}
    assert catalog_viewers == set(default_registry.registered_viewers)


def test_readme_table_matches_catalog():
    """Таблица форматов в README.md сгенерирована из того же каталога, что и About."""
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    m = re.search(
        r"<!-- format-table:start.*?-->\n(.*?)\n<!-- format-table:end -->",
        readme,
        re.DOTALL,
    )
    assert m, "Блок format-table не найден в README.md"
    assert m.group(1).strip() == render_markdown_table().strip()
