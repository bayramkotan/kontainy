"""The New button.

Bayram, 2026-09-25: "New'e mesela bastım, çalışmadı." It asked `discovery`
for reachable sockets and opened them itself, so on Windows — where Docker
listens on a named pipe — it found nothing and did nothing. It also created
containers through that socket, which could not work there either, and hid
the command the dialog exists to teach.
"""

import pytest

from kontainy.core.providers import base
from kontainy.core.providers.containers import DockerProvider, PodmanProvider
from kontainy.gui.pages import containers as page


@pytest.fixture
def engines(monkeypatch):
    monkeypatch.setattr(DockerProvider, "available", lambda self: True)
    monkeypatch.setattr(DockerProvider, "shown_here", lambda self: True)
    monkeypatch.setattr(DockerProvider, "targets", lambda self: [
        base.Target("default", "npipe:////./pipe/docker_engine", False),
        base.Target("desktop-linux",
                    "npipe:////./pipe/dockerDesktopLinuxEngine", True)])
    monkeypatch.setattr(DockerProvider, "objects", lambda self, t: base.Listing(
        columns=[], rows=[], command="docker ps -a"))
    monkeypatch.setattr(PodmanProvider, "available", lambda self: False)


def test_choices_come_from_the_providers_not_from_open_sockets(engines):
    choices = page.engine_choices()
    assert [c.target.name for c in choices] == ["default", "desktop-linux"]
    assert all(c.provider is not None for c in choices)
    assert all(c.reachable for c in choices)


def test_a_choice_names_the_engine_and_the_target(engines):
    choice = page.engine_choices()[1]
    assert "Docker" in choice.title and "desktop-linux" in choice.title
    assert "WSL 2" in choice.title, "say what kind of socket it is"


def test_an_unreachable_target_is_not_offered(engines, monkeypatch):
    def objects(self, target):
        if target.name == "default":
            return base.Listing(columns=[], rows=[], command="docker ps",
                                error="Cannot connect to the Docker daemon")
        return base.Listing(columns=[], rows=[], command="docker ps")
    monkeypatch.setattr(DockerProvider, "objects", objects)
    assert [c.target.name for c in page.engine_choices()] == ["desktop-linux"]


def test_nothing_at_all_is_a_message_not_silence(monkeypatch):
    monkeypatch.setattr(DockerProvider, "available", lambda self: False)
    monkeypatch.setattr(PodmanProvider, "available", lambda self: False)
    assert page.engine_choices() == []


@pytest.mark.skipif(
    __import__("PySide6").__version__ == "0.0.0-stub",
    reason="needs the real PySide6")
def test_the_command_names_the_chosen_context(engines, qt_app):
    from kontainy.gui.dialogs.create_container import CreateContainerDialog
    choices = page.engine_choices()
    dialog = CreateContainerDialog(choices, None)
    dialog.image.setText("nginx:1.27")
    dialog.engine_box.setCurrentIndex(1)          # desktop-linux
    dialog._update_preview()
    first = dialog.command_text().splitlines()[0]
    assert first.startswith("docker --context desktop-linux run"), first


@pytest.fixture
def qt_app():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app
