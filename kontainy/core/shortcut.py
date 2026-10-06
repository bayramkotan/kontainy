"""
kontainy — a desktop shortcut

Installed from PyPI, kontainy is a command. Most people expect an icon they
can click, and making one is three different jobs on three platforms.

The traps here were paid for once already in VenvStudio:

* A `.desktop` file must name its icon by NAME, not by path, when kontainy
  lives in a virtual environment — no desktop environment looks inside a
  venv's share directory. So the icon is COPIED into the user's own icon
  theme first.
* If there is no icon, the `Icon=` line is left out entirely. Writing
  `Icon=/usr/bin/kontainy` points at an ELF binary, and a desktop that
  cannot read it shows the shortcut as broken. No line means the generic
  application icon, which is an honest answer.
* A Windows `.lnk` without an explicit IconLocation uses the icon of the
  target executable — and that executable is a pip-generated wrapper
  carrying PYTHON's icon.
* The shortcut must start the SAME interpreter kontainy is running in, not
  whatever `kontainy` resolves to on PATH, which may be another
  environment entirely.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from .constants import APP_NAME, APP_TAGLINE

#: Where the icon is copied so a desktop environment can find it by name.
ICON_NAME = "kontainy"
HICOLOR = Path.home() / ".local/share/icons/hicolor/512x512/apps"


def launcher() -> list:
    """The command the shortcut runs.

    The interpreter running right now, not a name on PATH: the shortcut of
    a kontainy installed in one environment must not start another one.
    """
    gui = Path(sys.executable).with_name(
        "kontainy-gui.exe" if os.name == "nt" else "kontainy-gui")
    if gui.is_file():
        return [str(gui)]
    return [sys.executable, "-m", "kontainy"]


def desktop_dir() -> Path:
    """The user's desktop, asked of the system rather than guessed.

    xdg-user-dir knows the localised name; "Desktop" is only the English
    default and on a Turkish system the directory is "Masaüstü".
    """
    if shutil.which("xdg-user-dir"):
        try:
            out = subprocess.run(["xdg-user-dir", "DESKTOP"],
                                 capture_output=True, text=True, timeout=5)
            path = Path((out.stdout or "").strip())
            if path.is_dir():
                return path
        except (OSError, subprocess.SubprocessError):
            pass
    for name in ("Desktop", "Masaüstü", "Schreibtisch", "Bureau"):
        candidate = Path.home() / name
        if candidate.is_dir():
            return candidate
    return Path.home()


# --- Linux --------------------------------------------------------------------
def install_icon() -> str:
    """Copy the icon into the user's theme; return the name to use, or ""."""
    from .appicon import find_icon
    source = find_icon(".png")
    if source is None:
        return ""
    try:
        HICOLOR.mkdir(parents=True, exist_ok=True)
        target = HICOLOR / f"{ICON_NAME}.png"
        shutil.copyfile(source, target)
    except OSError:
        return ""
    if shutil.which("gtk-update-icon-cache"):
        subprocess.run(["gtk-update-icon-cache", "-f", "-t",
                        str(HICOLOR.parents[2])],
                       capture_output=True, timeout=30, check=False)
    return ICON_NAME


def desktop_entry(icon: str = "") -> str:
    command = " ".join(launcher())
    lines = ["[Desktop Entry]",
             "Type=Application",
             f"Name={APP_NAME}",
             f"Comment={APP_TAGLINE}",
             f"Exec={command}",
             "Terminal=false",
             "Categories=Development;System;",
             "Keywords=docker;podman;container;kubernetes;kvm;virtualisation;",
             f"StartupWMClass={APP_NAME}"]
    # No icon: no line at all. A line pointing at something that is not an
    # image is what makes a desktop show the shortcut as broken.
    if icon:
        lines.insert(5, f"Icon={icon}")
    return "\n".join(lines) + "\n"


def _write_linux(both: bool = True) -> list:
    icon = install_icon()
    text = desktop_entry(icon)
    written = []
    applications = Path.home() / ".local/share/applications"
    applications.mkdir(parents=True, exist_ok=True)
    menu_entry = applications / f"{ICON_NAME}.desktop"
    menu_entry.write_text(text, encoding="utf-8")
    menu_entry.chmod(0o755)
    written.append(menu_entry)

    if both:
        target = desktop_dir() / f"{ICON_NAME}.desktop"
        target.write_text(text, encoding="utf-8")
        target.chmod(0o755)
        # GNOME refuses to run a .desktop file it does not trust.
        if shutil.which("gio"):
            subprocess.run(["gio", "set", str(target),
                            "metadata::trusted", "true"],
                           capture_output=True, timeout=10, check=False)
        written.append(target)

    if shutil.which("update-desktop-database"):
        subprocess.run(["update-desktop-database", str(applications)],
                       capture_output=True, timeout=30, check=False)
    return written


# --- Windows ------------------------------------------------------------------
def _powershell_script(target: Path) -> str:
    from .appicon import find_icon
    argv = launcher()
    icon = find_icon(".ico")
    command = argv[0].replace("'", "''")
    arguments = " ".join(argv[1:]).replace("'", "''")
    lines = ["$ws = New-Object -ComObject WScript.Shell",
             f"$s = $ws.CreateShortcut('{str(target)}')",
             f"$s.TargetPath = '{command}'",
             f"$s.Arguments = '{arguments}'",
             f"$s.WorkingDirectory = '{str(Path.home())}'",
             f"$s.Description = '{APP_TAGLINE}'"]
    # Without this the shortcut shows the icon of the pip-generated wrapper,
    # which is Python's.
    if icon is not None:
        lines.append(f"$s.IconLocation = '{str(icon)}'")
    lines.append("$s.Save()")
    return "; ".join(lines)


def _write_windows(both: bool = True) -> list:
    written = []
    targets = [Path(os.environ.get("APPDATA", Path.home()))
               / "Microsoft/Windows/Start Menu/Programs" / f"{APP_NAME}.lnk"]
    if both:
        targets.append(desktop_dir() / f"{APP_NAME}.lnk")
    for target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             _powershell_script(target)],
            capture_output=True, text=True, timeout=60)
        if result.returncode == 0 and target.is_file():
            written.append(target)
    return written


# --- macOS --------------------------------------------------------------------
def _write_macos(both: bool = True) -> list:
    """A .command file: double-clickable, and no app bundle to sign."""
    target = desktop_dir() / f"{APP_NAME}.command"
    target.write_text("#!/bin/sh\nexec " + " ".join(launcher()) + "\n",
                      encoding="utf-8")
    target.chmod(0o755)
    return [target]


def create(both: bool = True) -> list:
    """Make the shortcut; returns the files written."""
    if sys.platform == "win32":
        return _write_windows(both)
    if sys.platform == "darwin":
        return _write_macos(both)
    return _write_linux(both)


def describe() -> str:
    """What create() would write, for the dialog that asks first."""
    if sys.platform == "win32":
        return (f"A .lnk shortcut in the Start menu and on the desktop, "
                f"starting {' '.join(launcher())}")
    if sys.platform == "darwin":
        return f"A .command file on the desktop, starting {' '.join(launcher())}"
    return (f"A .desktop entry in the application menu and on the desktop, "
            f"starting {' '.join(launcher())}")
