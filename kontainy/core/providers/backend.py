"""
kontainy — the Backend tab: what a technology runs on, on Windows

WSL is not a technology the user manages for its own sake; it is what
Docker Desktop, podman machine and — through kontainy — the Linux tools run
inside. So it has no page. Instead, on Windows, each page that depends on it
gets a Backend tab listing only the distributions that matter to it:

    Docker          docker-desktop            Docker Desktop's engine
    Podman          podman-machine-*          podman machine's engine
    KVM, Incus, LXD any general distribution  kontainy's Linux tools

with the actions that are actually useful there: pick the distribution that
carries the Linux tools, restart one (wsl --terminate), stop WSL entirely
(the usual cure for a Docker Desktop that has stopped answering), and read
.wslconfig, where WSL's memory, CPU and nested-virtualization settings live.
"""

from __future__ import annotations

from pathlib import Path

from ...utils.config import config
from .. import hosts
from ..actions import Action, USER
from .base import Column, Listing, Section, action

WSLCONFIG = Path.home() / ".wslconfig"

ROLES = {
    "docker": (("docker-desktop",), "Docker Desktop's engine"),
    "podman": (("podman-machine",), "podman machine's engine"),
}


def _role(name: str) -> str:
    lowered = name.lower()
    for _kind, (prefixes, role) in ROLES.items():
        if lowered.startswith(prefixes):
            return role
    if hosts.usable_for_tools(name) and name == hosts.linux_tools_distro():
        return "carries kontainy's Linux tools"
    return ""


def _listing(kind: str) -> Listing:
    listing = Listing(columns=[Column("name", "Distribution"),
                               Column("state", "State"),
                               Column("version", "WSL"),
                               Column("role", "Role")],
                      command="wsl --list --verbose")
    if not hosts.wsl_available():
        listing.error = "WSL is not installed. Install it with:  wsl --install"
        return listing
    for name, state, version, _default in hosts.wsl_distributions():
        lowered = name.lower()
        if kind in ROLES:
            if not lowered.startswith(ROLES[kind][0]):
                continue
        elif not hosts.usable_for_tools(name):
            continue
        listing.rows.append({"name": name, "state": state,
                             "version": version, "role": _role(name)})
    if not listing.rows:
        listing.error = {
            "docker": "No docker-desktop distribution. Docker Desktop has "
                      "not been started with the WSL 2 backend yet.",
            "podman": "No podman machine. Create one with:  "
                      "podman machine init",
        }.get(kind, "No WSL distribution to run Linux tools in. Install "
                    "one with:  wsl --install -d Ubuntu")
    return listing


def _row_actions(kind: str, row: dict) -> list:
    name = row.get("name", "")
    out = []
    if kind == "linux-tools" and name != hosts.linux_tools_distro():
        def use():
            config().set("wsl_distro", name)
            return f"kontainy's Linux tools now run in {name}"
        out.append(Action(
            id=f"wsl-use-{name}", label=f"\u2714  Use for Linux tools",
            command=[], scope=USER,
            shell_text=f"ky wsl use {name}",
            explanation=(f"KVM, libvirt, Incus, LXD and LXC will run in the "
                         f"WSL distribution {name}. This is kontainy's own "
                         f"setting; your default distribution "
                         f"(wsl --set-default) is not changed."),
            func=use))
    out.append(action(
        f"wsl-terminate-{name}", "\u21bb  Restart",
        ["wsl", "--terminate", name],
        f"Stops {name}; it starts again on the next command that needs it"
        + (" — Docker Desktop restarts its own." if kind == "docker" else ".")
        + " Nothing inside it is deleted.", destructive=True))
    out.append(action(
        "wsl-shutdown", "\u23fb  Shut down WSL",
        ["wsl", "--shutdown"],
        "Stops every WSL distribution and the WSL virtual machine — the usual "
        "cure when Docker Desktop stops answering, and needed after editing "
        ".wslconfig. Docker Desktop and podman machine stop with it.",
        destructive=True))
    out.append(Action(
        id="wsl-config", label="\U0001f4c4  Show .wslconfig",
        command=[], scope=USER, shell_text=f"type {WSLCONFIG}",
        explanation=("WSL 2's machine-wide settings: memory=, processors=, "
                     "swap=, and nestedVirtualization=true, which KVM inside "
                     "WSL needs. Changes apply after  wsl --shutdown."),
        func=lambda: (WSLCONFIG.read_text(encoding="utf-8")
                      if WSLCONFIG.is_file()
                      else f"{WSLCONFIG} does not exist yet; WSL uses its "
                           f"defaults.")))
    return out


def backend_section(kind: str) -> Section:
    """kind: "docker", "podman" or "linux-tools"."""
    summary = {
        "docker": ("On Windows, Docker Desktop runs its Linux engine inside "
                   "the WSL 2 distribution docker-desktop. This is where to "
                   "restart it when Docker stops answering."),
        "podman": ("On Windows, podman machine runs its engine inside a WSL "
                   "2 distribution named podman-machine-*."),
    }.get(kind, ("On Windows this technology runs inside a WSL 2 "
                 "distribution. Choose which one carries kontainy's Linux "
                 "tools; every command is shown with the  wsl -d  prefix "
                 "it really runs with."))
    return Section(
        id="backend", title="Backend", icon="\U0001fa9f", noun="Distribution",
        key="name", summary=summary,
        listing=lambda target: _listing(kind),
        row_actions=lambda target, row: _row_actions(kind, row))
