"""The top bar: which target, which socket, and switching without a popup.

Two complaints from Bayram (2026-09-24): the bar named the context but not
the socket behind it, and merely opening the dropdown to look at the list
ran the switch and put a dialog on screen.
"""

import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _real_qt() -> bool:
    try:
        import PySide6
    except ImportError:
        return False
    return getattr(PySide6, "__version__", "") != "0.0.0-stub"


pytestmark = pytest.mark.skipif(not _real_qt(), reason="needs the real PySide6")


@pytest.fixture
def docker_page(monkeypatch):
    from PySide6.QtWidgets import QApplication
    from kontainy.core.actions import Action, USER
    from kontainy.core.providers import base
    from kontainy.core.providers.containers import DockerProvider

    state = {"active": "desktop-linux", "switched": 0}
    monkeypatch.setattr(DockerProvider, "available", lambda self: True)
    monkeypatch.setattr(DockerProvider, "version", lambda self: "29.8.0")
    monkeypatch.setattr(DockerProvider, "targets", lambda self: [
        base.Target("default", "npipe:////./pipe/docker_engine",
                    state["active"] == "default"),
        base.Target("desktop-linux", "npipe:////./pipe/dockerDesktopLinuxEngine",
                    state["active"] == "desktop-linux")])
    monkeypatch.setattr(DockerProvider, "objects", lambda self, t: base.Listing(
        columns=[base.Column("Names", "Name")], rows=[], command="docker ps"))
    monkeypatch.setattr(DockerProvider, "resolution", lambda self: [])

    def activate(self, target):
        def do():
            state["active"] = target.name
            state["switched"] += 1
            return "ok"
        return Action(id=f"use-{target.name}", label="Make it active",
                      command=[], scope=USER,
                      shell_text=f"docker context use {target.name}",
                      explanation="Writes currentContext.", func=do)
    monkeypatch.setattr(DockerProvider, "activate", activate)

    app = QApplication.instance() or QApplication([])
    from kontainy.gui.main_window import MainWindow
    from kontainy.utils.workers import stop_all_jobs
    window = MainWindow()
    page = window.pages["platform-docker"]
    window.go("platform-docker")
    for _ in range(150):
        app.processEvents()
        time.sleep(0.02)
        if page.state:
            break
    yield page, app, state
    stop_all_jobs()
    window.close()


def test_the_bar_shows_the_socket_beside_the_context(docker_page):
    page, _app, _state = docker_page
    addresses = [page.address_selector.itemText(i)
                 for i in range(page.address_selector.count())]
    assert "npipe:////./pipe/docker_engine" in addresses
    assert page.selector.count() == page.address_selector.count()


def test_the_two_dropdowns_follow_each_other(docker_page):
    page, app, _state = docker_page
    page.selector.setCurrentIndex(0)
    app.processEvents()
    assert page.address_selector.currentIndex() == 0
    page.address_selector.setCurrentIndex(1)
    app.processEvents()
    assert page.selector.currentIndex() == 1


def test_choosing_does_not_switch(docker_page):
    """Looking at the list is not asking for a change."""
    page, app, state = docker_page
    page.selector.setCurrentIndex(0)
    for _ in range(20):
        app.processEvents()
        time.sleep(0.01)
    assert state["switched"] == 0
    assert state["active"] == "desktop-linux"


def test_choosing_shows_what_activate_would_run(docker_page):
    page, app, _state = docker_page
    page.selector.setCurrentIndex(0)
    app.processEvents()
    assert "docker context use default" in page.command_strip.label.text()


def test_activate_switches_without_a_dialog(docker_page):
    from PySide6.QtWidgets import QDialog
    page, app, state = docker_page
    page.selector.setCurrentIndex(0)
    app.processEvents()
    assert page.activate_btn.isEnabled()
    page.activate_btn.click()
    for _ in range(100):
        app.processEvents()
        time.sleep(0.02)
        if state["switched"]:
            break
    assert state["switched"] == 1 and state["active"] == "default"
    assert not [w for w in app.topLevelWidgets()
                if isinstance(w, QDialog) and w.isVisible()], \
        "switching a context must not open a window"


def test_the_button_says_active_for_the_active_one(docker_page):
    page, app, _state = docker_page
    page.selector.setCurrentIndex(1)          # already active
    app.processEvents()
    assert not page.activate_btn.isEnabled()
    assert "Active" in page.activate_btn.text()
