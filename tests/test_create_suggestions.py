"""Suggestions follow the image; anything typed by hand does not.

Bayram, 2026-09-26: choosing the PostgreSQL template and then the redis
image left "postgres" in the name box — "ben ne seçersem seçeyim postgres
yazısı geliyor". The rule: kontainy may replace what kontainy wrote, never
what the user wrote.
"""

import json
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from kontainy.core.providers import base                        # noqa: E402
from kontainy.core.providers.containers import (                # noqa: E402
    DockerProvider, PodmanProvider)


def _real_qt() -> bool:
    try:
        import PySide6
    except ImportError:
        return False
    return getattr(PySide6, "__version__", "") != "0.0.0-stub"


pytestmark = pytest.mark.skipif(not _real_qt(), reason="needs the real PySide6")

IMAGES = "\n".join(json.dumps(item) for item in [
    {"Repository": "redis", "Tag": "7-alpine", "Size": "39.1MB",
     "CreatedSince": "8 days ago"},
    {"Repository": "postgres", "Tag": "16", "Size": "432MB",
     "CreatedSince": "2 months ago"}])


def _inspect(reference: str) -> str:
    if reference.startswith("redis"):
        config = {"Cmd": ["redis-server"], "ExposedPorts": {"6379/tcp": {}},
                  "Env": [], "Volumes": {"/data": {}}, "Labels": {}}
    else:
        config = {"Cmd": ["postgres"], "ExposedPorts": {"5432/tcp": {}},
                  "Env": [], "Volumes": {"/var/lib/postgresql/data": {}},
                  "Labels": {}}
    return json.dumps([{"Config": config, "Size": 1, "Created": "2026-01-01"}])


@pytest.fixture
def dialog(monkeypatch):
    from PySide6.QtWidgets import QApplication

    def cli(argv, timeout=15.0):
        if "images" in argv:
            return True, IMAGES
        if "network" in argv:
            return True, json.dumps({"Name": "bridge", "Driver": "bridge"})
        if "volume" in argv:
            return True, ""
        if "inspect" in argv:
            return True, _inspect(argv[-1])
        return True, ""
    monkeypatch.setattr(base, "cli_text", cli)
    monkeypatch.setattr(DockerProvider, "available", lambda self: True)
    monkeypatch.setattr(DockerProvider, "shown_here", lambda self: True)
    monkeypatch.setattr(DockerProvider, "targets", lambda self: [
        base.Target("default", "npipe:///x", True)])
    monkeypatch.setattr(DockerProvider, "objects", lambda self, t: base.Listing(
        columns=[], rows=[], command="docker ps -a"))
    monkeypatch.setattr(PodmanProvider, "available", lambda self: False)

    app = QApplication.instance() or QApplication([])
    from kontainy.gui.dialogs.create_container import CreateContainerDialog
    from kontainy.gui.pages.containers import engine_choices
    widget = CreateContainerDialog(engine_choices(), None)
    _settle(app)
    yield widget, app
    from kontainy.utils.workers import stop_all_jobs
    stop_all_jobs()
    widget.close()


def _settle(app, rounds: int = 80):
    for _ in range(rounds):
        app.processEvents()
        time.sleep(0.02)


def test_choosing_an_image_names_the_container_after_it(dialog):
    widget, app = dialog
    widget.image.setCurrentText("redis:7-alpine")
    _settle(app)
    assert widget.name.text() == "redis"
    assert widget.ports.toPlainText() == "6379:6379"


def test_changing_the_image_replaces_the_earlier_suggestion(dialog):
    widget, app = dialog
    widget.image.setCurrentText("postgres:16")
    _settle(app)
    assert widget.name.text() == "postgres"
    widget.image.setCurrentText("redis:7-alpine")
    _settle(app)
    assert widget.name.text() == "redis", "a suggestion must follow the image"
    assert "6379" in widget.ports.toPlainText()


def test_a_name_typed_by_hand_is_never_overwritten(dialog):
    widget, app = dialog
    widget.image.setCurrentText("postgres:16")
    _settle(app)
    widget.name.setText("my-database")
    widget.image.setCurrentText("redis:7-alpine")
    _settle(app)
    assert widget.name.text() == "my-database"


def test_a_template_followed_by_another_image_is_flagged(dialog):
    widget, app = dialog
    for index in range(widget.template_box.count()):
        if "postgres" in str(widget.template_box.itemData(index) or ""):
            widget.template_box.setCurrentIndex(index)
            break
    _settle(app)
    assert widget.name.text() == "postgres"
    widget.image.setCurrentText("redis:7-alpine")
    _settle(app)
    assert widget.name.text() == "redis"
    assert "template is for" in widget.notes.text(), \
        "the template's environment does not fit another image; say so"


def test_the_button_comes_back_when_the_problem_is_fixed(dialog, monkeypatch):
    widget, app = dialog
    monkeypatch.setattr(DockerProvider, "objects", lambda self, t: base.Listing(
        columns=[], rows=[{"Names": "redis", "State": "running", "Ports": ""}],
        command="docker ps -a"))
    widget._load_context()
    _settle(app)
    widget.image.setCurrentText("redis:7-alpine")
    _settle(app)
    widget.name.setText("redis")             # taken
    app.processEvents()
    assert not widget.ok_button.isEnabled()
    widget.name.setText("redis-2")
    app.processEvents()
    assert widget.ok_button.isEnabled(), "fixing the problem must re-enable it"
