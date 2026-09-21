"""
kontainy — Preferences

Laid out the way VenvStudio's settings page is: one scrolling page divided
into sections rather than tabs, each section headed by a title row carrying
an icon, an information button and its own Reset.

Sections: Appearance · Language · General · Engines · Terminal · Catalogue ·
Diagnostics · Privileges · Advanced.

This is kontainy's OWN configuration. The 152 Docker and Podman settings live
on the Config Catalog page; the two were one page for a while and that was
the mistake — an application preference and a daemon setting have nothing in
common except the word "setting".
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QSpinBox,
    QToolButton, QVBoxLayout, QWidget,
)

from ...core.constants import LANGUAGES, START_PAGES, TERMINALS
from ...core.elevate import can_elevate, elevation_note
from ...utils.config import DEFAULTS, config, config_dir, data_dir, log_path
from ..styles import THEME_OPTIONS
from .base import Page




class PreferencesPage(Page):
    NAME = "preferences"
    TITLE = "Preferences"
    ICON = "\u2699"
    SUBTITLE = ("kontainy's own settings. The Docker and Podman configuration "
                "keys are on the Config Catalog page \u2014 an application "
                "preference and a daemon setting have nothing in common but "
                "the word.")

    theme_changed = Signal(str)
    restart_needed = Signal(str)

    # --- section helpers ---------------------------------------------------
    def _info_button(self, tooltip: str) -> QToolButton:
        c = self.colors()
        button = QToolButton()
        button.setText("\u2139")
        button.setToolTip(tooltip)
        button.setCursor(Qt.WhatsThisCursor)
        button.setStyleSheet(
            f"QToolButton {{ border: none; background: transparent;"
            f" color: {c['fg_muted']}; font-size: {c['fs_base'] + 2}px; }}"
            f"QToolButton:hover {{ color: {c['accent']}; }}")
        return button

    def _section(self, icon: str, title: str, tooltip: str,
                 reset: callable) -> QGridLayout:
        """Title row plus the grid every row of the section goes into."""
        c = self.colors()

        header = QHBoxLayout()
        label = QLabel(f"{icon}  {title}")
        label.setStyleSheet(
            f"color: {c['accent']}; font-size: {c['fs_base'] + 5}px;"
            f" font-weight: bold;")
        header.addWidget(label)
        header.addWidget(self._info_button(tooltip))
        header.addStretch()

        reset_btn = QPushButton("Reset section")
        reset_btn.setObjectName("secondary")
        reset_btn.setCursor(Qt.PointingHandCursor)
        reset_btn.clicked.connect(reset)
        header.addWidget(reset_btn)
        self._content.addLayout(header)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(
            f"background: {c['border']}; max-height: 1px; border: none;")
        self._content.addWidget(line)

        grid = QGridLayout()
        grid.setContentsMargins(6, 8, 6, 18)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(1, 1)
        self._content.addLayout(grid)
        return grid

    def _row(self, grid: QGridLayout, label: str, widget, hint: str = ""):
        c = self.colors()
        row = grid.rowCount()
        name = QLabel(label)
        name.setStyleSheet(f"color: {c['fg']}; font-size: {c['fs_base'] + 1}px;")
        grid.addWidget(name, row, 0, Qt.AlignLeft | Qt.AlignVCenter)
        grid.addWidget(widget, row, 1)
        if hint:
            note = QLabel(hint)
            note.setWordWrap(True)
            note.setStyleSheet(
                f"color: {c['fg_muted']}; font-size: {c['fs_small'] + 1}px;")
            grid.addWidget(note, row + 1, 1)
        return row

    # --- binding -----------------------------------------------------------
    def _bind_combo(self, key: str, items: list, on_change=None) -> QComboBox:
        box = QComboBox()
        for value, label in items:
            box.addItem(label, value)
        current = config().get(key)
        index = box.findData(current)
        box.setCurrentIndex(index if index >= 0 else 0)

        def changed(_i):
            config().set(key, box.currentData())
            if on_change:
                on_change(box.currentData())
        box.currentIndexChanged.connect(changed)
        return box

    def _bind_check(self, key: str, text: str, on_change=None) -> QCheckBox:
        box = QCheckBox(text)
        box.setChecked(bool(config().get(key)))

        def changed(state):
            config().set(key, bool(state))
            if on_change:
                on_change(bool(state))
        box.toggled.connect(changed)
        return box

    def _bind_spin(self, key: str, low: int, high: int, suffix: str = "",
                   on_change=None) -> QSpinBox:
        box = QSpinBox()
        box.setRange(low, high)
        box.setValue(int(config().get(key) or 0))
        if suffix:
            box.setSuffix(suffix)

        def changed(value):
            config().set(key, value)
            if on_change:
                on_change(value)
        box.valueChanged.connect(changed)
        return box

    def _bind_text(self, key: str, placeholder: str = "") -> QLineEdit:
        field = QLineEdit(str(config().get(key) or ""))
        field.setPlaceholderText(placeholder)
        field.editingFinished.connect(
            lambda: config().set(key, field.text().strip()))
        return field

    def _path_row(self, key: str, placeholder: str) -> QWidget:
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        field = self._bind_text(key, placeholder)
        row.addWidget(field, 1)
        browse = QPushButton("Browse\u2026")
        browse.setObjectName("secondary")
        browse.setFixedWidth(110)

        def pick():
            path, _ = QFileDialog.getOpenFileName(self, "Select executable")
            if path:
                field.setText(path)
                config().set(key, path)
        browse.clicked.connect(pick)
        row.addWidget(browse)
        return holder

    def _reset(self, keys: list, message: str):
        def do_reset():
            answer = QMessageBox.question(
                self, "Reset section",
                f"{message}\n\nReset these to their defaults?")
            if answer != QMessageBox.Yes:
                return
            for key in keys:
                config().set(key, DEFAULTS[key])
            self.status.emit("Section reset \u2014 reopen Preferences to see it")
            self.restart_needed.emit("Preferences were reset")
        return do_reset

    # --- page --------------------------------------------------------------
    def build(self) -> None:
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }")
        inner = QWidget()
        self._content = QVBoxLayout(inner)
        self._content.setContentsMargins(4, 4, 18, 18)
        self._content.setSpacing(4)
        area.setWidget(inner)
        self.body.addWidget(area, 1)

        self._appearance()
        self._language()
        self._general()
        self._engines()
        self._terminal()
        self._catalogue()
        self._diagnostics()
        self._privileges()
        self._advanced()
        self._content.addStretch()

    # --- sections ----------------------------------------------------------
    def _appearance(self):
        grid = self._section(
            "\U0001f3a8", "Appearance",
            "Thirteen themes and a three-tier font system: headings, base "
            "text and small print are sized separately.",
            self._reset(["theme", "font_family", "font_size",
                         "font_primary_family", "font_primary_size",
                         "font_tertiary_family", "font_tertiary_size"],
                        "Theme and all three font tiers."))

        self._row(grid, "Theme",
                  self._bind_combo("theme", list(THEME_OPTIONS),
                                   self.theme_changed.emit),
                  "Eight dark and five light themes. Applied immediately.")

        families = [("", "System default")] + [
            (f, f) for f in sorted(QFontDatabase.families())[:400]]
        self._row(grid, "Base font", self._bind_combo("font_family", families))
        self._row(grid, "Base size",
                  self._bind_spin("font_size", 9, 22, " px",
                                  lambda _v: self.theme_changed.emit(
                                      config().get("theme"))),
                  "Educational text sits at this size plus five, and never "
                  "below 18px \u2014 kontainy teaches container management, "
                  "so the material has to be readable.")
        self._row(grid, "Heading size",
                  self._bind_spin("font_primary_size", 14, 34, " px"))
        self._row(grid, "Small text size",
                  self._bind_spin("font_tertiary_size", 8, 16, " px"))

    def _language(self):
        grid = self._section(
            "\U0001f310", "Language",
            "The interface is written in English. A translation layer is "
            "planned; selecting a language now records the preference.",
            self._reset(["language"], "Interface language."))
        self._row(grid, "Interface language",
                  self._bind_combo("language", LANGUAGES),
                  "Eleven languages are planned. Until the translation layer "
                  "lands, the interface stays English regardless of this "
                  "setting.")

    def _general(self):
        grid = self._section(
            "\u2699", "General",
            "Which page opens first, and how much kontainy asks before it "
            "does something.",
            self._reset(["start_page", "confirm_destructive",
                         "show_command_strip", "record_history",
                         "history_limit"],
                        "Startup page, confirmations and history."))

        self._row(grid, "Open on start",
                  self._bind_combo("start_page", list(START_PAGES)))
        self._row(grid, "", self._bind_check(
            "confirm_destructive", "Ask before anything destructive"))
        self._row(grid, "", self._bind_check(
            "show_command_strip", "Show the command strip at the bottom"),
            "The terminal equivalent of whatever you just did, ready to copy.")
        self._row(grid, "", self._bind_check(
            "record_history", "Record every command to the history"))
        self._row(grid, "History limit",
                  self._bind_spin("history_limit", 100, 100000, " entries"))

    def _engines(self):
        grid = self._section(
            "\U0001f50c", "Engines",
            "How kontainy finds and talks to Docker and Podman.",
            self._reset(["probe_timeout", "auto_refresh_seconds",
                         "docker_binary", "podman_binary",
                         "preferred_engine", "probe_ssh_endpoints"],
                        "Probe behaviour and binary paths."))

        self._row(grid, "Preferred engine",
                  self._bind_combo("preferred_engine",
                                   [("auto", "Whichever answers"),
                                    ("docker", "Docker"),
                                    ("podman", "Podman")]),
                  "Used when an action could go to either engine. kontainy "
                  "still lists every engine it finds, always.")
        self._row(grid, "Probe timeout",
                  self._bind_spin("probe_timeout", 1, 60, " s"),
                  "How long to wait for a socket to answer before calling it "
                  "unreachable.")
        self._row(grid, "Auto refresh",
                  self._bind_spin("auto_refresh_seconds", 0, 600, " s"),
                  "0 turns polling off. Both engines expose an event stream, "
                  "which is the better answer and is on the roadmap.")
        self._row(grid, "docker binary",
                  self._path_row("docker_binary", "leave empty to use PATH"))
        self._row(grid, "podman binary",
                  self._path_row("podman_binary", "leave empty to use PATH"))
        self._row(grid, "", self._bind_check(
            "probe_ssh_endpoints", "Probe ssh:// endpoints as well"),
            "Off by default: an unreachable SSH host makes every scan wait "
            "for the connection to time out.")

    def _terminal(self):
        grid = self._section(
            "\u2328", "Terminal",
            "Which terminal opens when you ask kontainy to run something in "
            "your own shell rather than for you.",
            self._reset(["terminal_emulator", "terminal_arg"],
                        "Terminal emulator and its execute flag."))
        self._row(grid, "Terminal emulator",
                  self._bind_combo("terminal_emulator", TERMINALS),
                  "Auto-detect walks the usual list and takes the first one "
                  "present.")
        self._row(grid, "Execute flag",
                  self._bind_text("terminal_arg", "-e"),
                  "Most terminals take -e; some want --  or -x instead.")

    def _catalogue(self):
        grid = self._section(
            "\U0001f5c2", "Config Catalog",
            "How the 152 Docker and Podman configuration keys are presented.",
            self._reset(["catalog_editable_only", "catalog_warnings_only",
                         "catalog_show_effective",
                         "catalog_confirm_dangerous"],
                        "Catalogue filters and confirmations."))
        self._row(grid, "", self._bind_check(
            "catalog_editable_only", "Start filtered to editable settings"),
            "65 of the 152 can be written without elevation.")
        self._row(grid, "", self._bind_check(
            "catalog_warnings_only", "Start filtered to settings with a warning"),
            "66 carry a note about what breaks when they are misunderstood.")
        self._row(grid, "", self._bind_check(
            "catalog_show_effective", "Read effective values from the engines"),
            "Runs docker info and podman info so the declared value can be "
            "compared with what the engine reports it is actually using. "
            "When they disagree, the setting is being ignored.")
        self._row(grid, "", self._bind_check(
            "catalog_confirm_dangerous",
            "Confirm before applying a dangerous setting"),
            "15 settings weaken isolation or stability.")

    def _diagnostics(self):
        grid = self._section(
            "\U0001f52c", "Diagnostics",
            "Nineteen rules that detect, explain and hand you the fix. None "
            "of them need root to detect.",
            self._reset(["diagnostics_on_start", "diagnostics_min_severity",
                         "diagnostics_disabled_rules"],
                        "Diagnostic behaviour and rule filters."))
        self._row(grid, "", self._bind_check(
            "diagnostics_on_start", "Run diagnostics when kontainy starts"))
        self._row(grid, "Minimum severity",
                  self._bind_combo("diagnostics_min_severity",
                                   [("error", "Errors only"),
                                    ("warn", "Warnings and errors"),
                                    ("info", "Everything")]))

    def _privileges(self):
        grid = self._section(
            "\U0001f512", "Privileges",
            "kontainy performs root-scoped operations, but never quietly.",
            self._reset(["allow_elevation"], "Elevation behaviour."))

        check = self._bind_check(
            "allow_elevation", "Allow privileged operations")
        check.setEnabled(can_elevate())
        self._row(grid, "", check, elevation_note())

        locked = QCheckBox("Always show the command before running it")
        locked.setChecked(True)
        locked.setEnabled(False)
        self._row(grid, "", locked,
                  "Not adjustable. Nothing in kontainy runs a command you "
                  "have not seen, and an option to turn that off would "
                  "defeat the point of the tool.")

    def _advanced(self):
        c = self.colors()
        grid = self._section(
            "\U0001f527", "Advanced",
            "Where kontainy keeps its own files, and how to start over.",
            lambda: None)

        for label, value in (("Config file", config_dir() / "config.json"),
                             ("Data folder", data_dir()),
                             ("Log file", log_path())):
            field = QLineEdit(str(value))
            field.setReadOnly(True)
            self._row(grid, label, field)

        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        reset_all = QPushButton("Reset ALL preferences")
        reset_all.setObjectName("danger")
        reset_all.clicked.connect(self._reset_everything)
        row.addWidget(reset_all)
        row.addStretch()
        self._row(grid, "", holder,
                  "Only kontainy's own preferences. Your Docker and Podman "
                  "configuration files are never touched by this.")

    def _reset_everything(self):
        answer = QMessageBox.question(
            self, "Reset all preferences",
            "Every preference on this page goes back to its default.\n\n"
            "Your Docker and Podman configuration files are not touched.\n\n"
            "Continue?")
        if answer != QMessageBox.Yes:
            return
        for key, value in DEFAULTS.items():
            if key.startswith("window_"):
                continue
            config().set(key, value)
        self.restart_needed.emit("All preferences reset")
        self.status.emit("All preferences reset \u2014 restart to see it all")
