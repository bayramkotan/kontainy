"""
kontainy — About

The same shape as VenvStudio's: one message box, read top to bottom. A
heading with the version, what kontainy is, who wrote it and under which
licence, the platform and the Python and Qt it is running on, and the links
people actually click.

It was a three-tab dialog with a copyable system report. That belongs in a
bug report, not behind Help → About; when there is somewhere to put it, it
goes on the Diagnostics page, where someone is already looking for it.
"""

from __future__ import annotations

import platform
import sys

from PySide6.QtWidgets import QMessageBox

from ...core.constants import (APP_NAME, APP_REPO, APP_TAGLINE, APP_VERSION)
from ...core.registry import OS_LABEL

AUTHOR = "Bayram Kotan"
LICENSE = "MIT"
PYPI = "https://pypi.org/project/kontainy/"
GITHUB_USER = "https://github.com/bayramkotan"
LINKEDIN = "https://www.linkedin.com/in/bayramkotan"


def qt_version() -> str:
    """Read when the dialog opens, not when the module loads: the test stub
    that stands in for PySide6 in CI has no __version__, and importing it at
    module level made this file impossible to import there."""
    try:
        from PySide6.QtCore import __version__ as version
        return str(version)
    except ImportError:
        return "unknown"


def about_html() -> str:
    """The text of the dialog, separate so it can be checked without Qt."""
    return (
        f"<h2>{APP_NAME} v{APP_VERSION}</h2>"
        f"<p><b>{APP_TAGLINE}</b></p>"
        f"<p>Docker, Podman, Kubernetes, KVM, Hyper-V, Incus and LXD in one "
        f"window — and the same from the command line with <code>ky</code>.</p>"
        f"<hr>"
        f"<p><b>Author:</b> {AUTHOR}</p>"
        f"<p><b>License:</b> {LICENSE}</p>"
        f"<p><b>Platform:</b> {OS_LABEL} ({platform.machine()})</p>"
        f"<p><b>Python:</b> {sys.version.split()[0]}</p>"
        f"<p><b>Qt:</b> {qt_version()}</p>"
        f"<hr>"
        f"<p>Writing a bug report? <b>Diagnostics \u2192 System report</b> "
        f"has everything to paste, or run <code>ky report</code>.</p>"
        f"<hr>"
        f"<p>"
        f"<a href='{APP_REPO}'>GitHub</a> &nbsp;|&nbsp; "
        f"<a href='{PYPI}'>PyPI</a> &nbsp;|&nbsp; "
        f"<a href='{GITHUB_USER}'>github.com/bayramkotan</a> &nbsp;|&nbsp; "
        f"<a href='{LINKEDIN}'>LinkedIn</a>"
        f"</p>")


def show_about(parent=None) -> None:
    QMessageBox.about(parent, f"About {APP_NAME}", about_html())
