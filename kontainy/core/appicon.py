"""
kontainy — finding the application's own icon

Three places need it: the window's title bar, the taskbar, and the desktop
shortcut. A fourth copy of this search is what made the equivalent code in
VenvStudio wrong, so there is one function and everything calls it.

The order matters. An INSTALLED copy must find its own files rather than a
repository that happens to be lying around, so sys.prefix comes first, then
a frozen bundle, then the checkout. Without that, running the installed
kontainy from a directory that contains a git clone would use the clone's
icon — and when the clone changed, the installed application would change
with it.
"""

from __future__ import annotations

import sys
from pathlib import Path

#: Installed names, in the order data-files puts them there.
_INSTALLED = [
    "share/icons/hicolor/512x512/apps/icon-512.png",
    "share/pixmaps/icon.png",
    "share/kontainy/icon-1024.png",
]
_ICO = "share/kontainy/icon.ico"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def find_icon(ext: str = ".png") -> Path | None:
    """The best icon available, or None — never a guess.

    Returning None is a real answer: a shortcut with no icon shows the
    desktop's generic one, which is honest. VenvStudio used to write
    `Icon=/usr/bin/venvstudio` instead, and a desktop that cannot read an
    ELF binary showed the shortcut as broken.
    """
    names = [_ICO] + _INSTALLED if ext == ".ico" else _INSTALLED
    for name in names:
        candidate = Path(sys.prefix) / name
        if candidate.is_file():
            return candidate

    if getattr(sys, "frozen", False):                  # PyInstaller
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        for name in ("icon.ico", "icon-512.png", "icon.png"):
            candidate = base / name
            if candidate.is_file() and candidate.suffix == ext:
                return candidate

    assets = _repo_root() / "assets"
    for name in (("icon.ico",) if ext == ".ico"
                 else ("icon-512.png", "icon.png", "icon-1024.png")):
        candidate = assets / name
        if candidate.is_file():
            return candidate
    return None


def set_window_icon(widget) -> None:
    """Give a window the application's icon, where there is one."""
    path = find_icon(".ico" if sys.platform == "win32" else ".png")
    if path is None:
        return
    from PySide6.QtGui import QIcon
    widget.setWindowIcon(QIcon(str(path)))


def claim_taskbar_identity() -> None:
    """Windows: without this the taskbar shows Python's icon.

    An application started through pythonw or a pip-generated wrapper is
    grouped under Python unless it declares its own AppUserModelID, and no
    amount of setWindowIcon changes that.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "bayramkotan.kontainy")
    except (AttributeError, OSError):
        pass
