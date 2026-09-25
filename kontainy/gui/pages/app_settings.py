"""
kontainy — App Settings

The catalogue explains the engines. This page explains the applications
around them: Docker Desktop's memory and its TCP-2375 switch, WSL's
.wslconfig, VMware's preferences, VirtualBox's own file. Same rules as
everywhere: what it does, what breaks when it is wrong, the file it lives
in, the command or the write shown before anything happens.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QHeaderView, QLabel, QLineEdit, QPushButton, QSplitter,
    QTableWidget, QTableWidgetItem, QTextBrowser, QVBoxLayout, QWidget,
)

from ...core import appconfig
from ...utils.workers import CallableJob, run_job
from .base import Page


def _probe() -> list:
    """Every application on this system, with its file and current values."""
    out = []
    for app in appconfig.apps_here():
        values = appconfig.read_values(app)
        out.append({"app": app, "path": app.path(), "exists": app.exists(),
                    "values": values})
    return out


class AppSettingsPage(Page):
    NAME = "app-settings"
    TITLE = "App Settings"
    ICON = "\U0001f39b"
    SUBTITLE = ("The settings of the applications themselves \u2014 Docker "
                "Desktop, WSL, podman machine, VMware, VirtualBox \u2014 not "
                "the engines they run. Every one says what it does and what "
                "breaks when it is wrong.")

    def build(self) -> None:
        self.entries = []
        self.refresh_btn = self.add_tool_button("\U0001f504  Re-read",
                                                self.refresh)
        self.count_label = QLabel("")
        self.toolbar.addWidget(self.count_label)

        split = QSplitter(Qt.Horizontal)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["Application", "Setting", "Value", "File"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch)
        self.table.currentCellChanged.connect(self._selected)
        split.addWidget(self.table)

        right = QWidget()
        layout = QVBoxLayout(right)
        layout.setContentsMargins(0, 0, 0, 0)
        self.detail = QTextBrowser()
        self.detail.setOpenExternalLinks(True)
        layout.addWidget(self.detail, 1)

        self.editor = QLineEdit()
        self.editor.setPlaceholderText("New value\u2026")
        self.editor.returnPressed.connect(self._apply)
        layout.addWidget(self.editor)
        self.apply_btn = QPushButton("Apply")
        self.apply_btn.clicked.connect(self._apply)
        self.apply_btn.setEnabled(False)
        layout.addWidget(self.apply_btn)
        split.addWidget(right)
        split.setSizes([620, 560])
        self.body.addWidget(split, 1)

    # --- data ---------------------------------------------------------------
    def on_shown(self) -> None:
        if not self.entries:
            self.refresh()

    def refresh(self) -> None:
        self.busy.emit(True)
        self.refresh_btn.setEnabled(False)
        self.status.emit("Reading the applications' own settings\u2026")
        run_job(CallableJob(_probe), self._fill, self._failed)

    def _failed(self, message: str) -> None:
        self.busy.emit(False)
        self.refresh_btn.setEnabled(True)
        self.status.emit(f"Failed: {message}")

    def _fill(self, entries) -> None:
        self.entries = entries
        self.busy.emit(False)
        self.refresh_btn.setEnabled(True)
        self.rows = []
        for entry in entries:
            app = entry["app"]
            for key in app.keys:
                self.rows.append({"app": app, "key": key,
                                  "path": entry["path"],
                                  "exists": entry["exists"],
                                  "value": appconfig.value_of(
                                      app, key, entry["values"])})
        self.table.setRowCount(len(self.rows))
        for index, row in enumerate(self.rows):
            value = row["value"]
            shown = "\u2014 not set" if value in (None, "") else str(value)
            for column, text in enumerate(
                    [row["app"].app, row["key"].title, shown,
                     str(row["path"] or "")]):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(index, column, item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch)
        found = sum(1 for e in entries if e["exists"])
        self.count_label.setText(
            f"{len(self.rows)} settings \u00b7 {found} of {len(entries)} "
            f"applications found")
        if self.rows:
            self.table.selectRow(0)

    # --- detail --------------------------------------------------------------
    def _current(self):
        index = self.table.currentRow()
        return self.rows[index] if 0 <= index < len(self.rows) else None

    def _selected(self, *_):
        row = self._current()
        if row is None:
            return
        app, key = row["app"], row["key"]
        value = row["value"]
        parts = [f"<h2>{key.title}</h2>",
                 f"<p><b>{app.app}</b> \u2014 {app.file_label}</p>",
                 f"<p>{key.what}</p>"]
        if key.gotcha:
            parts.append(f"<p><b>\u26a0 What goes wrong:</b> "
                         f"{key.gotcha.replace(chr(10), '<br>')}</p>")
        parts.append("<table cellpadding='4'>")
        parts.append(f"<tr><td><b>Key</b></td><td><code>{key.key}</code>"
                     f"</td></tr>")
        parts.append(f"<tr><td><b>Now</b></td><td>"
                     f"{'not set' if value in (None, '') else value}</td></tr>")
        if key.default:
            parts.append(f"<tr><td><b>Default</b></td><td>{key.default}"
                         f"</td></tr>")
        parts.append(f"<tr><td><b>File</b></td><td><code>{row['path']}</code>"
                     f"{'' if row['exists'] else ' — does not exist yet'}"
                     f"</td></tr>")
        parts.append(f"<tr><td><b>Type</b></td><td>{key.vtype}</td></tr>")
        parts.append("</table>")
        if key.close_first:
            parts.append(f"<p>\u26a0 {app.app} rewrites this file when it "
                         f"closes: make the change with it shut down.</p>")
        if not app.writable:
            parts.append(f"<p>\u26a0 kontainy does not write this file. "
                         f"{app.note}</p>")
        elif app.note:
            parts.append(f"<p>{app.note}</p>")
        self.detail.setHtml("".join(parts))
        self.editor.setText("" if value in (None, "") else str(value))
        self.editor.setEnabled(app.writable)
        self.apply_btn.setEnabled(app.writable)
        self.show_command(f"# {row['path']}\n{key.key} = "
                          f"{value if value not in (None, '') else '…'}",
                          record=False)

    def _apply(self) -> None:
        from ..dialogs.run_command import RunCommandDialog
        row = self._current()
        if row is None or not row["app"].writable:
            return
        value = self.editor.text().strip()
        if not value:
            self.status.emit("Give a value first.")
            return
        action = appconfig.write_action(row["app"], row["key"], value)
        RunCommandDialog(action, self).exec()
        self.refresh()
