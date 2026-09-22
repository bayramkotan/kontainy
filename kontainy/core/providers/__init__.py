"""kontainy — one provider per technology, each with the same shape.

See base.py for why: every technology has targets, one active, each holding
objects. One page renders any of them.
"""

from __future__ import annotations

from .base import Field, Listing, Provider, Target
from .containers import DockerProvider, PodmanProvider
from .hyperv import HyperVProvider
from .platforms import (IncusProvider, KubernetesProvider, LibvirtProvider,
                        LxdProvider, WslProvider, parse_wsl_list)

# Order is the sidebar order.
PROVIDERS = [
    DockerProvider(),
    PodmanProvider(),
    KubernetesProvider(),
    LibvirtProvider(),
    HyperVProvider(),
    IncusProvider(),
    LxdProvider(),
    WslProvider(),
]


def by_id(provider_id: str):
    for provider in PROVIDERS:
        if provider.id == provider_id:
            return provider
    return None


__all__ = ["PROVIDERS", "by_id", "Provider", "Target", "Listing", "Field",
           "parse_wsl_list"]
