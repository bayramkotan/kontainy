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


@pytest.fixture(autouse=True)
def no_real_path(monkeypatch, tmp_path_factory):
    """PATH is the developer's machine, and these tests are about a rule.

    launcher() reads PATH when it looks for an installed command outside
    the checkout. Left alone, these tests passed on a machine with no
    kontainy installed and failed on Bayram's, where /usr/bin/kontainy-gui
    exists and is the correct answer for the real system and the wrong one
    for a fixture. Every test here that wants a PATH sets its own.
    """
    monkeypatch.setenv("PATH", str(tmp_path_factory.mktemp("empty-path")))


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


# --- the launcher must outlive the environment ------------------------------------
def test_an_installed_copy_beats_the_checkouts_venv(monkeypatch, tmp_path):
    """The one that was breaking it. kontainy was installed system-wide and
    working, and the icon still pointed at <repo>/.venv/bin/kontainy-gui —
    which a cache clear or a venv rebuild deletes. The shortcut must take
    the install that outlives the working tree."""
    checkout = tmp_path / "Github/kontainy"
    (checkout / ".venv/bin").mkdir(parents=True)
    main_py = checkout / "main.py"
    main_py.write_text("", encoding="utf-8")
    (checkout / "pyproject.toml").write_text("", encoding="utf-8")
    name = "kontainy-gui.exe" if os.name == "nt" else "kontainy-gui"
    (checkout / ".venv/bin" / name).write_text("", encoding="utf-8")
    system = tmp_path / "usr/bin"
    system.mkdir(parents=True)
    (system / name).write_text("", encoding="utf-8")

    monkeypatch.setattr(sys, "executable", str(checkout / ".venv/bin/python"))
    monkeypatch.setattr(shortcut, "checkout_main", lambda: main_py)
    monkeypatch.setattr(shortcut, "script_dirs",
                        lambda: [checkout / ".venv/bin", system])

    assert shortcut.launcher() == [str(system / name)]


def test_nothing_under_the_checkout_is_ever_chosen(monkeypatch, tmp_path):
    """Including from PATH, which an activated venv puts first."""
    checkout = tmp_path / "kontainy"
    (checkout / ".venv/bin").mkdir(parents=True)
    name = "kontainy-gui.exe" if os.name == "nt" else "kontainy-gui"
    (checkout / ".venv/bin" / name).write_text("", encoding="utf-8")
    main_py = checkout / "main.py"
    main_py.write_text("", encoding="utf-8")
    monkeypatch.setattr(shortcut, "checkout_main", lambda: main_py)
    monkeypatch.setattr(shortcut, "script_dirs",
                        lambda: [checkout / ".venv/bin"])
    monkeypatch.setenv("PATH", str(checkout / ".venv/bin"))

    assert shortcut.durable_command() is None


def test_the_working_directory_leaves_the_checkout_with_it(monkeypatch,
                                                            tmp_path):
    """Path= must not name a directory that disappears with the checkout
    when the shortcut no longer starts anything in it."""
    installed = tmp_path / "bin/kontainy-gui"
    installed.parent.mkdir(parents=True)
    installed.write_text("", encoding="utf-8")
    monkeypatch.setattr(shortcut, "launcher", lambda: [str(installed)])
    monkeypatch.setattr(shortcut, "checkout_main",
                        lambda: tmp_path / "repo/main.py")
    assert shortcut.working_dir() == Path.home()


def test_a_checkout_runs_main_py_not_the_pip_wrapper(monkeypatch, tmp_path):
    """0.1.5 wrote `.venv/bin/kontainy-gui` into the shortcut. That wrapper
    exists only while kontainy is pip-installed into the venv, and the
    ordinary clone-and-run flow does not put it back — so the icon died
    with "Could not find the program" while kontainy itself still ran."""
    checkout = tmp_path / "kontainy"
    venv_bin = checkout / ".venv/bin"
    venv_bin.mkdir(parents=True)
    main_py = checkout / "main.py"
    main_py.write_text("", encoding="utf-8")
    (checkout / "pyproject.toml").write_text("", encoding="utf-8")
    # The wrapper is there today — and must still not be chosen.
    wrapper = venv_bin / ("kontainy-gui.exe" if os.name == "nt"
                          else "kontainy-gui")
    wrapper.write_text("", encoding="utf-8")
    python = tmp_path / "usr/bin"
    python.mkdir(parents=True)
    # shutil.which finds a name on Windows only with an extension PATHEXT
    # lists, so a fake called "python3" there is invisible and the test
    # measures the fallback instead of the rule.
    interpreter = python / ("python3.exe" if os.name == "nt" else "python3")
    interpreter.write_text("", encoding="utf-8")
    interpreter.chmod(0o755)
    monkeypatch.setattr(sys, "executable", str(venv_bin / "python"))
    monkeypatch.setattr(shortcut, "checkout_main", lambda: main_py)
    monkeypatch.setattr(shortcut, "script_dirs", lambda: [venv_bin])
    monkeypatch.setenv("PATH", str(python))

    # No install outside the checkout, so main.py — started by an
    # interpreter that is not inside the disposable .venv either.
    assert shortcut.launcher() == [str(interpreter), str(main_py)]


def test_an_installed_copy_uses_the_gui_command(monkeypatch, tmp_path):
    """There it is the right answer: it opens the window with no console
    behind it on Windows, and it returns whenever the package does."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    name = "kontainy-gui.exe" if os.name == "nt" else "kontainy-gui"
    (bin_dir / name).write_text("", encoding="utf-8")
    monkeypatch.setattr(sys, "executable", str(bin_dir / "python"))
    monkeypatch.setattr(shortcut, "checkout_main", lambda: None)

    assert shortcut.launcher() == [str(bin_dir / name)]


def test_with_neither_it_falls_back_to_the_module(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "executable", str(tmp_path / "python"))
    monkeypatch.setattr(shortcut, "checkout_main", lambda: None)
    monkeypatch.setattr(shortcut, "script_dirs", lambda: [tmp_path])
    assert shortcut.launcher() == [str(tmp_path / "python"), "-m", "kontainy"]


def test_a_user_install_finds_its_command_in_local_bin(monkeypatch, tmp_path):
    """`pip install --user` puts the interpreter at /usr/bin/python3 and the
    command in ~/.local/bin, so looking only beside the interpreter misses
    it — and on Windows that costs the console-less kontainy-gui.exe."""
    local_bin = tmp_path / ".local/bin"
    local_bin.mkdir(parents=True)
    name = "kontainy-gui.exe" if os.name == "nt" else "kontainy-gui"
    (local_bin / name).write_text("", encoding="utf-8")
    # Stands in for /usr/bin, and must not BE /usr/bin: a machine with
    # kontainy installed system-wide has the real command there, and the
    # test would then pass or fail on what the developer happens to have
    # rather than on the rule.
    system_bin = tmp_path / "usr/bin"
    system_bin.mkdir(parents=True)
    monkeypatch.setattr(sys, "executable", str(system_bin / "python3"))
    monkeypatch.setattr(shortcut, "checkout_main", lambda: None)
    monkeypatch.setattr(shortcut, "script_dirs",
                        lambda: [system_bin, local_bin])

    assert shortcut.launcher() == [str(local_bin / name)]


def test_the_script_directories_are_asked_of_sysconfig():
    """Never PATH: a `kontainy` on PATH may belong to another install."""
    dirs = shortcut.script_dirs()
    assert Path(sys.executable).parent in dirs
    assert len(dirs) == len(set(dirs))


def test_this_checkout_is_recognised_as_one():
    main_py = shortcut.checkout_main()
    assert main_py is not None and main_py.name == "main.py"


def test_an_installed_copy_has_no_main_py(monkeypatch, tmp_path):
    """main.py is deliberately kept out of the wheel, so its absence is the
    test for "am I installed"."""
    fake = tmp_path / "a/b/c/shortcut.py"
    fake.parent.mkdir(parents=True)
    monkeypatch.setattr(shortcut, "__file__", str(fake))
    assert shortcut.checkout_main() is None


# --- nothing is written without checking first ------------------------------------
def test_a_launcher_that_is_gone_is_refused(monkeypatch, tmp_path):
    """The whole point: a shortcut is seen again only when it is clicked,
    which is the worst moment to find out it is wrong."""
    monkeypatch.setattr(shortcut, "launcher",
                        lambda: [str(tmp_path / "python"), "-m", "kontainy"])
    with pytest.raises(shortcut.ShortcutError) as caught:
        shortcut.verify()
    assert "does not exist" in str(caught.value)


def test_a_missing_script_is_refused_too(monkeypatch, tmp_path):
    python = tmp_path / "python"
    python.write_text("", encoding="utf-8")
    monkeypatch.setattr(shortcut, "launcher",
                        lambda: [str(python), str(tmp_path / "main.py")])
    with pytest.raises(shortcut.ShortcutError):
        shortcut.verify()


def test_the_error_is_an_oserror():
    """window_menu catches OSError; a new exception class outside that
    hierarchy would reach the user as a traceback."""
    assert issubclass(shortcut.ShortcutError, OSError)


def test_verify_passes_for_the_real_launcher():
    shortcut.verify()


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


# --- quoting, working directory, and a stale shortcut -----------------------------
def test_a_path_with_a_space_is_quoted():
    """`/home/me/My Projects/kontainy/main.py` unquoted is two arguments,
    and the shortcut fails with half a filename in the error."""
    line = shortcut._exec_value(["/opt/py thon/bin/python",
                                 "/home/me/My Projects/main.py"])
    assert line == '"/opt/py thon/bin/python" "/home/me/My Projects/main.py"'
    assert shortcut._exec_value(["/usr/bin/python", "-m", "kontainy"]) == \
        "/usr/bin/python -m kontainy"


def test_the_entry_names_a_working_directory():
    """Without Path=, `-m kontainy` and every relative path in a checkout
    resolve against whatever directory the desktop happened to use."""
    text = shortcut.desktop_entry("kontainy")
    path = [l for l in text.splitlines() if l.startswith("Path=")]
    assert path and Path(path[0][len("Path="):]).is_dir()


def test_a_stale_entry_is_reported_so_it_can_be_repaired(monkeypatch,
                                                          tmp_path):
    """Exactly the failure seen in 0.1.5: the file is still there, the
    program it names is not."""
    if os.name == "nt":
        pytest.skip("the text formats only")
    entry = tmp_path / "kontainy.desktop"
    entry.write_text(
        "[Desktop Entry]\n"
        f"Exec={tmp_path}/.venv/bin/kontainy-gui\n", encoding="utf-8")
    monkeypatch.setattr(shortcut, "existing", lambda: [entry])
    assert shortcut.broken() == f"{tmp_path}/.venv/bin/kontainy-gui"
    assert "no longer exists" in shortcut.describe()


def test_a_working_entry_is_not_called_broken(monkeypatch, tmp_path):
    if os.name == "nt":
        pytest.skip("the text formats only")
    program = tmp_path / "python"
    program.write_text("", encoding="utf-8")
    entry = tmp_path / "kontainy.desktop"
    entry.write_text(f"[Desktop Entry]\nExec={program} -m kontainy\n",
                     encoding="utf-8")
    monkeypatch.setattr(shortcut, "existing", lambda: [entry])
    assert shortcut.broken() == ""


def test_the_shortcut_can_be_repaired_without_the_window(monkeypatch,
                                                          tmp_path):
    """The case the Tools menu cannot serve: the shortcut is broken, so the
    window cannot be opened by clicking it, so the menu item that would
    repair it is out of reach."""
    from kontainy import __main__ as entry

    written = [tmp_path / "kontainy.desktop"]
    monkeypatch.setattr(shortcut, "create", lambda both=True: written)
    assert entry.cli_shortcut() == 0


def test_a_failure_to_write_is_reported_not_raised(monkeypatch, tmp_path):
    from kontainy import __main__ as entry

    def refuse(both=True):
        raise shortcut.ShortcutError("no such program")

    monkeypatch.setattr(shortcut, "create", refuse)
    assert entry.cli_shortcut() == 1


def test_shortcut_is_a_command_of_its_own():
    """`ky shortcut`, beside scan/doctor/stats, and `ky --shortcut` for the
    flag style the older releases used."""
    from kontainy import cli

    parser = cli.build_parser()
    assert parser.parse_args(["shortcut"]).command == "shortcut"


def test_broken_survives_an_entry_it_cannot_parse(monkeypatch, tmp_path):
    if os.name == "nt":
        pytest.skip("the text formats only")
    entry = tmp_path / "kontainy.desktop"
    entry.write_text('[Desktop Entry]\nExec="unclosed quote\n',
                     encoding="utf-8")
    monkeypatch.setattr(shortcut, "existing", lambda: [entry])
    assert shortcut.broken() == ""
