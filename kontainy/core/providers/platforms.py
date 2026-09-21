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
    summary = ("A remote is an Incus server: this machine, another host, or "
               "an image server. Instances are full operating systems — "
               "containers or virtual machines.")


class LxdProvider(_RemoteProvider):
    id = "lxd"
    name = "LXD"
    icon = "\U0001f4e6"
    binary = "lxc"
    tool_ids = ["lxd", "lxc"]
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
