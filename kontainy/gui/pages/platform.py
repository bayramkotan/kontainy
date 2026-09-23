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
    QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from ...core import actions as act
from ...core import registry as reg
from ...core import shellprofile
from ...core.providers.base import count_label as base_count
from ...core.providers.base import socket_kind
from ...core.catalog import ALL_SETTINGS
from ...core.terminal import describe, open_terminal
from ...utils.workers import CallableJob, run_job
from ..widgets import FlowLayout
from .base import Page


def _clear(layout) -> None:
    """Empty a layout at once.

    deleteLater() alone leaves the old buttons visible, at their old place,
    until the event loop gets round to deleting them — so the buttons for the
    previously selected row sat underneath the new ones. Hiding and
    detaching them first makes them disappear immediately.
    """
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()


def _probe(provider) -> dict:
    """Everything the page needs, gathered off the GUI thread."""
    from ...utils.config import log
    log().info("%s: reading %s\u2026", provider.name,
               provider.target_noun_plural.lower())
    available = provider.available()
    targets = provider.targets() if available else []
    active = next((t for t in targets if t.active), None)
    units = []
    # systemd exists only on Linux. On Windows every probe failed with
    # "command not found" and the Services tab would show nothing useful;
    # the probes also slowed shutdown enough to matter.
    services = provider.services if reg.OS_KIND == "linux" else []
    for unit, user, why in services:
        state = act._unit_property(unit, user, "is-active")
        enabled = act._unit_property(unit, user, "is-enabled")
        units.append(act.Unit(name=unit, user=user, state=state,
                              enabled=enabled, description=why))
    return {
        "available": available,
        "version": provider.version() if available else "",
        "targets": targets,
        "active": active,
        "objects": provider.objects(active) if available else None,
        "warning": provider.warning() if available else "",
        "resolution": provider.resolution() if available else [],
        "units": units,
        "linger": act.linger_state() if provider.needs_linger else None,
        "sections": ({s.id: s.listing(active) for s in provider.sections()}
                     if available else {}),
    }


class FieldsDialog(QDialog):
    """A form built from a list of Field()s."""

    def __init__(self, title: str, fields: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(560, 0)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.inputs = {}
        for field in fields:
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


def AddTargetDialog(provider, parent=None):
    return FieldsDialog(f"Add {provider.target_noun.lower()} \u2014 "
                        f"{provider.name}", provider.add_fields(), parent)


class PortsDialog(QDialog):
    """Edit a container's port mappings; applying recreates the container."""

    def __init__(self, name: str, bindings: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Ports \u2014 {name}")
        self.resize(640, 420)
        layout = QVBoxLayout(self)
        note = QLabel(
            "Docker and Podman cannot change the ports of an existing "
            "container. Applying these recreates it safely: the current one "
            "is kept, stopped and renamed, and restored automatically if the "
            "new one fails to start. Leave the host port empty to let the "
            "engine pick one.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["Host IP", "Host port", "Container port", "Protocol"])
        self.table.horizontalHeader().setStretchLastSection(True)
        for row in bindings:
            self._add_row(*row)
        layout.addWidget(self.table, 1)
        buttons_row = QHBoxLayout()
        add = QPushButton("\u2795  Add mapping")
        add.setObjectName("secondary")
        add.clicked.connect(lambda: self._add_row("", "", "", "tcp"))
        remove = QPushButton("\U0001f5d1  Remove selected")
        remove.setObjectName("secondary")
        remove.clicked.connect(
            lambda: self.table.removeRow(self.table.currentRow()))
        buttons_row.addWidget(add)
        buttons_row.addWidget(remove)
        buttons_row.addStretch()
        layout.addLayout(buttons_row)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.button(QDialogButtonBox.Ok).setText("Review and apply\u2026")
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        layout.addWidget(box)

    def _add_row(self, host_ip, host_port, container_port, proto):
        r = self.table.rowCount()
        self.table.insertRow(r)
        for col, text in enumerate([host_ip, host_port, container_port,
                                    proto or "tcp"]):
            self.table.setItem(r, col, QTableWidgetItem(str(text)))

    def bindings(self) -> list:
        out = []
        for r in range(self.table.rowCount()):
            cells = [(self.table.item(r, c).text().strip()
                      if self.table.item(r, c) else "") for c in range(4)]
            if cells[2]:
                out.append((cells[0], cells[1], cells[2], cells[3] or "tcp"))
        return out


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
        # Name and dropdown stay together; every other piece may move to a
        # second line. As one QHBoxLayout the bar set the page's width, and
        # with Windows' wider fonts that overflowed.
        head = QWidget()
        bar = QHBoxLayout(head)
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(12)
        self.name_label = QLabel(f"{provider.icon}  {provider.target_noun}:")
        self.name_label.setObjectName("platformName")
        bar.addWidget(self.name_label)

        self.selector = QComboBox()
        self.selector.setMinimumWidth(220)
        self.selector.setToolTip(
            f"The active {provider.target_noun.lower()}. Choosing another "
            f"shows the command that switches to it before anything runs.")
        self.selector.currentIndexChanged.connect(self._selector_changed)
        bar.addWidget(self.selector)
        self.toolbar.addWidget(head)

        self.version_label = QLabel("")
        self.version_label.setObjectName("platformVersion")
        self.toolbar.addWidget(self.version_label)

        self.terminal_btn = QPushButton(">_  Open Terminal")
        self.terminal_btn.setCursor(Qt.PointingHandCursor)
        self.terminal_btn.setToolTip(
            "Opens a terminal already pointed at the selected target, "
            "without changing anything global.")
        self.terminal_btn.clicked.connect(self._open_terminal)
        self.toolbar.addWidget(self.terminal_btn)

        self.count_label = QLabel("")
        self.toolbar.addWidget(self.count_label)

        # Short one-line labels in a horizontal bar stay on one line. A
        # wrapping label gets a narrower preferred width than its text, so
        # "Docker version 29.8.1" broke onto two lines with space to spare.
        for label in (self.name_label, self.version_label, self.count_label):
            label.setProperty("noWrap", True)

        self.refresh_btn = QPushButton("\u21bb")
        self.refresh_btn.setObjectName("secondary")
        self.refresh_btn.setToolTip("Re-read everything")
        self.refresh_btn.setFixedWidth(44)
        self.refresh_btn.clicked.connect(self.refresh)
        self.toolbar.addWidget(self.refresh_btn)

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
        self.section_widgets = {}
        for section in provider.sections():
            self.tabs.addTab(self._build_section_tab(section),
                             f"{section.icon}  {section.title}")
        self.install_tab = self._build_install_tab()
        self.tabs.addTab(self.install_tab, "\U0001f4e5  Install")
        if provider.services and reg.OS_KIND == "linux":
            self.tabs.addTab(self._build_services_tab(), "\U0001f6e0  Services")
        if shellprofile.VARIABLES.get(provider.id):
            self.tabs.addTab(self._build_shell_tab(), "\U0001f41a  Shell")
        self.tabs.addTab(self._build_settings_tab(), "\u2699  Settings")
        # A tab's contents are read the first time it is opened. Without
        # this the Install tab stayed empty on every platform: an embedded
        # panel never receives on_shown, which is what refreshes a page.
        self.tabs.currentChanged.connect(self._tab_opened)
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
            ["", provider.target_noun, "Address", "Kind", "Detail"])
        self.targets_table.doubleClicked.connect(self._activate_selected)
        layout.addWidget(self.targets_table, 1)

        # How the CLI actually picks its target. For Docker this is the part
        # people never see: a set DOCKER_HOST beats every context silently.
        self.resolution_label = QLabel(
            f"<b>How the {provider.binary} command picks its target</b> "
            f"\u2014 highest priority first; the marked layer wins")
        self.resolution_label.setTextFormat(Qt.RichText)
        self.resolution_table = self._table(["Layer", "Value", "Wins"])
        self.resolution_table.setMaximumHeight(170)
        self.resolution_label.hide()
        self.resolution_table.hide()
        layout.addWidget(self.resolution_label)
        layout.addWidget(self.resolution_table)

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
        self.objects_table.currentCellChanged.connect(self._object_selected)
        layout.addWidget(self.objects_table, 1)
        self.object_buttons = FlowLayout()
        layout.addLayout(self.object_buttons)
        self.bulk_buttons = FlowLayout()
        layout.addLayout(self.bulk_buttons)
        return tab

    def _build_install_tab(self) -> QWidget:
        from .tools import embedded_tools
        host = self.PROVIDER.host()
        self.tools_panel = embedded_tools(
            self.PROVIDER.tool_ids, self.PROVIDER.id,
            host if host is not None and host.is_wsl else None)
        self.tools_panel.status.connect(self.status.emit)
        return self.tools_panel

    def _build_services_tab(self) -> QWidget:
        provider = self.PROVIDER
        tab = QWidget()
        layout = QVBoxLayout(tab)
        note = QLabel(
            f"The system services {provider.name} depends on. Select one to "
            f"start, stop, enable at boot or read its status \u2014 every "
            f"command is shown before it runs.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.units_table = self._table(
            ["Unit", "Scope", "State", "At boot", "What it does"])
        self.units_table.currentCellChanged.connect(self._unit_selected)
        layout.addWidget(self.units_table, 1)
        self.unit_buttons = FlowLayout()
        layout.addLayout(self.unit_buttons)
        self.linger_row = FlowLayout()
        layout.addLayout(self.linger_row)
        return tab

    def _fill_units(self, units: list, linger) -> None:
        if not hasattr(self, "units_table"):
            return
        c = self.colors()
        table = self.units_table
        table.setRowCount(0)
        for unit in units:
            r = table.rowCount()
            table.insertRow(r)
            cells = [unit.name, unit.scope_label, unit.state, unit.enabled,
                     unit.description]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(str(text))
                if col == 2:
                    item.setForeground(QColor(
                        c["success"] if unit.active else c["fg_muted"]))
                table.setItem(r, col, item)
        table.resizeColumnsToContents()
        if units:
            table.selectRow(0)

        _clear(self.linger_row)
        if linger is not None:
            label = QLabel(
                f"Linger: <b style='color:"
                f"{c['success'] if linger else c['warning']}'>"
                f"{'enabled' if linger else 'disabled'}</b> \u2014 "
                + ("your user services keep running after logout and "
                   "start at boot." if linger else
                   "rootless containers stop when you log out and do not "
                   "come back after a reboot."))
            label.setTextFormat(Qt.RichText)
            label.setWordWrap(True)
            self.linger_row.addWidget(label, 1)
            action = act.linger_action(bool(linger))
            button = QPushButton(action.label)
            button.setCursor(Qt.PointingHandCursor)
            if action.destructive:
                button.setObjectName("danger")
            button.clicked.connect(lambda _=False, a=action: self._run(a))
            self.linger_row.addWidget(button)

    def _unit_selected(self, row, *_):
        units = (self.state or {}).get("units") or []
        _clear(self.unit_buttons)
        if row < 0 or row >= len(units):
            return
        for action in act.actions_for_unit(units[row]):
            button = QPushButton(action.label)
            button.setCursor(Qt.PointingHandCursor)
            if action.destructive:
                button.setObjectName("danger")
            elif action.scope != act.USER:
                button.setObjectName("secondary")
            button.clicked.connect(lambda _=False, a=action: self._run(a))
            self.unit_buttons.addWidget(button)
        self.unit_buttons.addStretch()

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

    def _tab_opened(self, index: int) -> None:
        widget = self.tabs.widget(index)
        if widget is self.install_tab and not getattr(widget, "rows", None):
            widget.refresh()

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

        self._fill_units(state.get("units") or [], state.get("linger"))
        self._fill_shell()

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
            # Only the name: an address in the dropdown got cut off mid-path.
            # The full address is on the line underneath and in the tooltip.
            self.selector.addItem(target.name, target.name)
            self.selector.setItemData(index, target.address, Qt.ToolTipRole)
            if target.active:
                active_index = index
        self.selector.setCurrentIndex(active_index)
        self._filling = False

        self.version_label.setText(state["version"])
        active = state["active"]
        listing = state["objects"]
        count = len(listing.rows) if listing and not listing.error else 0
        self.count_label.setText(
            base_count(count, provider.object_noun_plural))

        info = []
        host = provider.host()
        if host is not None and host.is_wsl:
            info.append(f"\U0001fa9f <b>{host.label}</b>")
        if active:
            info.append(f"\U0001f4cd {active.address or active.name}")
            kind = socket_kind(active.address)
            if kind:
                colour = c["warning"] if "root" in kind else c["accent"]
                info.append(f"<b style='color:{colour}'>{kind}</b>")
            if active.detail:
                info.append(active.detail)
        line = " &nbsp;\u00b7&nbsp; ".join(info)
        if state["warning"]:
            line += (f"<br><span style='color:{c['danger']}'>\u26a0 "
                     f"{state['warning']}</span>")
        self.info_label.setText(line)

        self._fill_targets(state["targets"])
        self._fill_sections(state.get("sections") or {})
        self._fill_resolution(state.get("resolution") or [])
        self._fill_objects(listing)
        summary = (f"{provider.name}: {len(state['targets'])} "
                   f"{provider.target_noun_plural.lower()}, {count} "
                   f"{provider.object_noun_plural.lower()}")
        self.status.emit(summary)
        from ...utils.config import log
        log().info("%s", summary)

    def _fill_targets(self, targets: list) -> None:
        c = self.colors()
        table = self.targets_table
        table.setRowCount(0)
        for target in targets:
            r = table.rowCount()
            table.insertRow(r)
            cells = ["\u2705" if target.active else "", target.name,
                     target.address, socket_kind(target.address),
                     target.detail]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if target.active:
                    item.setForeground(QColor(c["success"]))
                table.setItem(r, col, item)
        table.resizeColumnsToContents()

    def _fill_resolution(self, rows: list) -> None:
        visible = bool(rows)
        self.resolution_label.setVisible(visible)
        self.resolution_table.setVisible(visible)
        if not visible:
            return
        c = self.colors()
        table = self.resolution_table
        table.setRowCount(0)
        for layer, value, wins in rows:
            r = table.rowCount()
            table.insertRow(r)
            for col, text in enumerate([layer, value or "\u2014",
                                        "\u2705" if wins else ""]):
                item = QTableWidgetItem(text)
                if wins:
                    item.setForeground(QColor(c["success"]))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
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
        self._fill_bulk(listing.rows)
        for row in listing.rows:
            r = table.rowCount()
            table.insertRow(r)
            for col, column in enumerate(listing.columns):
                table.setItem(r, col,
                              QTableWidgetItem(str(row.get(column.key, ""))))
        table.resizeColumnsToContents()
        if listing.command:
            self.show_command(listing.command, record=False)


    # --- objects: per-object and bulk actions -------------------------------
    def _button(self, action, layout) -> None:
        button = QPushButton(action.label)
        button.setCursor(Qt.PointingHandCursor)
        if action.destructive:
            button.setObjectName("danger")
        elif action.scope != act.USER:
            button.setObjectName("secondary")
        button.clicked.connect(lambda _=False, a=action: self._run(a))
        layout.addWidget(button)

    def _object_row(self):
        listing = (self.state or {}).get("objects")
        row = self.objects_table.currentRow()
        if not listing or listing.error or row < 0 or row >= len(listing.rows):
            return None
        return listing.rows[row]

    def _object_selected(self, *_):
        _clear(self.object_buttons)
        row = self._object_row()
        if row is None:
            return
        active = (self.state or {}).get("active")
        label = QLabel(f"<b>{row.get(self.PROVIDER.object_key, '')}</b>")
        label.setTextFormat(Qt.RichText)
        self.object_buttons.addWidget(label)
        for action in self.PROVIDER.object_actions(active, row):
            self._button(action, self.object_buttons)
        if self.PROVIDER.can_edit_ports():
            ports = QPushButton("\U0001f50c  Ports\u2026")
            ports.setObjectName("secondary")
            ports.setCursor(Qt.PointingHandCursor)
            ports.clicked.connect(lambda: self._edit_ports(row))
            self.object_buttons.addWidget(ports)
        self.object_buttons.addStretch()

    def _fill_bulk(self, rows: list) -> None:
        _clear(self.bulk_buttons)
        active = (self.state or {}).get("active")
        actions = self.PROVIDER.bulk_actions(active, rows)
        if not actions:
            return
        label = QLabel("All on this target:")
        self.bulk_buttons.addWidget(label)
        for action in actions:
            self._button(action, self.bulk_buttons)
        self.bulk_buttons.addStretch()

    def _edit_ports(self, row: dict) -> None:
        provider = self.PROVIDER
        active = (self.state or {}).get("active")
        name = row.get(provider.object_key, "")
        bindings, _info = provider.inspect_ports(active, name)
        dialog = PortsDialog(name, bindings, self)
        if dialog.exec() == QDialog.Accepted:
            self._run(provider.recreate_with_ports(active, name,
                                                   dialog.bindings()))


    # --- extra sections (KVM networks, ...) ----------------------------------
    def _build_section_tab(self, section) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        summary = QLabel(section.summary)
        summary.setWordWrap(True)
        layout.addWidget(summary)
        note = QLabel("")
        note.setWordWrap(True)
        note.setTextFormat(Qt.RichText)
        layout.addWidget(note)
        table = self._table(["\u2014"])
        layout.addWidget(table, 1)
        row_buttons = FlowLayout()
        layout.addLayout(row_buttons)
        bottom = QHBoxLayout()
        if section.create is not None:
            create = QPushButton(f"\u2795  New {section.noun.lower()}\u2026")
            create.setCursor(Qt.PointingHandCursor)
            create.clicked.connect(lambda _=False, s=section: self._create_in(s))
            bottom.addWidget(create)
        bottom.addStretch()
        layout.addLayout(bottom)
        widgets = {"section": section, "table": table, "note": note,
                   "buttons": row_buttons, "rows": []}
        table.currentCellChanged.connect(
            lambda row, *_rest, w=widgets: self._section_selected(w, row))
        self.section_widgets[section.id] = widgets
        return tab

    def _fill_sections(self, listings: dict) -> None:
        c = self.colors()
        for sid, widgets in self.section_widgets.items():
            listing = listings.get(sid)
            table = widgets["table"]
            table.setRowCount(0)
            _clear(widgets["buttons"])
            if listing is None:
                continue
            table.setColumnCount(len(listing.columns) or 1)
            table.setHorizontalHeaderLabels(
                [col.title for col in listing.columns] or ["\u2014"])
            widgets["rows"] = [] if listing.error else listing.rows
            if listing.error:
                widgets["note"].setText(
                    f"<span style='color:{c['danger']}'>{listing.error}</span>"
                    f"<br><code>{listing.command}</code>")
                continue
            widgets["note"].setText(f"<code>{listing.command}</code>")
            for row in listing.rows:
                r = table.rowCount()
                table.insertRow(r)
                for col, column in enumerate(listing.columns):
                    table.setItem(r, col, QTableWidgetItem(
                        str(row.get(column.key, ""))))
            table.resizeColumnsToContents()

    def _section_selected(self, widgets: dict, row: int) -> None:
        _clear(widgets["buttons"])
        rows = widgets["rows"]
        if row < 0 or row >= len(rows):
            return
        section = widgets["section"]
        active = (self.state or {}).get("active")
        label = QLabel(f"<b>{rows[row].get(section.key, '')}</b>")
        label.setTextFormat(Qt.RichText)
        widgets["buttons"].addWidget(label)
        for action in section.row_actions(active, rows[row]):
            self._button(action, widgets["buttons"])
        widgets["buttons"].addStretch()

    def _create_in(self, section) -> None:
        dialog = FieldsDialog(f"New {section.noun.lower()} \u2014 "
                              f"{self.PROVIDER.name}", section.create_fields,
                              self)
        if dialog.exec() == QDialog.Accepted:
            active = (self.state or {}).get("active")
            self._run(section.create(active, dialog.values()))

    # --- shell profile ---------------------------------------------------------
    def _build_shell_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        path = shellprofile.profile_path()
        note = QLabel(
            f"Environment variables in your shell profile "
            f"(<code>{path}</code>) pin new terminals to a target without "
            f"changing the global choice. kontainy writes only inside its own "
            f"marked block and never edits a line you wrote; your own lines "
            f"are shown and can be commented out, with a backup. Changes take "
            f"effect in new shells.")
        note.setTextFormat(Qt.RichText)
        note.setWordWrap(True)
        layout.addWidget(note)
        self.shell_table = self._table(
            ["Variable", "In kontainy's block", "Set elsewhere",
             "In kontainy's environment"])
        self.shell_table.currentCellChanged.connect(self._shell_selected)
        layout.addWidget(self.shell_table, 1)
        self.shell_why = QLabel("")
        self.shell_why.setWordWrap(True)
        layout.addWidget(self.shell_why)
        self.shell_buttons = FlowLayout()
        layout.addLayout(self.shell_buttons)
        return tab

    def _fill_shell(self) -> None:
        if not hasattr(self, "shell_table"):
            return
        self.shell_entries = shellprofile.read(self.PROVIDER.id)
        table = self.shell_table
        table.setRowCount(0)
        for entry in self.shell_entries:
            r = table.rowCount()
            table.insertRow(r)
            elsewhere = "; ".join(f"line {n}: {text}"
                                  for n, text in entry.foreign) or "\u2014"
            for col, text in enumerate([entry.name,
                                        entry.managed_value or "\u2014",
                                        elsewhere,
                                        entry.current or "\u2014"]):
                table.setItem(r, col, QTableWidgetItem(text))
        table.resizeColumnsToContents()
        if self.shell_entries:
            table.selectRow(0)

    def _suggested_value(self, name: str) -> str:
        active = (self.state or {}).get("active")
        if not active:
            return ""
        if name in ("DOCKER_CONTEXT", "CONTAINER_CONNECTION"):
            return "" if active.name == "(local)" else active.name
        if name == "KUBECONFIG":
            return str(shellprofile.Path.home() / ".kube" / "config")
        return active.address

    def _shell_selected(self, row, *_):
        _clear(self.shell_buttons)
        entries = getattr(self, "shell_entries", [])
        if row < 0 or row >= len(entries):
            return
        entry = entries[row]
        why = dict(shellprofile.VARIABLES[self.PROVIDER.id]).get(entry.name, "")
        self.shell_why.setText(why)
        suggested = self._suggested_value(entry.name)
        if suggested:
            self._button(shellprofile.set_action(entry.name, suggested),
                         self.shell_buttons)
        custom = QPushButton("\u270e  Set another value\u2026")
        custom.setObjectName("secondary")
        custom.clicked.connect(lambda: self._shell_custom(entry.name))
        self.shell_buttons.addWidget(custom)
        if entry.managed_value:
            self._button(shellprofile.unset_action(entry.name),
                         self.shell_buttons)
        for number, text in entry.foreign:
            self._button(shellprofile.comment_action(entry.name, number, text),
                         self.shell_buttons)
        self.shell_buttons.addStretch()

    def _shell_custom(self, name: str) -> None:
        value, ok = QInputDialog.getText(
            self, name, f"Value for {name}:",
            text=self._suggested_value(name))
        if ok and value.strip():
            self._run(shellprofile.set_action(name, value.strip()))

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
        action = self.PROVIDER.prepare(action)
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
                      getattr(self, "objects_table", None),
                      getattr(self, "units_table", None),
                      getattr(self, "shell_table", None),
                      getattr(self, "resolution_table", None)):
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
