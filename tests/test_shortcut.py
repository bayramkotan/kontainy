"""Create Desktop Shortcut, and the icon it needs to exist first.

Every trap here was paid for once in VenvStudio: an Icon= line pointing at
a binary, a .lnk showing Python's icon, a venv's share directory no desktop
environment reads, and a shortcut that starts a different environment from
the one that made it.
"""

import os
import sys
from pathlib import Path

import pytest

from kontainy.core import appicon, shortcut


# --- the icon -------------------------------------------------------------------
def test_an_icon_is_found_in_the_checkout():
    found = appicon.find_icon(".png")
    assert found is not None and found.is_file()


def test_the_installed_copy_is_preferred_to_a_checkout(monkeypatch, tmp_path):
    """An installed kontainy must use its own files, not a clone that
    happens to be lying around."""
    installed = tmp_path / "share/icons/hicolor/512x512/apps"
    installed.mkdir(parents=True)
    (installed / "icon-512.png").write_bytes(b"x")
    monkeypatch.setattr(sys, "prefix", str(tmp_path))
    assert appicon.find_icon(".png") == installed / "icon-512.png"


def test_a_missing_icon_returns_none_rather_than_a_guess(monkeypatch,
                                                         tmp_path):
    monkeypatch.setattr(sys, "prefix", str(tmp_path))
    monkeypatch.setattr(appicon, "_repo_root", lambda: tmp_path)
    assert appicon.find_icon(".png") is None


def test_the_icon_is_packaged():
    """It was in the repository and in no wheel, so an installed copy had
    no icon to find."""
    root = Path(__file__).resolve().parents[1]
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert "[tool.setuptools.data-files]" in text
    assert "share/icons/hicolor/512x512/apps" in text
    assert "icon-512.png" in text and "icon.ico" in text


# --- the .desktop file ------------------------------------------------------------
def test_the_entry_is_valid_and_names_the_icon_by_name():
    """By name, not by path: no desktop environment looks inside a venv."""
    text = shortcut.desktop_entry("kontainy")
    assert text.startswith("[Desktop Entry]")
    assert "Type=Application" in text and "Terminal=false" in text
    assert "Icon=kontainy" in text
    assert "/" not in text.split("Icon=")[1].splitlines()[0]


def test_with_no_icon_the_line_is_left_out():
    """`Icon=/usr/bin/kontainy` points at an ELF binary, and a desktop that
    cannot read it shows the shortcut as broken."""
    text = shortcut.desktop_entry("")
    assert "Icon=" not in text
    assert "[Desktop Entry]" in text and "Exec=" in text


def test_the_shortcut_starts_this_interpreter():
    """Not a name on PATH: that may be another environment entirely."""
    argv = shortcut.launcher()
    assert argv[0].endswith(("python", "python3", "python.exe",
                             "kontainy-gui", "kontainy-gui.exe")), argv
    if argv[0] == sys.executable:
        assert argv[1:] == ["-m", "kontainy"]


def test_writing_puts_one_in_the_menu_and_one_on_the_desktop(monkeypatch,
                                                              tmp_path):
    if os.name == "nt":
        pytest.skip("the Linux path")
    desktop = tmp_path / "desktop"
    desktop.mkdir()
    home = tmp_path / "home"
    (home / ".local/share/applications").mkdir(parents=True)
    monkeypatch.setattr(shortcut, "desktop_dir", lambda: desktop)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    monkeypatch.setattr(shortcut, "install_icon", lambda: "kontainy")
    written = shortcut._write_linux()
    names = {path.name for path in written}
    assert names == {"kontainy.desktop"}
    assert (desktop / "kontainy.desktop").is_file()
    assert (home / ".local/share/applications/kontainy.desktop").is_file()
    assert (desktop / "kontainy.desktop").stat().st_mode & 0o111


def test_the_menu_only_version_writes_one_file(monkeypatch, tmp_path):
    if os.name == "nt":
        pytest.skip("the Linux path")
    home = tmp_path / "home"
    (home / ".local/share/applications").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    monkeypatch.setattr(shortcut, "install_icon", lambda: "")
    assert len(shortcut._write_linux(both=False)) == 1


# --- Windows ----------------------------------------------------------------------
def test_the_windows_shortcut_sets_its_own_icon(monkeypatch, tmp_path):
    """Without IconLocation a .lnk shows the icon of the pip wrapper, which
    is Python's."""
    icon = tmp_path / "icon.ico"
    icon.write_bytes(b"x")
    monkeypatch.setattr(appicon, "find_icon",
                        lambda ext=".png": icon if ext == ".ico" else None)
    script = shortcut._powershell_script(tmp_path / "kontainy.lnk")
    assert "IconLocation" in script and str(icon) in script
    assert "WScript.Shell" in script and "$s.Save()" in script


def test_a_quote_in_a_path_cannot_break_the_script(monkeypatch, tmp_path):
    monkeypatch.setattr(shortcut, "launcher",
                        lambda: ["C:\\it's\\python.exe", "-m", "kontainy"])
    script = shortcut._powershell_script(tmp_path / "k.lnk")
    assert "it''s" in script


def test_describe_says_what_will_be_written():
    text = shortcut.describe()
    assert "kontainy" in text
    assert any(word in text for word in (".desktop", ".lnk", ".command"))
