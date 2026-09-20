"""
kontainy — the run-a-command dialog

Nothing in kontainy runs a command the user has not seen first. This dialog
is that promise made concrete: the command appears at the top in the same
coloured form the Command Reference panel uses, with an explanation of what
it changes, and two ways out — run it here, or copy it and run it yourself.

For a root-scoped command it also says which elevation dialog will appear and
that kontainy never sees the password.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout,
)

from ...core.actions import NONE, ROOT, SHELL, USER, Action
from ...core.elevate import can_elevate, elevation_note
from ...utils.config import config
from ...utils.workers import CallableJob, run_job
from ..styles import cmd_html, get_colors


class RunCommandDialog(QDialog):
    """Show a command, explain it, then run it if the user agrees."""

    finished_ok = Signal(bool)

    def __init__(self, action: Action, parent=None):
        super().__init__(parent)
        self.action = action
        self.result_obj = None
        self.setWindowTitle(action.label)
        self.resize(760, 560)
        self._build()

    def _c(self) -> dict:
        return get_colors(config().get("theme", "dark"),
                          config().get("font_size", 13),
                          config().get("font_primary_size", 22),
                          config().get("font_tertiary_size", 11))

    def _build(self):
        c = self._c()
        h = cmd_html(c, size=16)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        heading = QLabel(self.action.label)
        heading.setObjectName("header")
        heading.setWordWrap(True)
        layout.addWidget(heading)

        # --- the command, coloured the way the reference panel colours it ---
        parts = self.action.display().split()
        rendered = []
        for index, token in enumerate(parts):
            if index == 0 or token in ("sudo", "systemctl", "docker",
                                       "podman", "loginctl"):
                rendered.append(h["cmd"](token))
            elif token.startswith("<") or "CHANGE_ME" in token:
                rendered.append(h["ph"](token))
            else:
                rendered.append(h["arg"](token))
        self.command_label = QLabel(h["line"](" ".join(rendered)))
        self.command_label.setTextFormat(Qt.RichText)
        self.command_label.setWordWrap(True)
        self.command_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.command_label)

        scope_text = {
            USER: "Runs as you \u2014 no elevation needed.",
            ROOT: ("Needs root. " + elevation_note()),
            SHELL: ("kontainy cannot run this for you. A child process "
                    "cannot change the environment of the shell that started "
                    "it, so copy the line and run it in your own terminal."),
            NONE: "",
        }.get(self.action.scope, "")
        self.scope_label = QLabel(scope_text)
        self.scope_label.setWordWrap(True)
        self.scope_label.setStyleSheet(
            f"color: {c['fg_muted']}; font-size: {c['fs_base']}px;")
        layout.addWidget(self.scope_label)

        explanation = QLabel(self.action.explanation.replace("\n", "<br>"))
        explanation.setWordWrap(True)
        explanation.setTextFormat(Qt.RichText)
        explanation.setStyleSheet(
            f"color: {c['fg']}; font-size: {c['fs_base'] + 2}px;"
            f" background: {c['card']}; border: 1px solid {c['border']};"
            f" border-radius: 8px; padding: 12px; line-height: 150%;")
        layout.addWidget(explanation, 1)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setVisible(False)
        self.output.setStyleSheet(
            f"QPlainTextEdit {{ font-family: monospace;"
            f" font-size: {c['fs_base'] + 1}px; }}")
        layout.addWidget(self.output, 1)

        row = QHBoxLayout()
        self.copy_btn = QPushButton("\U0001f4cb  Copy command")
        self.copy_btn.setObjectName("secondary")
        self.copy_btn.clicked.connect(self._copy)
        row.addWidget(self.copy_btn)
        row.addStretch()

        self.close_btn = QPushButton("Close")
        self.close_btn.setObjectName("secondary")
        self.close_btn.clicked.connect(self.reject)
        row.addWidget(self.close_btn)

        self.run_btn = QPushButton("Run it")
        if self.action.destructive:
            self.run_btn.setObjectName("danger")
            self.run_btn.setText("Run it anyway")
        self.run_btn.clicked.connect(self._run)
        if self.action.scope in (SHELL, NONE) or (
                self.action.scope == ROOT and not can_elevate()):
            self.run_btn.setEnabled(False)
            self.run_btn.setToolTip("Copy the command and run it yourself")
        row.addWidget(self.run_btn)
        layout.addLayout(row)

    def _copy(self):
        QGuiApplication.clipboard().setText(self.action.display())
        self.copy_btn.setText("\u2713  Copied")

    def _run(self):
        self.run_btn.setEnabled(False)
        self.run_btn.setText("Running\u2026")
        self.output.setVisible(True)
        self.output.setPlainText(f"$ {self.action.display()}\n")
        run_job(CallableJob(self.action.execute), self._done, self._failed)

    def _done(self, result):
        self.result_obj = result
        self.output.appendPlainText(result.output)
        if result.skipped:
            self.output.appendPlainText(f"\n\u2014 not run: {result.skipped}")
        elif result.ok:
            self.output.appendPlainText("\n\u2705 exit 0")
        else:
            self.output.appendPlainText(f"\n\u274c exit {result.returncode}")
        self.run_btn.setText("Done")
        self.close_btn.setText("Close")
        self.finished_ok.emit(bool(result.ok))

    def _failed(self, message: str):
        self.output.appendPlainText(f"\n\u274c {message}")
        self.run_btn.setText("Failed")
        self.finished_ok.emit(False)
