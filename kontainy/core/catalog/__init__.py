"""
kontainy — settings catalogue

This package is the heart of the project. The whole configuration surface of
Docker and Podman lives here as structured data; the interface is GENERATED
from it, and no setting is ever hard-coded into the GUI.

Parts
-----
base.py        the Setting dataclass, surface constants, file paths, doc links
docker.py      daemon.json and ~/.docker/config.json
podman.py      containers.conf, storage.conf and registries.conf
run_flags.py   per-container run flags, on both engines
quadlet.py     systemd unit keys, Podman only

Required fields when adding a setting: key, engine, surface, file, vtype,
title, desc. Strongly recommended: default, cli, restart, privilege, danger,
gotcha, docs, tags.

`gotcha` is what sets this catalogue apart. Listing a setting is easy;
writing down what breaks when it is misunderstood is not, and no rival tool
does it.
"""

from .base import (                                          # noqa: F401
    Setting, S, FILES,
    SURFACE_DAEMON, SURFACE_STORAGE, SURFACE_NETWORK, SURFACE_REGISTRY,
    SURFACE_CONTAINER, SURFACE_SECURITY, SURFACE_RESOURCE, SURFACE_LOGGING,
    SURFACE_BUILD, SURFACE_SYSTEMD,
)
from .docker import DOCKER_DAEMON, DOCKER_CLI
from .podman import PODMAN_CONTAINERS, PODMAN_STORAGE, PODMAN_REGISTRIES
from .run_flags import RUN_FLAGS
from .quadlet import QUADLET

ALL_SETTINGS: list = (
    DOCKER_DAEMON + DOCKER_CLI
    + PODMAN_CONTAINERS + PODMAN_STORAGE + PODMAN_REGISTRIES
    + RUN_FLAGS + QUADLET
)

SURFACE_TITLES = {
    SURFACE_DAEMON:    "Engine / Daemon",
    SURFACE_STORAGE:   "Storage",
    SURFACE_NETWORK:   "Networking",
    SURFACE_REGISTRY:  "Registry",
    SURFACE_CONTAINER: "Container",
    SURFACE_SECURITY:  "Security",
    SURFACE_RESOURCE:  "Resource limits",
    SURFACE_LOGGING:   "Logging",
    SURFACE_BUILD:     "Build",
    SURFACE_SYSTEMD:   "systemd / Quadlet",
}

SURFACE_ICONS = {
    SURFACE_DAEMON:    "⚙",
    SURFACE_STORAGE:   "💾",
    SURFACE_NETWORK:   "🌐",
    SURFACE_REGISTRY:  "📦",
    SURFACE_CONTAINER: "🧱",
    SURFACE_SECURITY:  "🔐",
    SURFACE_RESOURCE:  "📊",
    SURFACE_LOGGING:   "📝",
    SURFACE_BUILD:     "🏗",
    SURFACE_SYSTEMD:   "🔧",
}

DANGER_TITLES = {0: "Safe", 1: "Careful", 2: "Dangerous"}


# ---------------------------------------------------------------------------
#  Queries
# ---------------------------------------------------------------------------
def by_key(key: str):
    """One setting by key, or None."""
    for s in ALL_SETTINGS:
        if s.key == key:
            return s
    return None


def by_engine(engine: str) -> list:
    """Settings for one engine; 'both' entries are always included."""
    return [s for s in ALL_SETTINGS if s.engine in (engine, "both")]


def by_surface(surface: str, engine: str = None) -> list:
    """Settings for one surface, optionally filtered by engine."""
    out = [s for s in ALL_SETTINGS if s.surface == surface]
    if engine:
        out = [s for s in out if s.engine in (engine, "both")]
    return out


def by_file(file_key: str) -> list:
    """Settings written to one configuration file."""
    return [s for s in ALL_SETTINGS if s.file == file_key]


def search(text: str) -> list:
    """Free-text search across key, title, description, gotcha, CLI and tags."""
    t = text.casefold()
    hits = []
    for s in ALL_SETTINGS:
        haystack = " ".join(filter(None, [
            s.key, s.title, s.desc, s.gotcha or "", s.cli or "", " ".join(s.tags)
        ])).casefold()
        if t in haystack:
            hits.append(s)
    return hits


def with_gotchas() -> list:
    """Settings that burn hours when misunderstood; feeds the Gotchas page."""
    return [s for s in ALL_SETTINGS if s.gotcha]


def dangerous() -> list:
    """Settings that weaken isolation or stability."""
    return [s for s in ALL_SETTINGS if s.danger >= 2]


def user_scoped() -> list:
    """Settings kontainy can write without elevation."""
    return [s for s in ALL_SETTINGS if s.privilege == "user"]


def all_tags() -> list:
    """Every tag used in the catalogue, alphabetically."""
    tags = set()
    for s in ALL_SETTINGS:
        tags.update(s.tags)
    return sorted(tags)


def stats() -> dict:
    """Catalogue summary, shown in the status bar and the About box."""
    return {
        "total": len(ALL_SETTINGS),
        "docker": len([s for s in ALL_SETTINGS if s.engine == "docker"]),
        "podman": len([s for s in ALL_SETTINGS if s.engine == "podman"]),
        "shared": len([s for s in ALL_SETTINGS if s.engine == "both"]),
        "user_scope": len(user_scoped()),
        "gotchas": len(with_gotchas()),
        "dangerous": len(dangerous()),
        "surfaces": len({s.surface for s in ALL_SETTINGS}),
    }


if __name__ == "__main__":
    for k, v in stats().items():
        print(f"{k:22} {v}")
