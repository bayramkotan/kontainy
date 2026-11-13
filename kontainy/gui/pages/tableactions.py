"""
kontainy — what a table should answer when you talk to it

Eight pages carry a table and, between them, they had one context menu and
two double-click handlers. Everything else went: click the row, move the
mouse to the toolbar, find the button, click it. For the action people run
most — look at this container — that is three deliberate movements where
every other tool in this category takes one.

This is the layer that fixes it, and the rule it is built on is the one
this project keeps relearning: **the menu is built from the same actions
the toolbar uses.** A hand-written second list is how `--connection
(local)` shipped broken while the first copy was right there, and a right-
click menu that offers Start on a running container, or omits an action the
toolbar has, is the same bug wearing a different hat.

What every table gains:

* **Right-click** — every action the page can run on the row, in the
  engine's own words, with the destructive ones below a separator.
* **Double-click and Enter** — the default verb, which is whatever the
  page says is the obvious thing to do to that row.
* **Delete** — remove, through the same confirmation as the button.
* **Ctrl+C** — the row's name; with a modifier, the whole row as text.
* **F5** and **Ctrl+F** — refresh, and jump to the filter box.
* ⚠️ **A multi-row selection is never silently narrowed.** When a verb
  cannot apply to every selected row the menu says so instead of running
  it on the ones it fits: asking to remove four containers must not
  quietly remove three.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import QMenu

from ...core.providers.base import verb_of


class TableActions:
    """Mixin for a page with a table. Call `wire_table()` after building.

    The page supplies three things and gets the whole interaction layer:

        actions_for_rows(rows)  the actions for this selection
        run_action(action)      how this page runs one
        row_label(row)          what the row is called, for messages

    Everything else — the menu, the keys, the copying, the "that does not
    apply" message — is written once here.
    """

    #: The verb double-click and Enter run. Empty means "the first action".
    DEFAULT_VERB = ""
    #: What the Delete key runs. Empty switches the key off for that page.
    REMOVE_VERB = "remove"

    # --- the page fills these in -------------------------------------------
    def actions_for_rows(self, rows: list) -> list:
        raise NotImplementedError

    def run_action(self, action) -> None:
        raise NotImplementedError

    def row_label(self, row: dict) -> str:
        for key in ("name", "reference", "Names", "Name", "id"):
            if row.get(key):
                return str(row[key])
        return ""

    # --- wiring ------------------------------------------------------------
    def wire_table(self, table=None) -> None:
        table = table if table is not None else getattr(self, "table", None)
        if table is None:
            return
        self._wired_table = table
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(self._table_menu)
        table.doubleClicked.connect(lambda *_: self._run_default())

        def key(sequence, slot):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.setContext(Qt.WidgetWithChildrenShortcut)
            shortcut.activated.connect(slot)
            return shortcut

        key("Return", self._run_default)
        key("Enter", self._run_default)
        key(QKeySequence.Copy, self._copy_name)
        key("Ctrl+Shift+C", self._copy_row)
        key("F5", lambda: self.refresh())
        key("Ctrl+F", self._focus_filter)
        if self.REMOVE_VERB:
            key("Delete", lambda: self._run_verb(self.REMOVE_VERB))

    def _focus_filter(self) -> None:
        box = getattr(self, "search", None)
        if box is not None:
            box.setFocus()
            box.selectAll()

    # --- the selection -----------------------------------------------------
    def selected_rows(self) -> list:
        """Every selected row, in the order they appear.

        Read from the selection model rather than from `currentRow`, so a
        menu opened over a three-row selection acts on three rows. Falling
        back to the current row matters for right-click: Qt sets the
        current cell on press, and on an unselected row that is the only
        thing identifying what was clicked.
        """
        table = getattr(self, "_wired_table", None) or getattr(self, "table",
                                                               None)
        rows = getattr(self, "filtered", None)
        if table is None or rows is None:
            return []
        model = table.selectionModel()
        wanted = sorted({index.row() for index in model.selectedRows()}) \
            if model else []
        if not wanted and table.currentRow() >= 0:
            wanted = [table.currentRow()]
        return [rows[i] for i in wanted if 0 <= i < len(rows)]

    # --- the menu ----------------------------------------------------------
    def _table_menu(self, point) -> None:
        table = getattr(self, "_wired_table", None)
        if table is None:
            return
        menu = self.build_menu(self.selected_rows())
        if menu is not None:
            menu.exec(table.viewport().mapToGlobal(point))

    def build_menu(self, rows: list):
        """The menu for these rows, or None. Separated from showing it so
        the contents can be checked without a display and a mouse."""
        if not rows:
            return None

        menu = QMenu(self)
        plain, destructive = [], []
        for built in self.actions_for_rows(rows) or []:
            (destructive if built.destructive else plain).append(built)

        for built in plain:
            menu.addAction(self._menu_entry(menu, built, rows))
        if plain and destructive:
            menu.addSeparator()
        for built in destructive:
            menu.addAction(self._menu_entry(menu, built, rows))

        menu.addSeparator()
        label = self.row_label(rows[0])
        copy_one = QAction(f"\U0001f4cb  Copy “{label}”", menu)
        copy_one.triggered.connect(self._copy_name)
        menu.addAction(copy_one)
        copy_all = QAction("\U0001f4cb  Copy the whole row", menu)
        copy_all.setShortcut("Ctrl+Shift+C")
        copy_all.triggered.connect(self._copy_row)
        menu.addAction(copy_all)
        return menu

    def _menu_entry(self, menu, built, rows: list) -> QAction:
        """One menu row, carrying the command as its tooltip.

        The explanation is what the confirmation dialog shows, and it is
        the thing that makes kontainy worth using over the terminal — so
        it is on the menu as well, where it costs nothing to read before
        committing to the click.
        """
        entry = QAction(built.label, menu)
        if built.explanation:
            entry.setToolTip(built.explanation[:400])
            entry.setStatusTip(built.explanation.splitlines()[0][:160])
        entry.triggered.connect(lambda _checked=False, a=built:
                                self.run_action(a))
        return entry

    # --- what the keys do --------------------------------------------------
    def _run_default(self) -> None:
        rows = self.selected_rows()
        if not rows:
            return
        actions = self.actions_for_rows(rows) or []
        if not actions:
            return
        if self.DEFAULT_VERB:
            for built in actions:
                if verb_of(built.label) == self.DEFAULT_VERB:
                    self.run_action(built)
                    return
        # No default named, or the named one does not apply to this row:
        # the first action a provider offers is the one it considers
        # obvious, and running something destructive instead would be a
        # very expensive way to answer a double-click.
        first = actions[0]
        if not first.destructive:
            self.run_action(first)

    def _run_verb(self, verb: str) -> None:
        rows = self.selected_rows()
        if not rows:
            return
        for built in self.actions_for_rows(rows) or []:
            if verb_of(built.label) == verb:
                self.run_action(built)
                return
        # ⚠️ Said, not swallowed. A Delete key that does nothing visible
        # teaches people the keyboard is unreliable here, and a Delete key
        # that quietly acts on the subset it fits is far worse.
        noun = self.row_label(rows[0]) if len(rows) == 1 \
            else f"{len(rows)} selected rows"
        self.status.emit(f"{verb.capitalize()} does not apply to {noun}.")

    # --- copying -----------------------------------------------------------
    def _copy_name(self) -> None:
        rows = self.selected_rows()
        if not rows:
            return
        text = "\n".join(self.row_label(row) for row in rows)
        QGuiApplication.clipboard().setText(text)
        self.status.emit(f"Copied {text.splitlines()[0]}"
                         + (f" and {len(rows) - 1} more" if len(rows) > 1
                            else ""))

    def _copy_row(self) -> None:
        """The whole row, tab separated, so it pastes into a spreadsheet.

        What people actually do with a container table is paste it into a
        ticket or a message, and a screenshot of one is not searchable.
        """
        table = getattr(self, "_wired_table", None)
        rows = self.selected_rows()
        if table is None or not rows:
            return
        headers = [table.horizontalHeaderItem(c).text()
                   for c in range(table.columnCount())
                   if table.horizontalHeaderItem(c)]
        lines = ["\t".join(headers)]
        model = table.selectionModel()
        wanted = sorted({i.row() for i in model.selectedRows()}) \
            if model else []
        if not wanted and table.currentRow() >= 0:
            wanted = [table.currentRow()]
        for row in wanted:
            cells = [table.item(row, c).text() if table.item(row, c) else ""
                     for c in range(table.columnCount())]
            lines.append("\t".join(cells))
        QGuiApplication.clipboard().setText("\n".join(lines))
        self.status.emit(f"Copied {len(wanted)} row"
                         f"{'s' if len(wanted) != 1 else ''} as text")
