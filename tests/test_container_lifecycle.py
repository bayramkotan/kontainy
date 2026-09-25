"""Renaming, recreating and clearing out stopped containers.

Bayram, 2026-09-25, looking at six exited containers: "eski container'ları
sil, mevcut olanları sil, tekrar oluştur ve mümkünse rename".
"""

import json

import pytest

from kontainy.core.providers import base, containers
from kontainy.core.providers.containers import DockerProvider, PodmanProvider

TARGET = base.Target("default", "unix:///var/run/docker.sock", True)

INSPECT = json.dumps([{
    "Name": "/web",
    "Config": {"Image": "nginx:1.27", "Env": ["TZ=Europe/Istanbul"],
               "Labels": {}, "Cmd": None},
    "HostConfig": {"RestartPolicy": {"Name": "unless-stopped"},
                   "NetworkMode": "bridge",
                   "Binds": ["/srv/site:/usr/share/nginx/html:ro"],
                   "PortBindings": {"80/tcp": [{"HostIp": "",
                                                "HostPort": "8080"}]}},
}])


@pytest.fixture
def fake_docker(monkeypatch):
    ran = []
    monkeypatch.setattr(containers, "cli_text",
                        lambda argv, timeout=15.0: (True, INSPECT))

    class Result:
        ok = True
        output = ""
    monkeypatch.setattr(containers, "_run",
                        lambda argv, note="": ran.append(argv) or Result())
    return ran


# --- rename -----------------------------------------------------------------
def test_rename_is_one_command_and_loses_nothing():
    act = DockerProvider().rename_container(TARGET, "web", "web-old")
    assert act.display() == "docker --context default rename web web-old"
    assert not act.destructive
    for word in ("volumes", "id"):
        assert word in act.explanation


def test_rename_warns_about_other_containers_using_the_name():
    act = PodmanProvider().rename_container(TARGET, "db", "db2")
    assert "by name" in act.explanation


# --- recreate ---------------------------------------------------------------
def test_recreate_keeps_the_original_until_the_new_one_runs(fake_docker):
    act = DockerProvider().recreate_container(TARGET, "web")
    shown = act.display()
    assert "stop web" in shown
    assert "rename web web-before-recreate-" in shown
    assert "run" in shown and "nginx:1.27" in shown
    assert "8080" in shown, "the ports it already had must come back"
    assert "unless-stopped" in shown
    # Mounts come from the old container rather than being spelled out
    # again: that also carries the anonymous volumes, which a rebuilt
    # command line would silently drop.
    assert "--volumes-from web-before-recreate-" in shown


def test_recreate_rolls_back_when_the_new_container_fails(monkeypatch):
    monkeypatch.setattr(containers, "cli_text",
                        lambda argv, timeout=15.0: (True, INSPECT))
    ran = []

    class Ok:
        ok = True
        output = ""

    class Fail:
        ok = False
        output = "port already in use"

    def run(argv, note=""):
        ran.append(argv)
        return Fail() if "run" in argv else Ok()
    monkeypatch.setattr(containers, "_run", run)
    act = DockerProvider().recreate_container(TARGET, "web")
    with pytest.raises(RuntimeError) as error:
        act.func()
    assert "original was restored" in str(error.value)
    rolled = [" ".join(a) for a in ran]
    assert any("rename web-before-recreate-" in line and line.endswith("web")
               for line in rolled), "the old container must get its name back"
    assert any(line.endswith("start web") for line in rolled)


def test_recreate_says_where_the_old_container_went(fake_docker):
    act = DockerProvider().recreate_container(TARGET, "web")
    message = act.func()
    assert "web-before-recreate-" in message and "rm" in message


# --- remove stopped ----------------------------------------------------------
ROWS = [{"Names": "n8n", "State": "exited"},
        {"Names": "redis", "State": "exited"},
        {"Names": "api", "State": "running"}]


def test_remove_stopped_names_every_container_it_will_remove():
    act = containers.remove_stopped(DockerProvider(), TARGET, ROWS)
    assert "n8n" in act.explanation and "redis" in act.explanation
    assert "api" not in act.explanation.split("Named volumes")[0]
    assert act.destructive
    assert act.label.endswith("(2)")


def test_remove_stopped_runs_one_command_per_container(fake_docker):
    act = containers.remove_stopped(DockerProvider(), TARGET, ROWS)
    act.func()
    removed = [a[-1] for a in fake_docker if "rm" in a]
    assert removed == ["n8n", "redis"], "a running container is never removed"


def test_remove_stopped_appears_only_when_there_is_something_to_remove():
    provider = DockerProvider()
    running_only = [{"Names": "api", "State": "running"}]
    ids = {a.id for a in provider.bulk_actions(TARGET, running_only)}
    assert "rm-stopped" not in ids
    ids = {a.id for a in provider.bulk_actions(TARGET, ROWS)}
    assert "rm-stopped" in ids


def test_both_engines_offer_the_new_actions():
    for provider in (DockerProvider(), PodmanProvider()):
        ids = {a.id for a in provider.object_actions(
            TARGET, {"Names": "web", "State": "running"})}
        assert {"recreate-web", "rename-web"} <= ids
