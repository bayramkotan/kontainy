"""kontainy — Günlük ve Komut Geçmişi sayfası."""

from __future__ import annotations

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView, QHeaderView, QLabel, QPlainTextEdit, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from ...utils.config import history, log_path
from .base import Page


class LogPage(Page):
    NAME = "log"
    TITLE = "History & Log"
    ICON = "📝"
    SUBTITLE = ("The command history is the educational pillar itself: every "
                "action kontainy performs leaves its terminal equivalent "
                "here, ready to copy.")

    def build(self) -> None:
        self.add_tool_button("\U0001f504  Refresh", self.refresh, kind="primary")
        self.add_tool_button("\U0001f4cb  Copy Selected", self._copy)
        self.add_tool_button("\U0001f5d1  Clear History", self._clear,
                             kind="danger")
        self.add_tool_stretch()
        self.path_label = QLabel(str(log_path()))
        self.toolbar.addWidget(self.path_label)

        tabs = QTabWidget()

        hist = QWidget()
        hl = QVBoxLayout(hist)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Time", "Engine", "Command", "Note"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        hl.addWidget(self.table)
        tabs.addTab(hist, "\u2328  Command History")

        logw = QWidget()
        ll = QVBoxLayout(logw)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        ll.addWidget(self.log_view)
        tabs.addTab(logw, "\U0001f4c4  Application Log")

        self.body.addWidget(tabs, 1)

    def apply_theme(self) -> None:
        super().apply_theme()
        c = self.colors()
        self.table.setStyleSheet(
            f"QTableWidget {{ font-size: {c['fs_base'] + 2}px; }}"
            f"QTableWidget::item {{ padding: 7px 10px; }}"
            f"QHeaderView::section {{ font-size: {c['fs_base'] + 1}px;"
            f" font-weight: bold; padding: 9px; }}")

    def on_shown(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        entries = history().entries(500)
        self.table.setRowCount(0)
        for e in reversed(entries):
            r = self.table.rowCount()
            self.table.insertRow(r)
            for col, text in enumerate([e.get("at", ""), e.get("engine", ""),
                                        e.get("command", ""), e.get("note", "")]):
                self.table.setItem(r, col, QTableWidgetItem(str(text)))
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)

        try:
            text = log_path().read_text(encoding="utf-8")
            self.log_view.setPlainText("\n".join(text.splitlines()[-800:]))
            self.log_view.verticalScrollBar().setValue(
                self.log_view.verticalScrollBar().maximum())
        except OSError:
            self.log_view.setPlainText("(no log file yet)")

        self.status.emit(f"{len(entries)} commands recorded")

    def _copy(self) -> None:
        r = self.table.currentRow()
        if r < 0:
            return
        item = self.table.item(r, 2)
        if item:
            QGuiApplication.clipboard().setText(item.text())
            self.status.emit("Command copied")

    def _clear(self) -> None:
        history().clear()
        self.refresh()
