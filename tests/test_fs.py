"""Probing a path must never crash the application.

Found by CI on 2026-09-20: /run/podman is root-owned and mode 0700 on most
distributions, so Path("/run/podman/podman.sock").exists() raises
PermissionError rather than returning False. Discovery ran that on every
sweep, which meant kontainy crashed at startup for any ordinary user with
rootful Podman installed.
"""

import pathlib

import pytest

from kontainy.core import discovery
from kontainy.utils import fs


def _raiser(*args, **kwargs):
    raise PermissionError(13, "Permission denied")


def test_exists_survives_permission_error(monkeypatch):
    monkeypatch.setattr(pathlib.Path, "exists", _raiser)
    assert fs.exists("/run/podman/podman.sock") is False


def test_is_file_survives_permission_error(monkeypatch):
    monkeypatch.setattr(pathlib.Path, "is_file", _raiser)
    assert fs.is_file("/etc/shadow") is False


def test_is_dir_survives_permission_error(monkeypatch):
    monkeypatch.setattr(pathlib.Path, "is_dir", _raiser)
    assert fs.is_dir("/root") is False


def test_read_text_survives_permission_error(monkeypatch):
    monkeypatch.setattr(pathlib.Path, "is_file", _raiser)
    assert fs.read_text("/etc/shadow") == ""


def test_iterdir_survives_permission_error(monkeypatch):
    monkeypatch.setattr(pathlib.Path, "iterdir", _raiser)
    assert fs.iterdir("/root") == []


def test_glob_survives_permission_error(monkeypatch):
    monkeypatch.setattr(pathlib.Path, "glob", _raiser)
    assert fs.glob("/root", "*") == []


def test_read_text_refuses_an_enormous_file(tmp_path):
    big = tmp_path / "big"
    big.write_text("x" * 5000, encoding="utf-8")
    assert fs.read_text(big, limit=100) == ""
    assert fs.read_text(big, limit=10_000)


def test_discovery_survives_an_unreadable_socket_directory(monkeypatch):
    """The regression itself: discovery must not raise when a candidate
    socket sits in a directory the user cannot traverse."""
    monkeypatch.setattr(pathlib.Path, "exists", _raiser)
    endpoints = discovery.discover(probe=False)
    assert isinstance(endpoints, list)


def test_docker_config_survives_permission_error(monkeypatch):
    monkeypatch.setattr(pathlib.Path, "is_file", _raiser)
    assert discovery.docker_cli_config() == {}
    assert discovery.docker_contexts() == []
