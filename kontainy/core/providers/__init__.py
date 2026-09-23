"""kontainy — one provider per technology, each with the same shape.

See base.py for why: every technology has targets, one active, each holding
objects. One page renders any of them.
"""

from __future__ import annotations

from .base import Field, Listing, Provider, Target
from .containers import DockerProvider, PodmanProvider
from .hyperv import HyperVProvider
from .vmware import VMwareProvider
from .platforms import (IncusProvider, KubernetesProvider, LibvirtProvider,
                        LxdProvider, WslProvider, parse_wsl_list)

from . import backend as _backend
from .. import hosts as _hosts


def _add_backend(cls, kind: str) -> None:
    """On Windows, give a technology the Backend tab for what it runs on."""
    original = cls.sections

    def sections(self):
        out = list(original(self))
        if _hosts.on_windows():
            out.append(_backend.backend_section(kind))
        return out
    cls.sections = sections


_add_backend(DockerProvider, "docker")
_add_backend(PodmanProvider, "podman")
for _cls in (LibvirtProvider, IncusProvider, LxdProvider):
    _add_backend(_cls, "linux-tools")

# WSL is deliberately absent: it is what Docker Desktop, podman machine and
# the Linux tools run inside on Windows, not a technology of its own. It
# appears as each of those pages' Backend tab.
WslProvider.runs_in_wsl = False

# Order is the sidebar order.
PROVIDERS = [
    DockerProvider(),
    PodmanProvider(),
    KubernetesProvider(),
    LibvirtProvider(),
    HyperVProvider(),
    VMwareProvider(),
    IncusProvider(),
    LxdProvider(),
]


def by_id(provider_id: str):
    for provider in PROVIDERS:
        if provider.id == provider_id:
            return provider
    return None


__all__ = ["PROVIDERS", "by_id", "VMwareProvider", "Provider", "Target", "Listing", "Field",
           "parse_wsl_list"]
