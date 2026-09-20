"""kontainy — Motorlar sayfası."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QGroupBox, QHeaderView, QLabel, QTableWidget,
    QTableWidgetItem, QVBoxLayout,
)

from ...core import discovery
from ...utils.config import config, log
from ...utils.workers import CallableJob, run_job
from .base import Page


class EnginesPage(Page):
    NAME = "engines"
    TITLE = "Engines"
    ICON = "🔌"
    SUBTITLE = ("kontainy does not trust the context system: it connects to "
                "EVERY socket it finds, separately. The first panel shows "
                "where your terminal is pointing; the second shows which "
                "engines actually exist.")

    engines_ready = Signal(list)

    def build(self) -> None:
        self.endpoints = []

        self.refresh_btn = self.add_tool_button(
            "\U0001f501  Rescan", self.refresh, kind="primary")
        self.add_tool_stretch()
        self.count_label = QLabel("—")
        self.toolbar.addWidget(self.count_label)

        # --- terminal hedefi ---
        box = QGroupBox("Where is your terminal pointing right now?")
        bl = QVBoxLayout(box)
        self.target_table = QTableWidget(0, 3)
        self.target_table.setHorizontalHeaderLabels(["Layer", "Value", "Wins"])
        self.target_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.target_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.target_table.setAlternatingRowColors(True)
        self.target_table.setMaximumHeight(160)
        self.target_table.verticalHeader().setVisible(False)
        bl.addWidget(self.target_table)

        self.target_note = QLabel()
        self.target_note.setWordWrap(True)
        self.target_note.setOpenExternalLinks(False)
        bl.addWidget(self.target_note)
        self.body.addWidget(box)

        # --- bulunan motorlar ---
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Address", "Found via", "Engine", "State", "CLI target"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.body.addWidget(self.table, 1)

    def apply_theme(self) -> None:
        super().apply_theme()
        c = self.colors()
        self.table.setStyleSheet(
            f"QTableWidget {{ font-size: {c['fs_base'] + 2}px; }}"
            f"QTableWidget::item {{ padding: 7px 10px; }}"
            f"QHeaderView::section {{ font-size: {c['fs_base'] + 1}px;"
            f" font-weight: bold; padding: 9px; }}")

    def on_shown(self) -> None:
        if not self.endpoints:
            self.refresh()

    def refresh(self) -> None:
        self._fill_target()
        self.refresh_btn.setEnabled(False)
        self.busy.emit(True)
        self.status.emit("Scanning engines\u2026")
        timeout = float(config().get("probe_timeout", 4.0))
        run_job(CallableJob(discovery.discover, probe=True),
                self._fill_engines, self._failed)
        self.show_command("docker context ls && podman system connection ls",
                          note="motor keşfi", record=False)
        log().debug("Motor taraması başladı (timeout=%.1f)", timeout)

    def _failed(self, message: str) -> None:
        self.refresh_btn.setEnabled(True)
        self.busy.emit(False)
        self.status.emit(f"Scan failed: {message}")

    def _fill_target(self) -> None:
        target = discovery.resolve_cli_target()
        self.target_table.setRowCount(0)
        for layer, value, won in target.as_rows():
            r = self.target_table.rowCount()
            self.target_table.insertRow(r)
            for col, text in enumerate([layer, value, "✅" if won else ""]):
                item = QTableWidgetItem(text)
                if won:
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
                self.target_table.setItem(r, col, item)
        self.target_table.resizeColumnsToContents()
        self.target_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

        note = (f"Effective target: <b>{target.winner or '\u2014'}</b>"
                f" &nbsp;\u00b7&nbsp; via: {target.winner_layer}")
        if target.winner_layer.startswith("DOCKER_HOST"):
            note += ("<br><span style='color:#f38ba8'>DOCKER_HOST is set, so "
                     "<code>docker context use</code> has no effect. To use "
                     "contexts again, run <code>unset DOCKER_HOST</code> first."
                     " See Diagnostics \u2192 CTX01</span>")
        shim = discovery.docker_shim_warning()
        if shim:
            note += f"<br><span style='color:#f9e2af'>{shim}</span>"
        self.target_note.setText(note)

    def _fill_engines(self, endpoints) -> None:
        self.endpoints = endpoints
        self.table.setRowCount(0)
        for ep in endpoints:
            r = self.table.rowCount()
            self.table.insertRow(r)
            state = ep.title if ep.reachable else f"❌ {ep.error[:70]}"
            cells = [ep.address, ep.source, ep.family, state,
                     "\u2b05 terminal goes here" if ep.is_cli_default else ""]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if not ep.reachable:
                    item.setForeground(QColor("#f38ba8"))
                elif col == 3:
                    item.setForeground(QColor("#a6e3a1"))
                self.table.setItem(r, col, item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)

        alive = sum(1 for e in endpoints if e.reachable)
        self.count_label.setText(f"{len(endpoints)} endpoints \u00b7 {alive} reachable")
        self.refresh_btn.setEnabled(True)
        self.busy.emit(False)
        self.status.emit(f"{alive} engines reachable")
        self.engines_ready.emit(endpoints)
