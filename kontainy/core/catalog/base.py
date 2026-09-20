"""
kontainy — settings catalogue: definitions

This file is the heart of the project. The whole configuration surface of
Docker and Podman lives here as structured data; the interface is GENERATED
from it, and no setting is ever hard-coded into the GUI.

Fields
------
key              the real key in the configuration file, as a dotted path
engine           "docker" | "podman" | "both"
surface          which surface the setting belongs to (SURFACE_* constants)
file             the file it is written to, resolved per scope
vtype            bool | int | str | choice | list | dict | size | duration
choices          valid values when vtype == "choice"
default          the vendor default; None means undefined or dynamic
cli              the equivalent CLI flag, shown in the educational panel
restart          whether a restart is required after changing it
privilege        "user" | "root" — root entries are read-only with a command
danger           0 safe, 1 careful, 2 dangerous (weakens isolation)
title            short title
desc             what it does and when you would change it
gotcha           the detail that burns hours when it is not known; may be None
docs             link to the official documentation
"""

from dataclasses import dataclass, field
from typing import Any, Optional

# --- Surfaces ---------------------------------------------------------------
SURFACE_DAEMON = "daemon"        # daemon.json / containers.conf [engine]
SURFACE_STORAGE = "storage"      # storage-driver / storage.conf
SURFACE_NETWORK = "network"      # network configuration
SURFACE_REGISTRY = "registry"    # registries.conf / registry-mirrors
SURFACE_CONTAINER = "container"  # per-container run flags
SURFACE_SECURITY = "security"    # capabilities, seccomp, userns
SURFACE_RESOURCE = "resource"    # cgroup limits
SURFACE_LOGGING = "logging"      # log driver and rotation
SURFACE_BUILD = "build"          # BuildKit / buildah
SURFACE_SYSTEMD = "systemd"      # Quadlet / systemd integration

# --- Configuration file paths ------------------------------------------
FILES = {
    "docker.daemon":      {"root": "/etc/docker/daemon.json",
                           "user": "~/.config/docker/daemon.json"},
    "docker.cli":         {"user": "~/.docker/config.json"},
    "podman.containers":  {"root": "/etc/containers/containers.conf",
                           "user": "~/.config/containers/containers.conf",
                           "vendor": "/usr/share/containers/containers.conf"},
    "podman.storage":     {"root": "/etc/containers/storage.conf",
                           "user": "~/.config/containers/storage.conf",
                           "vendor": "/usr/share/containers/storage.conf"},
    "podman.registries":  {"root": "/etc/containers/registries.conf",
                           "user": "~/.config/containers/registries.conf",
                           "vendor": "/etc/containers/registries.conf.d/"},
    "podman.policy":      {"root": "/etc/containers/policy.json",
                           "user": "~/.config/containers/policy.json"},
    "podman.quadlet":     {"root": "/etc/containers/systemd/",
                           "user": "~/.config/containers/systemd/"},
}


@dataclass
class Setting:
    key: str
    engine: str
    surface: str
    file: str
    vtype: str
    title: str
    desc: str
    default: Any = None
    choices: Optional[list] = None
    cli: Optional[str] = None
    restart: bool = False
    privilege: str = "root"
    danger: int = 0
    gotcha: Optional[str] = None
    docs: Optional[str] = None
    tags: list = field(default_factory=list)


S = Setting
DOCS_D = "https://docs.docker.com/reference/cli/dockerd/"
DOCS_DJ = "https://docs.docker.com/engine/daemon/"
DOCS_RUN = "https://docs.docker.com/reference/cli/docker/container/run/"
DOCS_CC = "https://github.com/containers/common/blob/main/docs/containers.conf.5.md"
DOCS_SC = "https://github.com/containers/storage/blob/main/docs/containers-storage.conf.5.md"
DOCS_RC = "https://github.com/containers/image/blob/main/docs/containers-registries.conf.5.md"
DOCS_PR = "https://docs.podman.io/en/latest/markdown/podman-run.1.html"
DOCS_QD = "https://docs.podman.io/en/latest/markdown/podman-systemd.unit.5.html"


