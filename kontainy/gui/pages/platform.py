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

        # The address is the other half of the answer: a context name says
        # nothing about which socket it reaches. It goes in as its own item
        # of the flow layout, NOT inside the name-and-dropdown block, so a
        # narrow window can move it to the next line. Putting it in that
        # block made every platform page 20 to 60 px too wide on Windows.
        socket_box = QWidget()
        socket_bar = QHBoxLayout(socket_box)
        socket_bar.setContentsMargins(0, 0, 0, 0)
        socket_bar.setSpacing(8)
        socket_label = QLabel(f"{provider.address_noun}:")
        socket_label.setProperty("noWrap", True)
        socket_bar.addWidget(socket_label)
        self.address_selector = QComboBox()
        # Wide enough for a real endpoint to be read in full:
        # npipe:////./pipe/dockerDesktopLinuxEngine, qemu+ssh://user@host/system.
        # It still shrinks in a narrow window, because the flow layout can
        # move it to the next line instead of widening the page.
        self.address_selector.setMinimumWidth(330)
        self.address_selector.setSizeAdjustPolicy(
            QComboBox.AdjustToContents)
        self.address_selector.setToolTip(
            "The endpoint behind the selected " +
            provider.target_noun.lower() + ".")
        self.address_selector.currentIndexChanged.connect(
            self._address_changed)
        socket_bar.addWidget(self.address_selector)
        self.socket_box = socket_box
        # Only where the address says something the name does not. Hyper-V
        # and VMware have one local host whose address is the words "this
        # computer"; a dropdown for that is furniture.
        socket_box.setVisible(bool(provider.address_noun))
        self.toolbar.addWidget(socket_box)

        self.activate_btn = QPushButton("\u2714  Activate")
        self.activate_btn.setCursor(Qt.PointingHandCursor)
        self.activate_btn.setToolTip(
            "Make the selected one active. The command is shown in the strip "
            "below and in the log \u2014 nothing pops up.")
        self.activate_btn.clicked.connect(self._activate_selected)
        self.toolbar.addWidget(self.activate_btn)

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
        # Several rows at once: stopping or removing four containers is one
        # request, not four clicks. Ctrl and Shift work as everywhere else.
        table.setSelectionMode(QAbstractItemView.ExtendedSelection)
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
        self.targets_table.doubleClicked.connect(self._activate_row)
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
                ("\u2714  Make active", self._activate_row, "primary"),
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
        self.objects_table.itemSelectionChanged.connect(self._object_selected)
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
        self.address_selector.clear()
        active_index = 0
        # One entry per ADDRESS, not per target: two contexts can point at
        # the same socket, and listing it twice invites a choice that means
        # nothing. Where several share one, their names are shown with it.
        by_address = {}
        for target in state["targets"]:
            by_address.setdefault(target.address or "\u2014", []).append(target)
        for address, owners in by_address.items():
            label = address
            if len(owners) > 1:
                label += f"   ({', '.join(t.name for t in owners)})"
            self.address_selector.addItem(label, owners[0].name)

        for index, target in enumerate(state["targets"]):
            # Only the name: an address in the dropdown got cut off mid-path.
            # The full address is on the line underneath and in the tooltip.
            self.selector.addItem(target.name, target.name)
            self.selector.setItemData(index, target.address, Qt.ToolTipRole)
            if target.active:
                active_index = index
        # Even where an address is meaningful in general, it is not worth a
        # dropdown when every target reports the same one.
        self.socket_box.setVisible(bool(self.PROVIDER.address_noun)
                                   and len(by_address) > 1)
        self.selector.setCurrentIndex(active_index)
        self._sync_address_to_selector()
        self._filling = False
        self._update_activate()

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
                    item.setFont(_bold(item.font()))
                table.setItem(r, col, item)
        table.resizeColumnsToContents()

    def _offer_to_start(self, listing) -> None:
        """Installed but not answering: offer the thing that starts it.

        Bayram, 2026-09-25: "Madem yüklü, o zaman çalıştırabilelim oradan."
        A page that reports `unreachable` and offers nothing to do about it
        is a dead end; the user already knows the daemon is off.
        """
        if not listing.error or not (self.state or {}).get("available"):
            return
        action = self.PROVIDER.start_engine()
        if action is None:
            return
        self._button(self.PROVIDER.prepare(action), self.object_buttons)
        hint = QLabel("\u2014 it is installed; this starts it")
        hint.setProperty("noWrap", True)
        self.object_buttons.addWidget(hint)
        self.object_buttons.addStretch()

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
            _clear(self.object_buttons)
            self._offer_to_start(listing)
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

    def _selected_object_rows(self) -> list:
        listing = (self.state or {}).get("objects")
        if not listing or listing.error:
            return []
        indexes = sorted({index.row() for index
                          in self.objects_table.selectionModel().selectedRows()})
        return [listing.rows[i] for i in indexes if i < len(listing.rows)]

    def _selection_buttons(self, rows: list) -> None:
        """One button per verb that applies to EVERY selected row.

        A verb that does not apply to all of them is left out rather than
        run on the ones it fits: asked to start four machines, kontainy
        either starts four or says why it cannot.
        """
        from ...core.providers.base import actions_for_selection, verb_of
        active = (self.state or {}).get("active")
        label = QLabel(f"<b>{len(rows)} selected</b>")
        label.setTextFormat(Qt.RichText)
        label.setProperty("noWrap", True)
        self.object_buttons.addWidget(label)
        verbs = []
        for candidate in self.PROVIDER.object_actions(active, rows[0]):
            verb = verb_of(candidate.label)
            if verb not in verbs:
                verbs.append(verb)
        added = 0
        for verb in verbs:
            action = actions_for_selection(self.PROVIDER, active, rows, verb)
            if action is not None:
                self._button(action, self.object_buttons)
                added += 1
        if not added:
            self.object_buttons.addWidget(QLabel(
                "The selected rows are in different states, so no single "
                "action applies to all of them."))
        self.object_buttons.addStretch()

    def _object_selected(self, *_):
        _clear(self.object_buttons)
        rows = self._selected_object_rows()
        if len(rows) > 1:
            self._selection_buttons(rows)
            return
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

    def _sync_address_to_selector(self) -> None:
        """Point the address dropdown at whatever the selected target uses."""
        target = self._target(self.selector.currentData())
        if target is None:
            return
        wanted = target.address or "\u2014"
        for index in range(self.address_selector.count()):
            if self.address_selector.itemText(index).split("   (")[0] == wanted:
                self._filling = True
                self.address_selector.setCurrentIndex(index)
                self._filling = False
                return

    def _selector_changed(self, index: int) -> None:
        """Choosing is not switching.

        This used to run the switch the moment the dropdown changed, which
        put a dialog on screen for a glance at the list. Now the two
        dropdowns follow each other and the Activate button does the work.
        """
        if self._filling or index < 0:
            return
        self._sync_address_to_selector()
        self._preview_selected()

    def _address_changed(self, index: int) -> None:
        if self._filling or index < 0:
            return
        # An address can belong to several targets; keep the one already
        # selected if it is one of them, otherwise take the first.
        name = self.address_selector.itemData(index)
        current = self._target(self.selector.currentData())
        chosen_address = self.address_selector.itemText(index).split("   (")[0]
        if current is not None and (current.address or "\u2014") == chosen_address:
            return
        position = self.selector.findData(name)
        if position >= 0:
            self._filling = True
            self.selector.setCurrentIndex(position)
            self._filling = False
        self._preview_selected()

    def _selected_in_bar(self):
        return self._target(self.selector.currentData())

    def _update_activate(self) -> None:
        target = self._selected_in_bar()
        self.activate_btn.setEnabled(bool(target) and not target.active)
        self.activate_btn.setText("\u2714  Active" if target and target.active
                                  else "\u2714  Activate")

    def _preview_selected(self) -> None:
        """Show what Activate would run, without running it."""
        self._update_activate()
        target = self._selected_in_bar()
        if target is None or target.active:
            return
        action = self.PROVIDER.prepare(self.PROVIDER.activate(target))
        self.show_command(action.display(), note=action.id, record=False)
        self.status.emit(f"Selected {target.name} \u2014 press Activate to "
                         f"make it the active {self.PROVIDER.target_noun.lower()}")

    def _activate_selected(self) -> None:
        target = self._selected_in_bar()
        if target is None or target.active:
            return
        self._run_inline(self.PROVIDER.activate(target))

    def _activate_row(self, *_):
        target = self._selected_target()
        if target and not target.active:
            self._run_inline(self.PROVIDER.activate(target))

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

    def _run_inline(self, action) -> None:
        """Run a harmless switch without a dialog.

        Switching a context or a connection is reversible and changes
        nothing but a setting, so it does not deserve a modal window. The
        command is still shown — in the strip, in the status bar and in the
        log — which is what the rule is for. Anything destructive, or
        anything needing root, still goes through the dialog.
        """
        from ..dialogs.run_command import RunCommandDialog
        action = self.PROVIDER.prepare(action)
        if action.destructive or action.scope == act.ROOT:
            self.show_command(action.display(), note=action.id, record=False)
            RunCommandDialog(action, self).exec()
            self.refresh()
            return
        self.show_command(action.display(), note=action.id, record=True)
        self.status.emit(f"{action.label}\u2026")
        self.busy.emit(True)
        run_job(CallableJob(action.execute), self._inline_done,
                self._inline_failed)

    def _inline_done(self, result) -> None:
        self.busy.emit(False)
        text = (result.stdout or result.stderr or "").strip().splitlines()
        self.status.emit(text[-1] if text and not result.ok
                         else ("Done" if result.ok else "Failed"))
        self.refresh()

    def _inline_failed(self, message: str) -> None:
        self.busy.emit(False)
        self.status.emit(f"Failed: {message}")

    def _rename(self, name: str) -> None:
        from PySide6.QtWidgets import QInputDialog
        new_name, ok = QInputDialog.getText(
            self, f"Rename {name}",
            f"New name for {name}:\n\nThe container keeps its id, volumes, "
            f"network and state; only the name changes.", text=name)
        new_name = (new_name or "").strip()
        if not ok or not new_name or new_name == name:
            return
        target = self.state["active"] if self.state else None
        self._run(self.PROVIDER.rename_container(target, name, new_name))

    def _recreate(self, name: str) -> None:
        target = self.state["active"] if self.state else None
        self.status.emit(f"Reading {name}'s configuration\u2026")
        self._run(self.PROVIDER.recreate_container(target, name))

    def _open_logs(self, action) -> None:
        """A follow goes to the log viewer, not to the run-once dialog,
        which would wait for a command that never ends."""
        from ..dialogs.logs_viewer import LogsDialog
        self.show_command(" ".join(action.follow), note=action.id,
                          record=False)
        LogsDialog(action, self).exec()

    def _run(self, action) -> None:
        from ..dialogs.run_command import RunCommandDialog
        action = self.PROVIDER.prepare(action)
        if action.follow:
            self._open_logs(action)
            return
        # Two actions are placeholders: they name what will happen, but the
        # command can only be built once the page knows which container and,
        # for a rename, what the new name is.
        if action.id.startswith("rename-"):
            self._rename(action.id[len("rename-"):])
            return
        if action.id.startswith("recreate-") and not action.command \
                and action.func is None:
            self._recreate(action.id[len("recreate-"):])
            return
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


def _bold(font):
    """A bold copy of a font, safe on Windows.

    A stylesheet sets sizes in pixels, so pointSize() comes back as -1 and
    Qt complains — "QFont::setPointSize: Point size <= 0 (-1)" — as soon as
    the copy is used. The warning was always there; routing Qt's messages
    into kontainy's log is what made it visible.
    """
    if font.pointSize() <= 0 and font.pixelSize() <= 0:
        font.setPointSize(10)
    font.setBold(True)
    return font


def make_platform_page(provider) -> type:
    """A Page subclass bound to one provider, for the sidebar."""
    return type(f"{provider.id.title()}Page", (PlatformPage,), {
        "NAME": f"platform-{provider.id}",
        "TITLE": provider.name,
        "ICON": provider.icon,
        "SUBTITLE": provider.summary,
        "PROVIDER": provider,
    })
