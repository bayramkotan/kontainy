"""The context chain is the single most misunderstood thing in this ecosystem."""

import os

from src.core import discovery


def _clear(monkeypatch):
    for name in ("DOCKER_HOST", "DOCKER_CONTEXT"):
        monkeypatch.delenv(name, raising=False)


def test_docker_host_beats_everything(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("DOCKER_HOST", "unix:///tmp/test.sock")
    target = discovery.resolve_cli_target()
    assert target.winner == "unix:///tmp/test.sock"
    assert target.winner_layer.startswith("DOCKER_HOST")


def test_falls_back_to_the_builtin_default(monkeypatch, tmp_path):
    _clear(monkeypatch)
    monkeypatch.setattr(discovery, "docker_cli_config", lambda: {})
    monkeypatch.setattr(discovery, "docker_contexts", lambda: [])
    target = discovery.resolve_cli_target()
    assert target.winner.endswith("docker.sock")


def test_exactly_one_layer_wins(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("DOCKER_HOST", "unix:///tmp/a.sock")
    target = discovery.resolve_cli_target()
    assert sum(1 for _, _, won in target.as_rows() if won) == 1


def test_discovery_returns_endpoints_without_probing():
    endpoints = discovery.discover(probe=False)
    assert isinstance(endpoints, list)
    for endpoint in endpoints:
        assert "://" in endpoint.address
