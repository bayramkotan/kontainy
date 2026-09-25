"""
kontainy — from a fresh clone to a running window

`git clone` and then `python main.py` finds no PySide6 and stops with a
message. That message is honest but it leaves the reader to do four things
by hand, in the right order, with the right Python.

This does them — after asking. It never installs anything into the system
Python: it makes `.venv` in the checkout, installs the repository into it in
editable mode, and starts the window from there. Refusing is a normal
answer; the commands are printed either way, so the reader can run them
themselves and know exactly what happened.

Qt-free, and importable without installing anything.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

VENV_DIR = ".venv"


def in_virtualenv() -> bool:
    return sys.prefix != getattr(sys, "base_prefix", sys.prefix)


def venv_python(root: Path) -> Path:
    if os.name == "nt":
        return root / VENV_DIR / "Scripts" / "python.exe"
    return root / VENV_DIR / "bin" / "python"


def qt_present() -> bool:
    try:
        import PySide6  # noqa: F401
    except ImportError:
        return False
    return True


def plan(root: Path, inside_venv: bool = None) -> list:
    """The commands that would make this checkout runnable.

    Separate from running them so the plan can be printed, tested, and read
    before anyone agrees to it.
    """
    inside_venv = in_virtualenv() if inside_venv is None else inside_venv
    python = venv_python(root)
    if inside_venv:
        # Already in an environment: install into the one we are in rather
        # than nesting another.
        return [[sys.executable, "-m", "pip", "install", "-e", str(root)]]
    steps = []
    if not python.exists():
        steps.append([sys.executable, "-m", "venv", str(root / VENV_DIR)])
    steps.append([str(python), "-m", "pip", "install", "--upgrade", "pip"])
    steps.append([str(python), "-m", "pip", "install", "-e", str(root)])
    return steps


def describe(steps: list) -> str:
    return "\n".join("  " + " ".join(step) for step in steps)


def run(steps: list) -> int:
    for step in steps:
        print(f"\n$ {' '.join(step)}")
        code = subprocess.call(step)
        if code != 0:
            print(f"\nThat step failed with exit code {code}. Nothing else "
                  f"was run.", file=sys.stderr)
            return code
    return 0


def offer(root: Path, assume_yes: bool = False, interactive: bool = None) -> int:
    """Ask, then set the checkout up. Returns a process exit code.

    0 means kontainy can now start; anything else means it cannot and the
    reason has been printed.
    """
    interactive = (sys.stdin.isatty() if interactive is None else interactive)
    steps = plan(root)
    print("kontainy needs PySide6, which is not installed here.\n")
    print("It can be set up in this checkout, without touching your system "
          "Python:")
    print(describe(steps))
    if not assume_yes:
        if not interactive:
            print("\nRun those, or `python main.py --setup` to have kontainy "
                  "run them.")
            return 1
        answer = input("\nRun them now? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("Nothing was installed.")
            return 1
    code = run(steps)
    if code != 0:
        return code
    print("\nDone. kontainy is installed in this checkout.")
    return 0


def relaunch(root: Path) -> int:
    """Start the window with the environment's Python, once it exists."""
    python = venv_python(root)
    if not python.exists():
        python = Path(sys.executable)
    print(f"\n$ {python} {root / 'main.py'}\n")
    return subprocess.call([str(python), str(root / "main.py")])
