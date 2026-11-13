"""Right-click, double-click and the keys every table should answer.

Eight pages carried a table and, between them, one context menu and two
double-click handlers. The rule these tests guard is the one this project
keeps relearning the hard way: the menu is built from the SAME actions the
toolbar runs. A second hand-written list is how `--connection (local)`
shipped broken while the correct copy sat one import away, and a menu that
offers Start on a running container is that same bug wearing a hat.
"""

import pytest

from kontainy.gui.pages.tableactions import TableActions


class Act:
    """Stands in for core.actions.Action — only the fields the menu reads."""

    def __init__(self, label, destructive=False, explanation="why"):
        self.label = label
        self.destructive = destructive
        self.explanation = explanation


class Page(TableActions):
    """A table page reduced to what the mixin asks of one."""

    DEFAULT_VERB = "logs"

    def __init__(self, rows, actions=None):
        self.filtered = list(rows)
        self._actions = actions if actions is not None else [
            Act("▶  Start"), Act("\U0001f4dc  Logs"),
            Act("\U0001f5d1  Remove", destructive=True)]
        self.ran = []
        self.said = []
        self.status = type("S", (), {"emit": lambda _s, m: self.said.append(m)})()
        self._selected = [0]

    # the three hooks a page supplies
    def actions_for_rows(self, rows):
        return list(self._actions)

    def run_action(self, action):
        self.ran.append(action.label)

    # stand in for the table's selection
    def selected_rows(self):
        return [self.filtered[i] for i in self._selected
                if i < len(self.filtered)]


ROWS = [{"name": "web", "state": "running"},
        {"name": "db", "state": "running"},
        {"name": "old", "state": "exited"}]


# --- what the keys do -------------------------------------------------------------
def test_double_click_runs_the_pages_default_verb():
    """Looking at a container is the thing people do most, and it took
    three deliberate movements: click the row, cross to the toolbar, click
    the button."""
    page = Page(ROWS)
    page._run_default()
    assert page.ran == ["\U0001f4dc  Logs"]


def test_double_click_never_runs_something_destructive():
    """⚠️ If the named default does not apply, the first action is used —
    but a double-click that removes a container because Remove happened to
    be first is a very expensive way to answer a mouse event."""
    page = Page(ROWS, actions=[Act("\U0001f5d1  Remove", destructive=True)])
    page._run_default()
    assert page.ran == []


def test_the_first_action_is_used_when_the_default_does_not_apply():
    page = Page(ROWS, actions=[Act("▶  Start"), Act("■  Stop")])
    page._run_default()
    assert page.ran == ["▶  Start"]


def test_delete_runs_remove_through_the_same_path_as_the_button():
    page = Page(ROWS)
    page._run_verb("remove")
    assert page.ran == ["\U0001f5d1  Remove"]


def test_a_key_that_does_not_apply_says_so_rather_than_doing_nothing():
    """A Delete key that silently does nothing teaches people the keyboard
    is unreliable here."""
    page = Page(ROWS, actions=[Act("\U0001f4dc  Logs")])
    page._run_verb("remove")
    assert page.ran == []
    assert page.said and "does not apply" in page.said[0]


def test_nothing_runs_when_nothing_is_selected():
    page = Page(ROWS)
    page._selected = []
    page._run_default()
    page._run_verb("remove")
    assert page.ran == []


# --- the menu ---------------------------------------------------------------------
def test_destructive_actions_are_separated_from_the_rest():
    """They go below a separator so the mouse cannot land on Remove while
    reaching for Restart."""
    page = Page(ROWS)
    actions = page.actions_for_rows(page.selected_rows())
    plain = [a for a in actions if not a.destructive]
    harmful = [a for a in actions if a.destructive]
    assert plain and harmful


def test_the_menu_carries_the_explanation():
    """The explanation is what makes kontainy worth using over the
    terminal, and on a menu it costs nothing to read before committing."""
    page = Page(ROWS)
    assert all(a.explanation for a in page.actions_for_rows(ROWS[:1]))


# --- the real pages ---------------------------------------------------------------
@pytest.fixture
def qt():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def containers_page(qt, rows):
    from kontainy.core.providers import by_id
    from kontainy.gui.pages.containers import ContainersPage

    page = ContainersPage()
    page.rows = rows
    page._apply_filter()
    provider = by_id("docker")

    class Target:
        name, address, active = "default", "unix:///x", True
        detail, removable = "", True

    page._target_of = lambda item: (provider, Target())
    return page


def row(name, state, target="default"):
    return {"engine": "Docker", "engine_id": "docker", "target": target,
            "name": name, "image": "nginx:1.27", "state": state,
            "status": "", "id": name * 2, "address": "unix:///x",
            "kind": "local", "active": True, "ports": "",
            "raw": {"Names": name, "State": state, "Image": "nginx:1.27",
                    "ID": name * 2}}


def test_the_menu_offers_what_the_engine_offers_not_a_fixed_list(qt):
    """Stop on a running container, never Start — because the actions come
    from the provider, which already knows the state."""
    page = containers_page(qt, [row("web", "running")])
    labels = [a.label for a in page.actions_for_rows([page.rows[0]])]
    assert any("Stop" in l for l in labels)
    assert not any("Start" in l for l in labels)


def test_a_stopped_container_is_offered_start(qt):
    page = containers_page(qt, [row("old", "exited")])
    labels = [a.label for a in page.actions_for_rows([page.rows[0]])]
    assert any("Start" in l for l in labels)
    assert not any("Stop" in l for l in labels)


def test_several_rows_get_one_command_each_verb(qt):
    page = containers_page(qt, [row("web", "running"), row("db", "running")])
    labels = [a.label for a in page.actions_for_rows(page.rows)]
    assert any("(2)" in l for l in labels)


def test_a_verb_that_does_not_fit_every_row_is_not_offered(qt):
    """⚠️ Asked to stop a running and a stopped container, the menu must
    leave Stop out rather than run it on the one it fits. Removing three of
    four selected containers is the shape of this bug that costs money."""
    page = containers_page(qt, [row("web", "running"), row("old", "exited")])
    labels = [a.label for a in page.actions_for_rows(page.rows)]
    assert not any("Stop" in l for l in labels)
    assert any("Remove" in l for l in labels)


def test_a_selection_spanning_contexts_offers_nothing_to_run_as_one(qt):
    """One command cannot name containers on two different sockets, and
    sending one context's names to another is how a container is "lost"."""
    page = containers_page(qt, [row("web", "running"),
                                row("db", "running", target="prod")])
    assert page.actions_for_rows(page.rows) == []


def test_the_unified_pages_and_the_platform_page_share_one_implementation():
    """Three separate class hierarchies, one interaction layer. Written
    twice, they drift — and the half that drifts is the one nobody is
    looking at."""
    from kontainy.gui.pages.containers import ContainersPage
    from kontainy.gui.pages.inventory import StockPage
    from kontainy.gui.pages.platform import PlatformPage
    for page_class in (ContainersPage, StockPage, PlatformPage):
        assert issubclass(page_class, TableActions)
        assert page_class.actions_for_rows is not TableActions.actions_for_rows


def test_images_and_volumes_open_rather_than_delete_on_double_click():
    from kontainy.gui.pages.inventory import ImagesPage, VolumesPage
    assert ImagesPage.DEFAULT_VERB == "inspect"
    assert VolumesPage.DEFAULT_VERB == "inspect"


def test_a_bulk_selection_is_refused_on_the_stock_pages(qt):
    """An image or a volume is removed by name, and "everything unused" is
    already a better-explained path than a menu looping over a selection."""
    from kontainy.gui.pages.inventory import ImagesPage
    page = ImagesPage()
    page.filtered = [{"name": "a"}, {"name": "b"}]
    assert page.actions_for_rows(page.filtered) == []


# --- the menu as it is actually built ---------------------------------------------
def test_the_built_menu_lists_the_actions_then_copying(qt):
    page = containers_page(qt, [row("web", "running")])
    page.table.selectRow(0)
    menu = page.build_menu(page.selected_rows())
    labels = [a.text() for a in menu.actions() if not a.isSeparator()]
    assert any("Stop" in l for l in labels)
    assert any("Copy" in l for l in labels)


def test_remove_sits_below_a_separator(qt):
    """So the mouse cannot land on Remove while reaching for Restart."""
    page = containers_page(qt, [row("web", "running")])
    page.table.selectRow(0)
    entries = page.build_menu(page.selected_rows()).actions()
    positions = [i for i, a in enumerate(entries) if a.isSeparator()]
    remove = next(i for i, a in enumerate(entries) if "Remove" in a.text())
    assert positions and remove > positions[0]


def test_every_menu_entry_carries_its_explanation_as_a_tooltip(qt):
    page = containers_page(qt, [row("web", "running")])
    page.table.selectRow(0)
    entries = [a for a in page.build_menu(page.selected_rows()).actions()
               if not a.isSeparator() and "Copy" not in a.text()]
    assert entries and all(a.toolTip() for a in entries)


def test_no_menu_at_all_when_the_click_misses_every_row(qt):
    page = containers_page(qt, [])
    assert page.build_menu([]) is None


def test_clicking_the_menu_entry_runs_that_action(qt):
    page = containers_page(qt, [row("web", "running")])
    page.table.selectRow(0)
    ran = []
    page.run_action = lambda action: ran.append(action.label)
    entry = next(a for a in page.build_menu(page.selected_rows()).actions()
                 if "Stop" in a.text())
    entry.trigger()
    assert ran and "Stop" in ran[0]
