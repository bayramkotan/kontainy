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


def count_label(n: int, plural: str) -> str:
    """'1 container', '3 containers' — nouns are stored in the plural.

    Lives here, not in the GUI, because the CLI prints the same counts and
    must not import Qt to do it: `ky overview` said "1 containers".
    """
    word = plural.lower()
    if n == 1 and word.endswith("s"):
        word = word[:-1]
    return f"{n} {word}"


#: What a failed listing usually means, said the way a person would say it.
#: The raw text still exists — it goes behind "Details" — but a card that
#: shouts a Go stack trace at someone who may never install the thing is
#: noise. (Bayram, 2026-09-23, on the Overview cards.)
ERROR_MEANINGS = [
    (("cannot connect to the docker daemon", "failed to connect to the docker",
      "is the docker daemon running", "dockerdesktoplinuxengine",
      "docker_engine", "no such file or directory"), "installed, not running"),
    (("hyper-v administrators", "required permission", "access is denied",
      "permission denied", "not authorized"), "installed, needs permission"),
    (("couldn't get current server api group list", "connection refused",
      "was refused", "no route to host", "i/o timeout", "timed out",
      "unable to connect to the server"), "installed, nothing to connect to"),
    (("no cluster is configured", "no kubeconfig", "no configuration has been provided"),
     "installed, no cluster configured"),
    (("not found", "command not found", "no such command"), "installed"),
]


def summarise_error(text: str) -> str:
    """One short line for a card; the full text stays for the details pane."""
    lowered = (text or "").lower()
    for needles, meaning in ERROR_MEANINGS:
        if any(needle in lowered for needle in needles):
            return meaning
    return "installed, not answering"


def socket_kind(address: str) -> str:
    """Say plainly what kind of endpoint an address is.

    The question this answers is the one the old Engines page never did:
    is the selected socket root's or mine? A rootful socket runs containers
    as root and needs group membership or sudo to reach; a rootless one runs
    them as you and lives under /run/user.
    """
    a = (address or "").lower()
    if not a or a in ("this machine", "local"):
        return "local"
    # podman machine is reached over SSH on localhost, so it must be
    # recognised before the generic SSH case or it reads as a remote host.
    if "podman-machine" in a or ("/podman/" in a and "@127.0.0.1" in a):
        return "podman machine VM"
    if a.startswith("ssh://"):
        return "remote over SSH"
    if a.startswith(("tcp://", "http://", "https://")):
        return "remote over TCP"
    if a.startswith("npipe://"):
        if "dockerdesktoplinuxengine" in a or "docker_engine" in a:
            return "Docker Desktop \u00b7 Linux engine in WSL 2"
        return "Windows named pipe"
    if "/.docker/desktop/" in a or "docker-desktop" in a:
        return "Docker Desktop VM"
    if "/run/user/" in a:
        return "rootless \u00b7 your user socket"
    if a.startswith(("unix:///run/", "unix:///var/run/", "/run/", "/var/run/")):
        return "rootful \u00b7 system socket (root)"
    if a.startswith(("qemu:///system", "lxc:///", "xen:///")):
        return "system hypervisor (root)"
    if a.startswith("qemu:///session"):
        return "session hypervisor (your user)"
    if a.startswith("qemu+ssh://"):
        return "remote hypervisor over SSH"
    return ""


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


@dataclass
class Section:
    """An extra tab of manageable things beyond the main objects.

    KVM networks are the first: listed, started, stopped, set to start at
    boot, and created from a form. Docker networks and volumes, Podman pods
    and libvirt storage pools fit the same shape.
    """

    id: str
    title: str
    icon: str
    noun: str                       # "Network"
    key: str                        # column naming one row
    summary: str
    listing: object                 # callable(target) -> Listing
    row_actions: object             # callable(target, row) -> [Action]
    create_fields: list = field(default_factory=list)
    create: object = None           # callable(target, values) -> Action


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

    # --- where it runs -----------------------------------------------------
    def host(self):
        """Where this technology's commands run, or None if nowhere.

        Native here → this machine. A Linux tool on Windows → the WSL
        distribution kontainy uses for Linux tools. Otherwise → None, and
        the technology is not shown on this operating system.
        """
        from .. import hosts
        from ..registry import OS_KIND
        if OS_KIND in self.platforms:
            return hosts.LOCAL
        if OS_KIND == "windows" and "linux" in self.platforms \
                and self.runs_in_wsl:
            return hosts.linux_host()
        return None

    # Linux tools that also work inside a WSL 2 distribution on Windows.
    runs_in_wsl = True

    def shown_here(self) -> bool:
        """Whether this technology has a place on this operating system."""
        from .. import hosts
        from ..registry import OS_KIND
        if OS_KIND in self.platforms:
            return True
        return (OS_KIND == "windows" and "linux" in self.platforms
                and self.runs_in_wsl and hosts.wsl_available())

    def _cli(self, argv: list, timeout: float = 15.0) -> tuple:
        """Run a read-only query on this technology's host.

        Uses the cli_text of the module the provider lives in, so the tests
        that fake a module's CLI keep working unchanged.
        """
        import sys
        run = getattr(sys.modules[type(self).__module__], "cli_text", cli_text)
        host = self.host()
        return run(host.wrap(argv) if host else argv, timeout=timeout)

    def shown(self, argv: list) -> str:
        """The command as it really runs — with the wsl prefix when there is
        one. What a listing displays must be what was executed."""
        host = self.host()
        return " ".join(host.wrap(argv) if host else argv)

    def prepare(self, action):
        """Wrap an action's command for this host, just before it is shown.

        Every action a page or the CLI runs passes through here, so a Linux
        tool on Windows shows — and runs — `wsl -d Ubuntu -- virsh ...`.
        """
        host = self.host()
        if host is not None and host.is_wsl and action.command:
            action.command = host.wrap(action.command,
                                       root=action.scope == ROOT)
            if action.scope == ROOT:
                action.scope = USER       # wsl -u root needs no elevation
        return action

    # --- availability -----------------------------------------------------
    def available(self) -> bool:
        host = self.host()
        if host is None:
            return False
        return host.which(self.binary)

    def version(self) -> str:
        if not self.available():
            return ""
        ok, text = self._cli([self.binary, "--version"], timeout=8.0)
        return text.splitlines()[0] if ok and text else ""

    def unavailable_reason(self) -> str:
        host = self.host()
        if host is not None and host.is_wsl:
            return (f"`{self.binary}` was not found in the WSL distribution "
                    f"{host.distro}. Install it from the Install tab.")
        if host is None and self.shown_here():
            return ("No WSL distribution is available to run this Linux "
                    "tool. Install one with:  wsl --install -d Ubuntu")
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
    object_key = "name"          # the column that names one object

    def objects(self, target) -> Listing:
        return Listing(error="This technology has no object listing yet.")

    def object_actions(self, target, row: dict) -> list:
        """What can be done to one object: start, stop, restart, remove..."""
        return []

    def bulk_actions(self, target, rows: list) -> list:
        """Start all, stop all — over every object on the active target."""
        return []

    def can_edit_ports(self) -> bool:
        return False

    def sections(self) -> list:
        """Extra tabs — networks, volumes, storage pools — as Section()s."""
        return []

    # --- terminal ---------------------------------------------------------
    def terminal_env(self, target) -> dict:
        """Environment that points a fresh shell at this target."""
        return {}


def action(id: str, label: str, argv: list, explanation: str, *,
           scope: str = USER, destructive: bool = False) -> Action:
    return Action(id=id, label=label, command=argv, scope=scope,
                  explanation=explanation, destructive=destructive)


__all__ = ["Provider", "Target", "Listing", "Column", "Field", "cli_text",
           "socket_kind", "count_label", "Section",
           "json_lines", "json_value", "action", "Action", "USER", "ROOT",
           "SHELL", "NONE"]
