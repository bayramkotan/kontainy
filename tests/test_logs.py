"""Logging, crash reports and banners — modelled on VenvStudio's logger.

The point of each: a log that rotates cannot fill a disk and still holds
last week; a crash that writes a report does not vanish with the window;
Qt's own warnings are the clue that is always missing otherwise.
"""

import logging
import sys

import pytest

from kontainy.utils import logs


@pytest.fixture(autouse=True)
def temp_logs(tmp_path, monkeypatch):
    monkeypatch.setattr(logs, "log_dir", lambda: tmp_path)
    monkeypatch.setattr(logs, "_logger", None)
    yield tmp_path
    monkeypatch.setattr(logs, "_logger", None)


def test_the_log_file_rotates():
    from logging.handlers import RotatingFileHandler
    logger = logs.setup()
    handlers = [h for h in logger.handlers
                if isinstance(h, RotatingFileHandler)]
    assert handlers, "the log must rotate, or it grows without limit"
    assert handlers[0].backupCount >= 3


def test_a_crash_report_carries_the_session_context(temp_logs):
    path = logs.write_crash("main", "Traceback: ValueError: boom")
    assert path and path.exists()
    text = path.read_text(encoding="utf-8")
    assert "ValueError: boom" in text
    for key in ("kontainy", "python", "platform"):
        assert key in text, f"a report without {key} is hard to act on"


def test_reports_are_listed_newest_first(temp_logs):
    import time
    first = logs.write_crash("one", "a")
    time.sleep(0.01)
    second = logs.write_crash("two", "b")
    assert logs.crash_reports()[0] in (second, first)
    assert len(logs.crash_reports()) == 2


def test_old_reports_are_cleaned_but_recent_ones_kept(temp_logs):
    import os
    import time
    old = logs.write_crash("old", "x")
    recent = logs.write_crash("recent", "y")
    long_ago = time.time() - 60 * 60 * 24 * 40
    os.utime(old, (long_ago, long_ago))
    assert logs.clean_old_crashes(days=30) == 1
    assert recent.exists() and not old.exists()


def test_an_unhandled_exception_becomes_a_report(temp_logs, capsys):
    logs.install_hooks()
    try:
        raise ValueError("unhandled in a test")
    except ValueError:
        sys.excepthook(*sys.exc_info())
    reports = logs.crash_reports()
    assert reports, "nothing was written"
    assert "unhandled in a test" in reports[0].read_text(encoding="utf-8")
    assert "report was written" in capsys.readouterr().err


def test_ctrl_c_is_not_a_crash(temp_logs):
    logs.install_hooks()
    try:
        raise KeyboardInterrupt()
    except KeyboardInterrupt:
        try:
            sys.excepthook(*sys.exc_info())
        except SystemExit:
            pass
    assert not logs.crash_reports(), "interrupting is not a crash"


def test_a_worker_thread_crash_is_reported(temp_logs):
    import threading
    logs.install_hooks()

    def boom():
        raise RuntimeError("thread died")
    thread = threading.Thread(target=boom, name="worker")
    thread.start()
    thread.join(5)
    text = "".join(p.read_text(encoding="utf-8") for p in logs.crash_reports())
    assert "thread died" in text


@pytest.mark.parametrize("style,icon", [
    ("start", "\U0001f680"), ("success", "\u2705"), ("error", "\u274c"),
    ("warning", "\u26a0")])
def test_banners_carry_their_mark(style, icon, capsys):
    logs.banner("Doing the thing", style, record=False)
    assert icon in capsys.readouterr().out


def test_a_banner_without_a_terminal_has_no_colour_codes(capsys, monkeypatch):
    monkeypatch.setattr(logs, "colours_available", lambda: False)
    logs.banner("plain", "success", record=False)
    assert "\033[" not in capsys.readouterr().out


def test_the_command_banner_shows_one_copyable_line(capsys):
    logs.banner_command(["sudo", "apt", "install", "-y", "docker.io"],
                        "install-docker")
    out = capsys.readouterr().out
    assert "COMMAND \u2014 install-docker" in out
    # One unbroken line, so it can be selected and run.
    lines = [l for l in out.splitlines()
             if "sudo apt install -y docker.io" in l]
    assert len(lines) == 1


def test_the_ky_equivalent_stands_out_in_the_command_box(capsys):
    logs.banner_command("sudo apt install -y docker.io", "install",
                        ky_equivalent="ky install docker")
    out = capsys.readouterr().out
    assert "ky install docker" in out


def test_a_box_is_square(capsys):
    """Every line of a banner is the same width, emoji counted as two."""
    logs.banner("A title with an emoji", "success",
                ["a detail", "a much longer detail than the title itself"],
                record=False)
    lines = [l for l in capsys.readouterr().out.splitlines() if l.strip()]
    widths = {logs.visual_width(l) for l in lines}
    assert len(widths) == 1, f"ragged box: {sorted(widths)}"


def test_qt_messages_reach_the_log(temp_logs):
    pytest.importorskip("PySide6.QtCore")
    if getattr(__import__("PySide6"), "__version__", "") == "0.0.0-stub":
        pytest.skip("needs the real PySide6")
    assert logs.install_qt_handler() is True


def test_a_terminal_gets_the_narration_a_pipe_does_not(monkeypatch):
    """Started from a terminal kontainy says what it is doing; redirected,
    only warnings, so a script's output stays clean."""
    import logging as _logging

    class Tty:
        @staticmethod
        def isatty():
            return True

    class Pipe:
        @staticmethod
        def isatty():
            return False
    monkeypatch.delenv("KY_LOG_LEVEL", raising=False)
    monkeypatch.setattr(logs.sys, "stderr", Tty)
    assert logs.console_level() == _logging.INFO
    monkeypatch.setattr(logs.sys, "stderr", Pipe)
    assert logs.console_level() == _logging.WARNING
    monkeypatch.setenv("KY_LOG_LEVEL", "DEBUG")
    assert logs.console_level() == _logging.DEBUG


def test_a_probe_is_not_announced_like_a_users_command(monkeypatch, tmp_path):
    """Every systemctl probe at startup was printed as though the user had
    run it. `record` already tells a user's command from a probe."""
    import sys as _sys
    from kontainy.core import elevate
    lines = []
    monkeypatch.setattr(elevate, "log", lambda: type(
        "L", (), {"log": lambda self, level, *a: lines.append(level),
                  "info": lambda self, *a: lines.append(20),
                  "debug": lambda self, *a: lines.append(10)})())
    elevate.run([_sys.executable, "-c", "pass"], record=False)
    elevate.run([_sys.executable, "-c", "pass"], record=True)
    assert lines == [10, 20], "probe debug, user command info"


def test_timing_is_reported(caplog):
    import logging as _logging
    with caplog.at_level(_logging.INFO, logger="kontainy"):
        with logs.timer("Something"):
            pass
    assert any("Something" in record.message for record in caplog.records)
