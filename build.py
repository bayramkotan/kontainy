#!/usr/bin/env python3
"""
kontainy — PyInstaller build driver

Called by .github/workflows/build.yml in three shapes, the same contract
VenvStudio uses:

    python build.py            one file, windowed   -> dist/kontainy[.exe]
    python build.py --debug    one file, console    (retry when windowed fails)
    python build.py --onedir   a directory          -> dist/kontainy/  (AppImage)

Builds are made in CI, never locally — see the handoff.

⚠️ kontainy lives under ``src/`` and loads nothing from disk at runtime: the
settings catalogue, the diagnostic rules and the Learn content are all Python
modules, so they are collected as code rather than as data files. What DOES
need declaring is the Qt platform plugin set, because PyInstaller's automatic
analysis misses ``xcb`` dependencies often enough to produce a binary that
dies with "could not load the Qt platform plugin".
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = "kontainy"
ENTRY = ROOT / "main.py"
ICON_PNG = ROOT / "assets" / "icon.png"
ICON_ICO = ROOT / "assets" / "icon.ico"
ICON_ICNS = ROOT / "assets" / "icon.icns"

# Imported dynamically or only from inside Qt, so PyInstaller cannot see them.
HIDDEN_IMPORTS = [
    "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets",
    "src.core.catalog.docker", "src.core.catalog.podman",
    "src.core.catalog.run_flags", "src.core.catalog.quadlet",
    "src.rules.catalog", "src.learn.content", "src.core.templates",
]

# PySide6 ships far more than kontainy uses; excluding the heavy modules keeps
# the binary roughly half the size and shortens the build noticeably.
EXCLUDES = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
    "PySide6.QtQuick", "PySide6.QtQml", "PySide6.Qt3DCore",
    "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtNetworkAuth", "PySide6.QtBluetooth", "PySide6.QtSensors",
    "PySide6.QtPositioning", "PySide6.QtSerialPort", "PySide6.QtTest",
    "tkinter", "matplotlib", "numpy", "scipy", "pandas", "PIL",
]


def version() -> str:
    """Read APP_VERSION without importing PySide6."""
    text = (ROOT / "src" / "core" / "constants.py").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("APP_VERSION"):
            return line.split("=", 1)[1].strip().strip('"\'')
    return "0.0.0"


def icon_argument() -> list:
    if platform.system() == "Windows" and ICON_ICO.is_file():
        return ["--icon", str(ICON_ICO)]
    if platform.system() == "Darwin" and ICON_ICNS.is_file():
        return ["--icon", str(ICON_ICNS)]
    if ICON_PNG.is_file():
        return ["--icon", str(ICON_PNG)]
    print("note: no icon found under assets/, building without one")
    return []


def build(onedir: bool = False, debug: bool = False) -> int:
    for folder in ("build", "dist"):
        shutil.rmtree(ROOT / folder, ignore_errors=True)

    command = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP,
        "--noconfirm", "--clean",
        "--onedir" if onedir else "--onefile",
        # src/ is a package tree imported as `src.*`; PyInstaller needs the
        # root on the search path or every `from src.core…` import fails at
        # analysis time.
        "--paths", str(ROOT),
    ]
    command += ["--console"] if debug else ["--windowed"]
    command += icon_argument()

    for module in HIDDEN_IMPORTS:
        command += ["--hidden-import", module]
    for module in EXCLUDES:
        command += ["--exclude-module", module]

    # Collect the whole src package so nothing is dropped by static analysis.
    command += ["--collect-submodules", "src"]

    if platform.system() == "Linux":
        # Without the platform plugins the binary starts and immediately dies
        # with "could not load the Qt platform plugin xcb".
        command += ["--collect-binaries", "PySide6"]

    command.append(str(ENTRY))

    print(f"building {APP} {version()} on {platform.system()} "
          f"({'onedir' if onedir else 'onefile'}"
          f"{', console' if debug else ', windowed'})")
    print(" ".join(command))

    result = subprocess.run(command, cwd=ROOT)
    if result.returncode != 0:
        return result.returncode

    target = ROOT / "dist" / (APP if onedir else
                              (f"{APP}.exe" if os.name == "nt" else APP))
    if not target.exists():
        print(f"error: expected output {target} was not produced")
        return 1

    if target.is_file():
        size = target.stat().st_size / (1024 * 1024)
        print(f"built {target} ({size:.1f} MB)")
    else:
        total = sum(f.stat().st_size for f in target.rglob("*") if f.is_file())
        print(f"built {target}/ ({total / (1024 * 1024):.1f} MB)")
    return 0


def main() -> int:
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        return 0
    return build(onedir="--onedir" in sys.argv, debug="--debug" in sys.argv)


if __name__ == "__main__":
    sys.exit(main())
