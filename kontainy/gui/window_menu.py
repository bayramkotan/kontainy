"""
kontainy — Menu bar

Ported from VenvStudio's ``window_menu.py`` structure: File, View, Tools,
Help — in that order, with the same shortcut conventions (Ctrl+Q to quit,
F5 to refresh) and the same emoji-prefixed action labels.

The View menu lists every theme registered in ``styles.THEME_OPTIONS`` rather
than only Dark/Light, because kontainy ships all thirteen and a two-entry
theme menu would hide eleven of them.
"""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QAction, QActionGroup, QDesktopServices
from PySide6.QtWidgets import QMenu, QMessageBox

from ..core.catalog import stats as catalog_stats
from ..core.constants import APP_NAME, APP_REPO, APP_VERSION
from ..learn.content import learn_stats
from ..rules import rule_stats
from ..utils.config import config, config_dir, data_dir
from .styles import THEME_OPTIONS


class WindowMenuMixin:
    """Mixin for MainWindow: builds and owns the menu bar."""

    def _setup_menubar(self) -> None:
        menubar = self.menuBar()

        # ── File ──────────────────────────────────────────────────────────
        file_menu = menubar.addMenu("&File")

        new_container = QAction("\u2795 &New Container\u2026", self)
        new_container.setShortcut("Ctrl+N")
        new_container.setStatusTip(
            "Create a container with the full set of run flags")
        new_container.triggered.connect(self._menu_new_container)
        file_menu.addAction(new_container)

        from_template = QAction("\U0001f4e6 New from &Template\u2026", self)
        from_template.setShortcut("Ctrl+Shift+N")
        from_template.setStatusTip(
            "Ready-made definitions \u2014 no hunting for example code")
        from_template.triggered.connect(self._menu_from_template)
        file_menu.addAction(from_template)

        file_menu.addSeparator()

        rescan = QAction("\U0001f501 &Rescan Engines", self)
        rescan.setShortcut("Ctrl+R")
        rescan.setStatusTip("Probe every Docker and Podman socket again")
        rescan.triggered.connect(lambda: self._menu_refresh("engines"))
        file_menu.addAction(rescan)

        doctor = QAction("\U0001f52c Run &Diagnostics", self)
        doctor.setShortcut("Ctrl+D")
        doctor.setStatusTip("Run every diagnostic rule against this system")
        doctor.triggered.connect(lambda: self._menu_refresh("diagnostics"))
        file_menu.addAction(doctor)

        file_menu.addSeparator()

        export_history = QAction("\U0001f4be Export Command History\u2026", self)
        export_history.setStatusTip(
            "Write every command kontainy has shown you to a shell script")
        export_history.triggered.connect(self._export_history)
        file_menu.addAction(export_history)

        file_menu.addSeparator()

        quit_action = QAction("\u274c Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # ── View ──────────────────────────────────────────────────────────
        view_menu = menubar.addMenu("&View")

        refresh = QAction("\U0001f504 Refresh Current Page", self)
        refresh.setShortcut("F5")
        refresh.triggered.connect(self._menu_refresh_current)
        view_menu.addAction(refresh)
        view_menu.addSeparator()

        theme_menu = QMenu("\U0001f3a8 Theme", self)
        self._theme_group = QActionGroup(self)
        self._theme_group.setExclusive(True)
        current_theme = config().get("theme", "dark")
        for name, label in THEME_OPTIONS:
            action = QAction(label, self)
            action.setCheckable(True)
            action.setChecked(name == current_theme)
            action.triggered.connect(lambda _=False, n=name: self.set_theme(n))
            self._theme_group.addAction(action)
            theme_menu.addAction(action)
        view_menu.addMenu(theme_menu)
        view_menu.addSeparator()

        strip = QAction("\u2328 Show Command Strip", self)
        strip.setCheckable(True)
        strip.setChecked(bool(config().get("show_command_strip", True)))
        strip.setStatusTip(
            "Show the terminal equivalent of each action at the bottom")
        strip.triggered.connect(self._toggle_command_strip)
        view_menu.addAction(strip)
        self._strip_action = strip

        view_menu.addSeparator()

        # Page navigation belongs in View, not Tools. Tools is for things that
        # act on the system; View is for what you are looking at.
        for icon, label, page, shortcut, tip in (
            ("\U0001f50c", "Engines", "engines", "Ctrl+1",
             "Every socket found, and where your terminal points"),
            ("\U0001f4e6", "Containers", "containers", "Ctrl+2",
             "Containers from every engine, in one table"),
            ("\u2699", "Settings", "settings", "Ctrl+3",
             "Every Docker and Podman configuration key"),
            ("\u26a0", "Gotchas", "gotchas", "Ctrl+4",
             "Settings that burn hours when misunderstood"),
            ("\U0001f52c", "Diagnostics", "diagnostics", "Ctrl+5",
             "Detect, explain, fix"),
            ("\U0001f4da", "Learn", "learn", "Ctrl+6",
             "Containers from first principles"),
            ("\U0001f4dd", "History & Log", "log", "Ctrl+7",
             "Every command kontainy has run"),
        ):
            action = QAction(f"{icon} {label}", self)
            action.setShortcut(shortcut)
            action.setStatusTip(tip)
            action.triggered.connect(lambda _=False, name=page: self.go(name))
            view_menu.addAction(action)

        # ── Tools ─────────────────────────────────────────────────────────
        tools_menu = menubar.addMenu("&Tools")

        open_logs = QAction("\U0001f4c1 Open Data Folder", self)
        open_logs.setStatusTip(str(data_dir()))
        open_logs.triggered.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(data_dir()))))
        tools_menu.addAction(open_logs)

        open_config = QAction("\u2699 Open Config Folder", self)
        open_config.setStatusTip(str(config_dir()))
        open_config.triggered.connect(
            lambda: QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(config_dir()))))
        tools_menu.addAction(open_config)

        tools_menu.addSeparator()

        new_container_t = QAction("\u2795 New Container\u2026", self)
        new_container_t.triggered.connect(self._menu_new_container)
        tools_menu.addAction(new_container_t)

        from_template_t = QAction("\U0001f4e6 New from Template\u2026", self)
        from_template_t.triggered.connect(self._menu_from_template)
        tools_menu.addAction(from_template_t)

        # ── Help ──────────────────────────────────────────────────────────
        help_menu = menubar.addMenu("&Help")

        about = QAction(f"\u2139 About {APP_NAME}", self)
        about.triggered.connect(self._show_about)
        help_menu.addAction(about)

        help_menu.addSeparator()

        github = QAction("\U0001f419 GitHub Repository", self)
        github.triggered.connect(
            lambda: QDesktopServices.openUrl(QUrl(APP_REPO)))
        help_menu.addAction(github)

        issues = QAction("\U0001f41b Report an Issue", self)
        issues.triggered.connect(
            lambda: QDesktopServices.openUrl(QUrl(f"{APP_REPO}/issues")))
        help_menu.addAction(issues)

        help_menu.addSeparator()

        for label, url in (
            ("Docker Engine docs", "https://docs.docker.com/engine/"),
            ("Podman docs", "https://docs.podman.io/"),
            ("Quadlet reference",
             "https://docs.podman.io/en/latest/markdown/podman-systemd.unit.5.html"),
            ("Kubernetes docs", "https://kubernetes.io/docs/home/"),
        ):
            action = QAction(f"\U0001f517 {label}", self)
            action.triggered.connect(
                lambda _=False, u=url: QDesktopServices.openUrl(QUrl(u)))
            help_menu.addAction(action)

    # --- handlers ----------------------------------------------------------
    def _menu_new_container(self) -> None:
        self.go("containers")
        self.pages["containers"]._new_container()

    def _menu_from_template(self) -> None:
        self.go("containers")
        self.pages["containers"]._from_template()

    def _menu_refresh(self, page_name: str) -> None:
        self.go(page_name)
        page = self.pages.get(page_name)
        if page is not None:
            page.refresh()

    def _menu_refresh_current(self) -> None:
        page = self.stack.currentWidget()
        if page is not None:
            page.refresh()

    def _toggle_command_strip(self, checked: bool) -> None:
        config().set("show_command_strip", bool(checked))
        for page in self.pages.values():
            page.command_strip.setVisible(bool(checked))

    def _export_history(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        from ..utils.config import history

        path, _ = QFileDialog.getSaveFileName(
            self, "Export command history", "kontainy-commands.sh",
            "Shell script (*.sh);;All files (*)")
        if not path:
            return
        lines = ["#!/usr/bin/env bash",
                 f"# Command history exported from {APP_NAME} v{APP_VERSION}",
                 "# These are the commands kontainy showed you, in order.",
                 "# Review before running any of them.", ""]
        for entry in history().entries():
            note = f"  # {entry['note']}" if entry.get("note") else ""
            lines.append(f"# {entry.get('at', '')}{note}")
            lines.append(entry.get("command", ""))
            lines.append("")
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("\n".join(lines))
        except OSError as exc:
            QMessageBox.warning(self, "Export failed", str(exc))
            return
        self._set_status(f"Command history exported to {path}")

    def _show_about(self) -> None:
        cs = catalog_stats()
        rs = rule_stats()
        ls = learn_stats()
        QMessageBox.about(
            self, f"About {APP_NAME}",
            f"<h2>{APP_NAME} v{APP_VERSION}</h2>"
            "<p>Every Docker and Podman setting, in one interface.</p>"
            "<table cellpadding='4'>"
            f"<tr><td><b>Settings catalogue</b></td><td>{cs['total']} keys "
            f"({cs['docker']} docker, {cs['podman']} podman, "
            f"{cs['shared']} shared)</td></tr>"
            f"<tr><td><b>User scope</b></td><td>{cs['user_scope']} keys "
            "kontainy can write without elevation</td></tr>"
            f"<tr><td><b>Gotchas</b></td><td>{cs['gotchas']} keys carry a "
            "warning note</td></tr>"
            f"<tr><td><b>Diagnostic rules</b></td><td>{rs['total']} "
            f"({rs['error']} error, {rs['warning']} warning, "
            f"{rs['info']} info)</td></tr>"
            f"<tr><td><b>Learn</b></td><td>{ls['written']}/{ls['target']} topics "
            f"across {ls['categories']} categories</td></tr>"
            "</table>"
            "<p>kontainy never elevates privileges. Root-scoped settings are "
            "shown read-only with a copyable command.</p>"
            f"<p><a href='{APP_REPO}'>{APP_REPO}</a></p>")
