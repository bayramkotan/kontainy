"""
kontainy — Learn content
========================

The educational pillar: it explains the ecosystem, not kontainy. Written in
English, like the rest of the product.

Topics live in `kontainy/learn/topics/`, one module per category, because
204 topics in one file is a file nobody opens twice and because the
categories are written in batches. This module assembles them and provides
the search and the statistics the page uses.

RULE: topics are added, never removed. A body may grow richer later.
RULE: every command shown must be one the reader can type. No invented
flags — each one is checked against `--help`.
RULE: educational text is large. The base size is 18px (about 13pt).
"""

from .topics import compose as _compose
from .topics import docker as _docker
from .topics import images as _images
from .topics import kubernetes as _kubernetes
from .topics import kvm as _kvm
from .topics import lxc as _lxc
from .topics import migration as _migration
from .topics import systemd as _systemd
from .topics import fundamentals as _fundamentals
from .topics import network as _network
from .topics import quickstart as _quickstart
from .topics import podman as _podman
from .topics import performance as _performance
from .topics import security as _security
from .topics import storage as _storage
from .topics import troubleshooting as _troubleshooting

QUICK_START = _quickstart.TOPICS
FUNDAMENTALS = _fundamentals.TOPICS
COMPOSE = _compose.TOPICS
DOCKER = _docker.TOPICS
IMAGES = _images.TOPICS
KUBERNETES = _kubernetes.TOPICS
KVM = _kvm.TOPICS
LXC = _lxc.TOPICS
MIGRATION = _migration.TOPICS
SYSTEMD = _systemd.TOPICS
NETWORK = _network.TOPICS
PODMAN = _podman.TOPICS
PERFORMANCE = _performance.TOPICS
SECURITY = _security.TOPICS
STORAGE = _storage.TOPICS
TROUBLESHOOTING = _troubleshooting.TOPICS


LEARN_CATEGORIES = [
    {"id": "quickstart", "title": "Quick Start", "icon": "⚡",
     "color": "#f9e2af", "target": 8,
     "desc": "Your first container, ports, volumes and cleanup.",
     "topics": QUICK_START},
    {"id": "fundamentals", "title": "Container Internals", "icon": "📦",
     "color": "#89b4fa", "target": 14,
     "desc": "Namespaces, cgroups, capabilities and layered filesystems.",
     "topics": FUNDAMENTALS},
    {"id": "docker", "title": "Docker", "icon": "🐳",
     "color": "#89dceb", "target": 18,
     "desc": "Architecture, run flags, contexts, daemon.json, BuildKit.",
     "topics": DOCKER},
    {"id": "podman", "title": "Podman", "icon": "🦭",
     "color": "#a6e3a1", "target": 18,
     "desc": "Daemonless design, rootless, pods, containers.conf.",
     "topics": PODMAN},
    {"id": "systemd", "title": "systemd & Quadlet", "icon": "⚙️",
     "color": "#f5c2e7", "target": 10,
     "desc": "Units, linger, socket activation, .container files.",
     "topics": SYSTEMD},
    {"id": "kubernetes", "title": "Kubernetes", "icon": "☸️",
     "color": "#74c7ec", "target": 20,
     "desc": "Pods, deployments, services, kubeconfig, probes, RBAC.",
     "topics": KUBERNETES},
    {"id": "kvm", "title": "KVM / QEMU / libvirt", "icon": "🖥️",
     "color": "#cba6f7", "target": 12,
     "desc": "Hardware virtualisation, domain XML, virtio, snapshots, VFIO.",
     "topics": KVM},
    {"id": "lxc", "title": "LXC / LXD / Incus", "icon": "🧱",
     "color": "#fab387", "target": 10,
     "desc": "System containers, idmap, storage pools, clustering.",
     "topics": LXC},
    {"id": "network", "title": "Networking", "icon": "🌐",
     "color": "#94e2d5", "target": 14,
     "desc": "Bridges, macvlan, DNS, nftables, MTU, subnet clashes.",
     "topics": NETWORK},
    {"id": "storage", "title": "Storage", "icon": "💾",
     "color": "#f2cdcd", "target": 12,
     "desc": "Volumes, bind mounts, overlay2, quotas, SELinux labels.",
     "topics": STORAGE},
    {"id": "security", "title": "Security", "icon": "🔐",
     "color": "#f38ba8", "target": 14,
     "desc": "Rootless, capabilities, seccomp, signing, scanning, SBOM.",
     "topics": SECURITY},
    {"id": "images", "title": "Images & Registries", "icon": "🏗️",
     "color": "#eba0ac", "target": 12,
     "desc": "Manifests, digests, multi-arch, buildah, skopeo, mirrors.",
     "topics": IMAGES},
    {"id": "compose", "title": "Compose & Orchestration", "icon": "🎼",
     "color": "#b4befe", "target": 10,
     "desc": "Compose schema, profiles, healthchecks, when you need more.",
     "topics": COMPOSE},
    {"id": "troubleshooting", "title": "Troubleshooting", "icon": "🔍",
     "color": "#f9e2af", "target": 14,
     "desc": "Lost containers, permissions, full disks, exit codes.",
     "topics": TROUBLESHOOTING},
    {"id": "performance", "title": "Performance", "icon": "🚀",
     "color": "#a6e3a1", "target": 10,
     "desc": "crun vs runc, overlay vs fuse, cache strategy, measuring.",
     "topics": PERFORMANCE},
    {"id": "migration", "title": "Migration & Interop", "icon": "🔄",
     "color": "#89b4fa", "target": 8,
     "desc": "Docker to Podman, the shim, Desktop leftovers, WSL2, CI.",
     "topics": MIGRATION},
]


def learn_stats() -> dict:
    written = sum(len(c["topics"]) for c in LEARN_CATEGORIES)
    target = sum(c["target"] for c in LEARN_CATEGORIES)
    return {
        "categories": len(LEARN_CATEGORIES),
        "written": written,
        "target": target,
        "percent": round(100 * written / target) if target else 0,
    }


def search_topics(text: str) -> list:
    """(category, topic) pairs whose title or body matches."""
    t = text.casefold()
    hits = []
    for cat in LEARN_CATEGORIES:
        for topic in cat["topics"]:
            blob = " ".join(str(topic.get(k, "")) for k in
                            ("title", "body", "snippet", "tip", "note", "warning"))
            if t in blob.casefold():
                hits.append((cat, topic))
    return hits
