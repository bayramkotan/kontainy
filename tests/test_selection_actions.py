"""Acting on several selected rows at once.

Bayram, 2026-09-25: "seçili olanları (1 ya da daha fazla) silme
yapmamışsın." A selection of four containers is one request; it must also
be one confirmation, with every command shown.
"""

import pytest

from kontainy.core.providers import base
from kontainy.core.providers.containers import DockerProvider
from kontainy.core.providers.platforms import LibvirtProvider

TARGET = base.Target("default", "unix:///var/run/docker.sock", True)
STOPPED = [{"Names": "n8n", "State": "exited"},
           {"Names": "redis", "State": "exited"}]


def test_one_action_carries_every_selected_row():
    act = base.actions_for_selection(DockerProvider(), TARGET, STOPPED,
                                     "remove")
    lines = act.display().splitlines()
    assert len(lines) == 2
    assert lines[0].endswith("rm -f n8n") and lines[1].endswith("rm -f redis")
    assert act.destructive, "removing several is still removing"
    assert "n8n, redis" in act.explanation, "say which ones, before running"


def test_a_verb_that_does_not_fit_them_all_is_refused():
    """Asked to start two stopped containers and one running one, kontainy
    must not quietly start two of the three."""
    mixed = STOPPED + [{"Names": "api", "State": "running"}]
    assert base.actions_for_selection(DockerProvider(), TARGET, mixed,
                                      "start") is None
    assert base.actions_for_selection(DockerProvider(), TARGET, mixed,
                                      "remove") is not None


def test_streaming_and_input_actions_stay_out_of_a_selection():
    """Following the logs of four containers at once, or renaming them all
    to one name, is not something to offer."""
    for verb in ("logs", "rename", "recreate"):
        assert base.actions_for_selection(DockerProvider(), TARGET, STOPPED,
                                          verb) is None


def test_it_works_for_virtual_machines_too(monkeypatch):
    from kontainy.core.providers import platforms
    monkeypatch.setattr(platforms, "cli_text", lambda argv, timeout=15.0:
                        (True, ""))
    rows = [{"name": "win11", "state": "shut off"},
            {"name": "fedora", "state": "shut off"}]
    act = base.actions_for_selection(LibvirtProvider(),
                                     base.Target("system", "qemu:///system"),
                                     rows, "start")
    assert act is not None
    assert act.display().count("virsh") == 2


def test_a_failure_in_the_middle_is_reported_not_swallowed(monkeypatch):
    from kontainy.core import elevate

    class Ok:
        ok = True
        output = ""

    class Fail:
        ok = False
        output = "No such container"

    monkeypatch.setattr(elevate, "run",
                        lambda argv, note="": Fail() if "redis" in argv
                        else Ok())
    act = base.actions_for_selection(DockerProvider(), TARGET, STOPPED,
                                     "remove")
    with pytest.raises(RuntimeError) as error:
        act.func()
    assert "redis" in str(error.value) and "No such container" in str(error.value)


def test_the_label_counts_what_was_selected():
    act = base.actions_for_selection(DockerProvider(), TARGET, STOPPED, "stop")
    assert act is None          # both are already stopped
    running = [{"Names": "a", "State": "running"}, {"Names": "b",
                                                    "State": "running"}]
    act = base.actions_for_selection(DockerProvider(), TARGET, running, "stop")
    assert act.label.endswith("(2)")
