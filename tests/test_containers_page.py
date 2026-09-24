"""The Containers page shows WHERE each container lives.

Two faults it had: it opened the engine sockets itself, so on Windows —
where Docker listens on a named pipe — it showed nothing while the Docker
page showed three containers; and it never said which context or connection
a row came from, which is the oldest way to lose a container here.
"""

import pytest

from kontainy.core.providers import base
from kontainy.core.providers.containers import DockerProvider, PodmanProvider
from kontainy.gui.pages import containers as page


@pytest.fixture
def two_contexts(monkeypatch):
    monkeypatch.setattr(DockerProvider, "available", lambda self: True)
    monkeypatch.setattr(DockerProvider, "shown_here", lambda self: True)
    monkeypatch.setattr(DockerProvider, "targets", lambda self: [
        base.Target("default", "unix:///var/run/docker.sock", True),
        base.Target("build-box", "ssh://me@10.0.0.5", False)])

    def objects(self, target):
        rows = ([{"Names": "web", "Image": "nginx", "State": "running",
                  "Status": "Up", "Ports": "0.0.0.0:8080->80/tcp"}]
                if target and target.name == "default"
                else [{"Names": "buildkit", "Image": "moby/buildkit",
                       "State": "running", "Status": "Up", "Ports": ""}])
        return base.Listing(columns=[], rows=rows, command="docker ps")
    monkeypatch.setattr(DockerProvider, "objects", objects)
    monkeypatch.setattr(PodmanProvider, "available", lambda self: False)


def test_containers_come_from_every_context(two_contexts):
    rows = page._collect_all()
    assert {r["name"] for r in rows} == {"web", "buildkit"}


def test_each_row_names_its_source(two_contexts):
    rows = {r["name"]: r for r in page._collect_all()}
    assert rows["web"]["target"] == "default"
    assert rows["web"]["active"] is True
    assert "root" in rows["web"]["kind"]
    assert rows["buildkit"]["target"] == "build-box"
    assert rows["buildkit"]["kind"] == "remote over SSH"
    assert rows["buildkit"]["active"] is False


def test_an_unreachable_context_does_not_hide_the_others(two_contexts,
                                                          monkeypatch):
    def objects(self, target):
        if target.name == "default":
            return base.Listing(columns=[], rows=[], command="docker ps",
                                error="Cannot connect to the Docker daemon")
        return base.Listing(columns=[], rows=[{"Names": "buildkit",
                                               "State": "running"}],
                            command="docker ps")
    monkeypatch.setattr(DockerProvider, "objects", objects)
    assert [r["name"] for r in page._collect_all()] == ["buildkit"]


def test_nothing_is_read_through_a_socket_directly():
    """The page must go through the providers, which use each engine's CLI:
    that is what made it work on Windows named pipes."""
    import inspect
    source = inspect.getsource(page._collect_all)
    assert "client_for" not in source and "api" not in source
    assert "provider.objects" in source or "provider.targets" in source


def test_the_verb_helper_matches_action_labels():
    assert page.ContainersPage._verb("\u25a0  Stop") == "stop"
    assert page.ContainersPage._verb("\U0001f5d1  Remove") == "remove"
