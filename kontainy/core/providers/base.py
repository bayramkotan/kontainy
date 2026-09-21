"""
kontainy — providers

Every container and virtualisation technology has the same shape, under
different names:

    Docker      contexts
    Podman      system connections
    Kubernetes  kubeconfig contexts
    libvirt     connection URIs  (qemu:///system, qemu:///session, +ssh)
    Incus/LXD   remotes
    WSL         distributions

Each has a set of TARGETS, exactly one of which is ACTIVE, and each target
holds OBJECTS — containers, pods, domains, instances. A provider describes
one technology in those terms, and one page renders any provider. That is
what lets the interface offer the same dropdown, the same add / remove /
activate / test, and the same tabs for every one of them, instead of a
bespoke page per engine that each work differently.

Everything goes through the tool's own CLI, never a private API. The CLI is
what the user would type, so the command shown before each action is the
real one, and it is also what works on Windows, where Docker Desktop speaks
over a named pipe rather than a UNIX socket.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field

from ..actions import Action, NONE, ROOT, SHELL, USER


@dataclass
class Target:
    """One selectable endpoint: a context, connection, URI, remote, distro."""

    name: str
    address: str = ""
    active: bool = False
    detail: str = ""
    removable: bool = True


@dataclass
class Column:
    key: str
    title: str


@dataclass
class Listing:
    """What the Objects tab shows for the active target."""

    columns: list = field(default_factory=list)
    rows: list = field(default_factory=list)      # list of dicts
    error: str = ""
    command: str = ""


@dataclass
class Field:
    """One input on the Add dialog."""

    key: str
    label: str
    placeholder: str = ""
    hint: str = ""
    required: bool = True


def cli_text(argv: list, timeout: float = 15.0) -> tuple:
    """Run a CLI and return (ok, text).

    Decodes UTF-16 as well as UTF-8, because `wsl.exe` writes UTF-16LE to a
    pipe and every line comes back interleaved with NUL bytes otherwise.
    """
    try:
        proc = subprocess.run(argv, capture_output=True, timeout=timeout)
    except FileNotFoundError:
        return False, f"{argv[0]}: not found"
    except subprocess.TimeoutExpired:
        return False, f"{argv[0]}: timed out after {timeout:.0f}s"
    except OSError as exc:
        return False, str(exc)

    def decode(raw: bytes) -> str:
        if raw.count(b"\x00") > len(raw) // 4:
            return raw.decode("utf-16-le", errors="replace")
        return raw.decode("utf-8", errors="replace")

    text = decode(proc.stdout).strip() or decode(proc.stderr).strip()
    return proc.returncode == 0, text.replace("\x00", "").replace("\ufeff", "")


def json_lines(text: str) -> list:
    """Parse output that is one JSON object per line, skipping noise."""
    out = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def json_value(text: str, default=None):
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return default


class Provider:
    """One technology. Subclasses fill in the CLI specifics."""

    id = ""
    name = ""
    icon = ""
    binary = ""
    target_noun = "Target"          # "Context", "Connection", "Remote" ...
    target_noun_plural = "Targets"
    object_noun_plural = "Objects"  # "Containers", "Pods", "Domains" ...
    tool_ids: list = []             # registry entries for the Install tab
    catalog_engine = ""             # "docker" | "podman" | ""
    learn_category = ""
    platforms = ("linux", "macos", "windows")
    summary = ""
    # systemd units that make this technology work: (unit, user_scope, why).
    # Shown on the Services tab, where each can be started and enabled.
    services: list = []
    # Whether rootless use depends on linger (Podman, for one).
    needs_linger = False

    # --- availability -----------------------------------------------------
    def available(self) -> bool:
        return bool(shutil.which(self.binary))

    def version(self) -> str:
        if not self.available():
            return ""
        ok, text = cli_text([self.binary, "--version"], timeout=8.0)
        return text.splitlines()[0] if ok and text else ""

    def unavailable_reason(self) -> str:
        return (f"`{self.binary}` was not found on PATH. Install it from the "
                f"Install tab.")

    # --- targets ----------------------------------------------------------
    def targets(self) -> list:
        return []

    def active(self):
        for target in self.targets():
            if target.active:
                return target
        return None

    def activate(self, target: Target) -> Action:
        raise NotImplementedError

    def add_fields(self) -> list:
        return []

    def add(self, values: dict) -> Action:
        raise NotImplementedError

    def remove(self, target: Target) -> Action:
        raise NotImplementedError

    def test(self, target: Target) -> Action:
        raise NotImplementedError

    def warning(self) -> str:
        """Something the top bar must say before anyone touches the dropdown."""
        return ""

    def resolution(self) -> list:
        """How the CLI decides which target to use, highest priority first.

        Rows of (layer, value, wins). Docker's is the one that matters: a
        set DOCKER_HOST silently beats every context.
        """
        return []

    # --- objects ----------------------------------------------------------
    def objects(self, target) -> Listing:
        return Listing(error="This technology has no object listing yet.")

    # --- terminal ---------------------------------------------------------
    def terminal_env(self, target) -> dict:
        """Environment that points a fresh shell at this target."""
        return {}


def action(id: str, label: str, argv: list, explanation: str, *,
           scope: str = USER, destructive: bool = False) -> Action:
    return Action(id=id, label=label, command=argv, scope=scope,
                  explanation=explanation, destructive=destructive)


__all__ = ["Provider", "Target", "Listing", "Column", "Field", "cli_text",
           "json_lines", "json_value", "action", "Action", "USER", "ROOT",
           "SHELL", "NONE"]
