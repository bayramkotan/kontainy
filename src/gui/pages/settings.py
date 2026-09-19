"""kontainy — Ayarlar sayfası (katalog tarayıcısı)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QSplitter,
    QTableWidget, QTableWidgetItem, QTextBrowser, QVBoxLayout, QWidget,
)

from ...core.catalog import (
    ALL_SETTINGS, DANGER_TITLES, SURFACE_ICONS, SURFACE_TITLES,
    search as catalog_search, stats, with_gotchas,
)
from ...core.readers import CHAINS, MISSING, StateReader
from ...core.writers import WriteRefused, restart_hint, write_setting
from ...utils.workers import CallableJob, run_job
from .base import Page

DANGER_COLORS = {0: "#a6e3a1", 1: "#f9e2af", 2: "#f38ba8"}


class SettingsPage(Page):
    NAME = "settings"
    TITLE = "Settings"
    ICON = "⚙️"
    SUBTITLE = ("The entire configuration surface of Docker and Podman. Rival "
                "tools hide most of these; here they all sit, each with an "
                "explanation and a gotcha note.")

    ONLY_GOTCHAS = False

    def build(self) -> None:
        self.items = with_gotchas() if self.ONLY_GOTCHAS else list(ALL_SETTINGS)
        self.filtered = []
        self.states = {}
        self.reader = StateReader()
        self.current = None

        self.reload_btn = self.add_tool_button(
            "\U0001f504  Read values", self.refresh, kind="primary")
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText(
            "Search: key, title, description, CLI flag, tag\u2026")
        self.search_box.textChanged.connect(self._apply)
        self.toolbar.addWidget(self.search_box, 3)

        self.engine_filter = QComboBox()
        self.engine_filter.addItems(["All engines", "docker", "podman", "both"])
        self.engine_filter.currentIndexChanged.connect(self._apply)
        self.toolbar.addWidget(self.engine_filter)

        self.surface_filter = QComboBox()
        self.surface_filter.addItem("All surfaces", None)
        for key, title in SURFACE_TITLES.items():
            self.surface_filter.addItem(f"{SURFACE_ICONS.get(key, '')} {title}", key)
        self.surface_filter.currentIndexChanged.connect(self._apply)
        self.toolbar.addWidget(self.surface_filter)

        self.scope_filter = QComboBox()
        self.scope_filter.addItems(["All scopes", "user", "root"])
        self.scope_filter.currentIndexChanged.connect(self._apply)
        self.toolbar.addWidget(self.scope_filter)

        self.danger_filter = QComboBox()
        self.danger_filter.addItems(
            ["All risk levels", "Safe", "Careful", "Dangerous"])
        self.danger_filter.currentIndexChanged.connect(self._apply)
        self.toolbar.addWidget(self.danger_filter)

        # Of 152 settings roughly 65 can be written without elevation. Without
        # this filter the first screenful is all root-scoped daemon.json keys
        # and the page looks read-only.
        self.editable_only = QCheckBox("Editable only")
        self.editable_only.setToolTip(
            "Show only settings kontainy can write without elevation")
        self.editable_only.toggled.connect(self._apply)
        self.toolbar.addWidget(self.editable_only)

        split = QSplitter(Qt.Horizontal)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["", "Key", "Title", "Engine", "Declared", "Effective", "Scope",
             "Risk"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.currentCellChanged.connect(self._show_detail)
        split.addWidget(self.table)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)

        self.detail = QTextBrowser()
        self.detail.setOpenExternalLinks(True)
        rl.addWidget(self.detail, 1)

        self.editor_box = QGroupBox("Change this setting")
        el = QVBoxLayout(self.editor_box)

        self.editor_target = QLabel()
        self.editor_target.setWordWrap(True)
        el.addWidget(self.editor_target)

        row = QHBoxLayout()
        self.editor_field = QLineEdit()
        self.editor_field.setPlaceholderText("new value")
        row.addWidget(self.editor_field, 1)
        self.editor_choice = QComboBox()
        self.editor_choice.setVisible(False)
        self.editor_choice.currentTextChanged.connect(
            lambda v: self.editor_field.setText(v))
        row.addWidget(self.editor_choice, 1)
        self.editor_bool = QCheckBox("enabled")
        self.editor_bool.setVisible(False)
        self.editor_bool.toggled.connect(
            lambda v: self.editor_field.setText("true" if v else "false"))
        row.addWidget(self.editor_bool)
        el.addLayout(row)

        buttons = QHBoxLayout()
        self.apply_btn = QPushButton("Apply")
        self.apply_btn.clicked.connect(self._apply_value)
        buttons.addWidget(self.apply_btn)
        self.revert_btn = QPushButton("Reset field")
        self.revert_btn.setObjectName("secondary")
        self.revert_btn.clicked.connect(self._reset_field)
        buttons.addWidget(self.revert_btn)
        buttons.addStretch()
        self.editor_hint = QLabel()
        self.editor_hint.setWordWrap(True)
        buttons.addWidget(self.editor_hint, 1)
        el.addLayout(buttons)

        rl.addWidget(self.editor_box)
        split.addWidget(right)
        split.setSizes([700, 560])
        self.body.addWidget(split, 1)

        self.count_label = QLabel()
        self.body.addWidget(self.count_label)

        self._apply()

    def focus_key(self, key: str) -> None:
        """Teşhis veya Learn sayfasından gelen atlama."""
        self.search_box.setText(key)
        self._apply()

    def _filtered(self) -> list:
        rows = self.items
        text = self.search_box.text().strip()
        if text:
            hits = {id(s) for s in catalog_search(text)}
            rows = [s for s in rows if id(s) in hits]
        engine = self.engine_filter.currentText()
        if engine != "All engines":
            rows = [s for s in rows if s.engine == engine]
        surface = self.surface_filter.currentData()
        if surface:
            rows = [s for s in rows if s.surface == surface]
        scope = self.scope_filter.currentIndex()
        if scope == 1:
            rows = [s for s in rows if s.privilege == "user"]
        elif scope == 2:
            rows = [s for s in rows if s.privilege != "user"]
        di = self.danger_filter.currentIndex()
        if di > 0:
            rows = [s for s in rows if s.danger == di - 1]
        if self.editable_only.isChecked():
            rows = [s for s in rows if self._is_editable(s)]
        return rows

    def _is_editable(self, setting) -> bool:
        """Can kontainy write this without elevation?"""
        if setting.privilege != "user":
            return False
        if setting.file not in CHAINS:
            return False                     # a run flag, not a stored setting
        return self.reader.writable_layer(setting.file) is not None

    def _editable_mark(self, setting) -> tuple:
        if self._is_editable(setting):
            return "\u270e", "Editable here \u2014 written without elevation"
        if setting.privilege != "user":
            return "\U0001f512", ("Root-scoped: shown read-only with a "
                                   "copyable command")
        return "\u25b6", ("Runtime flag \u2014 set it when creating a "
                           "container, not in a file")

    def _apply(self) -> None:
        self.filtered = self._filtered()
        self.table.setRowCount(0)
        for s in self.filtered:
            r = self.table.rowCount()
            self.table.insertRow(r)
            state = self.states.get(s.key)
            declared_text = state.display(state.declared) if state else "\u2014"
            effective_text = state.display(state.effective) if state else "\u2014"
            mark, tip = self._editable_mark(s)
            cells = [
                mark, s.key, s.title, s.engine, declared_text, effective_text,
                "\U0001f464 user" if s.privilege == "user" else "\U0001f5a5 root",
                DANGER_TITLES[s.danger],
            ]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col == 0:
                    item.setToolTip(tip)
                elif col == 7:
                    item.setForeground(QColor(DANGER_COLORS[s.danger]))
                elif col == 4 and state and state.has_declared:
                    item.setForeground(QColor("#a6e3a1"))
                elif col == 5 and state and state.mismatch:
                    # Declared and effective disagree: the setting is being
                    # silently ignored. This is the finding, not a detail.
                    item.setForeground(QColor("#f38ba8"))
                    item.setToolTip(
                        "Declared value differs from what the engine reports "
                        "it is using \u2014 this setting is being ignored.")
                self.table.setItem(r, col, item)
        self.table.resizeColumnsToContents()

        st = stats()
        self.count_label.setText(
            f"\u270e {sum(1 for s in self.filtered if self._is_editable(s))}"
            f" editable  \u00b7  showing {len(self.filtered)}"
            f" of {len(self.items)} settings"
            f"  \u00b7  catalogue total {st['toplam']} "
            f"(docker {st['docker']} \u00b7 podman {st['podman']} "
            f"\u00b7 shared {st['ortak']})")
        if self.filtered:
            self.table.selectRow(0)

    # --- reading real values ----------------------------------------------
    def on_shown(self) -> None:
        if not self.states:
            self.refresh()

    def refresh(self) -> None:
        """Read declared and effective values for everything on screen."""
        self.reload_btn.setEnabled(False)
        self.busy.emit(True)
        self.status.emit("Reading configuration files\u2026")
        self.reader = StateReader()
        run_job(CallableJob(self.reader.states, self.items),
                self._values_ready, self._values_failed)

    def _values_ready(self, states: dict) -> None:
        self.states = states
        self.reload_btn.setEnabled(True)
        self.busy.emit(False)
        declared = sum(1 for s in states.values() if s.has_declared)
        mismatched = sum(1 for s in states.values() if s.mismatch)
        message = f"{declared} settings declared in configuration files"
        if mismatched:
            message += (f" \u00b7 \u26a0 {mismatched} declared but NOT in "
                        f"effect")
        self.status.emit(message)
        self._apply()

    def _values_failed(self, message: str) -> None:
        self.reload_btn.setEnabled(True)
        self.busy.emit(False)
        self.status.emit(f"Could not read configuration: {message}")

    # --- editing -----------------------------------------------------------
    def _load_editor(self, setting) -> None:
        """Prepare the edit widgets for one setting."""
        self.current = setting
        state = self.states.get(setting.key)
        layer = state.writable_layer if state else None

        self.editor_choice.blockSignals(True)
        self.editor_choice.clear()
        if setting.choices:
            self.editor_choice.addItems([str(c) for c in setting.choices])
            self.editor_choice.setVisible(True)
        else:
            self.editor_choice.setVisible(False)
        self.editor_choice.blockSignals(False)

        self.editor_bool.setVisible(setting.vtype == "bool")
        self._reset_field()

        writable = self._is_editable(setting)
        self.apply_btn.setEnabled(writable)
        self.editor_field.setEnabled(writable)
        self.editor_choice.setEnabled(writable)
        self.editor_bool.setEnabled(writable)

        if writable and layer is not None:
            exists = "" if layer.exists else " (the file will be created)"
            self.editor_target.setText(
                f"\u270e Writes to <code>{layer.path}</code>{exists}. "
                f"A <code>.bak</code> backup is kept, the write is atomic and "
                f"existing comments are preserved.")
            self.editor_hint.setText(restart_hint(setting))
        elif not self.states:
            self.editor_target.setText(
                "Press <b>Read values</b> first \u2014 kontainy has not read "
                "your configuration files yet.")
            self.editor_hint.setText("")
        elif setting.privilege != "user":
            self.editor_target.setText(
                f"\U0001f512 <b>Root-scoped.</b> This lives in a file only "
                f"root can write, so kontainy shows it read-only \u2014 it "
                f"never elevates. Use the command shown above instead.")
            self.editor_hint.setText(
                "Tick <i>Editable only</i> in the toolbar to hide these.")
        else:
            self.editor_target.setText(
                "\u25b6 <b>Runtime flag.</b> This is not stored in a "
                "configuration file \u2014 set it per container in "
                "<i>Containers \u2192 New Container</i>.")
            self.editor_hint.setText(
                f"CLI equivalent: <code>{setting.cli or setting.key}</code>")

    def _reset_field(self) -> None:
        setting = self.current
        if setting is None:
            return
        state = self.states.get(setting.key)
        if state is not None and state.has_declared:
            value = state.display(state.declared)
        elif setting.default is not None:
            value = state.display(setting.default) if state else str(setting.default)
        else:
            value = ""
        self.editor_field.setText(value)
        if setting.vtype == "bool":
            self.editor_bool.setChecked(str(value).lower() == "true")

    def _apply_value(self) -> None:
        setting = self.current
        if setting is None:
            return
        state = self.states.get(setting.key)
        layer = state.writable_layer if state else None
        raw = self.editor_field.text().strip()

        if setting.danger >= 2:
            answer = QMessageBox.question(
                self, "Dangerous setting",
                f"<b>{setting.title}</b> is marked dangerous.<br><br>"
                f"{setting.gotcha or setting.desc}<br><br>Apply anyway?")
            if answer != QMessageBox.Yes:
                return

        try:
            result = write_setting(setting, layer, raw)
        except WriteRefused as exc:
            QMessageBox.warning(self, "Write refused", str(exc))
            return
        except Exception as exc:                             # noqa: BLE001
            QMessageBox.critical(self, "Write failed", str(exc))
            return

        self.show_command(
            f"# {setting.key} = {raw}  \u2192  {result.path}",
            note="setting changed")
        backup = f" Backup: {result.backup}" if result.backup else ""
        QMessageBox.information(
            self, "Setting applied",
            f"{result.summary()}<br><br>"
            f"<code>{setting.key}</code>: "
            f"<b>{result.old_value}</b> \u2192 <b>{raw}</b>{backup}<br><br>"
            f"{restart_hint(setting)}")

        # Re-read only this file's chain so the selection is not lost.
        self.reader._chains.pop(setting.file, None)
        self.states[setting.key] = self.reader.state(setting)
        row = self.table.currentRow()
        self._apply()
        if 0 <= row < self.table.rowCount():
            self.table.selectRow(row)

    def _show_detail(self, row, *_) -> None:
        if row < 0 or row >= len(self.filtered):
            self.detail.clear()
            return
        s = self.filtered[row]
        p = [f"<h2 style='margin-bottom:2px'>{s.title}</h2>",
             f"<code style='font-size:12pt'>{s.key}</code>",
             f"<p>{s.desc}</p>", "<table cellpadding='4'>",
             f"<tr><td><b>Engine</b></td><td>{s.engine}</td></tr>",
             f"<tr><td><b>Surface</b></td><td>{SURFACE_ICONS.get(s.surface, '')} "
             f"{SURFACE_TITLES.get(s.surface, s.surface)}</td></tr>",
             f"<tr><td><b>Type</b></td><td>{s.vtype}</td></tr>"]
        if s.default is not None:
            p.append(f"<tr><td><b>Default</b></td>"
                     f"<td><code>{s.default}</code></td></tr>")
        if s.choices:
            p.append("<tr><td><b>Choices</b></td><td>"
                     + ", ".join(f"<code>{c}</code>" for c in s.choices)
                     + "</td></tr>")
        if s.cli:
            p.append(f"<tr><td><b>CLI equivalent</b></td>"
                     f"<td><code>{s.cli}</code></td></tr>")
        p.append(f"<tr><td><b>File</b></td><td>{s.file}</td></tr>")
        p.append("<tr><td><b>Scope</b></td><td>"
                 + ("\U0001f464 user \u2014 kontainy can write this directly"
                    if s.privilege == "user"
                    else "\U0001f5a5 root \u2014 shown read-only with a command")
                 + "</td></tr>")
        p.append(f"<tr><td><b>Restart</b></td>"
                 f"<td>{'required' if s.restart else 'not required'}</td></tr>")
        p.append(f"<tr><td><b>Risk</b></td><td style='color:"
                 f"{DANGER_COLORS[s.danger]}'>{DANGER_TITLES[s.danger]}</td></tr>")
        p.append("</table>")

        if s.gotcha:
            p.append("<div style='background:#3a2e12;border-left:4px solid #f9e2af;"
                     f"padding:9px;margin-top:12px'><b>\u26a0 Gotcha</b><br>{s.gotcha}"
                     "</div>")
        if s.tags:
            p.append("<p style='color:#9399b2'>Tags: "
                     + ", ".join(s.tags) + "</p>")
        if s.docs:
            p.append(f"<p><a href='{s.docs}'>Official documentation \u2192</a></p>")
        state = self.states.get(s.key)
        if state is not None:
            p.append("<h3 style='margin-top:14px'>On this machine</h3>")
            p.append("<table cellpadding='4'>")
            p.append(f"<tr><td><b>Declared</b></td><td><code>"
                     f"{state.display(state.declared)}</code></td></tr>")
            p.append(f"<tr><td><b>Effective</b></td><td><code>"
                     f"{state.display(state.effective)}</code></td></tr>")
            p.append(f"<tr><td><b>Source</b></td>"
                     f"<td>{state.source_label}</td></tr>")
            p.append("</table>")

            # The override chain is the thing no other tool shows: the same
            # key can live in three files and only the last one wins.
            layers = self.reader.chain(s.file)
            if layers:
                p.append("<h4>Override chain</h4><table cellpadding='3'>")
                for layer in layers:
                    mark = "\u2190 wins" if layer is state.declared_layer else ""
                    exists = "" if layer.exists else " (missing)"
                    scope = "\U0001f464" if layer.writable else "\U0001f5a5"
                    p.append(f"<tr><td>{scope} {layer.label}{exists}</td>"
                             f"<td><code>{layer.path}</code></td>"
                             f"<td>{mark}</td></tr>")
                p.append("</table>")

            if state.mismatch:
                p.append(
                    "<div style='background:#3a1620;border-left:4px solid "
                    "#f38ba8;padding:9px;margin-top:10px'><b>\u26a0 Declared "
                    "but not in effect</b><br>The file says one thing and the "
                    "engine reports another. This setting is being ignored "
                    "\u2014 either a restart is pending, or the value is not "
                    "supported in this configuration.</div>")

        self.detail.setHtml("".join(p))
        self._load_editor(s)

        if s.cli:
            self.show_command(f"# {s.key} → {s.cli}", record=False)


class GotchasPage(SettingsPage):
    NAME = "gotchas"
    TITLE = "Gotchas"
    ICON = "⚠️"
    SUBTITLE = ("Settings that burn hours when misunderstood. Listing a setting "
                "is easy; writing down what breaks when it is wrong is not, "
                "and no rival tool does it.")
    ONLY_GOTCHAS = True

    def apply_theme(self) -> None:
        super().apply_theme()
        c = self.colors()
        self.table.setStyleSheet(
            f"QTableWidget {{ font-size: {c['fs_base'] + 2}px; }}"
            f"QTableWidget::item {{ padding: 7px 10px; }}"
            f"QHeaderView::section {{ font-size: {c['fs_base'] + 1}px;"
            f" font-weight: bold; padding: 9px; }}")
