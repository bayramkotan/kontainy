"""kontainy — Kubernetes, KVM/libvirt, Incus, LXD and WSL providers."""

from __future__ import annotations

import os
import platform
import re
import shutil
from pathlib import Path

from ...utils import fs
from ...utils.config import config
from .base import (NONE, Column, Field, Listing, Provider, Target, action,
                   cli_text, json_value)
from ..actions import Action, USER


# ===========================================================================
#  Kubernetes — kubeconfig contexts
# ===========================================================================
class KubernetesProvider(Provider):
    id = "kubernetes"
    name = "Kubernetes"
    icon = "\u2638"
    binary = "kubectl"
    target_noun = "Context"
    target_noun_plural = "Contexts"
    object_noun_plural = "Pods"
    tool_ids = ["kubectl", "k3s", "kind", "minikube", "helm", "k9s", "lens"]
    services = [
        ("k3s.service", False, "The k3s server, if this machine runs one."),
        ("kubelet.service", False, "The node agent on a kubeadm node."),
    ]
    learn_category = "kubernetes"
    summary = ("A kubeconfig context joins a cluster, a user and a default "
               "namespace. The current context is where every kubectl "
               "command goes.")

    def version(self):
        if not self.available():
            return ""
        ok, text = cli_text(["kubectl", "version", "--client", "-o", "json"])
        data = json_value(text, {}) if ok else {}
        return ((data or {}).get("clientVersion") or {}).get("gitVersion", "")

    def _config(self) -> dict:
        ok, text = cli_text(["kubectl", "config", "view", "-o", "json"])
        return (json_value(text, {}) or {}) if ok else {}

    def targets(self):
        data = self._config()
        current = data.get("current-context", "")
        out = []
        for entry in data.get("contexts") or []:
            ctx = entry.get("context") or {}
            name = entry.get("name", "")
            ns = ctx.get("namespace", "default")
            out.append(Target(
                name=name, address=ctx.get("cluster", ""),
                active=name == current,
                detail=f"user {ctx.get('user', '?')} \u00b7 namespace {ns}"))
        return out

    def activate(self, target):
        return action(f"kubectl-use-{target.name}",
                      f"Make '{target.name}' the current context",
                      ["kubectl", "config", "use-context", target.name],
                      "Writes current-context into your kubeconfig. Every "
                      "kubectl command, and tools like k9s and Lens, follow it.")

    def add_fields(self):
        return [
            Field("name", "Name", "staging"),
            Field("cluster", "Cluster", "an existing cluster entry"),
            Field("user", "User", "an existing user entry"),
            Field("namespace", "Namespace", "default", required=False),
        ]

    def add(self, values):
        argv = ["kubectl", "config", "set-context", values["name"],
                f"--cluster={values['cluster']}", f"--user={values['user']}"]
        if values.get("namespace"):
            argv.append(f"--namespace={values['namespace']}")
        return action(f"kubectl-set-context-{values['name']}",
                      f"Create context '{values['name']}'", argv,
                      "A context only joins a cluster and a user that already "
                      "exist in your kubeconfig; it does not create either.")

    def remove(self, target):
        return action(f"kubectl-delete-context-{target.name}",
                      f"Delete context '{target.name}'",
                      ["kubectl", "config", "delete-context", target.name],
                      "Removes the context entry. The cluster and user "
                      "entries it referred to stay in the kubeconfig.",
                      destructive=True)

    def test(self, target):
        return action(f"kubectl-test-{target.name}", f"Test '{target.name}'",
                      ["kubectl", "--context", target.name, "cluster-info"],
                      "Asks the API server for its address and core services.")

    def objects(self, target):
        argv = ["kubectl"]
        if target:
            argv += ["--context", target.name]
        argv += ["get", "pods", "-A", "-o", "json", "--request-timeout=8s"]
        ok, text = cli_text(argv, timeout=12.0)
        listing = Listing(
            columns=[Column("namespace", "Namespace"), Column("name", "Pod"),
                     Column("phase", "Phase"), Column("node", "Node"),
                     Column("restarts", "Restarts")],
            command=" ".join(argv))
        if not ok:
            listing.error = text
            return listing
        for item in (json_value(text, {}) or {}).get("items") or []:
            meta, spec = item.get("metadata") or {}, item.get("spec") or {}
            status = item.get("status") or {}
            restarts = sum(c.get("restartCount", 0)
                           for c in status.get("containerStatuses") or [])
            listing.rows.append({
                "namespace": meta.get("namespace", ""),
                "name": meta.get("name", ""),
                "phase": status.get("phase", ""),
                "node": spec.get("nodeName", ""),
                "restarts": str(restarts)})
        return listing


# ===========================================================================
#  KVM / QEMU via libvirt — connection URIs
# ===========================================================================
LIBVIRT_CONF = Path.home() / ".config" / "libvirt" / "libvirt.conf"
BUILTIN_URIS = [
    ("system", "qemu:///system",
     "Machines owned by root, managed by the system libvirtd. What "
     "virt-manager opens by default."),
    ("session", "qemu:///session",
     "Machines owned by you, run under your own account. A completely "
     "separate set from qemu:///system."),
]


def _read_uri_default() -> str:
    for line in fs.read_text(LIBVIRT_CONF).splitlines():
        match = re.match(r'\s*uri_default\s*=\s*"([^"]*)"', line)
        if match:
            return match.group(1)
    return ""


def _write_uri_default(uri: str) -> str:
    """Set uri_default in the user's libvirt.conf, keeping every other line."""
    LIBVIRT_CONF.parent.mkdir(parents=True, exist_ok=True)
    lines = fs.read_text(LIBVIRT_CONF).splitlines()
    new_line = f'uri_default = "{uri}"'
    replaced = False
    for i, line in enumerate(lines):
        if re.match(r"\s*#?\s*uri_default\s*=", line):
            lines[i] = new_line
            replaced = True
            break
    if not replaced:
        lines.append(new_line)
    tmp = LIBVIRT_CONF.with_suffix(".conf.tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, LIBVIRT_CONF)
    return f"{LIBVIRT_CONF} now sets uri_default = {uri}"


class LibvirtProvider(Provider):
    id = "libvirt"
    name = "KVM / libvirt"
    icon = "\U0001f5a5"
    binary = "virsh"
    target_noun = "Connection"
    target_noun_plural = "Connections"
    object_noun_plural = "Virtual machines"
    tool_ids = ["libvirt", "qemu", "virt-manager", "virtualbox", "multipass",
                "vagrant"]
    learn_category = "kvm"
    services = [
        ("libvirtd.service", False,
         "The monolithic libvirt daemon, on older setups."),
        ("virtqemud.service", False,
         "The modular QEMU driver daemon that replaced libvirtd."),
        ("virtqemud.socket", False, "Socket activation for virtqemud."),
    ]
    platforms = ("linux", "macos")
    summary = ("A libvirt connection URI selects which hypervisor and which "
               "set of machines you are looking at. qemu:///system and "
               "qemu:///session hold entirely separate machines \u2014 the "
               "usual reason a VM seems to have vanished.")

    def _custom(self) -> list:
        return list(config().get("libvirt_uris") or [])

    def _active_uri(self) -> str:
        return (os.environ.get("LIBVIRT_DEFAULT_URI")
                or _read_uri_default() or "qemu:///system")

    def warning(self):
        if os.environ.get("LIBVIRT_DEFAULT_URI"):
            return ("LIBVIRT_DEFAULT_URI is set in this environment and "
                    "overrides libvirt.conf, the same way DOCKER_HOST "
                    "overrides a docker context.")
        return ""

    def targets(self):
        active = self._active_uri()
        out = [Target(name=name, address=uri, active=uri == active,
                      detail=detail, removable=False)
               for name, uri, detail in BUILTIN_URIS]
        for entry in self._custom():
            out.append(Target(name=entry.get("name", entry.get("uri", "")),
                              address=entry.get("uri", ""),
                              active=entry.get("uri") == active,
                              detail=entry.get("detail", "added in kontainy")))
        if not any(t.active for t in out):
            out.append(Target(name="(environment)", address=active,
                              active=True, removable=False,
                              detail="from LIBVIRT_DEFAULT_URI"))
        return out

    def activate(self, target):
        return Action(
            id=f"libvirt-default-{target.name}",
            label=f"Make {target.address} the default connection",
            command=[], scope=USER,
            shell_text=f"echo 'uri_default = \"{target.address}\"' >> "
                       f"{LIBVIRT_CONF}",
            explanation=(
                f"Sets uri_default in {LIBVIRT_CONF}, so virsh and "
                f"virt-install use {target.address} when no -c is given. "
                f"kontainy rewrites the existing line rather than appending "
                f"a duplicate, and keeps every other line of the file."),
            func=lambda: _write_uri_default(target.address))

    def add_fields(self):
        return [
            Field("name", "Name", "lab-server"),
            Field("uri", "URI", "qemu+ssh://user@host/system",
                  "qemu+ssh://… for a remote host, "
                  "qemu:///system or qemu:///session locally."),
        ]

    def add(self, values):
        def store():
            entries = self._custom()
            entries = [e for e in entries if e.get("name") != values["name"]]
            entries.append({"name": values["name"], "uri": values["uri"]})
            config().set("libvirt_uris", entries)
            return f"saved {values['name']} = {values['uri']}"
        return Action(
            id=f"libvirt-add-{values['name']}",
            label=f"Add connection '{values['name']}'",
            command=[], scope=USER,
            shell_text=f"virsh -c {values['uri']} list --all",
            explanation=(
                "libvirt has no list of saved connections of its own, so "
                "kontainy keeps this one in its preferences. The command "
                "shown is how you would reach it by hand."),
            func=store)

    def remove(self, target):
        def drop():
            config().set("libvirt_uris", [e for e in self._custom()
                                          if e.get("name") != target.name])
            return f"removed {target.name}"
        return Action(
            id=f"libvirt-remove-{target.name}",
            label=f"Remove connection '{target.name}'",
            command=[], scope=USER, destructive=True,
            shell_text=f"# forget {target.address} in kontainy",
            explanation="Only forgets the saved URI. No machine is touched.",
            func=drop)

    def test(self, target):
        return action(f"virsh-test-{target.name}", f"Test '{target.name}'",
                      ["virsh", "-c", target.address, "version"],
                      "Connects to the hypervisor and reports the library, "
                      "API and hypervisor versions.")

    def objects(self, target):
        uri = target.address if target else self._active_uri()
        argv = ["virsh", "-c", uri, "list", "--all"]
        ok, text = cli_text(argv)
        listing = Listing(
            columns=[Column("id", "Id"), Column("name", "Name"),
                     Column("state", "State")],
            command=" ".join(argv))
        if not ok:
            listing.error = text
            return listing
        for line in text.splitlines():
            # A shut-off domain has "-" as its id, so only the ruler line of
            # dashes may be skipped — not every line starting with a dash.
            if line.strip().startswith("--"):
                continue
            parts = line.split(None, 2)
            if len(parts) < 3 or parts[0] == "Id":
                continue
            listing.rows.append({"id": parts[0], "name": parts[1],
                                 "state": parts[2].strip()})
        return listing

    def terminal_env(self, target):
        return {"LIBVIRT_DEFAULT_URI": target.address} if target else {}


# ===========================================================================
#  Incus and LXD — remotes
# ===========================================================================
class _RemoteProvider(Provider):
    target_noun = "Remote"
    target_noun_plural = "Remotes"
    object_noun_plural = "Instances"
    learn_category = "lxc"
    platforms = ("linux",)

    def targets(self):
        ok, text = cli_text([self.binary, "remote", "list", "--format", "json"])
        remotes = (json_value(text, {}) or {}) if ok else {}
        ok, current = cli_text([self.binary, "remote", "get-default"])
        current = current.strip() if ok else "local"
        out = []
        for name, info in remotes.items():
            info = info or {}
            out.append(Target(
                name=name, address=info.get("Addr", info.get("addr", "")),
                active=name == current,
                detail=info.get("Protocol", info.get("protocol", "")),
                removable=name not in ("local",) and not info.get("Static")))
        return out

    def activate(self, target):
        return action(f"{self.binary}-switch-{target.name}",
                      f"Make '{target.name}' the default remote",
                      [self.binary, "remote", "switch", target.name],
                      "Every command without an explicit remote: prefix now "
                      f"goes to {target.address or target.name}.")

    def add_fields(self):
        return [Field("name", "Name", "server"),
                Field("url", "Address", "https://server:8443")]

    def add(self, values):
        return action(f"{self.binary}-remote-add-{values['name']}",
                      f"Add remote '{values['name']}'",
                      [self.binary, "remote", "add", values["name"],
                       values["url"]],
                      "Adds the remote. You may be asked to trust its "
                      "certificate the first time.")

    def remove(self, target):
        return action(f"{self.binary}-remote-remove-{target.name}",
                      f"Remove remote '{target.name}'",
                      [self.binary, "remote", "remove", target.name],
                      "Forgets the remote. Instances on it are untouched.",
                      destructive=True)

    def test(self, target):
        return action(f"{self.binary}-test-{target.name}",
                      f"Test '{target.name}'",
                      [self.binary, "info", f"{target.name}:"],
                      "Asks the server for its version and configuration.")

    def objects(self, target):
        remote = f"{target.name}:" if target else ""
        argv = [self.binary, "list"] + ([remote] if remote else []) + [
            "--format", "json"]
        ok, text = cli_text(argv)
        listing = Listing(
            columns=[Column("name", "Name"), Column("type", "Type"),
                     Column("status", "Status"), Column("image", "Image")],
            command=" ".join(argv))
        if not ok:
            listing.error = text
            return listing
        for item in json_value(text, []) or []:
            cfg = item.get("config") or {}
            listing.rows.append({
                "name": item.get("name", ""),
                "type": item.get("type", ""),
                "status": item.get("status", ""),
                "image": cfg.get("image.description", "")})
        return listing


class IncusProvider(_RemoteProvider):
    id = "incus"
    name = "Incus"
    icon = "\U0001f9f1"
    binary = "incus"
    tool_ids = ["incus", "lxc", "distrobox", "systemd-nspawn"]
    services = [("incus.service", False, "The Incus daemon."),
                ("incus.socket", False, "Socket activation for Incus.")]
    summary = ("A remote is an Incus server: this machine, another host, or "
               "an image server. Instances are full operating systems — "
               "containers or virtual machines.")


class LxdProvider(_RemoteProvider):
    id = "lxd"
    name = "LXD"
    icon = "\U0001f4e6"
    binary = "lxc"
    tool_ids = ["lxd", "lxc"]
    services = [("lxd.service", False, "The LXD daemon."),
                ("snap.lxd.daemon.service", False,
                 "The LXD daemon when installed as a snap.")]
    summary = ("LXD's client is also called `lxc`. A remote is an LXD "
               "server; instances are system containers or VMs.")

    def available(self):
        # `lxc` alone could be the classic LXC toolset; LXD's client answers
        # `lxc remote`. Checking the daemon binary avoids the confusion.
        return super().available() and bool(shutil.which("lxd"))

    def unavailable_reason(self):
        return ("LXD was not found. Note that `lxc` on its own may be the "
                "classic LXC tools rather than LXD's client.")


# ===========================================================================
#  WSL — Windows only
# ===========================================================================
def parse_wsl_list(text: str) -> list:
    """Parse `wsl --list --verbose`.

    The default distribution is marked with an asterisk in the first
    column. Docker Desktop's own Linux shows up here as docker-desktop.
    """
    out = []
    for line in text.splitlines():
        if not line.strip() or line.strip().upper().startswith("NAME"):
            continue
        active = line.lstrip().startswith("*")
        parts = line.replace("*", " ").split()
        if len(parts) < 3:
            continue
        name, state, version = parts[0], parts[1], parts[2]
        note = ""
        if name.startswith("docker-desktop"):
            note = " \u2014 Docker Desktop's own Linux"
        elif name.startswith("podman-machine"):
            note = " \u2014 Podman machine"
        out.append(Target(name=name, address=f"WSL {version}", active=active,
                          detail=f"{state}{note}",
                          removable=not name.startswith("docker-desktop")))
    return out


class WslProvider(Provider):
    id = "wsl"
    name = "WSL"
    icon = "\U0001fa9f"
    binary = "wsl"
    target_noun = "Distribution"
    target_noun_plural = "Distributions"
    object_noun_plural = "Distributions"
    tool_ids = ["docker-desktop", "podman-desktop"]
    platforms = ("windows",)
    summary = ("Windows Subsystem for Linux. Docker Desktop and podman "
               "machine both run their engine inside a WSL distribution, so "
               "this is where the Linux behind them actually lives.")

    def available(self):
        return platform.system() == "Windows" and super().available()

    def unavailable_reason(self):
        if platform.system() != "Windows":
            return "WSL exists only on Windows."
        return "wsl.exe was not found. Enable it with: wsl --install"

    def version(self):
        ok, text = cli_text(["wsl", "--version"])
        return text.splitlines()[0] if ok and text else ""

    def targets(self):
        ok, text = cli_text(["wsl", "--list", "--verbose"])
        return parse_wsl_list(text) if ok else []

    def activate(self, target):
        return action(f"wsl-default-{target.name}",
                      f"Make '{target.name}' the default distribution",
                      ["wsl", "--set-default", target.name],
                      "Plain `wsl` and `bash.exe` will open this distribution.")

    def add_fields(self):
        return [Field("name", "Distribution", "Ubuntu-24.04",
                      "Run `wsl --list --online` to see the names available.")]

    def add(self, values):
        return action(f"wsl-install-{values['name']}",
                      f"Install '{values['name']}'",
                      ["wsl", "--install", "-d", values["name"]],
                      "Downloads and registers the distribution. The first "
                      "start asks you to create a Linux user.")

    def remove(self, target):
        return action(f"wsl-unregister-{target.name}",
                      f"Unregister '{target.name}'",
                      ["wsl", "--unregister", target.name],
                      "\u26a0 This DELETES the distribution and every file "
                      "inside it. There is no undo.",
                      destructive=True)

    def test(self, target):
        return action(f"wsl-test-{target.name}", f"Test '{target.name}'",
                      ["wsl", "-d", target.name, "-e", "uname", "-a"],
                      "Starts the distribution if needed and prints its "
                      "kernel version.")

    def objects(self, target):
        listing = Listing(columns=[Column("name", "Distribution"),
                                   Column("state", "State"),
                                   Column("version", "WSL")],
                          command="wsl --list --verbose")
        for t in self.targets():
            listing.rows.append({"name": t.name, "state": t.detail,
                                 "version": t.address})
        return listing


# ===========================================================================
#  Object and bulk actions
# ===========================================================================
from ..elevate import run as _run


def _sequence(id: str, label: str, commands: list, explanation: str,
              destructive: bool = False) -> Action:
    """Run several commands one after another — for tools like virsh that
    take a single object per call. The dialog shows every line."""
    def execute():
        failures = []
        for argv in commands:
            result = _run(argv, note=id)
            if not result.ok:
                failures.append(f"{' '.join(argv)}: {result.output}")
        if failures:
            raise RuntimeError("\n".join(failures))
        return f"{len(commands)} commands succeeded"
    return Action(id=id, label=label, command=[], scope=USER,
                  shell_text="\n".join(" ".join(c) for c in commands),
                  explanation=explanation, destructive=destructive, func=execute)


def _libvirt_running(row):
    return str(row.get("state", "")).lower() in ("running", "idle", "paused")


def _libvirt_object_actions(self, target, row):
    uri = target.address if target else self._active_uri()
    name = row.get("name", "")
    base = ["virsh", "-c", uri]
    out = []
    if _libvirt_running(row):
        out += [
            action(f"virsh-shutdown-{name}", "\u23fb  Shut down",
                   base + ["shutdown", name],
                   "Asks the guest operating system to shut down cleanly, "
                   "like pressing the power button once."),
            action(f"virsh-reboot-{name}", "\u21bb  Reboot",
                   base + ["reboot", name], "Asks the guest to reboot."),
            action(f"virsh-destroy-{name}", "\u26a1  Force off",
                   base + ["destroy", name],
                   "Pulls the plug. Despite the name nothing is deleted, but "
                   "unsaved data inside the guest is lost.", destructive=True),
        ]
    else:
        out.append(action(f"virsh-start-{name}", "\u25b6  Start",
                          base + ["start", name], f"Boots {name}."))
    out.append(action(f"virsh-autostart-{name}", "\u23f0  Start at boot",
                      base + ["autostart", name],
                      "Starts this machine whenever the host boots."))
    out.append(action(f"virsh-info-{name}", "\u2139  Info",
                      base + ["dominfo", name],
                      "State, CPUs, memory and autostart setting."))
    return out


def _libvirt_bulk(self, target, rows):
    uri = target.address if target else self._active_uri()
    stopped = [r["name"] for r in rows if not _libvirt_running(r)]
    running = [r["name"] for r in rows if _libvirt_running(r)]
    out = []
    if stopped:
        out.append(_sequence("virsh-start-all", f"\u25b6  Start all ({len(stopped)})",
                             [["virsh", "-c", uri, "start", n] for n in stopped],
                             "Boots every stopped machine on this connection. "
                             "virsh takes one machine per command, so they run "
                             "in turn."))
    if running:
        out.append(_sequence("virsh-shutdown-all",
                             f"\u23fb  Shut down all ({len(running)})",
                             [["virsh", "-c", uri, "shutdown", n] for n in running],
                             "Asks every running guest to shut down cleanly.",
                             destructive=True))
    return out


LibvirtProvider.object_actions = _libvirt_object_actions
LibvirtProvider.bulk_actions = _libvirt_bulk


def _remote_running(row):
    return str(row.get("status", "")).lower() == "running"


def _remote_object_actions(self, target, row):
    name = row.get("name", "")
    ref = f"{target.name}:{name}" if target else name
    out = []
    if _remote_running(row):
        out += [action(f"{self.binary}-stop-{name}", "\u25a0  Stop",
                       [self.binary, "stop", ref], f"Stops {name}."),
                action(f"{self.binary}-restart-{name}", "\u21bb  Restart",
                       [self.binary, "restart", ref], f"Restarts {name}.")]
    else:
        out.append(action(f"{self.binary}-start-{name}", "\u25b6  Start",
                          [self.binary, "start", ref], f"Starts {name}."))
    out.append(action(f"{self.binary}-delete-{name}", "\U0001f5d1  Delete",
                      [self.binary, "delete", "--force", ref],
                      f"Deletes {name} and its root filesystem.",
                      destructive=True))
    return out


def _remote_bulk(self, target, rows):
    prefix = f"{target.name}:" if target else ""
    stopped = [prefix + r["name"] for r in rows if not _remote_running(r)]
    running = [prefix + r["name"] for r in rows if _remote_running(r)]
    out = []
    if stopped:
        out.append(action(f"{self.binary}-start-all",
                          f"\u25b6  Start all ({len(stopped)})",
                          [self.binary, "start"] + stopped,
                          "Starts every stopped instance, in one command."))
    if running:
        out.append(action(f"{self.binary}-stop-all",
                          f"\u25a0  Stop all ({len(running)})",
                          [self.binary, "stop"] + running,
                          "Stops every running instance, in one command.",
                          destructive=True))
    return out


for _cls in (IncusProvider, LxdProvider):
    _cls.object_actions = _remote_object_actions
    _cls.bulk_actions = _remote_bulk


def _kube_object_actions(self, target, row):
    ctx = ["--context", target.name] if target else []
    ns, name = row.get("namespace", "default"), row.get("name", "")
    return [
        action(f"kubectl-logs-{name}", "\U0001f4dc  Logs",
               ["kubectl"] + ctx + ["-n", ns, "logs", "--tail=200", name],
               "The last 200 lines from the pod's first container."),
        action(f"kubectl-describe-{name}", "\u2139  Describe",
               ["kubectl"] + ctx + ["-n", ns, "describe", "pod", name],
               "Events, conditions and container states — where most "
               "\u2018why is it not starting\u2019 answers are."),
        action(f"kubectl-delete-{name}", "\u21bb  Delete (recreate)",
               ["kubectl"] + ctx + ["-n", ns, "delete", "pod", name],
               "Deletes the pod. If a Deployment, StatefulSet or DaemonSet "
               "owns it, a replacement is created at once — the usual way to "
               "restart a pod. A bare pod is simply gone.", destructive=True),
    ]


KubernetesProvider.object_actions = _kube_object_actions


def _wsl_object_actions(self, target, row):
    name = row.get("name", "")
    return [
        action(f"wsl-terminate-{name}", "\u25a0  Terminate",
               ["wsl", "--terminate", name],
               f"Stops {name}. Its files are untouched.", destructive=True),
        action(f"wsl-run-{name}", "\u25b6  Start",
               ["wsl", "-d", name, "-e", "true"],
               f"Starts {name} in the background by running a no-op in it."),
    ]


def _wsl_bulk(self, target, rows):
    return [action("wsl-shutdown", "\u25a0  Shut down all WSL",
                   ["wsl", "--shutdown"],
                   "Stops every distribution and the WSL virtual machine, "
                   "including Docker Desktop's and podman machine's.",
                   destructive=True)]


WslProvider.object_actions = _wsl_object_actions
WslProvider.bulk_actions = _wsl_bulk


# ===========================================================================
#  KVM / libvirt virtual networks
# ===========================================================================
import ipaddress as _ip
import tempfile as _tempfile

from .base import Section


def parse_net_list(text: str) -> list:
    """Parse `virsh net-list --all`: Name, State, Autostart, Persistent."""
    rows = []
    for line in text.splitlines():
        if line.strip().startswith("--") or not line.strip():
            continue
        parts = line.split()
        if parts[0] == "Name" or len(parts) < 4:
            continue
        rows.append({"name": parts[0], "state": parts[1],
                     "autostart": parts[2], "persistent": parts[3]})
    return rows


def network_xml(name: str, bridge: str, address: str, prefix: int,
                dhcp_start: str, dhcp_end: str, mode: str = "nat") -> str:
    """A libvirt network definition. mode is nat, route or isolated."""
    forward = "" if mode == "isolated" else f"  <forward mode='{mode}'/>\n"
    dhcp = (f"    <dhcp>\n      <range start='{dhcp_start}' end='{dhcp_end}'/>\n"
            f"    </dhcp>\n") if dhcp_start and dhcp_end else ""
    netmask = str(_ip.IPv4Network(f"0.0.0.0/{prefix}").netmask)
    return (f"<network>\n  <name>{name}</name>\n{forward}"
            f"  <bridge name='{bridge}' stp='on' delay='0'/>\n"
            f"  <ip address='{address}' netmask='{netmask}'>\n{dhcp}"
            f"  </ip>\n</network>\n")


def _net_listing(self, target):
    uri = target.address if target else self._active_uri()
    argv = ["virsh", "-c", uri, "net-list", "--all"]
    ok, text = cli_text(argv)
    listing = Listing(columns=[Column("name", "Network"), Column("state", "State"),
                               Column("autostart", "At boot"),
                               Column("persistent", "Persistent")],
                      command=" ".join(argv))
    if not ok:
        listing.error = text
    else:
        listing.rows = parse_net_list(text)
    return listing


def _net_actions(self, target, row):
    uri = target.address if target else self._active_uri()
    base = ["virsh", "-c", uri]
    name = row.get("name", "")
    active = row.get("state") == "active"
    out = []
    if active:
        out.append(action(f"net-destroy-{name}", "\u25a0  Stop",
                          base + ["net-destroy", name],
                          f"Stops {name}. Guests on it lose connectivity until "
                          f"it is started again; the definition is kept.",
                          destructive=True))
    else:
        out.append(action(f"net-start-{name}", "\u25b6  Start",
                          base + ["net-start", name], f"Starts {name}."))
    if row.get("autostart") == "yes":
        out.append(action(f"net-noauto-{name}", "\u23f0  Don't start at boot",
                          base + ["net-autostart", "--disable", name],
                          f"{name} will no longer start with the host."))
    else:
        out.append(action(f"net-auto-{name}", "\u23f0  Start at boot",
                          base + ["net-autostart", name],
                          f"Starts {name} whenever the host boots. The "
                          f"'default' network usually needs this, or VMs "
                          f"come up with no network after a reboot."))
    out.append(action(f"net-xml-{name}", "\U0001f4c4  Show definition",
                      base + ["net-dumpxml", name],
                      "The network's full XML: forward mode, bridge, "
                      "addresses and DHCP range."))
    out.append(action(f"net-leases-{name}", "\U0001f4cb  DHCP leases",
                      base + ["net-dhcp-leases", name],
                      "Which guest got which address — the quickest way to "
                      "find a VM's IP."))
    out.append(action(f"net-undefine-{name}", "\U0001f5d1  Delete",
                      base + ["net-undefine", name],
                      f"Deletes the definition of {name}. Stop it first; "
                      f"guests that use it will have no network.",
                      destructive=True))
    return out


NET_FIELDS = [
    Field("name", "Name", "labnet"),
    Field("bridge", "Bridge", "virbr10",
          "The Linux bridge libvirt creates for this network."),
    Field("address", "Host address", "192.168.110.1",
          "The host's own address on this network; guests use it as gateway."),
    Field("prefix", "Prefix", "24", "24 means 255.255.255.0."),
    Field("dhcp_start", "DHCP from", "192.168.110.100", required=False),
    Field("dhcp_end", "DHCP to", "192.168.110.200", required=False),
    Field("mode", "Mode", "nat",
          "nat (guests reach out through the host), route, or isolated "
          "(guests see only each other and the host)."),
]


def _net_create(self, target, values):
    uri = target.address if target else self._active_uri()
    name = values["name"]
    mode = (values.get("mode") or "nat").strip().lower()
    if mode not in ("nat", "route", "isolated"):
        mode = "nat"
    xml = network_xml(name, values["bridge"], values["address"],
                      int(values.get("prefix") or 24), values.get("dhcp_start", ""),
                      values.get("dhcp_end", ""), mode)

    def execute():
        handle = _tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False,
                                              encoding="utf-8")
        handle.write(xml)
        handle.close()
        try:
            for argv in (["virsh", "-c", uri, "net-define", handle.name],
                         ["virsh", "-c", uri, "net-start", name],
                         ["virsh", "-c", uri, "net-autostart", name]):
                result = _run(argv, note=f"net-create-{name}")
                if not result.ok:
                    raise RuntimeError(f"{' '.join(argv)}: {result.output}")
        finally:
            os.unlink(handle.name)
        return f"network {name} defined, started and set to start at boot"

    return Action(
        id=f"net-create-{name}", label=f"Create network '{name}'",
        command=[], scope=USER,
        shell_text=(f"cat > {name}.xml <<'EOF'\n{xml}EOF\n"
                    f"virsh -c {uri} net-define {name}.xml\n"
                    f"virsh -c {uri} net-start {name}\n"
                    f"virsh -c {uri} net-autostart {name}"),
        explanation=(f"Defines a {mode} network from the XML shown, starts it "
                     f"and sets it to start at boot. On qemu:///system this "
                     f"needs permission to manage libvirt — membership of the "
                     f"libvirt group, or root."),
        func=execute)


def _libvirt_sections(self):
    return [Section(
        id="networks", title="Networks", icon="\U0001f310", noun="Network",
        key="name",
        summary=("Virtual networks the machines on this connection attach to. "
                 "'default' is the NAT network most VMs use; if it is not "
                 "active, guests boot with no network at all."),
        listing=lambda target: _net_listing(self, target),
        row_actions=lambda target, row: _net_actions(self, target, row),
        create_fields=NET_FIELDS,
        create=lambda target, values: _net_create(self, target, values))]


LibvirtProvider.sections = _libvirt_sections
