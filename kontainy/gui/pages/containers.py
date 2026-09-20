"""kontainy — Container'lar sayfası."""

from __future__ import annotations

import json

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QHeaderView, QLabel, QLineEdit, QMessageBox, QSplitter,
    QTableWidget, QTableWidgetItem, QTabWidget, QTextBrowser, QVBoxLayout,
    QWidget,
)

from ...core import discovery
from ...core.api import EngineError
from ...utils.config import log
from ...utils.workers import CallableJob, run_job
from .base import Page

STATE_COLORS = {
    "running": "#a6e3a1", "exited": "#9399b2", "created": "#89dceb",
    "paused": "#f9e2af", "dead": "#f38ba8", "stopped": "#9399b2",
}


def _collect(endpoints) -> list:
    rows = []
    for ep in endpoints:
        if not ep.reachable:
            continue
        client = discovery.client_for(ep)
        try:
            containers = client.containers(all_=True)
        except EngineError as exc:
            log().warning("%s listelenemedi: %s", ep.address, exc)
            continue
        for c in containers:
            names = c.get("Names") or []
            name = (names[0] if names else c.get("Id", "")[:12]).lstrip("/")
            rows.append({
                "engine": ep.title, "endpoint": ep.address,
                "engine_kind": ep.family,
                "name": name, "image": c.get("Image", ""),
                "state": c.get("State", ""), "status": c.get("Status", ""),
                "id": c.get("Id", "")[:12], "ports": c.get("Ports") or [],
                "raw": c,
            })
    return rows


class ContainersPage(Page):
    NAME = "containers"
    TITLE = "Containers"
    ICON = "📦"
    SUBTITLE = ("Containers from EVERY engine found, in one table. The Engine "
                "column tells you which one holds it \u2014 a container is "
                "never \"lost\".")

    def build(self) -> None:
        self.endpoints = []
        self.rows = []
        self.filtered = []

        self.add_tool_button("\u2795  New Container", self._new_container,
                             kind="primary")
        self.add_tool_button("\U0001f4e6  From Template\u2026",
                             self._from_template)
        self.refresh_btn = self.add_tool_button(
            "\U0001f504  Refresh", self.refresh)
        self.add_tool_button("\u25b6  Start", lambda: self._act("start"))
        self.add_tool_button("\u25a0  Stop", lambda: self._act("stop"))
        self.add_tool_button("\u21bb  Restart", lambda: self._act("restart"))
        self.add_tool_button("\U0001f5d1  Remove", lambda: self._act("remove"),
                             kind="danger")

        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter: name, image, engine, state\u2026")
        self.search.textChanged.connect(self._apply_filter)
        self.toolbar.addWidget(self.search, 1)

        self.count_label = QLabel("—")
        self.toolbar.addWidget(self.count_label)

        split = QSplitter(Qt.Vertical)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Engine", "Name", "Image", "State", "Status", "ID"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.currentCellChanged.connect(self._show_detail)
        split.addWidget(self.table)

        self.detail = QTabWidget()
        self.tab_summary = QTextBrowser()
        self.tab_ports = QTextBrowser()
        self.tab_raw = QTextBrowser()
        self.detail.addTab(self.tab_summary, "Summary")
        self.detail.addTab(self.tab_ports, "Ports")
        self.detail.addTab(self.tab_raw, "Raw JSON")
        split.addWidget(self.detail)
        split.setSizes([420, 260])

        self.body.addWidget(split, 1)

    def set_endpoints(self, endpoints) -> None:
        self.endpoints = endpoints
        self.refresh()

    def apply_theme(self) -> None:
        super().apply_theme()
        c = self.colors()
        self.table.setStyleSheet(
            f"QTableWidget {{ font-size: {c['fs_base'] + 2}px; }}"
            f"QTableWidget::item {{ padding: 7px 10px; }}"
            f"QHeaderView::section {{ font-size: {c['fs_base'] + 1}px;"
            f" font-weight: bold; padding: 9px; }}")

    def on_shown(self) -> None:
        if self.endpoints and not self.rows:
            self.refresh()

    def refresh(self) -> None:
        if not self.endpoints:
            self.status.emit("Scan engines first, on the Engines page")
            return
        self.refresh_btn.setEnabled(False)
        self.busy.emit(True)
        run_job(CallableJob(_collect, self.endpoints), self._fill, self._failed)

    def _failed(self, message: str) -> None:
        self.refresh_btn.setEnabled(True)
        self.busy.emit(False)
        self.status.emit(f"Listing failed: {message}")

    def _fill(self, rows) -> None:
        self.rows = rows
        self.refresh_btn.setEnabled(True)
        self.busy.emit(False)
        self._apply_filter()

    def _apply_filter(self) -> None:
        text = self.search.text().strip().casefold()
        if text:
            self.filtered = [r for r in self.rows if text in " ".join(
                [r["name"], r["image"], r["engine"], r["state"]]).casefold()]
        else:
            self.filtered = list(self.rows)

        self.table.setRowCount(0)
        for row in self.filtered:
            r = self.table.rowCount()
            self.table.insertRow(r)
            cells = [row["engine"], row["name"], row["image"],
                     row["state"], row["status"], row["id"]]
            for col, text_ in enumerate(cells):
                item = QTableWidgetItem(str(text_))
                if col == 3:
                    item.setForeground(QColor(STATE_COLORS.get(text_, "#9399b2")))
                self.table.setItem(r, col, item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)

        running = sum(1 for x in self.filtered if x["state"] == "running")
        self.count_label.setText(
            f"{len(self.filtered)}/{len(self.rows)} containers \u00b7 {running} running")
        if self.filtered:
            self.table.selectRow(0)

    def _current(self):
        r = self.table.currentRow()
        if r < 0 or r >= len(self.filtered):
            return None
        return self.filtered[r]

    def _show_detail(self, row, *_) -> None:
        item = self._current()
        if item is None:
            for tab in (self.tab_summary, self.tab_ports, self.tab_raw):
                tab.clear()
            return

        self.tab_summary.setHtml(
            f"<h2>{item['name']}</h2>"
            f"<table cellpadding='4'>"
            f"<tr><td><b>Engine</b></td><td>{item['engine']}</td></tr>"
            f"<tr><td><b>Endpoint</b></td><td><code>{item['endpoint']}</code></td></tr>"
            f"<tr><td><b>Image</b></td><td>{item['image']}</td></tr>"
            f"<tr><td><b>State</b></td><td>{item['state']} \u2014 {item['status']}</td></tr>"
            f"<tr><td><b>ID</b></td><td><code>{item['id']}</code></td></tr>"
            f"</table>")

        ports = item["ports"]
        if ports:
            lines = ["<table cellpadding='4'><tr><th>Host</th><th>Container</th>"
                     "<th>Protocol</th></tr>"]
            for p in ports:
                host = f"{p.get('IP', '')}:{p.get('PublicPort', '')}".strip(":")
                lines.append(f"<tr><td>{host or '—'}</td>"
                             f"<td>{p.get('PrivatePort', '')}</td>"
                             f"<td>{p.get('Type', '')}</td></tr>")
            lines.append("</table>")
            self.tab_ports.setHtml("".join(lines))
        else:
            self.tab_ports.setHtml("<p>No published ports.</p>")

        self.tab_raw.setHtml(
            f"<pre>{json.dumps(item['raw'], indent=2, ensure_ascii=False)}</pre>")

        cli = "podman" if item["engine_kind"] == "podman" else "docker"
        self.show_command(f"{cli} inspect {item['id']}",
                          engine=item["engine_kind"], record=False)

    # --- creation ----------------------------------------------------------
    def _new_container(self, preset: str = "") -> None:
        if not self.endpoints:
            self.status.emit("Scan engines first, on the Engines page")
            return
        from ..dialogs.create_container import CreateContainerDialog
        dialog = CreateContainerDialog(self.endpoints, self, preset=preset)
        dialog.created.connect(self._on_created)
        dialog.exec()

    def _on_created(self, container_id: str) -> None:
        self.status.emit(f"Container created: {container_id[:12]}")
        self.refresh()

    def _from_template(self) -> None:
        from ...core import templates as tpl
        from PySide6.QtWidgets import QInputDialog
        labels = [f"{t.category} \u00b7 {t.name}  \u2014  {t.image}"
                  for t in tpl.TEMPLATES]
        choice, ok = QInputDialog.getItem(
            self, "Start from a template",
            "Ready-made definitions with ports, volumes, environment, "
            "healthcheck and a sane capability set already filled in:",
            labels, 0, False)
        if not ok:
            return
        self._new_container(tpl.TEMPLATES[labels.index(choice)].id)

    def _act(self, action: str) -> None:
        item = self._current()
        if item is None:
            return
        cli = "podman" if item["engine_kind"] == "podman" else "docker"
        verb = {"start": "start", "stop": "stop",
                "restart": "restart", "remove": "rm -f"}[action]
        command = f"{cli} {verb} {item['id']}"

        if action == "remove":
            answer = QMessageBox.question(
                self, "Remove container?",
                f"<b>{item['name']}</b> will be removed permanently.\n\n"
                f"Equivalent: <code>{command}</code>")
            if answer != QMessageBox.Yes:
                return

        ep = next((e for e in self.endpoints if e.address == item["endpoint"]), None)
        if ep is None:
            return
        client = discovery.client_for(ep)
        try:
            if action == "remove":
                client.remove(item["id"], force=True)
            else:
                getattr(client, action)(item["id"])
        except EngineError as exc:
            self.show_command(command, engine=item["engine_kind"],
                              note=str(exc), record=True)
            QMessageBox.warning(self, "Operation failed", str(exc))
            return

        self.show_command(command, engine=item["engine_kind"], record=True)
        self.status.emit(f"{item['name']}: {action} done")
        self.refresh()
