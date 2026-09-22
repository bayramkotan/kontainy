"""When Qt cannot load, kontainy says why and what to install.

0.0.5's CI run failed opening the window with a bare
`ImportError: libEGL.so.1: cannot open shared object file`. Anyone on a
minimal Linux install would see the same traceback; now they see the
missing library and the command for their distribution.
"""

import sys

import pytest

from kontainy import __main__ as entry
from kontainy.core import registry


def test_missing_system_library_names_the_fix(monkeypatch):
    monkeypatch.setattr(registry, "OS_KIND", "linux")
    monkeypatch.setattr(registry, "OS_FAMILY", "debian")
    monkeypatch.setattr(registry, "OS_LABEL", "Debian / Ubuntu / Mint")
    message = entry.qt_missing_message(
        ImportError("libEGL.so.1: cannot open shared object file"))
    assert "libEGL.so.1" in message
    assert "sudo apt install libegl1" in message
    assert "ky --scan" in message, "the CLI modes still work and it says so"


def test_arch_gets_pacman(monkeypatch):
    monkeypatch.setattr(registry, "OS_KIND", "linux")
    monkeypatch.setattr(registry, "OS_FAMILY", "arch")
    message = entry.qt_missing_message(ImportError("libEGL.so.1"))
    assert "pacman -S --needed libglvnd" in message


def test_unknown_distribution_lists_every_option(monkeypatch):
    monkeypatch.setattr(registry, "OS_KIND", "linux")
    monkeypatch.setattr(registry, "OS_FAMILY", "")
    message = entry.qt_missing_message(ImportError("libEGL.so.1"))
    assert "apt install" in message and "dnf install" in message


def test_missing_pyside6_says_pip(monkeypatch):
    message = entry.qt_missing_message(
        ModuleNotFoundError("No module named 'PySide6'"))
    assert "pip install PySide6" in message


def test_main_returns_1_instead_of_a_traceback(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["ky"])
    monkeypatch.setitem(sys.modules, "PySide6.QtWidgets", None)
    assert entry.main() == 1
    err = capsys.readouterr().err
    assert "could not start its window" in err
    assert "Traceback" not in err


def test_a_closed_pipe_ends_quietly():
    """`ky --stats | head -3` printed a traceback once head had its lines.

    The reader must be gone BEFORE kontainy writes, or there is nothing to
    catch: the output is flushed in one piece at exit, so a test that reads
    a line first finds everything already written. The first two versions of
    this test passed with the fix removed for exactly that reason. The child
    waits until the pipe has been closed, then runs.

    stderr is read directly rather than through communicate(): on Windows
    communicate() starts a reader thread for every pipe, including the
    stdout closed here, which fails with "read of closed file".
    """
    import pathlib
    import subprocess
    code = ("import sys, time; time.sleep(0.5)\n"
            "sys.argv = ['ky', '--stats']\n"
            "from kontainy.__main__ import main\n"
            "raise SystemExit(main())")
    proc = subprocess.Popen([sys.executable, "-c", code],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            cwd=str(pathlib.Path(__file__).resolve().parents[1]))
    proc.stdout.close()             # the reader leaves before a word is written
    err = proc.stderr.read()
    proc.stderr.close()
    proc.wait(timeout=30)
    assert b"Traceback" not in err, err.decode(errors="replace")
    assert proc.returncode == 0
