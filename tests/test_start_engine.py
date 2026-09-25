"""Installed but not answering: offer the thing that starts it.

Bayram, 2026-09-25: "Madem yüklü, o zaman çalıştırabilelim oradan." A page
that says `unreachable` and offers nothing to do is a dead end.
"""

import pytest

from kontainy.core import registry
from kontainy.core.providers import PROVIDERS
from kontainy.core.providers.containers import DockerProvider, PodmanProvider
from kontainy.core.providers.platforms import KubernetesProvider


@pytest.fixture(autouse=True)
def on_linux(monkeypatch):
    monkeypatch.setattr(registry, "OS_KIND", "linux")


def test_a_daemon_offers_the_command_that_starts_it():
    act = DockerProvider().start_engine()
    assert act.display() == "sudo systemctl start docker.service"
    assert "not answering" in act.explanation
    assert "at boot" in act.explanation, "say where the permanent fix lives"


def test_a_rootless_socket_needs_no_root():
    from kontainy.core.actions import USER
    act = PodmanProvider().start_engine()
    assert act.scope == USER
    assert "--user" in act.command


def test_a_client_has_nothing_to_start():
    """kubectl talks to a cluster elsewhere; offering to start k3s would be
    a guess dressed as a fix."""
    assert KubernetesProvider().start_engine() is None


def test_docker_desktop_is_an_application_not_a_service(monkeypatch):
    monkeypatch.setattr(registry, "OS_KIND", "windows")
    act = DockerProvider().start_engine()
    assert "Docker Desktop" in act.label
    assert "systemctl" not in act.display()
    monkeypatch.setattr(registry, "OS_KIND", "macos")
    assert "open" in DockerProvider().start_engine().command


def test_podman_off_linux_starts_its_machine(monkeypatch):
    monkeypatch.setattr(registry, "OS_KIND", "windows")
    act = PodmanProvider().start_engine()
    assert act.command[-2:] == ["machine", "start"]
    assert "virtual machine" in act.explanation


def test_hyperv_starts_its_service(monkeypatch):
    from kontainy.core.providers.hyperv import HyperVProvider
    act = HyperVProvider().start_engine()
    assert "Start-Service vmms" in act.display()


def test_every_provider_either_offers_one_or_says_none():
    for provider in PROVIDERS:
        act = provider.start_engine()
        if act is None:
            continue
        assert act.command, f"{provider.id}: a start action with no command"
        assert act.explanation, f"{provider.id}: no explanation"


def test_the_cli_refuses_politely_for_a_client(capsys):
    import subprocess
    import sys
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    proc = subprocess.run([sys.executable, "-m", "kontainy", "kubernetes",
                           "start-engine"], capture_output=True, text=True,
                          cwd=str(root), timeout=120)
    assert proc.returncode != 0
    assert "client" in proc.stderr
