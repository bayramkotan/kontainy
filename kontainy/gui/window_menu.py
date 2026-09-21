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

from ..core.constants import APP_NAME, APP_REPO, APP_VERSION
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

        # Page navigation belongs in View, not Tools. Built from the sidebar
        # itself, so the menu can never list a page that does not exist on
        # this operating system, or miss one that does.
        shortcuts = ["Ctrl+1", "Ctrl+2", "Ctrl+3", "Ctrl+4", "Ctrl+5",
                     "Ctrl+6", "Ctrl+7", "Ctrl+8", "Ctrl+9", "Ctrl+0"]
        for index, (name, page) in enumerate(self.pages.items()):
            action = QAction(f"{page.ICON}  {page.TITLE}", self)
            if index < len(shortcuts):
                action.setShortcut(shortcuts[index])
            if name == "preferences":
                action.setShortcut("Ctrl+,")
            action.setStatusTip(page.SUBTITLE[:120])
            action.triggered.connect(lambda _=False, n=name: self.go(n))
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

        ext_apps = QAction("\U0001f5b1 External Applications\u2026", self)
        ext_apps.setStatusTip(
            "Docker Desktop, Podman Desktop, Virtual Machine Manager, Lens, "
            "k9s, Cockpit \u2014 installed, running, installable")
        ext_apps.triggered.connect(self._open_external_apps)
        tools_menu.addAction(ext_apps)

        vmm = QAction("\U0001f5a5 Virtual Machine Manager\u2026", self)
        vmm.setStatusTip("KVM, QEMU, libvirt and virt-manager")
        vmm.triggered.connect(
            lambda: self.go("platform-libvirt")
            if "platform-libvirt" in self.pages else self._open_external_apps())
        tools_menu.addAction(vmm)



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

    def _open_external_apps(self) -> None:
        self.go("install")
        self.pages["install"].show_group("Desktop applications")

    def _show_about(self) -> None:
        from .dialogs.about import AboutDialog
        AboutDialog(self).exec()
