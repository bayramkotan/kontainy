"""
kontainy — About

The old About was a one-shot QMessageBox with a table crammed into it and a
local log path nobody wanted on screen. This is a real dialog: the logo, the
version, the links people actually click, what kontainy currently knows, and
a system summary that can be copied straight into a bug report.

That last part is the reason it exists. "It does not work on my machine" is
unanswerable; the same sentence with the Python version, the Qt version, the
distribution and which engines were found is a bug report.
"""

from __future__ import annotations

import platform
import sys

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices, QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QTabWidget, QTextBrowser,
    QVBoxLayout, QWidget,
)

from ...core.catalog import stats as catalog_stats
from ...core.constants import APP_NAME, APP_REPO, APP_TAGLINE, APP_VERSION
from ...core.registry import OS_LABEL
from ...core.registry import stats as registry_stats
from ...learn.content import learn_stats
from ...rules import rule_stats
from ...utils.config import config, config_dir, data_dir, log_path
from ..styles import get_colors

PYPI_URL = "https://pypi.org/project/kontainy/"


def _icon_path():
    from pathlib import Path
    here = Path(__file__).resolve().parents[3]
    for candidate in (here / "assets" / "icon.png",
                      here / "assets" / "icon-512.png"):
        if candidate.is_file():
            return candidate
    return None


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"About {APP_NAME}")
        self.resize(720, 620)
        self._build()

    def _c(self) -> dict:
        return get_colors(config().get("theme", "dark"),
                          config().get("font_size", 13),
                          config().get("font_primary_size", 22),
                          config().get("font_tertiary_size", 11))

    def _build(self):
        c = self._c()
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # --- header -------------------------------------------------------
        header = QHBoxLayout()
        icon = _icon_path()
        if icon:
            image = QLabel()
            image.setPixmap(QPixmap(str(icon)).scaled(
                96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            header.addWidget(image)

        titles = QVBoxLayout()
        name = QLabel(APP_NAME)
        name.setStyleSheet(
            f"color: {c['accent']}; font-size: {c['fs_header'] + 8}px;"
            f" font-weight: bold;")
        titles.addWidget(name)
        version = QLabel(f"version {APP_VERSION}")
        version.setStyleSheet(
            f"color: {c['fg_muted']}; font-size: {c['fs_base'] + 2}px;")
        titles.addWidget(version)
        tagline = QLabel(APP_TAGLINE)
        tagline.setWordWrap(True)
        tagline.setStyleSheet(f"color: {c['fg']}; font-size: {c['fs_base'] + 2}px;")
        titles.addWidget(tagline)
        titles.addStretch()
        header.addLayout(titles, 1)
        layout.addLayout(header)

        # --- links --------------------------------------------------------
        links = QHBoxLayout()
        for label, url in (("\U0001f4e6  PyPI", PYPI_URL),
                           ("\U0001f419  GitHub", APP_REPO),
                           ("\U0001f41b  Issues", f"{APP_REPO}/issues"),
                           ("\U0001f4dc  Releases", f"{APP_REPO}/releases")):
            button = QPushButton(label)
            button.setObjectName("secondary")
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(
                lambda _=False, u=url: QDesktopServices.openUrl(QUrl(u)))
            links.addWidget(button)
        links.addStretch()
        layout.addLayout(links)

        # --- tabs ---------------------------------------------------------
        tabs = QTabWidget()
        tabs.addTab(self._tab(self._about_html()), "About")
        tabs.addTab(self._tab(self._system_html()), "System")
        tabs.addTab(self._tab(self._license_html()), "License")
        layout.addWidget(tabs, 1)

        # --- buttons ------------------------------------------------------
        row = QHBoxLayout()
        copy_btn = QPushButton("\U0001f4cb  Copy system info")
        copy_btn.setObjectName("secondary")
        copy_btn.setToolTip("Paste this into a bug report")
        copy_btn.clicked.connect(self._copy_system)
        row.addWidget(copy_btn)
        row.addStretch()
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        layout.addLayout(row)

    def _tab(self, html: str) -> QWidget:
        view = QTextBrowser()
        view.setOpenExternalLinks(True)
        view.setHtml(html)
        return view

    # --- content -----------------------------------------------------------
    def _about_html(self) -> str:
        c = self._c()
        cs, rs, ls, ts = (catalog_stats(), rule_stats(), learn_stats(),
                          registry_stats())
        return f"""
        <p>kontainy shows the configuration surface that Docker Desktop and
        Podman Desktop hide, explains what each setting does, and says what
        breaks when it is set wrong.</p>

        <h3>What it currently knows</h3>
        <table cellpadding='5'>
          <tr><td><b>Settings catalogue</b></td>
              <td>{cs['total']} keys — {cs['docker']} docker,
                  {cs['podman']} podman, {cs['shared']} shared</td></tr>
          <tr><td><b>Writable without elevation</b></td>
              <td>{cs['user_scope']} keys</td></tr>
          <tr><td><b>Carrying a warning</b></td>
              <td>{cs['gotchas']} keys explain what goes wrong</td></tr>
          <tr><td><b>Diagnostic rules</b></td>
              <td>{rs['total']} — {rs['error']} error, {rs['warning']}
                  warning, {rs['info']} info</td></tr>
          <tr><td><b>Tools known</b></td>
              <td>{ts['total']} across {ts['groups']} groups,
                  {ts['installed']} installed here</td></tr>
          <tr><td><b>Learn</b></td>
              <td>{ls['written']} of {ls['target']} topics across
                  {ls['categories']} categories</td></tr>
        </table>

        <h3>Principles</h3>
        <ul>
          <li><b>It never trusts the context system.</b> Every socket found
              is probed separately and shown together, so a container is
              never lost.</li>
          <li><b>It never runs a command you have not seen.</b> Privileged
              work goes through your desktop's own authentication dialog;
              kontainy never handles a password.</li>
          <li><b>It never claims to do what it cannot.</b>
              <code>unset DOCKER_HOST</code> cannot be performed for you —
              a child process cannot change its parent's environment — so
              kontainy finds which file sets it instead.</li>
        </ul>

        <p style='color:{c['fg_muted']}'>Built with Python and PySide6.
        Talks to both engines over the Docker Engine API directly, with no
        client library.</p>
        """

    def _system_summary(self) -> str:
        return "\n".join([
            f"kontainy {APP_VERSION}",
            f"Python   {sys.version.split()[0]} ({platform.python_implementation()})",
            f"Qt       {self._qt_version()}",
            f"System   {platform.system()} {platform.release()}",
            f"Distro   {OS_LABEL}",
            f"Machine  {platform.machine()}",
            f"Config   {config_dir()}",
            f"Data     {data_dir()}",
        ])

    def _qt_version(self) -> str:
        try:
            from PySide6 import __version__ as pyside
            from PySide6.QtCore import qVersion
            return f"{qVersion()} (PySide6 {pyside})"
        except Exception:                                    # noqa: BLE001
            return "unknown"

    def _system_html(self) -> str:
        c = self._c()
        return (f"<p>Copy this into a bug report. \"It does not work on my "
                f"machine\" cannot be answered; the same sentence with these "
                f"lines can.</p>"
                f"<pre style='background:{c['input_bg']};padding:12px;"
                f"border-radius:8px'>{self._system_summary()}</pre>"
                f"<p style='color:{c['fg_muted']}'>Log file: "
                f"<code>{log_path()}</code></p>")

    def _license_html(self) -> str:
        return f"""
        <h3>MIT License</h3>
        <p>Copyright &copy; 2026 Bayram Kotan</p>
        <p>Permission is hereby granted, free of charge, to any person
        obtaining a copy of this software and associated documentation files
        (the "Software"), to deal in the Software without restriction,
        including without limitation the rights to use, copy, modify, merge,
        publish, distribute, sublicense, and/or sell copies of the Software,
        and to permit persons to whom the Software is furnished to do so,
        subject to the following conditions:</p>
        <p>The above copyright notice and this permission notice shall be
        included in all copies or substantial portions of the Software.</p>
        <p>THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
        EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
        MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
        NONINFRINGEMENT.</p>
        <p><a href="{APP_REPO}/blob/main/LICENSE">Full text on GitHub</a></p>
        """

    def _copy_system(self):
        QGuiApplication.clipboard().setText(self._system_summary())
