"""Which terminal opens, and which shell runs inside it.

Bayram, 2026-09-27: "Neden Open Terminal dediğimizde fish çıkıyor? Neden
default terminal çıkmıyor?" Two separate answers: the shell was $SHELL,
which on CachyOS is fish even when the person works in bash; and the
emulator was simply the first one installed, which is not what the desktop
would have opened.
"""

import os
import shutil

import pytest

from kontainy.core import terminal
from kontainy.utils import config as config_module


@pytest.fixture(autouse=True)
def clean(monkeypatch, tmp_path):
    monkeypatch.setattr(config_module, "config", lambda: {})
    monkeypatch.setattr(terminal, "config", lambda: {})
    # These are the Linux rules; macOS and Windows take their own branch,
    # which the two tests at the end cover. Without this the file passed on
    # Linux and failed on the other two runners.
    monkeypatch.setattr(terminal.platform, "system", lambda: "Linux")
    for name in ("TERMINAL", "XDG_CURRENT_DESKTOP", "XDG_SESSION_DESKTOP",
                 "DESKTOP_SESSION", "SHELL"):
        monkeypatch.delenv(name, raising=False)


def _installed(*names):
    return lambda binary, *a, **k: f"/usr/bin/{binary}" if binary in names \
        else None


def test_the_preference_wins_over_everything(monkeypatch):
    monkeypatch.setattr(terminal, "config",
                        lambda: {"terminal_emulator": "alacritty"})
    monkeypatch.setattr(shutil, "which", _installed("alacritty", "konsole"))
    monkeypatch.setenv("TERMINAL", "konsole")
    assert terminal._chosen()[0] == "alacritty"


def test_the_terminal_environment_variable_is_honoured(monkeypatch):
    """How people say it on Arch and CachyOS."""
    monkeypatch.setenv("TERMINAL", "kitty")
    monkeypatch.setattr(shutil, "which", _installed("kitty", "xterm"))
    assert terminal._chosen()[0] == "kitty"


def test_the_freedesktop_helper_is_preferred_to_guessing(monkeypatch):
    monkeypatch.setattr(shutil, "which",
                        _installed("xdg-terminal-exec", "xterm"))
    binary, prefix = terminal._chosen()
    assert binary == "xdg-terminal-exec"
    assert prefix == ["xdg-terminal-exec"], "it takes the command directly"


def test_the_desktops_own_terminal_beats_the_first_installed(monkeypatch):
    """A KDE user with kitty installed still expects Konsole."""
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    monkeypatch.setattr(shutil, "which", _installed("konsole", "kitty"))
    assert terminal._chosen()[0] == "konsole"


def test_gnome_and_xfce_are_known_too(monkeypatch):
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "GNOME")
    monkeypatch.setattr(shutil, "which", _installed("gnome-terminal", "xterm"))
    assert terminal.desktop_terminal() == "gnome-terminal"
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "XFCE")
    monkeypatch.setattr(shutil, "which", _installed("xfce4-terminal"))
    assert terminal.desktop_terminal() == "xfce4-terminal"


def test_a_desktop_terminal_that_is_not_installed_is_not_chosen(monkeypatch):
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    monkeypatch.setattr(shutil, "which", _installed("kitty"))
    assert terminal.desktop_terminal() == ""
    assert terminal._chosen()[0] == "kitty"


def test_nothing_installed_is_reported_not_guessed(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda *a, **k: None)
    assert terminal._chosen() == ("", [])


# --- the shell ------------------------------------------------------------------
def test_by_default_no_shell_is_forced(monkeypatch):
    """The terminal already knows which shell to run: the one in its own
    profile. kontainy appended $SHELL, which overrode that profile and
    opened fish for someone whose Konsole runs bash."""
    monkeypatch.setenv("SHELL", "/usr/bin/fish")
    assert terminal.login_shell() == ""


def test_the_terminal_is_started_on_its_own(monkeypatch):
    monkeypatch.setenv("SHELL", "/usr/bin/fish")
    monkeypatch.setattr(shutil, "which", _installed("konsole"))
    started = {}
    monkeypatch.setattr(terminal.subprocess, "Popen",
                        lambda argv, **k: started.setdefault("argv", argv))
    terminal.open_terminal({"DOCKER_CONTEXT": "prod"})
    assert started["argv"] == ["konsole"], started
    assert "fish" not in " ".join(started["argv"])


def test_a_chosen_shell_is_passed_to_the_terminal(monkeypatch):
    monkeypatch.setattr(terminal, "config",
                        lambda: {"terminal_shell": "/bin/bash"})
    monkeypatch.setattr(shutil, "which", _installed("konsole", "/bin/bash"))
    started = {}
    monkeypatch.setattr(terminal.subprocess, "Popen",
                        lambda argv, **k: started.setdefault("argv", argv))
    terminal.open_terminal({})
    assert started["argv"] == ["konsole", "-e", "/bin/bash"]


def test_a_shell_that_is_not_installed_is_ignored(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda *a, **k: None)
    monkeypatch.setattr(terminal, "config",
                        lambda: {"terminal_shell": "nushell"})
    assert terminal.login_shell() == ""


def test_the_environment_still_reaches_the_terminal(monkeypatch):
    monkeypatch.setattr(shutil, "which", _installed("konsole"))
    seen = {}

    def popen(argv, **kwargs):
        seen.update(kwargs.get("env") or {})
    monkeypatch.setattr(terminal.subprocess, "Popen", popen)
    terminal.open_terminal({"DOCKER_CONTEXT": "prod"})
    assert seen.get("DOCKER_CONTEXT") == "prod"


def test_the_shown_command_matches_what_runs(monkeypatch):
    monkeypatch.setattr(shutil, "which", _installed("konsole"))
    shown = terminal.describe({"DOCKER_CONTEXT": "prod"})
    assert shown == "env DOCKER_CONTEXT=prod konsole"


# --- the other two platforms ---------------------------------------------------
def test_macos_asks_terminal_app_to_run_the_exports(monkeypatch):
    monkeypatch.setattr(terminal.platform, "system", lambda: "Darwin")
    started = {}
    monkeypatch.setattr(terminal.subprocess, "Popen",
                        lambda argv, **k: started.setdefault("argv", argv))
    terminal.open_terminal({"DOCKER_CONTEXT": "prod"})
    assert started["argv"][0] == "osascript"
    assert "export DOCKER_CONTEXT='prod'" in started["argv"][-1]
    assert "Terminal" in started["argv"][-1]


def test_windows_prefers_windows_terminal_and_keeps_the_shell_open(
        monkeypatch):
    monkeypatch.setattr(terminal.platform, "system", lambda: "Windows")
    monkeypatch.setattr(shutil, "which", _installed("wt.exe"))
    started = {}
    monkeypatch.setattr(terminal.subprocess, "Popen",
                        lambda argv, **k: started.setdefault("argv", argv))
    terminal.open_terminal({"DOCKER_CONTEXT": "prod"})
    assert started["argv"][0] == "wt.exe"
    assert "-NoExit" in started["argv"], "a window that closes at once is no use"
    assert "$env:DOCKER_CONTEXT='prod'" in started["argv"][-1]


def test_windows_without_windows_terminal_still_opens_one(monkeypatch):
    monkeypatch.setattr(terminal.platform, "system", lambda: "Windows")
    monkeypatch.setattr(shutil, "which", lambda *a, **k: None)
    started = {}
    monkeypatch.setattr(terminal.subprocess, "Popen",
                        lambda argv, **k: started.setdefault("argv", argv))
    terminal.open_terminal({})
    assert started["argv"][:3] == ["cmd.exe", "/c", "start"]
