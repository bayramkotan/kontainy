"""
kontainy — actions on engines, contexts and systemd units

The Engines page used to be a report you could not touch. This module is what
makes it actionable, and every action carries three things the interface needs
before it runs anything:

    command      exactly what will execute, shown and copyable first
    scope        "user", "root" or "shell" — shell means kontainy cannot do it
    explanation  why this is the right command, and what it changes

The `shell` scope matters more than it looks. `unset DOCKER_HOST` cannot be
performed for the user at all: a child process cannot change its parent's
environment, so no amount of privilege lets kontainy alter the shell that is
already open. Pretending otherwise would be the most damaging kind of lie this
tool could tell, because the symptom it fixes is invisible. kontainy instead
finds WHERE the variable is set and hands over the exact line to remove.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..utils import fs
from ..utils.config import history, log
from . import discovery
from .api import EngineError
from .elevate import CommandResult, run, run_elevated

USER = "user"
ROOT = "root"
SHELL = "shell"          # must be run by the user in their own shell
NONE = "none"


@dataclass
class Action:
    """One thing the user can do, with the command shown before it runs."""

    id: str
    label: str
    command: list                    # argv; empty for SHELL-only actions
    scope: str
    explanation: str
    shell_text: str = ""             # what to paste when scope is SHELL
    destructive: bool = False
    note: str = ""
    # A command that never ends on its own: logs with --follow, a live
    # stats stream. The window opens the log viewer for these instead of
    # the run-once dialog, which would sit there filling memory forever.
    follow: list = None
    # Some actions are not a command at all but a file kontainy writes itself
    # — libvirt's uri_default, for instance. They still go through the same
    # show-first dialog; shell_text then carries the equivalent command so the
    # user sees exactly what is about to change and could do it by hand.
    func: object = None

    def display(self) -> str:
        # With no command to run, whatever text the action carries IS what it
        # has to show. Without this, an action that only explains something
        # ("nothing to switch to") appeared as an empty line.
        if self.scope == SHELL or not self.command or \
                (self.func is not None and self.shell_text):
            return self.shell_text
        prefix = "sudo " if self.scope == ROOT else ""
        return prefix + " ".join(self.command)

    def execute(self) -> CommandResult:
        if self.func is not None:
            try:
                message = self.func() or "done"
                history().add(self.display(), note=self.id, ok=True)
                return CommandResult(self.display(), 0, str(message))
            except Exception as exc:                          # noqa: BLE001
                history().add(self.display(), note=self.id, ok=False)
                return CommandResult(self.display(), 1, "", str(exc))
        if self.scope == SHELL or not self.command:
            return CommandResult(self.display(), 1,
                                 skipped="must be run in your own shell")
        if self.scope == ROOT:
            return run_elevated(self.command, note=self.id)
        return run(self.command, note=self.id)


# ---------------------------------------------------------------------------
#  Where an environment variable comes from
# ---------------------------------------------------------------------------
SHELL_FILES = [
    "~/.bashrc", "~/.bash_profile", "~/.profile", "~/.zshrc", "~/.zshenv",
    "~/.config/fish/config.fish", "~/.config/environment.d/",
    "/etc/environment", "/etc/profile", "/etc/profile.d/",
]


def find_variable_source(name: str) -> list:
    """Find which startup file sets an environment variable.

    Returns (path, line number, line) for every match. This is the part users
    cannot do for themselves easily, and the part that actually resolves
    CTX01: knowing DOCKER_HOST is set does not tell you where to delete it.
    """
    pattern = re.compile(rf"^\s*(export\s+)?{re.escape(name)}\s*=", re.M)
    hits = []

    def scan(path: Path):
        text = fs.read_text(path, limit=512_000)
        if not text:
            return
        for index, line in enumerate(text.splitlines(), 1):
            if pattern.match(line) and not line.strip().startswith("#"):
                hits.append((str(path), index, line.strip()))

    for entry in SHELL_FILES:
        path = Path(os.path.expanduser(entry))
        if fs.is_dir(path):
            for child in fs.iterdir(path):
                scan(child)
        else:
            scan(path)
    return hits


# ---------------------------------------------------------------------------
#  Context and target actions
# ---------------------------------------------------------------------------
def docker_context_for(address: str) -> str:
    """The docker context whose endpoint matches this address, if any."""
    wanted = address.replace("unix://", "")
    for name, host in discovery.docker_contexts():
        if host.replace("unix://", "") == wanted:
            return name
    return ""


def actions_for_endpoint(endpoint, cli_target=None) -> list:
    """Everything the user can do with one discovered engine."""
    actions = []
    address = endpoint.address
    context = docker_context_for(address)
    docker_host = os.environ.get("DOCKER_HOST", "")
    is_podman = endpoint.family == "podman"
    binary = "podman" if is_podman else "docker"

    # --- Make this the terminal's target ---------------------------------
    if context:
        actions.append(Action(
            id="context-use",
            label=f"Make default (context: {context})",
            command=["docker", "context", "use", context],
            scope=USER,
            explanation=(
                f"Writes `currentContext: {context}` into "
                f"~/.docker/config.json, so new shells use this engine.\n\n"
                + ("\u26a0 DOCKER_HOST is currently set, which overrides the "
                   "context entirely. This command will report success and "
                   "change nothing until that variable is removed."
                   if docker_host else
                   "New shells will pick this up immediately; shells already "
                   "open keep their current target.")),
        ))

    actions.append(Action(
        id="export-host",
        label="Point THIS shell at it",
        command=[],
        scope=SHELL,
        shell_text=f"export DOCKER_HOST={address}",
        explanation=(
            "Sets the variable for one shell session. kontainy cannot do "
            "this for you: a child process cannot change the environment of "
            "the shell that started it. Copy the line and run it in the "
            "terminal you want to affect.\n\n"
            "Note that DOCKER_HOST overrides any context, so this wins over "
            "`docker context use` for as long as it is set."),
    ))

    # --- Verify it actually answers --------------------------------------
    actions.append(Action(
        id="test-ps",
        label="Test: list containers here",
        command=[binary, "-H", address, "ps", "-a",
                 "--format", "{{.Names}}"] if not is_podman
        else ["podman", "--url", address, "ps", "-a", "--format", "{{.Names}}"],
        scope=USER,
        explanation=(
            "Runs the real CLI against this endpoint and shows what comes "
            "back. This is the check that separates 'the socket exists' from "
            "'the engine answers and has containers' \u2014 the two are not "
            "the same, and the difference is usually why a container seems "
            "to have vanished."),
    ))

    # --- Podman socket lifecycle -----------------------------------------
    if is_podman and "/run/user/" in address:
        actions.append(Action(
            id="socket-restart",
            label="Restart the user socket",
            command=["systemctl", "--user", "restart", "podman.socket"],
            scope=USER,
            explanation=(
                "Restarts the rootless Podman API socket. Worth trying when "
                "the socket file exists but nothing answers on it."),
        ))

    return actions


def actions_for_docker_host(docker_host: str) -> list:
    """What to do about a DOCKER_HOST that is overriding the context."""
    if not docker_host:
        return []

    sources = find_variable_source("DOCKER_HOST")
    if sources:
        where = "\n".join(f"  {path}:{line}  {text}"
                          for path, line, text in sources)
        explanation = (
            "DOCKER_HOST is set, so every context is ignored. It is set in:"
            f"\n\n{where}\n\n"
            "Remove or comment out that line, then open a new shell. To "
            "affect the shell you have open right now, run `unset "
            "DOCKER_HOST` in it \u2014 kontainy cannot do that for you, "
            "because a child process cannot change its parent's environment.")
    else:
        explanation = (
            "DOCKER_HOST is set, so every context is ignored, but it does "
            "not appear in any of the usual startup files. It may come from "
            "your desktop session, a systemd user environment, or the "
            "terminal's own profile. Check with:\n\n"
            "  systemctl --user show-environment | grep DOCKER\n"
            "  grep -rn DOCKER_HOST ~/.config/")

    return [Action(
        id="unset-docker-host",
        label="Stop DOCKER_HOST overriding contexts",
        command=[],
        scope=SHELL,
        shell_text="unset DOCKER_HOST",
        explanation=explanation,
    )]


# ---------------------------------------------------------------------------
#  systemd units
# ---------------------------------------------------------------------------
@dataclass
class Unit:
    name: str
    user: bool
    state: str = "unknown"
    enabled: str = "unknown"
    description: str = ""

    @property
    def scope_label(self) -> str:
        return "user" if self.user else "system"

    @property
    def active(self) -> bool:
        return self.state == "active"


UNITS = [
    ("podman.socket", True,
     "The rootless Podman API socket. Without it kontainy cannot talk to "
     "Podman over the API at all."),
    ("podman-auto-update.timer", True,
     "Performs the update for containers labelled AutoUpdate=registry. The "
     "label does nothing while this is inactive."),
    ("podman-restart.service", True,
     "Restarts containers marked --restart=always after a reboot. Rootless "
     "Podman has no daemon to do this on its own."),
    ("podman.socket", False,
     "The rootful Podman API socket, for containers running as root."),
    ("docker.socket", False,
     "Socket activation for Docker. While this is active, stopping "
     "docker.service is not enough \u2014 the next docker command starts it "
     "again."),
    ("docker.service", False,
     "The Docker daemon itself."),
]


# systemctl writes its own diagnostics to stdout as well as stderr, so a
# machine without systemd, or a user session without a bus, produces a
# multi-line paragraph where a one-word state belongs. Collapse those to a
# single readable token rather than pasting a stack of error text into a
# table cell.
_UNAVAILABLE = (
    "has not been booted with systemd",
    "failed to connect to bus",
    "no medium found",
    "host is down",
    "command not found",
)


def _unit_property(unit: str, user: bool, prop: str) -> str:
    cmd = ["systemctl"]
    if user:
        cmd.append("--user")
    cmd += [prop, unit]
    result = run(cmd, timeout=6.0, record=False)
    text = (result.stdout or result.stderr).strip()
    if not text:
        return "unknown"
    lowered = text.lower()
    if any(marker in lowered for marker in _UNAVAILABLE):
        return "unavailable"
    # is-active and is-enabled answer in one word; anything longer is noise.
    return text.splitlines()[0].strip() or "unknown"


def list_units() -> list:
    out = []
    for name, user, description in UNITS:
        unit = Unit(name=name, user=user, description=description)
        unit.state = _unit_property(name, user, "is-active")
        unit.enabled = _unit_property(name, user, "is-enabled")
        out.append(unit)
    return out


def actions_for_unit(unit: Unit) -> list:
    scope = USER if unit.user else ROOT
    base = ["systemctl"] + (["--user"] if unit.user else [])
    actions = []

    if unit.state == "unavailable":
        actions.append(Action(
            id=f"unavailable-{unit.name}", label="systemd is not reachable",
            command=[], scope=NONE,
            explanation=(
                "systemctl could not be queried here. Either this system does "
                "not run systemd as PID 1 \u2014 a container or WSL without "
                "systemd enabled \u2014 or there is no user session bus. "
                "Unit actions are unavailable until that is resolved.")))
        return actions

    if unit.active:
        actions.append(Action(
            id=f"stop-{unit.name}", label="Stop",
            command=base + ["stop", unit.name], scope=scope,
            explanation=f"Stops {unit.name} for this session.",
            destructive=True))
    else:
        actions.append(Action(
            id=f"start-{unit.name}", label="Start",
            command=base + ["start", unit.name], scope=scope,
            explanation=f"Starts {unit.name} now, for this session only."))

    if unit.enabled.startswith("enabled"):
        actions.append(Action(
            id=f"disable-{unit.name}", label="Disable at boot",
            command=base + ["disable", unit.name], scope=scope,
            explanation=f"Stops {unit.name} starting automatically.",
            destructive=True))
    else:
        actions.append(Action(
            id=f"enable-{unit.name}", label="Enable and start",
            command=base + ["enable", "--now", unit.name], scope=scope,
            explanation=(
                f"Starts {unit.name} and makes it start automatically. "
                + ("\u26a0 For a USER unit to survive logout and come back "
                   "after a reboot, linger must also be enabled \u2014 see "
                   "the Linger action below."
                   if unit.user else ""))))

    actions.append(Action(
        id=f"status-{unit.name}", label="Show status",
        command=base + ["status", "--no-pager", unit.name], scope=USER,
        explanation=f"Full systemd status and the last log lines for "
                    f"{unit.name}."))
    return actions


def linger_state() -> bool:
    user = os.environ.get("USER") or os.environ.get("LOGNAME") or ""
    if not user:
        return False
    result = run(["loginctl", "show-user", user, "-p", "Linger"],
                 timeout=6.0, record=False)
    return result.stdout.strip().endswith("=yes")


def linger_action(enabled: bool) -> Action:
    user = os.environ.get("USER") or "$USER"
    if enabled:
        return Action(
            id="linger-off", label="Disable linger",
            command=["loginctl", "disable-linger", user], scope=USER,
            explanation=(
                "Turns off linger. Rootless containers and Quadlet units will "
                "then stop when you log out and will not return after a "
                "reboot."),
            destructive=True)
    return Action(
        id="linger-on", label="Enable linger",
        command=["loginctl", "enable-linger", user], scope=USER,
        explanation=(
            "User systemd units only run while a session is open. With "
            "linger enabled they keep running after logout and start again "
            "at boot.\n\n"
            "This is required for Quadlet units and for any expectation that "
            "`--restart=always` survives a reboot. It is the single most "
            "commonly skipped step in a rootless setup."))
