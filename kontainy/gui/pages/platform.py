"""
kontainy — platform page

Laid out like VenvStudio's Packages page. A bar across the top holds the
thing you are working ON — a dropdown of every context, connection, remote
or distribution, the active one selected — next to its version, an Open
Terminal button and a count. Beneath it, tabs hold what you can do with it.

One class renders every technology. Docker, Podman, Kubernetes, KVM/libvirt,
Incus, LXD and WSL each differ only in the provider handed to it, which is
why switching the active target, adding one, removing one and testing one
work the same way everywhere.

Tabs:
    <Targets>   every context / connection / remote, with add, remove,
                make-active and test
    <Objects>   containers / pods / VMs / instances on the active target
    Install     the tools for this technology, installable per distribution
    Settings    this technology's configuration keys and files
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from ...core import registry as reg
from ...core.catalog import ALL_SETTINGS
from ...core.terminal import describe, open_terminal
from ...utils.workers import CallableJob, run_job
from .base import Page


def _probe(provider) -> dict:
    """Everything the page needs, gathered off the GUI thread."""
    available = provider.available()
    targets = provider.targets() if available else []
    active = next((t for t in targets if t.active), None)
    return {
        "available": available,
        "version": provider.version() if available else "",
        "targets": targets,
        "active": active,
        "objects": provider.objects(active) if available else None,
        "warning": provider.warning() if available else "",
    }


class AddTargetDialog(QDialog):
    """A form built from the provider's add_fields()."""

    def __init__(self, provider, parent=None):
        super().__init__(parent)
        self.provider = provider
        self.setWindowTitle(f"Add {provider.target_noun.lower()} "
                            f"\u2014 {provider.name}")
        self.resize(560, 0)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.inputs = {}
        for field in provider.add_fields():
            box = QLineEdit()
            box.setPlaceholderText(field.placeholder)
            if field.hint:
                box.setToolTip(field.hint)
            label = field.label + ("" if field.required else " (optional)")
            form.addRow(label, box)
            if field.hint:
                hint = QLabel(field.hint)
                hint.setWordWrap(True)
                hint.setStyleSheet("color: gray;")
                form.addRow("", hint)
            self.inputs[field.key] = (field, box)
        layout.addLayout(form)
        self.error = QLabel()
        self.error.setStyleSheet("color: #f38ba8;")
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept(self):
        missing = [f.label for f, box in self.inputs.values()
                   if f.required and not box.text().strip()]
        if missing:
            self.error.setText("Required: " + ", ".join(missing))
            return
        self.accept()

    def values(self) -> dict:
        return {key: box.text().strip()
                for key, (_f, box) in self.inputs.items()}


class PlatformPage(Page):
    """Subclassed per provider by make_platform_page()."""

    PROVIDER = None
    open_setting = Signal(str)

    # --- construction ------------------------------------------------------
    def build(self) -> None:
        self.state = None
        self._filling = False
        provider = self.PROVIDER

        # The page's own title row is replaced by the bar below, the way
        # VenvStudio puts the environment selector where a title would be.
        self.header.hide()
        if hasattr(self, "subheader"):
            self.subheader.hide()

        # --- top bar ---
        bar = QHBoxLayout()
        bar.setSpacing(12)
        self.name_label = QLabel(f"{provider.icon}  {provider.target_noun}:")
        self.name_label.setObjectName("platformName")
        bar.addWidget(self.name_label)

        self.selector = QComboBox()
        self.selector.setMinimumWidth(280)
        self.selector.setToolTip(
            f"The active {provider.target_noun.lower()}. Choosing another "
            f"shows the command that switches to it before anything runs.")
        self.selector.currentIndexChanged.connect(self._selector_changed)
        bar.addWidget(self.selector)

        self.version_label = QLabel("")
        self.version_label.setObjectName("platformVersion")
        bar.addWidget(self.version_label)

        self.terminal_btn = QPushButton(">_  Open Terminal")
        self.terminal_btn.setCursor(Qt.PointingHandCursor)
        self.terminal_btn.setToolTip(
            "Opens a terminal already pointed at the selected target, "
            "without changing anything global.")
        self.terminal_btn.clicked.connect(self._open_terminal)
        bar.addWidget(self.terminal_btn)

        self.count_label = QLabel("")
        bar.addWidget(self.count_label)
        bar.addStretch()

        self.refresh_btn = QPushButton("\U0001f501")
        self.refresh_btn.setObjectName("secondary")
        self.refresh_btn.setToolTip("Re-read everything")
        self.refresh_btn.setFixedWidth(44)
        self.refresh_btn.clicked.connect(self.refresh)
        bar.addWidget(self.refresh_btn)
        self.toolbar.addLayout(bar)

        # --- info line under the bar ---
        self.info_label = QLabel("")
        self.info_label.setWordWrap(True)
        self.info_label.setTextFormat(Qt.RichText)
        self.body.addWidget(self.info_label)

        # --- tabs ---
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_targets_tab(),
                         f"\U0001f3af  {provider.target_noun_plural}")
        self.tabs.addTab(self._build_objects_tab(),
                         f"\U0001f4e6  {provider.object_noun_plural}")
        self.install_tab = self._build_install_tab()
        self.tabs.addTab(self.install_tab, "\U0001f4e5  Install")
        self.tabs.addTab(self._build_settings_tab(), "\u2699  Settings")
        self.body.addWidget(self.tabs, 1)

    def _table(self, headers: list) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setStretchLastSection(True)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        return table

    def _build_targets_tab(self) -> QWidget:
        provider = self.PROVIDER
        tab = QWidget()
        layout = QVBoxLayout(tab)
        summary = QLabel(provider.summary)
        summary.setWordWrap(True)
        layout.addWidget(summary)

        self.targets_table = self._table(
            ["", provider.target_noun, "Address", "Detail"])
        self.targets_table.doubleClicked.connect(self._activate_selected)
        layout.addWidget(self.targets_table, 1)

        row = QHBoxLayout()
        for text, handler, kind in (
                ("\u2714  Make active", self._activate_selected, "primary"),
                (f"\u2795  Add {provider.target_noun.lower()}\u2026",
                 self._add, "secondary"),
                ("\U0001f50e  Test", self._test_selected, "secondary"),
                ("\U0001f5d1  Remove", self._remove_selected, "danger")):
            button = QPushButton(text)
            button.setCursor(Qt.PointingHandCursor)
            if kind != "primary":
                button.setObjectName(kind)
            button.clicked.connect(handler)
            row.addWidget(button)
        row.addStretch()
        layout.addLayout(row)
        return tab

    def _build_objects_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.objects_note = QLabel("")
        self.objects_note.setWordWrap(True)
        layout.addWidget(self.objects_note)
        self.objects_table = self._table(["\u2014"])
        layout.addWidget(self.objects_table, 1)
        return tab

    def _build_install_tab(self) -> QWidget:
        from .tools import embedded_tools
        self.tools_panel = embedded_tools(self.PROVIDER.tool_ids,
                                          self.PROVIDER.id)
        self.tools_panel.status.connect(self.status.emit)
        return self.tools_panel

    def _build_settings_tab(self) -> QWidget:
        provider = self.PROVIDER
        tab = QWidget()
        layout = QVBoxLayout(tab)
        settings = [s for s in ALL_SETTINGS
                    if provider.catalog_engine
                    and s.engine in (provider.catalog_engine, "both")]
        if settings:
            note = QLabel(
                f"{len(settings)} configuration keys apply to "
                f"{provider.name}. Double-click one to open it in the Config "
                f"Catalog, where its declared value, effective value and "
                f"override chain are shown and it can be edited.")
            note.setWordWrap(True)
            layout.addWidget(note)
            table = self._table(["Key", "Title", "Scope", "File"])
            for s in settings:
                r = table.rowCount()
                table.insertRow(r)
                for col, text in enumerate([s.key, s.title, s.privilege,
                                            s.file]):
                    table.setItem(r, col, QTableWidgetItem(str(text)))
            table.resizeColumnsToContents()
            table.doubleClicked.connect(
                lambda index, t=table: self.open_setting.emit(
                    t.item(index.row(), 0).text()))
            layout.addWidget(table, 1)
        else:
            files = []
            for tool_id in provider.tool_ids:
                tool = reg.by_id(tool_id)
                if tool:
                    files.extend(tool.config_files)
            text = (f"The Config Catalog does not cover {provider.name} "
                    f"yet \u2014 it is on the roadmap.")
            if files:
                text += ("<br><br><b>Configuration files:</b><br>"
                         + "<br>".join(f"<code>{f}</code>" for f in files))
            note = QLabel(text)
            note.setTextFormat(Qt.RichText)
            note.setWordWrap(True)
            note.setAlignment(Qt.AlignTop)
            layout.addWidget(note, 1)
        return tab

    # --- refresh -----------------------------------------------------------
    def on_shown(self) -> None:
        if self.state is None:
            self.refresh()

    def refresh(self) -> None:
        self.refresh_btn.setEnabled(False)
        self.busy.emit(True)
        self.status.emit(f"Reading {self.PROVIDER.name}\u2026")
        run_job(CallableJob(_probe, self.PROVIDER), self._fill, self._failed)

    def _failed(self, message: str) -> None:
        self.refresh_btn.setEnabled(True)
        self.busy.emit(False)
        self.status.emit(f"{self.PROVIDER.name}: {message}")

    def _fill(self, state: dict) -> None:
        self.state = state
        provider = self.PROVIDER
        c = self.colors()
        self.refresh_btn.setEnabled(True)
        self.busy.emit(False)

        available = state["available"]
        self.selector.setEnabled(available)
        self.terminal_btn.setEnabled(available)
        self.tabs.setTabEnabled(0, available)
        self.tabs.setTabEnabled(1, available)
        if not available:
            self.version_label.setText("not installed")
            self.count_label.setText("")
            self.info_label.setText(
                f"<span style='color:{c['warning']}'>\u26a0 "
                f"{provider.unavailable_reason()}</span>")
            self.tabs.setCurrentWidget(self.install_tab)
            self._filling = True
            self.selector.clear()
            self._filling = False
            self.status.emit(f"{provider.name} is not installed")
            return

        # --- selector ---
        self._filling = True
        self.selector.clear()
        active_index = 0
        for index, target in enumerate(state["targets"]):
            label = target.name + (f"  \u2014  {target.address}"
                                   if target.address else "")
            self.selector.addItem(label, target.name)
            if target.active:
                active_index = index
        self.selector.setCurrentIndex(active_index)
        self._filling = False

        self.version_label.setText(state["version"])
        active = state["active"]
        listing = state["objects"]
        count = len(listing.rows) if listing and not listing.error else 0
        self.count_label.setText(
            f"{count} {provider.object_noun_plural.lower()}")

        info = []
        if active:
            info.append(f"\U0001f4cd {active.address or active.name}")
            if active.detail:
                info.append(active.detail)
        line = " &nbsp;\u00b7&nbsp; ".join(info)
        if state["warning"]:
            line += (f"<br><span style='color:{c['danger']}'>\u26a0 "
                     f"{state['warning']}</span>")
        self.info_label.setText(line)

        self._fill_targets(state["targets"])
        self._fill_objects(listing)
        self.status.emit(
            f"{provider.name}: {len(state['targets'])} "
            f"{provider.target_noun_plural.lower()}, {count} "
            f"{provider.object_noun_plural.lower()}")

    def _fill_targets(self, targets: list) -> None:
        c = self.colors()
        table = self.targets_table
        table.setRowCount(0)
        for target in targets:
            r = table.rowCount()
            table.insertRow(r)
            cells = ["\u2705" if target.active else "", target.name,
                     target.address, target.detail]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if target.active:
                    item.setForeground(QColor(c["success"]))
                table.setItem(r, col, item)
        table.resizeColumnsToContents()

    def _fill_objects(self, listing) -> None:
        c = self.colors()
        table = self.objects_table
        table.setRowCount(0)
        if listing is None:
            return
        table.setColumnCount(len(listing.columns) or 1)
        table.setHorizontalHeaderLabels([col.title for col in listing.columns]
                                        or ["\u2014"])
        if listing.error:
            self.objects_note.setText(
                f"<span style='color:{c['danger']}'>{listing.error}</span>"
                f"<br><code>{listing.command}</code>")
            return
        self.objects_note.setText(f"<code>{listing.command}</code>")
        for row in listing.rows:
            r = table.rowCount()
            table.insertRow(r)
            for col, column in enumerate(listing.columns):
                table.setItem(r, col,
                              QTableWidgetItem(str(row.get(column.key, ""))))
        table.resizeColumnsToContents()
        if listing.command:
            self.show_command(listing.command, record=False)

    # --- actions -----------------------------------------------------------
    def _target(self, name: str):
        if not self.state:
            return None
        for target in self.state["targets"]:
            if target.name == name:
                return target
        return None

    def _selected_target(self):
        row = self.targets_table.currentRow()
        if row < 0 or not self.state or row >= len(self.state["targets"]):
            return None
        return self.state["targets"][row]

    def _selector_changed(self, index: int) -> None:
        if self._filling or index < 0:
            return
        target = self._target(self.selector.itemData(index))
        if target is None or target.active:
            return
        self._run(self.PROVIDER.activate(target))

    def _activate_selected(self, *_):
        target = self._selected_target()
        if target and not target.active:
            self._run(self.PROVIDER.activate(target))

    def _test_selected(self):
        target = self._selected_target() or (self.state or {}).get("active")
        if target:
            self._run(self.PROVIDER.test(target))

    def _remove_selected(self):
        target = self._selected_target()
        if target is None:
            return
        if not target.removable:
            self.status.emit(f"'{target.name}' is built in and cannot be "
                             f"removed")
            return
        self._run(self.PROVIDER.remove(target))

    def _add(self):
        dialog = AddTargetDialog(self.PROVIDER, self)
        if dialog.exec() == QDialog.Accepted:
            self._run(self.PROVIDER.add(dialog.values()))

    def _run(self, action) -> None:
        from ..dialogs.run_command import RunCommandDialog
        self.show_command(action.display(), note=action.id, record=False)
        dialog = RunCommandDialog(action, self)
        dialog.exec()
        # Re-read whatever happened, including a cancelled dialog: the
        # selector must always show the real active target, never the one
        # the user clicked but did not confirm.
        self.refresh()

    def _open_terminal(self):
        active = (self.state or {}).get("active")
        env = self.PROVIDER.terminal_env(active)
        self.show_command(describe(env), note="open-terminal", record=False)
        try:
            open_terminal(env)
            self.status.emit("Terminal opened")
        except (RuntimeError, OSError) as exc:
            self.status.emit(f"Could not open a terminal: {exc}")

    def apply_theme(self) -> None:
        super().apply_theme()
        c = self.colors()
        self.name_label.setStyleSheet(
            f"color: {c['accent']}; font-size: {c['fs_base'] + 4}px;"
            f" font-weight: bold;")
        self.version_label.setStyleSheet(
            f"color: {c['success']}; font-size: {c['fs_base'] + 3}px;"
            f" font-weight: bold;")
        self.selector.setStyleSheet(
            f"QComboBox {{ font-size: {c['fs_base'] + 3}px; padding: 6px 10px;"
            f" border: 2px solid {c['accent']}; border-radius: 8px; }}")
        for table in (getattr(self, "targets_table", None),
                      getattr(self, "objects_table", None)):
            if table is not None:
                table.setStyleSheet(
                    f"QTableWidget {{ font-size: {c['fs_base'] + 2}px; }}"
                    f"QTableWidget::item {{ padding: 7px 10px; }}")


def make_platform_page(provider) -> type:
    """A Page subclass bound to one provider, for the sidebar."""
    return type(f"{provider.id.title()}Page", (PlatformPage,), {
        "NAME": f"platform-{provider.id}",
        "TITLE": provider.name,
        "ICON": provider.icon,
        "SUBTITLE": provider.summary,
        "PROVIDER": provider,
    })
