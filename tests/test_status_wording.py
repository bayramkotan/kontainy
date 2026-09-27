"""What a page says when a technology cannot be used.

Bayram, 2026-09-26, on the Kubernetes page: "Madem k8s yok neden remove var?
Install olması gerekmiyor mu?" The header said "not installed" while the
Install tab offered to REMOVE kubectl — both true of different things, and
together only confusing. The tool was installed; the cluster was missing.
"""

import shutil

import pytest

from kontainy.core import registry
from kontainy.core.providers import PROVIDERS, platforms
from kontainy.core.providers.containers import DockerProvider
from kontainy.core.providers.platforms import KubernetesProvider


def test_a_missing_tool_is_still_called_not_installed(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name, *a, **k: None)
    assert DockerProvider().unavailable_label() == "not installed"


def test_kubectl_without_a_cluster_says_what_is_actually_missing(monkeypatch):
    monkeypatch.setattr(shutil, "which",
                        lambda name, *a, **k: "/usr/local/bin/kubectl"
                        if name == "kubectl" else None)
    assert KubernetesProvider().unavailable_label() == "no cluster configured"


def test_without_kubectl_it_is_not_installed(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name, *a, **k: None)
    assert KubernetesProvider().unavailable_label() == "not installed"


def test_every_provider_has_a_short_label_and_a_full_reason():
    for provider in PROVIDERS:
        label = provider.unavailable_label()
        assert 0 < len(label) < 32, f"{provider.id}: {label!r}"
        assert provider.unavailable_reason(), provider.id


# --- the version column -------------------------------------------------------
def test_helm_is_asked_the_way_helm_answers():
    """`helm --version` prints "Error: unknown flag", which landed in the
    version column of a tool that was installed and working."""
    tool = registry.by_id("helm")
    assert tool.version_args == ["version", "--short"]


def test_kubectl_is_asked_for_the_client_version_only():
    """Without --client it tries to reach the cluster and times out."""
    assert registry.by_id("kubectl").version_args == ["version", "--client"]


@pytest.mark.parametrize("tool_id", ["helm", "kubectl", "docker", "podman"])
def test_a_version_command_never_reaches_the_network(tool_id):
    tool = registry.by_id(tool_id)
    joined = " ".join(tool.version_args)
    assert "--server" not in joined
    assert tool.version_args, f"{tool_id}: no version arguments at all"
