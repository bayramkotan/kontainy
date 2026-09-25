"""
kontainy — the settings of the applications themselves

The 152-entry catalogue covers the ENGINES: daemon.json, containers.conf,
storage.conf. This covers the APPLICATIONS around them — Docker Desktop's
own preferences, WSL's .wslconfig, podman machine's size, VMware's and
VirtualBox's own files. They decide how much memory a machine gets, whether
the API is exposed on a TCP port, whether nested virtualization is on; and
every one of them is edited today by hand, in a different format, in a
different place per operating system.

Bayram, 2026-09-25: "ky'den Docker Desktop, KVM, VirtualBox, VMware Pro
içinde config'lere ulaşıp değiştirebilelim. Bu uygulamanın en önemli
özelliklerinden biri olmalı."

Rules that make this safe:

* Every key says what it does AND what breaks when it is wrong.
* A file is backed up before it is written, and the change is shown first.
* Some applications rewrite their file when they close, so a change made
  while they run is lost: those keys are marked `close_first`.
* Anything owned by root is shown, never written; kontainy prints the
  command instead.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from ..utils import fs


@dataclass(frozen=True)
class AppKey:
    key: str                     # dotted for JSON, "section.name" for INI
    title: str
    vtype: str                   # str | int | bool | path
    what: str                    # what it does
    gotcha: str = ""             # what goes wrong when it is wrong
    default: str = ""
    danger: bool = False         # a wrong value can expose or destroy
    close_first: bool = False    # the app overwrites the file when it closes


@dataclass(frozen=True)
class AppConfig:
    id: str
    app: str                     # the application, as people call it
    file_label: str              # what the file is, in words
    fmt: str                     # json | ini | keyvalue | xml
    paths: dict                  # {"windows": [...], "linux": [...], ...}
    keys: list = field(default_factory=list)
    writable: bool = True        # false: kontainy shows, never writes
    note: str = ""

    def path(self) -> Path | None:
        """The first candidate that exists, else the first candidate."""
        from ..core.registry import OS_KIND
        candidates = [Path(os.path.expandvars(str(p))).expanduser()
                      for p in self.paths.get(OS_KIND, [])]
        if not candidates:
            return None
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return candidates[0]

    def exists(self) -> bool:
        path = self.path()
        return bool(path and path.is_file())


DOCKER_DESKTOP = AppConfig(
    id="docker-desktop", app="Docker Desktop",
    file_label="Docker Desktop's own settings",
    fmt="json",
    paths={
        "windows": [r"%APPDATA%\Docker\settings-store.json",
                    r"%APPDATA%\Docker\settings.json"],
        "macos": ["~/Library/Group Containers/group.com.docker/settings-store.json",
                  "~/Library/Group Containers/group.com.docker/settings.json"],
        "linux": ["~/.docker/desktop/settings-store.json",
                  "~/.docker/desktop/settings.json"],
    },
    note=("Docker Desktop writes this file when it closes, so edit it with "
          "the application shut down or the change is lost."),
    keys=[
        AppKey("Cpus", "CPUs", "int",
               "How many processor cores the Linux virtual machine gets.",
               "More than the host has does not fail, it just contends; the "
               "VM feels slower, not faster.", "half the host's cores",
               close_first=True),
        AppKey("MemoryMiB", "Memory (MiB)", "int",
               "Memory for the virtual machine, in MiB.",
               "Too little is the usual cause of a build that dies with exit "
               "code 137 — the kernel killed it, and the message says nothing "
               "about Docker Desktop.", "2048", close_first=True),
        AppKey("DiskSizeMiB", "Disk image size (MiB)", "int",
               "The upper limit of the virtual disk holding images, "
               "containers and volumes.",
               "Shrinking it is not a resize: Docker Desktop offers to reset "
               "the disk, which deletes everything in it.",
               danger=True, close_first=True),
        AppKey("AutoStart", "Start at login", "bool",
               "Whether Docker Desktop starts when you log in.",
               "With it off, every docker command after a reboot fails until "
               "the application is opened by hand.", "true",
               close_first=True),
        AppKey("KubernetesEnabled", "Kubernetes", "bool",
               "Runs a single-node Kubernetes inside Docker Desktop and "
               "writes a kubeconfig context for it.",
               "Turning it on downloads images and takes minutes; the "
               "cluster is not the same as a production one.", "false",
               close_first=True),
        AppKey("ExposeDockerAPIOnTCP2375", "Expose the API on TCP 2375",
               "bool",
               "Publishes the daemon API on localhost:2375 without TLS.",
               "Anyone who can reach that port owns the machine: the Docker "
               "API can mount the host filesystem into a container. Leave it "
               "off unless you know exactly who can reach the port.",
               "false", danger=True, close_first=True),
        AppKey("UseVirtualizationFramework", "Apple virtualization", "bool",
               "On macOS, use Apple's Virtualization.framework instead of "
               "the older hypervisor.",
               "Switching restarts the VM; a stopped container is fine, an "
               "unsaved one is not.", close_first=True),
        AppKey("UseResourceSaver", "Resource Saver", "bool",
               "Pauses the virtual machine when no container is running.",
               "The first command after a pause waits for the VM to wake, "
               "which looks like Docker being slow.", "true",
               close_first=True),
    ])

WSLCONFIG = AppConfig(
    id="wslconfig", app="WSL 2",
    file_label="the machine-wide WSL configuration",
    fmt="ini",
    paths={"windows": [r"%UserProfile%\.wslconfig"]},
    note=("Applies to every distribution. Changes take effect after "
          "`wsl --shutdown`, which stops Docker Desktop's engine too."),
    keys=[
        AppKey("wsl2.memory", "Memory", "str",
               "The ceiling for the WSL virtual machine, e.g. 8GB.",
               "Without it WSL takes up to half the host's memory, which is "
               "why a build can leave the desktop swapping.", "50% of host"),
        AppKey("wsl2.processors", "Processors", "int",
               "How many cores WSL may use.", "", "all of them"),
        AppKey("wsl2.swap", "Swap", "str",
               "Swap file size for the VM, e.g. 4GB; 0 disables it.",
               "With swap off, a build that exceeds the memory limit is "
               "killed rather than slowed."),
        AppKey("wsl2.nestedVirtualization", "Nested virtualization", "bool",
               "Lets KVM, QEMU and Android emulators run INSIDE a WSL "
               "distribution.",
               "Without it there is no /dev/kvm in the distribution and QEMU "
               "falls back to software emulation. Windows 11 only.", "true"),
        AppKey("wsl2.networkingMode", "Networking mode", "str",
               "NAT (the default) or mirrored, which gives the distribution "
               "the host's own addresses.",
               "Mirrored fixes VPN and localhost cases and breaks some "
               "port-forwarding habits; it needs a recent Windows 11."),
        AppKey("wsl2.autoMemoryReclaim", "Reclaim memory", "str",
               "gradual, dropcache or disabled — whether WSL gives freed "
               "memory back to Windows.",
               "Without it WSL keeps every byte it ever touched until it "
               "shuts down.", "disabled"),
    ])

PODMAN_MACHINE = AppConfig(
    id="podman-machine", app="podman machine",
    file_label="the default machine's size",
    fmt="keyvalue", writable=False,
    paths={
        "windows": [r"%APPDATA%\containers\podman\machine\wsl"],
        "macos": ["~/.config/containers/podman/machine/applehv"],
        "linux": ["~/.config/containers/podman/machine/qemu"],
    },
    note=("Podman keeps a machine's CPU, memory and disk in its own files. "
          "kontainy shows them; change them with  podman machine set "
          "--cpus N --memory MB --disk-size GB,  which is the supported way."),
    keys=[])

VMWARE = AppConfig(
    id="vmware", app="VMware Workstation / Fusion",
    file_label="VMware's own preferences",
    fmt="keyvalue",
    paths={
        "windows": [r"%APPDATA%\VMware\preferences.ini"],
        "linux": ["~/.vmware/preferences"],
        "macos": ["~/Library/Preferences/VMware Fusion/preferences"],
    },
    note="VMware rewrites this file when it closes; edit it with VMware shut "
         "down.",
    keys=[
        AppKey("prefvmx.minVmMemPct", "Guest memory in host RAM (%)", "int",
               "How much of a guest's memory VMware keeps in host RAM rather "
               "than swapping to the .vmem file.",
               "100 makes guests fast and can starve the host; 50 is the "
               "usual compromise.", "50", close_first=True),
        AppKey("prefvmx.useRecommendedLockedMemSize",
               "Allow all guest memory to be locked", "bool",
               "Lets VMware lock the full guest memory in host RAM.",
               "With several guests this can leave the host with nothing.",
               close_first=True),
        AppKey("pref.vmplayer.exit.vmAction", "On closing a VM window", "str",
               "What VMware does with a running guest when its window is "
               "closed: suspend, poweroff or ask.",
               "poweroff is a power cut for the guest; suspend keeps its "
               "state.", "suspend", close_first=True),
    ])

VIRTUALBOX = AppConfig(
    id="virtualbox", app="VirtualBox",
    file_label="VirtualBox's own configuration",
    fmt="xml", writable=False,
    paths={
        "windows": [r"%UserProfile%\.VirtualBox\VirtualBox.xml"],
        "linux": ["~/.config/VirtualBox/VirtualBox.xml"],
        "macos": ["~/Library/VirtualBox/VirtualBox.xml"],
    },
    note=("kontainy shows this file but does not write it: VirtualBox holds "
          "it open and rewrites it, and the supported way to change these is "
          "`VBoxManage setproperty`. The commands are shown per setting."),
    keys=[
        AppKey("SystemProperties.defaultMachineFolder",
               "Default machine folder", "path",
               "Where new virtual machines are created.",
               "Moving it does not move the existing machines; they keep "
               "their own paths.\n\nVBoxManage setproperty machinefolder PATH"),
        AppKey("SystemProperties.LoggingLevel", "Logging level", "str",
               "How much VBoxSVC writes to its log.",
               "VBoxManage setproperty loghistorycount N"),
    ])

ALL_APPS = [DOCKER_DESKTOP, WSLCONFIG, PODMAN_MACHINE, VMWARE, VIRTUALBOX]


def by_id(app_id: str):
    return next((app for app in ALL_APPS if app.id == app_id), None)


def apps_here() -> list:
    """The applications whose file could exist on this operating system."""
    from ..core.registry import OS_KIND
    return [app for app in ALL_APPS if app.paths.get(OS_KIND)]


# --- reading ----------------------------------------------------------------
def parse_ini(text: str) -> dict:
    """{"section.key": value} — enough for .wslconfig, which is flat INI."""
    out, section = {}, ""
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        name = f"{section}.{key.strip()}" if section else key.strip()
        out[name] = value.strip()
    return out


def parse_keyvalue(text: str) -> dict:
    """VMware's preferences: `name = "value"`, one per line."""
    out = {}
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip().strip('"')
    return out


def parse_xml(text: str) -> dict:
    """Attributes of the elements VirtualBox keeps its properties in."""
    import xml.etree.ElementTree as ET
    out = {}
    try:
        root = ET.fromstring(text or "")
    except ET.ParseError:
        return out
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        for name, value in element.attrib.items():
            out[f"{tag}.{name}"] = value
    return out


def read_values(app: AppConfig) -> dict:
    """Current values, by key, or {} when the file is not there."""
    path = app.path()
    if not path or not path.is_file():
        return {}
    text = fs.read_text(path)
    if app.fmt == "json":
        import json
        try:
            data = json.loads(text or "{}")
        except ValueError:
            return {}
        return {key: data.get(key) for key in data}
    if app.fmt == "ini":
        return parse_ini(text)
    if app.fmt == "keyvalue":
        return parse_keyvalue(text)
    if app.fmt == "xml":
        return parse_xml(text)
    return {}


def value_of(app: AppConfig, key: AppKey, values: dict = None):
    values = read_values(app) if values is None else values
    if key.key in values:
        return values[key.key]
    # A JSON key can be nested, an INI key carries its section.
    tail = key.key.rsplit(".", 1)[-1]
    return values.get(tail)


# --- writing -----------------------------------------------------------------
def set_ini_key(path: Path, dotted: str, value: str) -> str:
    """Return the file's new text with one section.key set.

    Written as text rather than through configparser: .wslconfig is read by
    Windows, comments in it are the user's notes, and configparser would
    drop them and reorder everything.
    """
    section, _, name = dotted.rpartition(".")
    lines = (fs.read_text(path) or "").splitlines()
    out, in_section, done = [], not section, False
    for raw in lines:
        stripped = raw.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_section and not done and section:
                out.append(f"{name} = {value}")
                done = True
            in_section = stripped[1:-1].strip() == section
            out.append(raw)
            continue
        if in_section and not done and "=" in stripped and \
                stripped.split("=", 1)[0].strip() == name:
            out.append(f"{name} = {value}")
            done = True
            continue
        out.append(raw)
    if not done:
        if section and not any(l.strip() == f"[{section}]" for l in out):
            if out and out[-1].strip():
                out.append("")
            out.append(f"[{section}]")
        out.append(f"{name} = {value}")
    return "\n".join(out) + "\n"


def write_action(app: AppConfig, key: AppKey, value: str):
    """An Action that writes one setting, with the file backed up first."""
    from .actions import Action, USER
    path = app.path()
    if not app.writable or path is None:
        return Action(
            id=f"appset-{app.id}-{key.key}",
            label=f"{app.app}: {key.title} is read-only here",
            command=[], scope="none",
            shell_text=key.gotcha.splitlines()[-1] if key.gotcha else "",
            explanation=(f"kontainy does not write {app.app}'s file. "
                         f"{app.note}"))

    def execute():
        from .writers import WriteRefused, _backup, _atomic_write, coerce
        if app.fmt == "json":
            import json
            data = {}
            if path.is_file():
                try:
                    data = json.loads(fs.read_text(path) or "{}")
                except ValueError as exc:
                    raise WriteRefused(f"{path} is not valid JSON: {exc}")
            data[key.key] = coerce(value, key.vtype)
            text = json.dumps(data, indent=2) + "\n"
        elif app.fmt == "ini":
            text = set_ini_key(path, key.key, value)
        else:
            raise WriteRefused(f"kontainy cannot write {app.fmt} files")
        path.parent.mkdir(parents=True, exist_ok=True)
        backup = _backup(path) if path.is_file() else None
        _atomic_write(path, text)
        return (f"{key.title} = {value} written to {path}"
                + (f"\nThe previous file is kept as {backup.name}"
                   if backup else "")
                + (f"\n\n{app.note}" if app.note else ""))

    return Action(
        id=f"appset-{app.id}-{key.key}",
        label=f"Set {key.title} to {value}",
        command=[], scope=USER,
        shell_text=f"# {path}\n{key.key} = {value}",
        explanation=(f"{key.what}\n\n"
                     + (f"\u26a0 {key.gotcha}\n\n" if key.gotcha else "")
                     + (f"\u26a0 {app.app} rewrites this file when it "
                        f"closes, so make this change with it shut down.\n\n"
                        if key.close_first else "")
                     + f"The file is backed up before it is written."),
        destructive=key.danger, func=execute)
