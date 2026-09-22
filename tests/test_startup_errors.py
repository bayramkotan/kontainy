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
