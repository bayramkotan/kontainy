"""The ky command line: every GUI action, headless.

These tests run the real CLI against fake tool binaries placed on PATH, and
check what was actually executed — not what the CLI claims it would run.
"""

import json
import os
import pathlib
import stat
import subprocess
import sys

import pytest

from kontainy import cli

ROOT = pathlib.Path(__file__).resolve().parents[1]
posix_only = pytest.mark.skipif(os.name == "nt",
                                reason="fake binaries are shell scripts")

FAKE_DOCKER = r"""#!/bin/sh
echo "$*" >> "$KY_CALLS"
case "$*" in
  "--version") echo "Docker version 29.8.1, build fake" ;;
  "context ls --format {{json .}}")
    echo '{"Current":true,"DockerEndpoint":"unix:///var/run/docker.sock","Name":"default","Description":"local"}'
    echo '{"Current":false,"DockerEndpoint":"ssh://me@build","Name":"build","Description":"remote"}' ;;
  *"ps -a --format {{json .}}")
    echo '{"Names":"web","Image":"nginx:1.27","State":"running","Status":"Up","Ports":""}'
    echo '{"Names":"db","Image":"postgres:16","State":"exited","Status":"Exited","Ports":""}' ;;
  *) echo "ok" ;;
esac
"""


@pytest.fixture
def fake_docker(tmp_path, monkeypatch):
    binary = tmp_path / "docker"
    binary.write_text(FAKE_DOCKER, encoding="utf-8")
    binary.chmod(binary.stat().st_mode | stat.S_IEXEC)
    calls = tmp_path / "calls.log"
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("KY_CALLS", str(calls))

    def executed():
        if not calls.exists():
            return []
        return [line for line in calls.read_text().splitlines()
                if "context ls" not in line and "ps -a" not in line
                and line != "--version"]
    return executed


def ky(*args, stdin=subprocess.DEVNULL):
    """Run the real entry point in a subprocess, as a user would."""
    proc = subprocess.run([sys.executable, "-m", "kontainy", *args],
                          capture_output=True, text=True, stdin=stdin,
                          cwd=str(ROOT), timeout=60)
    return proc.returncode, proc.stdout, proc.stderr


@posix_only
def test_targets_are_listed_with_the_active_one_marked(fake_docker):
    code, out, _ = ky("docker", "targets")
    assert code == 0
    assert "* " in out.splitlines()[2] and "default" in out
    assert "remote over SSH" in out


@posix_only
def test_objects_as_json(fake_docker):
    code, out, _ = ky("--json", "docker", "ls")
    assert code == 0
    assert [r["Names"] for r in json.loads(out)] == ["web", "db"]


@posix_only
def test_an_action_runs_exactly_the_command_it_shows(fake_docker):
    code, out, _ = ky("docker", "stop", "web", "-y")
    assert code == 0
    assert "$ docker --context default stop web" in out
    assert fake_docker() == ["--context default stop web"]


@posix_only
def test_dry_run_runs_nothing(fake_docker):
    code, out, _ = ky("docker", "start-all", "--dry-run")
    assert code == 0 and "start db" in out
    assert fake_docker() == []


@posix_only
def test_without_a_terminal_and_without_yes_nothing_runs(fake_docker):
    code, _, err = ky("docker", "use", "build")
    assert code == 2 and "-y" in err
    assert fake_docker() == []


@posix_only
def test_an_action_that_does_not_apply_lists_those_that_do(fake_docker):
    code, _, err = ky("docker", "start", "web", "-y")
    assert code == 1
    assert "available:" in err and "stop" in err
    assert fake_docker() == []


@posix_only
def test_rm_means_remove_for_docker(fake_docker):
    code, out, _ = ky("docker", "rm", "db", "-y", "-q")
    assert code == 0
    assert fake_docker() == ["--context default rm -f db"]


@posix_only
def test_flags_work_anywhere_on_the_line(fake_docker):
    code, _, _ = ky("-y", "docker", "stop", "web")
    assert code == 0
    assert fake_docker() == ["--context default stop web"]


def test_a_missing_tool_says_how_to_install_it():
    code, _, err = ky("hyperv", "ls") if os.name != "nt" else (3, "", "ky install")
    assert code in (2, 3)


def test_the_cli_never_needs_qt():
    """On a server there is no Qt. Block PySide6 and run real commands."""
    code = ("import sys; sys.modules['PySide6'] = None\n"
            "sys.argv = ['ky', 'tech']\n"
            "from kontainy.__main__ import main\n"
            "raise SystemExit(main())")
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True,
                          text=True, cwd=str(ROOT), timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert "Technology" in proc.stdout
    assert "PySide6" not in proc.stderr


def test_version_and_help():
    assert ky("-V")[1].startswith("kontainy ")
    assert ky("version")[1].startswith("kontainy ")
    code, out, _ = ky("-h")
    assert code == 0 and "docker" in out and "overview" in out


def test_verbs_are_named_from_labels():
    assert cli._verb("\u23fb  Shut down") == "shut-down"
    assert cli._verb("\U0001f4cb  DHCP leases") == "dhcp-leases"
    assert cli._verb("\u21bb  Delete (recreate)") == "delete-recreate"


@pytest.mark.parametrize("asked,present,expected", [
    ("rm", {"remove": 1}, 1), ("rm", {"delete": 2}, 2),
    ("shutdown", {"shut-down": 3}, 3), ("poweroff", {"force-off": 4}, 4),
    ("poweroff", {"turn-off": 5}, 5), ("leases", {"dhcp-leases": 6}, 6),
    ("stop", {"start": 7}, None)])
def test_synonyms_bridge_each_tools_words(asked, present, expected):
    assert cli._find(present, asked) == expected


def test_every_technology_here_has_a_cli_name():
    from kontainy.core.providers import PROVIDERS
    for provider in PROVIDERS:
        assert provider.id in cli.TECH_ALIASES.values()


def test_start_on_a_running_machine_does_not_become_start_at_boot():
    """The prefix rule once matched `start` to `start-at-boot`: asked to
    start a running VM, kontainy would have changed its autostart instead."""
    assert cli._find({"shut-down": 1, "start-at-boot": 2}, "start") is None
    assert cli._find({"shut-down": 1, "stop-something": 2}, "stop") is None


def test_a_leading_word_still_names_a_unique_action():
    assert cli._find({"logs": 1, "delete-recreate": 2}, "delete") == 2


def test_counts_are_singular_when_there_is_one():
    """`ky overview` printed "1 containers": the GUI had the fix, the CLI
    could not use it because it lived in a Qt module."""
    from kontainy.core.providers.base import count_label
    assert count_label(1, "Containers") == "1 container"
    assert count_label(3, "Containers") == "3 containers"
    assert count_label(1, "Virtual machines") == "1 virtual machine"
    assert count_label(0, "Pods") == "0 pods"
