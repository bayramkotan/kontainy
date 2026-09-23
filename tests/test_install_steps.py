"""An install that prints nothing for two minutes teaches nothing and looks
broken. These check that each package manager's own words are turned into
the same few stages, and that the progress shown is the tool's own."""

import pytest

from kontainy.core import install_steps as steps

APT = ["Reading package lists...", "Building dependency tree...",
       "Get:1 http://deb.debian.org/debian bookworm/main amd64 docker.io",
       "Preparing to unpack .../docker.io_20.10_amd64.deb ...",
       "Unpacking docker.io (20.10) ...", "Setting up docker.io (20.10) ...",
       "Processing triggers for man-db (2.11.2-2) ..."]

PACMAN = [":: Synchronizing package databases...", "resolving dependencies...",
          "looking for conflicting packages...",
          ":: Retrieving packages...", "checking keys in keyring",
          "installing docker...", ":: Running post-transaction hooks..."]

DNF = ["Dependencies resolved.", "Downloading Packages:",
       "Running transaction", "  Installing       : docker-ce-3:26.1",
       "Installed:"]

PULL = ["Using default tag: latest", "latest: Pulling from library/nginx",
        "a2abf6c4d29d: Downloading  12.3MB/31.4MB",
        "a2abf6c4d29d: Extracting  31.4MB/31.4MB",
        "a2abf6c4d29d: Pull complete",
        "Status: Downloaded newer image for nginx:latest"]


def stages(lines):
    """The stages a run passes through, in order, without repeats."""
    out = []
    for line in lines:
        key = steps.stage_of(line)
        if key and (not out or out[-1] != key):
            out.append(key)
    return out


@pytest.mark.parametrize("lines", [APT, PACMAN, DNF])
def test_every_manager_walks_the_same_four_stages(lines):
    assert stages(lines) == ["resolve", "download", "install", "configure"]


def test_a_pull_has_its_own_wording():
    keys = [key for key, _label, _why in steps.steps_for("docker pull nginx")]
    assert keys == ["resolve", "download", "install", "configure"]
    labels = [label for _k, label, _w in steps.steps_for("docker pull nginx")]
    assert "Downloading layers" in labels
    assert stages(PULL) == ["resolve", "download", "install", "configure"]


def test_a_windows_feature_warns_about_the_restart():
    text = " ".join(
        why for _k, _l, why in steps.steps_for(
            "powershell -Command Enable-WindowsOptionalFeature -Online"))
    assert "restart" in text.lower()


def test_lines_that_say_nothing_are_ignored():
    for line in ("", "   ", "docker.io is already the newest version"):
        assert steps.stage_of(line) == ""


def test_percentages_come_from_the_tool_only():
    assert steps.percent_of("Progress: [ 45%]") == 45
    assert steps.percent_of("100% complete") == 100
    assert steps.percent_of("Unpacking docker.io") == -1
    assert steps.percent_of("error 500%") == -1


def test_every_stage_explains_itself():
    for source in (steps.GENERIC, steps.DOCKER_PULL, steps.WINDOWS_FEATURE):
        for key, label, why in source:
            assert key and label and len(why) > 30
