"""
kontainy — can Qt actually open a window here?

PySide6 installs cleanly and then the first window aborts the process:

    qt.qpa.plugin: From 6.5.0, xcb-cursor0 or libxcb-cursor0 is needed
    This application failed to start because no Qt platform plugin could
    be initialized. Reinstalling the application may fix this problem.

Nothing in that message says which package to install, and it is not an
exception: Qt calls abort(), so kontainy cannot catch it and explain
afterwards. So it is checked BEFORE Qt starts — the plugin's own shared
libraries are read with ldd, and a missing one is named together with the
command that installs it on the distribution in use.

The other half is a machine with no display at all, which is not a fault:
a server is where the command line belongs, and kontainy says so instead
of failing.
"""

from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path

#: The package that carries each library, per distribution family. Only the
#: ones people actually hit; anything else is reported by its library name.
PACKAGES = {
    "libxcb-cursor.so.0": {"debian": "libxcb-cursor0",
                           "fedora": "xcb-util-cursor",
                           "arch": "xcb-util-cursor",
                           "suse": "libxcb-cursor0",
                           "alpine": "xcb-util-cursor"},
    "libEGL.so.1": {"debian": "libegl1", "fedora": "mesa-libEGL",
                    "arch": "mesa", "suse": "Mesa-libEGL1",
                    "alpine": "mesa-egl"},
    "libGL.so.1": {"debian": "libgl1", "fedora": "mesa-libGL",
                   "arch": "mesa", "suse": "Mesa-libGL1",
                   "alpine": "mesa-gl"},
    "libxkbcommon.so.0": {"debian": "libxkbcommon0",
                          "fedora": "libxkbcommon", "arch": "libxkbcommon",
                          "suse": "libxkbcommon0", "alpine": "libxkbcommon"},
    "libxkbcommon-x11.so.0": {"debian": "libxkbcommon-x11-0",
                              "fedora": "libxkbcommon-x11",
                              "arch": "libxkbcommon-x11",
                              "suse": "libxkbcommon-x11-0",
                              "alpine": "libxkbcommon-x11"},
    "libfontconfig.so.1": {"debian": "libfontconfig1",
                           "fedora": "fontconfig", "arch": "fontconfig",
                           "suse": "fontconfig", "alpine": "fontconfig"},
    "libdbus-1.so.3": {"debian": "libdbus-1-3", "fedora": "dbus-libs",
                       "arch": "dbus", "suse": "libdbus-1-3",
                       "alpine": "dbus-libs"},
}


def headless() -> bool:
    """No display to draw on. Not a fault — a reason to use the CLI."""
    if platform.system() != "Linux":
        return False
    return not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def plugin_path(name: str = "") -> Path | None:
    """The platform plugin Qt would load, or None if PySide6 is not here."""
    try:
        import PySide6
    except ImportError:
        return None
    if not name:
        name = "libqwayland.so" if os.environ.get("WAYLAND_DISPLAY") \
            else "libqxcb.so"
    path = Path(PySide6.__file__).parent / "Qt" / "plugins" / "platforms" / name
    return path if path.is_file() else None


def missing_libraries(path: Path) -> list:
    """Libraries the plugin needs and cannot find, by name, in order."""
    try:
        result = subprocess.run(["ldd", str(path)], capture_output=True,
                                text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return []
    out = []
    for line in (result.stdout or "").splitlines():
        if "not found" not in line:
            continue
        name = line.split("=>")[0].strip()
        if name and name not in out:
            out.append(name)
    return out


def install_command(libraries: list) -> str:
    """One command that installs the packages carrying those libraries."""
    from .registry import LINUX_FAMILIES, OS_FAMILY
    if not OS_FAMILY or OS_FAMILY not in LINUX_FAMILIES:
        return ""
    packages = []
    for library in libraries:
        package = PACKAGES.get(library, {}).get(OS_FAMILY)
        if package and package not in packages:
            packages.append(package)
    if not packages:
        return ""
    return f"sudo {LINUX_FAMILIES[OS_FAMILY][1]} {' '.join(packages)}"


def preflight() -> str:
    """"" when a window can open; otherwise what is wrong and what to do."""
    if platform.system() != "Linux":
        return ""
    forced = os.environ.get("QT_QPA_PLATFORM", "")
    if forced and forced not in ("xcb", "wayland"):
        return ""                      # offscreen, minimal: no display needed
    if headless():
        return ("There is no display on this machine (no DISPLAY and no "
                "WAYLAND_DISPLAY), so there is nowhere to open a window.\n\n"
                "Everything kontainy does works from the command line:\n"
                "    ky overview        every technology here\n"
                "    ky docker ls       containers on the active context\n"
                "    ky --help          the rest\n\n"
                "Over SSH, `ssh -X` forwards a display; in a container, pass "
                "the host's.")
    path = plugin_path()
    if path is None:
        return ""
    missing = missing_libraries(path)
    if not missing:
        return ""
    command = install_command(missing)
    lines = ["Qt cannot open a window here: its platform plugin is installed "
             "but the system libraries it needs are not.",
             "",
             "Missing: " + ", ".join(missing)]
    if command:
        lines += ["", "Install them with:", f"    {command}"]
    else:
        lines += ["", "Install the packages that carry those libraries with "
                      "your distribution's package manager."]
    lines += ["",
              "Qt reports this by aborting, which is why the message you "
              "would otherwise see says only that a plugin could not be "
              "initialized.",
              "",
              "The command-line modes need none of this:  ky overview,  "
              "ky doctor,  ky --help."]
    return "\n".join(lines)
