"""From a fresh clone to a running window.

`git clone` then `python main.py` used to end at a message telling the
reader to run four commands by hand. kontainy offers to run them — after
asking, and never into the system Python.
"""

import os
import pathlib
import subprocess
import sys

import pytest

from kontainy import bootstrap

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_outside_an_environment_it_makes_one_in_the_checkout(tmp_path):
    steps = bootstrap.plan(tmp_path, inside_venv=False)
    assert steps[0][1:3] == ["-m", "venv"], "the first step creates .venv"
    assert str(tmp_path / ".venv") in steps[0][-1]
    assert steps[-1][-3:] == ["install", "-e", str(tmp_path)]
    assert all(str(tmp_path) in " ".join(step) for step in steps[1:]), \
        "everything goes into the checkout, not the system Python"


def test_inside_an_environment_it_installs_into_that_one(tmp_path):
    steps = bootstrap.plan(tmp_path, inside_venv=True)
    assert len(steps) == 1
    assert steps[0][0] == sys.executable
    # The check is on the STEP, not on the text: the running interpreter is
    # itself inside a .venv, so its path contains the word — which made this
    # test fail on Windows for a correct plan.
    assert steps[0][1:3] != ["-m", "venv"], "no environment inside another"


def test_an_existing_environment_is_not_created_twice(tmp_path):
    python = bootstrap.venv_python(tmp_path)
    python.parent.mkdir(parents=True)
    python.write_text("")
    steps = bootstrap.plan(tmp_path, inside_venv=False)
    assert not any(step[1:3] == ["-m", "venv"] for step in steps)


def test_the_plan_is_printable_before_anyone_agrees(tmp_path):
    text = bootstrap.describe(bootstrap.plan(tmp_path, inside_venv=False))
    assert "pip install -e" in text
    assert text.startswith("  "), "indented, so it reads as a list"


def test_without_a_terminal_it_prints_and_refuses(tmp_path, capsys):
    code = bootstrap.offer(tmp_path, interactive=False)
    out = capsys.readouterr().out
    assert code == 1, "a script must not be set up behind its back"
    assert "--setup" in out, "say how to ask for it deliberately"
    assert "pip install" in out


def test_saying_no_installs_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda _="": "n")
    ran = []
    monkeypatch.setattr(bootstrap, "run", lambda steps: ran.append(steps) or 0)
    assert bootstrap.offer(tmp_path, interactive=True) == 1
    assert not ran
    assert "Nothing was installed" in capsys.readouterr().out


def test_saying_yes_runs_exactly_the_plan(tmp_path, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _="": "y")
    ran = []
    monkeypatch.setattr(bootstrap, "run", lambda steps: ran.append(steps) or 0)
    assert bootstrap.offer(tmp_path, interactive=True) == 0
    assert ran and ran[0] == bootstrap.plan(tmp_path)


def test_a_failed_step_stops_the_rest(monkeypatch, capsys):
    calls = []

    def call(step):
        calls.append(step)
        return 0 if len(calls) == 1 else 2
    monkeypatch.setattr(bootstrap.subprocess, "call", call)
    code = bootstrap.run([["a"], ["b"], ["c"]])
    assert code == 2 and len(calls) == 2, "nothing runs after a failure"
    assert "Nothing else" in capsys.readouterr().err


def test_no_setup_never_installs_anything():
    """The launcher itself, run the way a reader would.

    With PySide6 present it opens the window, so the test gives it a display
    it can use and a few seconds to prove it does not install anything and
    does not raise.
    """
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    try:
        proc = subprocess.run([sys.executable, "main.py", "--no-setup"],
                              capture_output=True, text=True, cwd=str(ROOT),
                              timeout=20, env=env)
    except subprocess.TimeoutExpired as waited:
        text = (waited.stdout or b"").decode(errors="replace")
        assert "pip install" not in text, "it must not install on its own"
        return                      # the window opened and stayed up: fine
    assert "Traceback" not in proc.stderr
    if proc.returncode == 1:
        assert "pip install" in proc.stdout, "say what to run"


def test_the_command_line_modes_need_no_qt():
    proc = subprocess.run([sys.executable, "main.py", "--stats"],
                          capture_output=True, text=True, cwd=str(ROOT),
                          timeout=120)
    assert proc.returncode == 0
    assert "Settings catalogue" in proc.stdout
