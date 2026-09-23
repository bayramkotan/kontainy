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
    QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QProgressBar, QPushButton,
    QVBoxLayout,
)

from ...core.actions import NONE, ROOT, SHELL, USER, Action
from ...core.elevate import can_elevate, elevation_note, run_streaming
from ...core.install_steps import percent_of, stage_of, steps_for
from ...utils.config import config
from ...utils.workers import CallableJob, StreamJob, run_job
from ..styles import cmd_html, get_colors


class RunCommandDialog(QDialog):
    """Show a command, explain it, then run it if the user agrees."""

    finished_ok = Signal(bool)

    def __init__(self, action: Action, parent=None):
        super().__init__(parent)
        self.action = action
        self.result_obj = None
        self._reached = 0
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

        # --- what is happening, while it happens ---
        self.steps = steps_for(self.action.display())
        self.step_labels = {}
        self.step_box = QLabel("")
        self.step_box.setVisible(False)
        self.step_box.setWordWrap(True)
        self.step_box.setTextFormat(Qt.RichText)
        self.step_box.setStyleSheet(
            f"color: {c['fg']}; font-size: {c['fs_base'] + 1}px;"
            f" background: {c['card']}; border: 1px solid {c['border']};"
            f" border-radius: 8px; padding: 12px; line-height: 150%;")
        layout.addWidget(self.step_box)

        self.progress = QProgressBar()
        self.progress.setRange(0, len(self.steps))
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setFormat("")
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

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

    # --- the steps panel -------------------------------------------------
    def _stage_index(self, key: str) -> int:
        for index, (name, _label, _why) in enumerate(self.steps):
            if name == key:
                return index
        return -1

    def _render_steps(self):
        c = self._c()
        rows = []
        for index, (_key, label, why) in enumerate(self.steps):
            if index < self._reached:
                mark, colour = "\u2705", c["success"]
            elif index == self._reached:
                mark, colour = "\u25b6", c["accent"]
            else:
                mark, colour = "\u25cb", c["fg_muted"]
            rows.append(f"<div style='color:{colour}'>{mark} <b>{label}</b>"
                        f"<br><span style='color:{c['fg_muted']}'>{why}"
                        f"</span></div>")
        self.step_box.setText("<br>".join(rows))

    def _on_line(self, line: str):
        self.output.appendPlainText(line)
        key = stage_of(line)
        if key:
            index = self._stage_index(key)
            # Never go backwards: a late "Reading package lists" from a
            # sub-process should not undo the progress already shown.
            if index > self._reached:
                self._reached = index
                self.progress.setValue(index)
                self._render_steps()
        percent = percent_of(line)
        if percent >= 0:
            self.progress.setFormat(f"{self.steps[self._reached][1]} "
                                    f"\u2014 {percent}%")
        else:
            self.progress.setFormat(self.steps[self._reached][1])

    def _run(self):
        self.run_btn.setEnabled(False)
        self.run_btn.setText("Running\u2026")
        self.close_btn.setEnabled(False)
        self.output.setVisible(True)
        self.output.setPlainText(f"$ {self.action.display()}\n")
        self._reached = 0
        self.step_box.setVisible(True)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self._render_steps()

        # A command kontainy runs itself (writing a file, storing a setting)
        # has no output to follow; only a real process can be streamed.
        if self.action.func is not None or self.action.scope == ROOT:
            run_job(CallableJob(self.action.execute), self._done, self._failed)
            return
        run_job(StreamJob(lambda emit: run_streaming(
            list(self.action.command), emit, note=self.action.id)),
            self._done, self._failed, on_progress=self._on_line)

    def _done(self, result):
        self.result_obj = result
        # Streamed output is already on screen; a captured one is not.
        if result.output and result.output not in self.output.toPlainText():
            self.output.appendPlainText(result.output)
        self._reached = len(self.steps)
        self.progress.setValue(len(self.steps))
        self.progress.setFormat("Done" if result.ok else "Failed")
        self._render_steps()
        self.close_btn.setEnabled(True)
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
        self.progress.setFormat("Failed")
        self.close_btn.setEnabled(True)
        self.run_btn.setText("Failed")
        self.finished_ok.emit(False)
