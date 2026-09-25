"""Live logs.

`docker logs --follow` never ends, so it cannot go through the run-once
dialog, and the process must die with the window: a shell's children keep
the pipe open, so stopping the shell alone leaves a process behind and Qt
aborts with "QThread: Destroyed while thread is still running".
"""

import os
import sys
import time

import pytest

from kontainy.core.providers import base
from kontainy.core.providers.containers import DockerProvider, PodmanProvider
from kontainy.core.providers.platforms import KubernetesProvider

posix_only = pytest.mark.skipif(os.name == "nt", reason="uses sh")


def _logs_action(provider, target, row):
    return next(a for a in provider.object_actions(target, row)
                if a.id.startswith(("logs-", "kubectl-logs-")))


def test_docker_and_podman_follow_with_timestamps():
    for provider in (DockerProvider(), PodmanProvider()):
        act = _logs_action(provider, base.Target("default", "unix:///x", True),
                           {"Names": "web", "State": "running"})
        assert act.follow, f"{provider.id}: no follow command"
        assert "--follow" in act.follow and "--timestamps" in act.follow
        assert "--follow" not in act.command, "the one-shot stays one-shot"


def test_kubernetes_follows_too():
    act = _logs_action(KubernetesProvider(), base.Target("c", "c", True),
                       {"namespace": "default", "name": "api"})
    assert "--follow" in act.follow


def test_a_follow_is_wrapped_for_wsl(monkeypatch):
    from kontainy.core import hosts, registry
    monkeypatch.setattr(registry, "OS_KIND", "windows")
    monkeypatch.setattr(hosts, "on_windows", lambda: True)
    monkeypatch.setattr(hosts, "wsl_available", lambda: True)
    monkeypatch.setattr(hosts, "linux_host",
                        lambda: hosts.Host("wsl", "Ubuntu-24.04"))
    from kontainy.core.providers.platforms import IncusProvider
    provider = IncusProvider()
    act = base.Action(id="x", label="Logs", command=["incus", "info", "a"],
                      scope=base.USER, explanation="",
                      follow=["incus", "console", "--show-log", "a"])
    prepared = provider.prepare(act)
    assert prepared.follow[:4] == ["wsl", "-d", "Ubuntu-24.04", "--"]


@posix_only
def test_stopping_kills_the_whole_tree():
    """A shell whose child sleeps keeps the pipe open; killing only the
    shell left the reader blocked forever."""
    from kontainy.core.elevate import run_streaming
    handle = {}
    lines = []
    import threading
    done = threading.Event()

    def run():
        run_streaming(["sh", "-c", "echo first; sleep 300"], lines.append,
                      record=False,
                      on_start=lambda stopper: handle.setdefault("stop",
                                                                 stopper))
        done.set()
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    for _ in range(100):
        if lines:
            break
        time.sleep(0.05)
    assert lines == ["first"]
    handle["stop"].stop()
    assert done.wait(10), "the reader never ended after the stop"
    assert handle["stop"].alive() is False


@posix_only
def test_the_viewer_filters_without_losing_lines(qt_app):
    from kontainy.core.actions import Action, USER
    from kontainy.gui.dialogs.logs_viewer import LogsDialog
    script = ("i=0; while [ $i -lt 10 ]; do "
              "echo \"line $i $([ $((i%5)) -eq 0 ] && echo ERROR || echo ok)\";"
              " i=$((i+1)); done; sleep 60")
    act = Action(id="logs-x", label="\U0001f4dc  Logs", command=["true"],
                 scope=USER, explanation="", follow=["sh", "-c", script])
    dialog = LogsDialog(act)
    for _ in range(200):
        qt_app.processEvents()
        time.sleep(0.02)
        if len(dialog.lines) >= 10:
            break
    assert len(dialog.lines) == 10
    dialog.filter_box.setText("ERROR")
    qt_app.processEvents()
    shown = [l for l in dialog.view.toPlainText().splitlines() if l]
    assert len(shown) == 2, shown
    dialog.filter_box.clear()
    qt_app.processEvents()
    assert len([l for l in dialog.view.toPlainText().splitlines() if l]) == 10
    dialog.close()
    for _ in range(100):
        qt_app.processEvents()
        time.sleep(0.02)
        if not dialog._proc.alive():
            break
    assert dialog._proc.alive() is False, "closing must stop the stream"


@pytest.fixture
def qt_app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        pytest.skip("needs PySide6")
    import PySide6
    if getattr(PySide6, "__version__", "") == "0.0.0-stub":
        pytest.skip("needs the real PySide6")
    app = QApplication.instance() or QApplication([])
    yield app
    from kontainy.utils.workers import stop_all_jobs
    stop_all_jobs()
