"""
kontainy — the log viewer

`docker logs --follow` never ends, so it cannot go through the run-once
dialog: that dialog waits for the command to finish and would grow in memory
until the container stopped. This window reads the stream line by line,
keeps a bounded number of lines, and stops the process when it is closed —
a log window left open all day must not become a leak.

What it adds over the terminal: a filter that hides the noise without
losing it, a pause that stops the scroll while the lines keep arriving, and
the command in full at the top, because that is the command the user could
have typed.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
    QPushButton, QVBoxLayout,
)

from ...core.elevate import run_streaming
from ...utils.config import log
from ...utils.workers import StreamJob, run_job
from ..styles import get_colors

#: Enough to scroll back through a startup failure, small enough that a
#: chatty container cannot fill memory.
MAX_LINES = 5000


class LogsDialog(QDialog):
    @staticmethod
    def _theme_name() -> str:
        from ...utils.config import config
        return config().get("theme", "dark")

    def __init__(self, action, parent=None):
        super().__init__(parent)
        self.action = action
        self.lines = []
        self._job = None
        self._proc = None
        self._stopped = False
        c = get_colors(self._theme_name())

        self.setWindowTitle(action.label.split("  ")[-1] + " — live")
        self.resize(940, 620)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        command = " ".join(action.follow or action.command)
        head = QLabel(f"$ {command}")
        head.setWordWrap(True)
        head.setTextInteractionFlags(Qt.TextSelectableByMouse)
        head.setObjectName("CommandText")
        layout.addWidget(head)

        bar = QHBoxLayout()
        self.follow_box = QCheckBox("Follow")
        self.follow_box.setChecked(True)
        self.follow_box.setToolTip(
            "Keep scrolling to the newest line. Unticking only stops the "
            "scrolling; the lines keep arriving.")
        bar.addWidget(self.follow_box)

        self.wrap_box = QCheckBox("Wrap lines")
        self.wrap_box.toggled.connect(self._set_wrap)
        bar.addWidget(self.wrap_box)

        self.filter_box = QLineEdit()
        self.filter_box.setPlaceholderText("Filter: text that must appear…")
        self.filter_box.setClearButtonEnabled(True)
        self.filter_box.textChanged.connect(self._render)
        bar.addWidget(self.filter_box, 1)

        self.count_label = QLabel("0 lines")
        self.count_label.setProperty("noWrap", True)
        bar.addWidget(self.count_label)
        layout.addLayout(bar)

        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.view.setMaximumBlockCount(MAX_LINES + 10)
        self.view.setStyleSheet(
            f"color: {c['fg']}; background: {c['card']};"
            f' font-family: "Cascadia Mono", "DejaVu Sans Mono", '
            f'"Consolas", monospace;')
        layout.addWidget(self.view, 1)

        buttons = QHBoxLayout()
        self.copy_btn = QPushButton("\U0001f4cb  Copy visible")
        self.copy_btn.setObjectName("secondary")
        self.copy_btn.clicked.connect(self._copy)
        buttons.addWidget(self.copy_btn)
        self.clear_btn = QPushButton("\u2327  Clear")
        self.clear_btn.setObjectName("secondary")
        self.clear_btn.clicked.connect(self._clear)
        buttons.addWidget(self.clear_btn)
        buttons.addStretch()
        self.state_label = QLabel("Streaming\u2026")
        buttons.addWidget(self.state_label)
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.close)
        buttons.addWidget(self.close_btn)
        layout.addLayout(buttons)

        self._start()

    # --- the stream ---------------------------------------------------------
    def _start(self) -> None:
        argv = list(self.action.follow or self.action.command)
        log().info("Logs: %s", " ".join(argv))
        self._job = StreamJob(lambda emit: run_streaming(
            argv, emit, timeout=24 * 3600, note=self.action.id, record=False,
            should_stop=lambda: self._stopped,
            on_start=self._keep_process))
        run_job(self._job, self._finished, self._failed,
                on_progress=self._line)

    def _keep_process(self, stopper) -> None:
        self._proc = stopper
        if self._stopped:              # closed before it even started
            self._terminate()

    def _terminate(self) -> None:
        if self._proc is not None:
            self._proc.stop()

    def _line(self, text: str) -> None:
        self.lines.append(text)
        if len(self.lines) > MAX_LINES:
            del self.lines[:len(self.lines) - MAX_LINES]
            self._render()
            return
        if self._matches(text):
            self._append(text)
        self.count_label.setText(f"{len(self.lines)} lines")

    def _finished(self, result) -> None:
        self.state_label.setText(
            "Ended" if result.ok else f"Ended \u2014 exit {result.returncode}")

    def _failed(self, message: str) -> None:
        self.state_label.setText(f"Failed: {message}")

    # --- display ------------------------------------------------------------
    def _matches(self, text: str) -> bool:
        needle = self.filter_box.text().strip().casefold()
        return not needle or needle in text.casefold()

    def _append(self, text: str) -> None:
        self.view.appendPlainText(text)
        if self.follow_box.isChecked():
            self.view.moveCursor(QTextCursor.End)

    def _render(self) -> None:
        self.view.setPlainText(
            "\n".join(line for line in self.lines if self._matches(line)))
        if self.follow_box.isChecked():
            self.view.moveCursor(QTextCursor.End)

    def _set_wrap(self, on: bool) -> None:
        self.view.setLineWrapMode(QPlainTextEdit.WidgetWidth if on
                                  else QPlainTextEdit.NoWrap)

    def _copy(self) -> None:
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.view.toPlainText())
        self.state_label.setText("Copied")

    def _clear(self) -> None:
        self.lines = []
        self.view.clear()
        self.count_label.setText("0 lines")

    # --- closing ------------------------------------------------------------
    def closeEvent(self, event) -> None:
        """Stop the process; a follow runs until it is stopped."""
        # The flag is read by the streaming loop, which terminates the
        # process on the next line it receives; a container that has gone
        # quiet is caught by the job's own deadline.
        self._stopped = True
        self._terminate()
        self.state_label.setText("Stopped")
        super().closeEvent(event)
