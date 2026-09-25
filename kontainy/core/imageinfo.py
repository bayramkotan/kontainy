"""
kontainy — what an image already tells you

A create dialog full of empty boxes is worse than the command line: it asks
the user to know the image's exposed port, its entrypoint, the environment
it expects, and then to type all of it correctly. The image knows all of
that about itself. This reads it.

Bayram, 2026-09-25: "Ben yazacaksam her şeyi, bunun ne önemi var ki? Bu
uygulama yönlendirici olacak, seçenekler sunacak, gerekirse hataları
söyleyecek."

Qt-free: the dialog uses it, and `ky create` will use the same facts.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

#: Names that Docker and Podman refuse; better said before the command runs.
NAME_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")


@dataclass
class ImageFacts:
    """What one image says about itself."""

    reference: str = ""
    local: bool = False
    size: str = ""
    created: str = ""
    entrypoint: list = field(default_factory=list)
    command: list = field(default_factory=list)
    working_dir: str = ""
    user: str = ""
    ports: list = field(default_factory=list)      # ["80/tcp", "443/tcp"]
    env: list = field(default_factory=list)        # ["PATH=...", "TZ=..."]
    volumes: list = field(default_factory=list)
    labels: dict = field(default_factory=dict)
    error: str = ""

    @property
    def needs_pull(self) -> bool:
        return not self.local


def _conn(provider, target) -> list:
    from .providers.containers import _conn_args
    return [provider.binary] + _conn_args(provider, target)


def local_images(provider, target) -> list:
    """Images already on this target, newest first.

    Offering these first is the difference between a dropdown and a blank
    box: most of the time the image is one that is already here.
    """
    from .providers.base import cli_text
    argv = _conn(provider, target) + [
        "images", "--format", "{{json .}}", "--filter", "dangling=false"]
    ok, text = cli_text(argv, timeout=15.0)
    if not ok:
        return []
    out = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except ValueError:
            continue
        repo, tag = item.get("Repository", ""), item.get("Tag", "")
        if not repo or repo == "<none>" or tag == "<none>":
            continue
        out.append({"reference": f"{repo}:{tag}",
                    "size": item.get("Size", ""),
                    "created": item.get("CreatedSince", "")})
    return out


def _first_config(data):
    if isinstance(data, list):
        data = data[0] if data else {}
    return data or {}


def read_facts(provider, target, reference: str) -> ImageFacts:
    """Inspect an image; an image that is not here yet is not an error."""
    from .providers.base import cli_text
    facts = ImageFacts(reference=reference)
    if not reference:
        return facts
    ok, text = cli_text(
        _conn(provider, target) + ["image", "inspect", reference],
        timeout=20.0)
    if not ok:
        facts.error = (text or "").strip().splitlines()[-1] if text else ""
        return facts
    try:
        data = _first_config(json.loads(text or "[]"))
    except ValueError:
        facts.error = "the engine returned something that is not JSON"
        return facts

    facts.local = True
    config = data.get("Config") or {}
    facts.entrypoint = list(config.get("Entrypoint") or [])
    facts.command = list(config.get("Cmd") or [])
    facts.working_dir = config.get("WorkingDir") or ""
    facts.user = config.get("User") or ""
    facts.ports = sorted((config.get("ExposedPorts") or {}).keys())
    facts.env = list(config.get("Env") or [])
    facts.volumes = sorted((config.get("Volumes") or {}).keys())
    facts.labels = dict(config.get("Labels") or {})
    size = data.get("Size")
    if isinstance(size, (int, float)) and size:
        facts.size = f"{size / 1_000_000:.0f} MB"
    facts.created = str(data.get("Created", ""))[:10]
    return facts


# --- suggestions --------------------------------------------------------------
def suggest_name(reference: str, taken: list) -> str:
    """nginx:1.27 -> nginx; nginx-2 when nginx is taken."""
    base = (reference or "").split("/")[-1].split(":")[0].strip()
    base = re.sub(r"[^a-zA-Z0-9_.-]", "-", base) or "container"
    used = {str(name) for name in taken}
    if base not in used:
        return base
    for number in range(2, 100):
        candidate = f"{base}-{number}"
        if candidate not in used:
            return candidate
    return base


def suggest_ports(facts: ImageFacts, taken_host_ports: list = None) -> list:
    """[(container_port, suggested_host_port, note)] for each EXPOSE.

    The host port matches the container's where it is free, because that is
    what a person expects; where it is taken, the next free one up, with the
    reason said out loud.
    """
    used = {str(p) for p in (taken_host_ports or [])}
    out = []
    for entry in facts.ports:
        container = entry.split("/")[0]
        proto = entry.split("/")[1] if "/" in entry else "tcp"
        host, note = container, ""
        if host in used:
            # Away from the privileged range: suggesting 81 because 80 was
            # taken produced a port that needs root on Linux, which the
            # dialog then warned about — a suggestion that argues with
            # itself. 8080 upwards is what people use anyway.
            number = int(container) if container.isdigit() else 8080
            if number < 1024:
                number += 8000
            while str(number) in used:
                number += 1
            host, note = str(number), f"{container} is already published"
        used.add(host)
        out.append((f"{container}/{proto}", host, note))
    return out


def env_defaults(facts: ImageFacts) -> list:
    """The image's own environment, minus the ones nobody should edit here."""
    skip = ("PATH=", "LANG=", "LC_ALL=", "GPG_KEY=", "HOME=")
    return [entry for entry in facts.env
            if not entry.startswith(skip)]


# --- what would go wrong --------------------------------------------------------
def problems(name: str, image: str, existing_names: list,
             host_ports: list, taken_host_ports: list) -> list:
    """Everything kontainy can see is wrong, before the command runs.

    Each one is (severity, text): "error" stops, "warning" is worth reading.
    """
    out = []
    if not image.strip():
        out.append(("error", "Pick an image first \u2014 it is the one thing "
                             "a container cannot be created without."))
    elif ":" not in image.split("/")[-1]:
        out.append(("warning",
                    f"{image} has no tag, so :latest is used. Six months "
                    f"from now that is a different image; a tag is what "
                    f"makes the container reproducible."))
    if name:
        if not NAME_PATTERN.match(name):
            out.append(("error",
                        "A name may contain letters, digits, dots, dashes "
                        "and underscores, and must start with a letter or a "
                        "digit."))
        elif name in set(existing_names):
            out.append(("error",
                        f"There is already a container called {name} on this "
                        f"target. Remove it, rename it, or choose another "
                        f"name."))
    for port in host_ports:
        if port and str(port) in {str(p) for p in taken_host_ports}:
            out.append(("error",
                        f"Host port {port} is already published by another "
                        f"container; the engine will refuse to start this "
                        f"one."))
        elif port and str(port).isdigit() and int(port) < 1024:
            out.append(("warning",
                        f"Host port {port} is below 1024, which needs root "
                        f"on Linux; a rootless engine cannot bind it."))
    return out
