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

And one paid for here, in 0.1.5:

* ⚠️ In a SOURCE CHECKOUT the shortcut must not point at the pip-generated
  `kontainy-gui` wrapper. That wrapper is the single most short-lived file
  in a checkout: it exists only while kontainy itself is pip-installed into
  `.venv`, and the ordinary clone-and-run flow
  (`python -m venv .venv` + `pip install -r requirements.txt`) does not put
  it back. A shortcut made on Monday then dies with

      Could not find the program '…/kontainy/.venv/bin/kontainy-gui'

  while kontainy itself still runs perfectly. So a checkout's shortcut runs
  `main.py` instead — which is in git, survives every rebuild of the
  environment, and knows how to set the environment up again by itself.

Nothing here is written without checking first that what it points at
exists. A shortcut is seen again only when it is clicked, which is the
worst moment to discover it is wrong.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from .constants import APP_NAME, APP_TAGLINE

#: Where the icon is copied so a desktop environment can find it by name.
ICON_NAME = "kontainy"
HICOLOR = Path.home() / ".local/share/icons/hicolor/512x512/apps"


class ShortcutError(OSError):
    """The shortcut cannot be written, with the reason in plain words.

    An OSError subclass on purpose: the caller already handles those, and a
    shortcut that cannot be written IS a filesystem problem.
    """


# --- what the shortcut runs -----------------------------------------------------
def checkout_main() -> Path | None:
    """``main.py`` of the checkout kontainy is running from, or None.

    An installed copy has no such file — `main.py` is deliberately left out
    of the wheel — so this is also the test for "am I a checkout".
    """
    root = Path(__file__).resolve().parents[2]
    if (root / "main.py").is_file() and (root / "pyproject.toml").is_file():
        return root / "main.py"
    return None


def script_dirs() -> list:
    """Where pip put THIS installation's commands.

    Beside `sys.executable` is right for a venv and for pipx, and wrong for
    `pip install --user`, where the interpreter is `/usr/bin/python3` and
    the command is in `~/.local/bin`. Asked of sysconfig rather than
    guessed, and PATH is never consulted: a `kontainy` on PATH may belong
    to a completely different installation.
    """
    import sysconfig
    found = [Path(sys.executable).parent]
    schemes = [None, "nt_user" if os.name == "nt" else "posix_user"]
    for scheme in schemes:
        try:
            path = (sysconfig.get_path("scripts") if scheme is None
                    else sysconfig.get_path("scripts", scheme))
        except (KeyError, ValueError):
            continue
        candidate = Path(path)
        if candidate not in found:
            found.append(candidate)
    return found


def launcher() -> list:
    """The command the shortcut runs.

    The interpreter running right now, not a name on PATH: the shortcut of
    a kontainy installed in one environment must not start another one.

    In a checkout this runs `main.py`, which outlives the environment. Only
    an installed copy uses the `kontainy-gui` wrapper — and there it is the
    right answer, because on Windows it opens the window with no console
    behind it, and it comes back whenever the package does.
    """
    main_py = checkout_main()
    if main_py is not None:
        return [sys.executable, str(main_py)]

    name = "kontainy-gui.exe" if os.name == "nt" else "kontainy-gui"
    for directory in script_dirs():
        gui = directory / name
        if gui.is_file():
            return [str(gui)]
    return [sys.executable, "-m", "kontainy"]


def working_dir() -> Path:
    """Where the shortcut starts.

    The checkout, so `python -m kontainy` and every relative path in it
    resolve; the home directory otherwise, which is where a file dialog
    should open.
    """
    main_py = checkout_main()
    return main_py.parent if main_py is not None else Path.home()


def verify(argv: list | None = None) -> None:
    """Refuse to write a shortcut that cannot start. Raises ShortcutError.

    Everything a shortcut points at is an absolute path recorded once, and
    a wrong one is invisible until the day it is clicked. Checked here,
    while there is still someone watching.
    """
    argv = argv or launcher()
    program = Path(argv[0])
    if not program.is_file():
        raise ShortcutError(
            f"the program the shortcut would run does not exist: {program}")
    if len(argv) > 1 and not argv[1].startswith("-"):
        script = Path(argv[1])
        if not script.is_file():
            raise ShortcutError(
                f"the script the shortcut would run does not exist: {script}")


# --- an existing shortcut -------------------------------------------------------
def existing() -> list:
    """Shortcut files already written, whichever platform this is."""
    if sys.platform == "win32":
        names = [Path(os.environ.get("APPDATA", Path.home()))
                 / "Microsoft/Windows/Start Menu/Programs" / f"{APP_NAME}.lnk",
                 desktop_dir() / f"{APP_NAME}.lnk"]
    elif sys.platform == "darwin":
        names = [desktop_dir() / f"{APP_NAME}.command"]
    else:
        names = [Path.home() / ".local/share/applications"
                 / f"{ICON_NAME}.desktop",
                 desktop_dir() / f"{ICON_NAME}.desktop"]
    return [path for path in names if path.is_file()]


def broken() -> str:
    """The program a stale shortcut points at, or "" if nothing is stale.

    Only the text formats can be read back — a `.lnk` is a binary structure
    and reading it needs the COM object that wrote it. Linux and macOS are
    where the problem lives anyway: the venv is in the checkout there.
    """
    if sys.platform == "win32":
        return ""
    for path in existing():
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            if line.startswith("Exec="):
                command = line[len("Exec="):]
            elif line.startswith("exec "):
                command = line[len("exec "):]
            else:
                continue
            try:
                argv = shlex.split(command)
            except ValueError:
                continue
            if argv and not Path(argv[0]).is_file():
                return argv[0]
    return ""


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


def _exec_value(argv: list) -> str:
    """One Exec= line, quoted the way the Desktop Entry spec asks.

    A path with a space in it — `/home/me/My Projects/kontainy/main.py` —
    is read as two arguments unquoted, and the shortcut fails with half a
    filename in the error.
    """
    parts = []
    for item in argv:
        if any(ch in item for ch in ' \t"\'\\><~|&;$*?#()`'):
            escaped = item.replace("\\", "\\\\").replace('"', '\\"')
            parts.append(f'"{escaped}"')
        else:
            parts.append(item)
    return " ".join(parts)


def desktop_entry(icon: str = "") -> str:
    lines = ["[Desktop Entry]",
             "Type=Application",
             f"Name={APP_NAME}",
             f"Comment={APP_TAGLINE}",
             f"Exec={_exec_value(launcher())}",
             f"Path={working_dir()}",
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
    arguments = " ".join(f'"{a}"' if " " in a else a
                         for a in argv[1:]).replace("'", "''")
    lines = ["$ws = New-Object -ComObject WScript.Shell",
             f"$s = $ws.CreateShortcut('{str(target)}')",
             f"$s.TargetPath = '{command}'",
             f"$s.Arguments = '{arguments}'",
             f"$s.WorkingDirectory = '{str(working_dir())}'",
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
    argv = launcher()
    quoted = " ".join(f'"{a}"' if " " in a else a for a in argv)
    target.write_text(f'#!/bin/sh\ncd "{working_dir()}"\nexec {quoted}\n',
                      encoding="utf-8")
    target.chmod(0o755)
    return [target]


def create(both: bool = True) -> list:
    """Make the shortcut; returns the files written.

    Verifies first: a shortcut nobody can start is worse than no shortcut,
    because it looks like one until it is clicked.
    """
    verify()
    if sys.platform == "win32":
        return _write_windows(both)
    if sys.platform == "darwin":
        return _write_macos(both)
    return _write_linux(both)


def describe() -> str:
    """What create() would write, for the dialog that asks first."""
    command = " ".join(launcher())
    if sys.platform == "win32":
        text = (f"A .lnk shortcut in the Start menu and on the desktop, "
                f"starting {command}")
    elif sys.platform == "darwin":
        text = f"A .command file on the desktop, starting {command}"
    else:
        text = (f"A .desktop entry in the application menu and on the "
                f"desktop, starting {command}")

    stale = broken()
    if stale:
        text += (f"\n\nThe shortcut you have now points at {stale}, which no "
                 f"longer exists — writing it again repairs it.")
    elif checkout_main() is not None:
        text += ("\n\nThis is a checkout, so the shortcut runs main.py "
                 "rather than the kontainy-gui command: main.py is in git "
                 "and survives rebuilding .venv, which that command does "
                 "not.")
    return text
