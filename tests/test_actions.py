"""Actions carry a command the user must be able to see before it runs."""

import pytest

from kontainy.core import actions as act
from kontainy.core.discovery import Endpoint


def _endpoint(**kw):
    base = dict(address="unix:///run/user/1000/podman/podman.sock",
                source="test", family="podman", reachable=True)
    base.update(kw)
    return Endpoint(**base)


def test_every_action_displays_a_command():
    for action in act.actions_for_endpoint(_endpoint()):
        assert action.display().strip(), f"{action.id} shows nothing"
        assert action.explanation.strip(), f"{action.id} explains nothing"
        assert action.scope in (act.USER, act.ROOT, act.SHELL, act.NONE)


def test_root_actions_are_prefixed_with_sudo():
    unit = act.Unit(name="docker.service", user=False, state="inactive",
                    enabled="disabled")
    for action in act.actions_for_unit(unit):
        if action.scope == act.ROOT:
            assert action.display().startswith("sudo ")


def test_user_actions_are_not_prefixed():
    unit = act.Unit(name="podman.socket", user=True, state="inactive",
                    enabled="disabled")
    for action in act.actions_for_unit(unit):
        assert not action.display().startswith("sudo ")


def test_shell_actions_are_never_executed():
    """unset and export cannot be done for the user: a child process cannot
    change its parent's environment. Executing them would silently do
    nothing, which is worse than refusing."""
    action = act.Action(id="t", label="t", command=[], scope=act.SHELL,
                        explanation="x", shell_text="unset DOCKER_HOST")
    result = action.execute()
    assert result.skipped
    assert not result.ok


def test_unavailable_systemd_offers_no_unit_actions():
    unit = act.Unit(name="podman.socket", user=True, state="unavailable")
    actions = act.actions_for_unit(unit)
    assert len(actions) == 1
    assert actions[0].scope == act.NONE
    assert not actions[0].command


def test_linger_action_flips():
    assert act.linger_action(False).id == "linger-on"
    assert act.linger_action(True).id == "linger-off"
    assert act.linger_action(True).destructive


def test_variable_source_finds_a_real_entry(tmp_path, monkeypatch):
    rc = tmp_path / "bashrc"
    rc.write_text("# comment\nexport DOCKER_HOST=unix:///tmp/x.sock\n",
                  encoding="utf-8")
    monkeypatch.setattr(act, "SHELL_FILES", [str(rc)])
    hits = act.find_variable_source("DOCKER_HOST")
    assert hits and hits[0][1] == 2


def test_commented_out_lines_are_not_reported(tmp_path, monkeypatch):
    rc = tmp_path / "bashrc"
    rc.write_text("# export DOCKER_HOST=unix:///tmp/x.sock\n", encoding="utf-8")
    monkeypatch.setattr(act, "SHELL_FILES", [str(rc)])
    assert act.find_variable_source("DOCKER_HOST") == []
