"""kontainy — Teşhis sayfası (VenvStudio'daki Conflict Manager'ın karşılığı)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (
    QPlainTextEdit, QTabWidget, QVBoxLayout, QWidget,
    QAbstractItemView, QHeaderView, QLabel, QPushButton, QSplitter,
    QTableWidget, QTableWidgetItem, QTextBrowser,
)

from ...rules import RULES, SEVERITY_ICONS, SEVERITY_TITLES, diagnose, rule_stats
from ...utils.workers import CallableJob, run_job
from .base import Page

SEVERITY_COLORS = {"error": "#f38ba8", "warn": "#f9e2af", "info": "#89dceb"}


class DiagnosticsPage(Page):
    NAME = "diagnostics"
    TITLE = "Diagnostics"
    ICON = "🔬"
    SUBTITLE = ("Every rule says three things: what was found, why it happens, "
                "how to fix it. Most failures in this ecosystem are silent "
                "\u2014 an empty list, an ignored limit, a bypassed context.")

    open_setting = Signal(str)

    def build(self) -> None:
        self.findings = []

        self.run_btn = self.add_tool_button(
            "\U0001f52c  Run Diagnostics", self.refresh, kind="primary")
        self.copy_btn = self.add_tool_button("\U0001f4cb  Copy Fix Command", self._copy_fix)
        self.setting_btn = self.add_tool_button("\u2699  Open Setting", self._goto_setting)
        self.add_tool_stretch()
        self.count_label = QLabel("—")
        self.toolbar.addWidget(self.count_label)

        self.report_btn = self.add_tool_button(
            "\U0001f4cb  Copy system report", self._copy_report)
        self.report_btn.setToolTip(
            "Everything a bug report needs: versions, platform, which "
            "technologies answered, which tools are installed.")

        self.tabs = QTabWidget()

        findings = QWidget()
        findings_layout = QVBoxLayout(findings)
        findings_layout.setContentsMargins(0, 8, 0, 0)

        split = QSplitter(Qt.Horizontal)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["", "ID", "Finding", "Scope"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.currentCellChanged.connect(self._show_detail)
        split.addWidget(self.table)

        self.detail = QTextBrowser()
        self.detail.setOpenExternalLinks(True)
        split.addWidget(self.detail)
        split.setSizes([520, 640])
        findings_layout.addWidget(split, 1)
        self.tabs.addTab(findings, "\U0001f50e  Findings")

        # The system report used to be a tab of the About dialog, where
        # nobody writing a bug report would think to look. It belongs here,
        # beside what is wrong.
        report_tab = QWidget()
        report_layout = QVBoxLayout(report_tab)
        report_layout.setContentsMargins(0, 8, 0, 0)
        self.report_view = QPlainTextEdit()
        self.report_view.setReadOnly(True)
        self.report_view.setObjectName("systemReport")
        self.report_view.setLineWrapMode(QPlainTextEdit.NoWrap)
        # The report is columns of key and value; a proportional font turns
        # them into a ragged mess.
        # A widget stylesheet, because the application-wide one sets a
        # proportional family for QPlainTextEdit and wins over setFont.
        self.report_view.setStyleSheet(
            'font-family: "Cascadia Mono", "Cascadia Code", "DejaVu Sans '
            'Mono", "Fira Code", "JetBrains Mono", "Consolas", monospace;')
        report_layout.addWidget(self.report_view, 1)
        self.tabs.addTab(report_tab, "\U0001f9fe  System report")
        self.tabs.currentChanged.connect(self._tab_changed)
        self.body.addWidget(self.tabs, 1)

        rs = rule_stats()
        self.body.addWidget(QLabel(
            f"Rule set: {rs['total']} rules "
            f"({rs['error']} error \u00b7 {rs['warning']} warning \u00b7 "
            f"{rs['info']} info). None require root \u2014 detection always "
            f"runs with your own privileges."))

    def apply_theme(self) -> None:
        super().apply_theme()
        c = self.colors()
        self.table.setStyleSheet(
            f"QTableWidget {{ font-size: {c['fs_base'] + 2}px; }}"
            f"QTableWidget::item {{ padding: 7px 10px; }}"
            f"QHeaderView::section {{ font-size: {c['fs_base'] + 1}px;"
            f" font-weight: bold; padding: 9px; }}")

    def _tab_changed(self, index: int) -> None:
        if index == 1 and not self.report_view.toPlainText():
            self._build_report()

    def _build_report(self) -> None:
        from ...core import report
        self.report_view.setPlainText("Gathering\u2026")
        run_job(CallableJob(report.build), self.report_view.setPlainText,
                lambda message: self.report_view.setPlainText(
                    f"Could not gather the report: {message}"))

    def _copy_report(self) -> None:
        from PySide6.QtWidgets import QApplication
        from ...core import report
        text = self.report_view.toPlainText()
        if not text or text.startswith("Gathering"):
            text = report.build()
            self.report_view.setPlainText(text)
        QApplication.clipboard().setText(text)
        self.tabs.setCurrentIndex(1)
        self.status.emit("System report copied \u2014 paste it into the issue")

    def on_shown(self) -> None:
        if not self.findings:
            self.refresh()

    def refresh(self) -> None:
        self.run_btn.setEnabled(False)
        self.busy.emit(True)
        self.status.emit("Running diagnostics\u2026")
        run_job(CallableJob(diagnose, True), self._fill, self._failed)

    def _failed(self, message: str) -> None:
        self.run_btn.setEnabled(True)
        self.busy.emit(False)
        self.status.emit(f"Diagnostics failed: {message}")

    def _fill(self, result) -> None:
        _env, findings = result
        self.findings = findings
        self.table.setRowCount(0)
        for f in findings:
            r = self.table.rowCount()
            self.table.insertRow(r)
            scope = {"user": "\U0001f464 user", "root": "\U0001f5a5 root",
                     "none": "\u2014"}.get(f.rule.fix_scope, "\u2014")
            cells = [SEVERITY_ICONS.get(f.severity, ""), f.id,
                     f.rule.title, scope]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col in (0, 2):
                    item.setForeground(QColor(SEVERITY_COLORS.get(f.severity,
                                                                  "#cdd6f4")))
                self.table.setItem(r, col, item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)

        errors = sum(1 for f in findings if f.severity == "error")
        warns = sum(1 for f in findings if f.severity == "warn")
        self.count_label.setText(
            f"{len(findings)} findings \u00b7 {errors} errors "
            f"\u00b7 {warns} warnings"
            if findings else "\u2705 nothing found")
        self.run_btn.setEnabled(True)
        self.busy.emit(False)
        self.status.emit(f"{len(findings)} findings from {len(RULES)} rules")

        if findings:
            self.table.selectRow(0)
        else:
            self.detail.setHtml(
                "<h2>\u2705 Nothing found</h2><p>None of the rules fired. "
                "That means your system has none of the <i>known</i> problems "
                "\u2014 not that everything is configured well.</p>")

    def _current(self):
        r = self.table.currentRow()
        if r < 0 or r >= len(self.findings):
            return None
        return self.findings[r]

    def _show_detail(self, row, *_) -> None:
        f = self._current()
        if f is None:
            return
        color = SEVERITY_COLORS.get(f.severity, "#cdd6f4")
        explain = f.explain().replace("\n\n", "</p><p>").replace("\n", "<br>")

        p = [f"<h2 style='color:{color}'>{SEVERITY_ICONS.get(f.severity, '')} "
             f"{f.rule.title}</h2>",
             f"<p style='color:#9399b2'><code>{f.id}</code> · "
             f"{SEVERITY_TITLES.get(f.severity, '')}</p>",
             f"<p>{explain}</p>"]

        cmd = f.fix_command()
        if cmd:
            scope_note = ("This command needs root. kontainy will not run "
                          "it \u2014 you run it."
                          if f.rule.fix_scope == "root"
                          else "Runs in user scope.")
            p.append("<div style='background:#11111b;border-left:4px solid "
                     f"{color};padding:10px;margin-top:12px'>"
                     f"<b>Fix</b><br><code>{cmd}</code>"
                     f"<br><span style='color:#9399b2'>{scope_note}</span></div>")
        if f.rule.setting_key:
            p.append(f"<p>Related setting: <code>{f.rule.setting_key}</code>"
                     " \u2014 use <i>Open Setting</i>.</p>")
        if f.rule.learn_topic:
            p.append(f"<p>Learn topic: <code>{f.rule.learn_topic}</code></p>")
        if f.rule.tags:
            p.append("<p style='color:#9399b2'>Tags: "
                     + ", ".join(f.rule.tags) + "</p>")
        self.detail.setHtml("".join(p))

        if cmd:
            self.show_command(cmd, note=f.id, record=False)

    def _copy_fix(self) -> None:
        f = self._current()
        if f and f.fix_command():
            QGuiApplication.clipboard().setText(f.fix_command())
            self.status.emit(f"{f.id} fix command copied")

    def _goto_setting(self) -> None:
        f = self._current()
        if f and f.rule.setting_key:
            self.open_setting.emit(f.rule.setting_key)
