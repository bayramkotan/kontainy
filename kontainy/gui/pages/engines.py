"""
kontainy — Engines page

The first version of this page was a report you could not touch: it told you
DOCKER_HOST was overriding your context and then left you to fix it in a
terminal. It now acts.

Three panels:

* **Where is your terminal pointing** — the resolved five-layer chain, with
  the winning layer marked and a fix offered when DOCKER_HOST is overriding
  everything. That fix includes finding WHICH startup file sets the variable,
  which is the part nobody can do quickly by hand.
* **Engines** — every socket found, with per-engine actions: make it the
  default context, point a shell at it, or test that it actually answers.
* **systemd units** — podman.socket, the auto-update timer, docker.service
  and the rest, with start, enable and status. Plus linger, because rootless
  containers die at logout without it.

Every action opens the run dialog first: the command is shown, explained, and
can be copied instead of run. Nothing executes unseen.
"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QMenu,
    QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QTextBrowser,
    QVBoxLayout, QWidget,
)

from ...core import actions as act
from ...core import discovery
from ...utils.config import config, log
from ...utils.workers import CallableJob, run_job
from ..styles import cmd_html
from ..widgets import PathElideMiddleDelegate
from .base import Page

SCOPE_ICONS = {act.USER: "\U0001f464", act.ROOT: "\U0001f5a5",
               act.SHELL: "\u2328", act.NONE: ""}


def _probe() -> tuple:
    """Everything the page needs, gathered off the GUI thread."""
    endpoints = discovery.discover(probe=True)
    units = act.list_units()
    return endpoints, units, act.linger_state()


class EnginesPage(Page):
    NAME = "engines"
    TITLE = "Engines"
    ICON = "\U0001f50c"
    SUBTITLE = ("kontainy does not trust the context system: it connects to "
                "EVERY socket it finds, separately. Select a row to act on "
                "it \u2014 nothing runs before you have seen the command.")

    engines_ready = Signal(list)

    def build(self) -> None:
        self.endpoints = []
        self.units = []
        self.linger = False
        self.current_actions = []

        self.refresh_btn = self.add_tool_button(
            "\U0001f501  Rescan", self.refresh, kind="primary")
        self.add_tool_stretch()
        self.count_label = QLabel("\u2014")
        self.toolbar.addWidget(self.count_label)

        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(10)

        # --- terminal target -------------------------------------------------
        target_box = QGroupBox("Where is your terminal pointing right now?")
        tb = QVBoxLayout(target_box)
        self.target_table = QTableWidget(0, 3)
        self.target_table.setHorizontalHeaderLabels(["Layer", "Value", "Wins"])
        self.target_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch)
        self.target_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.target_table.setAlternatingRowColors(True)
        self.target_table.setMaximumHeight(155)
        self.target_table.verticalHeader().setVisible(False)
        tb.addWidget(self.target_table)

        self.target_note = QLabel()
        self.target_note.setWordWrap(True)
        tb.addWidget(self.target_note)

        self.fix_row = QHBoxLayout()
        tb.addLayout(self.fix_row)
        ll.addWidget(target_box)

        # --- engines ---------------------------------------------------------
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Address", "Found via", "Engine", "State", "CLI target"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setItemDelegateForColumn(0, PathElideMiddleDelegate(self))
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._engine_menu)
        self.table.currentCellChanged.connect(self._engine_selected)
        ll.addWidget(self.table, 1)

        # --- systemd ---------------------------------------------------------
        unit_box = QGroupBox("systemd units")
        ub = QVBoxLayout(unit_box)
        self.unit_table = QTableWidget(0, 5)
        self.unit_table.setHorizontalHeaderLabels(
            ["Unit", "Scope", "State", "At boot", "What it does"])
        self.unit_table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.Stretch)
        self.unit_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.unit_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.unit_table.setAlternatingRowColors(True)
        self.unit_table.setMaximumHeight(210)
        self.unit_table.verticalHeader().setVisible(False)
        self.unit_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.unit_table.customContextMenuRequested.connect(self._unit_menu)
        self.unit_table.currentCellChanged.connect(self._unit_selected)
        ub.addWidget(self.unit_table)

        self.linger_row = QHBoxLayout()
        ub.addLayout(self.linger_row)
        ll.addWidget(unit_box)
        split.addWidget(left)

        # --- command reference ----------------------------------------------
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        self.reference = QTextBrowser()
        self.reference.setOpenExternalLinks(True)
        rl.addWidget(self.reference, 1)

        self.action_row = QVBoxLayout()
        rl.addLayout(self.action_row)
        split.addWidget(right)
        split.setSizes([900, 470])
        self.body.addWidget(split, 1)

    # --- refreshing --------------------------------------------------------
    def on_shown(self) -> None:
        if not self.endpoints:
            self.refresh()

    def refresh(self) -> None:
        self._fill_target()
        self.refresh_btn.setEnabled(False)
        self.busy.emit(True)
        self.status.emit("Scanning engines and systemd units\u2026")
        run_job(CallableJob(_probe), self._probed, self._failed)
        self.show_command("docker context ls && podman system connection ls",
                          note="engine discovery", record=False)

    def _failed(self, message: str) -> None:
        self.refresh_btn.setEnabled(True)
        self.busy.emit(False)
        self.status.emit(f"Scan failed: {message}")

    def _probed(self, payload) -> None:
        endpoints, units, linger = payload
        self.endpoints = endpoints
        self.units = units
        self.linger = linger
        self._fill_engines()
        self._fill_units()
        self.refresh_btn.setEnabled(True)
        self.busy.emit(False)
        alive = sum(1 for e in endpoints if e.reachable)
        self.status.emit(f"{alive} engines reachable")
        self.engines_ready.emit(endpoints)

    # --- terminal target ---------------------------------------------------
    def _fill_target(self) -> None:
        target = discovery.resolve_cli_target()
        self.target_table.setRowCount(0)
        for layer, value, won in target.as_rows():
            r = self.target_table.rowCount()
            self.target_table.insertRow(r)
            for col, text in enumerate([layer, value, "\u2705" if won else ""]):
                item = QTableWidgetItem(text)
                if won:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                self.target_table.setItem(r, col, item)
        self.target_table.resizeColumnsToContents()
        self.target_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch)

        c = self.colors()
        note = (f"Effective target: <b>{target.winner or '\u2014'}</b>"
                f" &nbsp;\u00b7&nbsp; via: {target.winner_layer}")
        shim = discovery.docker_shim_warning()
        if shim:
            note += f"<br><span style='color:{c['warning']}'>{shim}</span>"
        self.target_note.setText(note)

        while self.fix_row.count():
            item = self.fix_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        docker_host = os.environ.get("DOCKER_HOST", "")
        if docker_host:
            warn = QLabel(
                "DOCKER_HOST is set, so <code>docker context use</code> has "
                "no effect on any shell.")
            warn.setWordWrap(True)
            warn.setStyleSheet(f"color: {c['danger']};")
            self.fix_row.addWidget(warn, 1)
            for action in act.actions_for_docker_host(docker_host):
                button = QPushButton(f"\u2328  {action.label}")
                button.setCursor(Qt.PointingHandCursor)
                button.clicked.connect(
                    lambda _=False, a=action: self._open_action(a))
                self.fix_row.addWidget(button)

    # --- engines -----------------------------------------------------------
    def _fill_engines(self) -> None:
        c = self.colors()
        self.table.setRowCount(0)
        for endpoint in self.endpoints:
            r = self.table.rowCount()
            self.table.insertRow(r)
            state = (endpoint.title if endpoint.reachable
                     else f"\u274c {endpoint.error[:70]}")
            cells = [endpoint.address, endpoint.source, endpoint.family, state,
                     "\u2b05 terminal goes here" if endpoint.is_cli_default
                     else ""]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col == 0:
                    item.setToolTip(endpoint.address)
                if not endpoint.reachable:
                    item.setForeground(QColor(c["danger"]))
                elif col == 3:
                    item.setForeground(QColor(c["success"]))
                self.table.setItem(r, col, item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

        alive = sum(1 for e in self.endpoints if e.reachable)
        self.count_label.setText(
            f"{len(self.endpoints)} endpoints \u00b7 {alive} reachable")
        if self.endpoints:
            self.table.selectRow(0)

    def _current_endpoint(self):
        r = self.table.currentRow()
        if r < 0 or r >= len(self.endpoints):
            return None
        return self.endpoints[r]

    def _engine_selected(self, row, *_):
        endpoint = self._current_endpoint()
        if endpoint is None:
            return
        self._show_actions(
            act.actions_for_endpoint(endpoint),
            title=f"{endpoint.family} \u00b7 {endpoint.address}",
            intro=self._engine_intro(endpoint))

    def _engine_intro(self, endpoint) -> str:
        c = self.colors()
        rows = [f"<tr><td><b>Found via</b></td><td>{endpoint.source}</td></tr>"]
        if endpoint.info:
            rows.append(f"<tr><td><b>Version</b></td>"
                        f"<td>{endpoint.info.version}</td></tr>")
            rows.append(f"<tr><td><b>API</b></td>"
                        f"<td>{endpoint.info.api_version}</td></tr>")
            rows.append(f"<tr><td><b>Mode</b></td><td>"
                        f"{'rootless' if endpoint.info.rootless else 'rootful'}"
                        f"</td></tr>")
        context = act.docker_context_for(endpoint.address)
        if context:
            rows.append(f"<tr><td><b>Context</b></td><td>{context}</td></tr>")
        if not endpoint.reachable:
            rows.append(f"<tr><td><b>Error</b></td>"
                        f"<td style='color:{c['danger']}'>{endpoint.error}"
                        f"</td></tr>")
        return "<table cellpadding='4'>" + "".join(rows) + "</table>"

    def _engine_menu(self, point):
        endpoint = self._current_endpoint()
        if endpoint is None:
            return
        self._popup(act.actions_for_endpoint(endpoint),
                    self.table.viewport().mapToGlobal(point))

    # --- systemd units -----------------------------------------------------
    def _fill_units(self) -> None:
        c = self.colors()
        self.unit_table.setRowCount(0)
        for unit in self.units:
            r = self.unit_table.rowCount()
            self.unit_table.insertRow(r)
            cells = [unit.name, unit.scope_label, unit.state, unit.enabled,
                     unit.description]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(str(text))
                if col == 2:
                    item.setForeground(QColor(
                        c["success"] if unit.active else c["fg_muted"]))
                self.unit_table.setItem(r, col, item)
        self.unit_table.resizeColumnsToContents()
        self.unit_table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.Stretch)

        while self.linger_row.count():
            item = self.linger_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        label = QLabel(
            f"Linger: <b style='color:"
            f"{c['success'] if self.linger else c['warning']}'>"
            f"{'enabled' if self.linger else 'disabled'}</b> \u2014 "
            + ("user units survive logout and start at boot."
               if self.linger else
               "rootless containers will stop when you log out."))
        label.setWordWrap(True)
        self.linger_row.addWidget(label, 1)
        action = act.linger_action(self.linger)
        button = QPushButton(action.label)
        if action.destructive:
            button.setObjectName("danger")
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(lambda: self._open_action(action))
        self.linger_row.addWidget(button)

    def _current_unit(self):
        r = self.unit_table.currentRow()
        if r < 0 or r >= len(self.units):
            return None
        return self.units[r]

    def _unit_selected(self, row, *_):
        unit = self._current_unit()
        if unit is None:
            return
        self._show_actions(
            act.actions_for_unit(unit),
            title=f"{unit.name} ({unit.scope_label})",
            intro=f"<p>{unit.description}</p><table cellpadding='4'>"
                  f"<tr><td><b>State</b></td><td>{unit.state}</td></tr>"
                  f"<tr><td><b>At boot</b></td><td>{unit.enabled}</td></tr>"
                  f"</table>")

    def _unit_menu(self, point):
        unit = self._current_unit()
        if unit is None:
            return
        self._popup(act.actions_for_unit(unit),
                    self.unit_table.viewport().mapToGlobal(point))

    # --- action presentation -----------------------------------------------
    def _show_actions(self, actions: list, *, title: str, intro: str) -> None:
        """Render the Command Reference panel for the selected row."""
        self.current_actions = actions
        c = self.colors()
        h = cmd_html(c, size=c["fs_base"] + 3)

        parts = [f"<h2 style='color:{c['accent']}'>{title}</h2>", intro,
                 h["title"]("\u2328", "What you can do here")]
        for action in actions:
            scope = SCOPE_ICONS.get(action.scope, "")
            parts.append(h["title"]("", f"{scope} {action.label}",
                                    c["fg"]))
            parts.append(h["line"](_colourise(action.display(), h)))
            first = action.explanation.split("\n\n")[0]
            parts.append(h["note"](first))
        self.reference.setHtml("".join(parts))

        while self.action_row.count():
            item = self.action_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for action in actions:
            button = QPushButton(
                f"{SCOPE_ICONS.get(action.scope, '')}  {action.label}")
            button.setCursor(Qt.PointingHandCursor)
            if action.destructive:
                button.setObjectName("danger")
            elif action.scope != act.USER:
                button.setObjectName("secondary")
            button.clicked.connect(
                lambda _=False, a=action: self._open_action(a))
            self.action_row.addWidget(button)

    def _popup(self, actions: list, position) -> None:
        menu = QMenu(self)
        for action in actions:
            entry = menu.addAction(
                f"{SCOPE_ICONS.get(action.scope, '')}  {action.label}")
            entry.triggered.connect(
                lambda _=False, a=action: self._open_action(a))
        menu.exec(position)

    def _open_action(self, action) -> None:
        from ..dialogs.run_command import RunCommandDialog
        self.show_command(action.display(), note=action.id, record=False)
        dialog = RunCommandDialog(action, self)
        dialog.finished_ok.connect(self._after_action)
        dialog.exec()

    def _after_action(self, ok: bool) -> None:
        if ok:
            self.status.emit("Done \u2014 rescanning")
            self.refresh()

    def apply_theme(self) -> None:
        super().apply_theme()
        c = self.colors()
        for table in (self.table, self.unit_table, self.target_table):
            table.setStyleSheet(
                f"QTableWidget {{ font-size: {c['fs_base'] + 2}px; }}"
                f"QTableWidget::item {{ padding: 7px 10px; }}"
                f"QHeaderView::section {{ font-size: {c['fs_base'] + 1}px;"
                f" font-weight: bold; padding: 9px; }}")


def _colourise(command: str, h: dict) -> str:
    """Colour a command the way the reference panel does."""
    out = []
    for index, token in enumerate(command.split()):
        if index == 0 or token in ("sudo", "docker", "podman", "systemctl",
                                   "loginctl", "export", "unset"):
            out.append(h["cmd"](token))
        elif token.startswith("<") or "CHANGE_ME" in token:
            out.append(h["ph"](token))
        else:
            out.append(h["arg"](token))
    return " ".join(out)
