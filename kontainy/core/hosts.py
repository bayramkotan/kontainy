"""
kontainy — where a command runs

On Linux and macOS every tool runs here. On Windows the Linux tools — KVM
and libvirt, Incus, LXD, LXC — run inside a WSL 2 distribution, reached as

    wsl -d Ubuntu-24.04 -- virsh list --all

WSL is the vehicle, not the thing being managed. It has no page of its own;
the pages for the technologies it carries say "via WSL · Ubuntu-24.04" and
show the wrapped command, so what kontainy runs is exactly what the user
could type.

Which distribution carries the Linux tools is a kontainy setting
(`wsl_distro`), changed from a technology's Backend tab or with
`ky wsl use NAME`. It never touches `wsl --set-default`: that is the
user's own default, and Docker Desktop's distribution must not become it.

KVM inside WSL needs nested virtualization — Windows 11 on a CPU that
supports it, with `nestedVirtualization=true` under [wsl2] in .wslconfig.
Without it there is no /dev/kvm in the distribution and QEMU falls back to
slow software emulation; the libvirt page says so.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
from dataclasses import dataclass

from ..utils.config import config

# Distributions that belong to another product and must never carry
# kontainy's Linux tools.
RESERVED_PREFIXES = ("docker-desktop", "podman-machine", "rancher-desktop")


#: How long to wait for a remote host before giving up. Short, because a
#: page that hangs on an unreachable server is worse than one that says so.
SSH_TIMEOUT = 10


@dataclass(frozen=True)
class Host:
    kind: str = "local"          # "local" | "wsl" | "ssh"
    distro: str = ""             # WSL distribution, or user@host for ssh
    port: int = 0                # ssh only
    identity: str = ""           # ssh only: a key file
    jump: str = ""               # ssh only: ProxyJump

    @property
    def is_wsl(self) -> bool:
        return self.kind == "wsl"

    @property
    def is_remote(self) -> bool:
        return self.kind == "ssh"

    @property
    def label(self) -> str:
        if self.is_wsl:
            return f"via WSL \u00b7 {self.distro}"
        if self.is_remote:
            return f"via SSH \u00b7 {self.distro}"
        return ""

    def ssh_prefix(self, tty: bool = False) -> list:
        """The ssh command that runs something on this host.

        BatchMode means: never ask for a password. kontainy does not store
        passwords and must not stop a background probe on a prompt nobody
        can see — a key or an agent is the way in.
        """
        argv = ["ssh", "-o", "BatchMode=yes",
                "-o", f"ConnectTimeout={SSH_TIMEOUT}",
                # One connection reused for every command: a page makes
                # dozens of calls and a handshake each time is the
                # difference between usable and unbearable.
                "-o", "ControlMaster=auto",
                "-o", "ControlPath=~/.ssh/kontainy-%r@%h:%p",
                "-o", "ControlPersist=60"]
        if tty:
            argv.append("-t")
        if self.port:
            argv += ["-p", str(self.port)]
        if self.identity:
            argv += ["-i", self.identity]
        if self.jump:
            argv += ["-J", self.jump]
        return argv + [self.distro]

    def wrap(self, argv: list, root: bool = False) -> list:
        """argv as it must be run on this host."""
        if not argv or self.kind == "local":
            return list(argv)
        if self.is_remote:
            if argv[:1] == ["ssh"]:
                return list(argv)                   # already wrapped
            if root and argv[:1] != ["sudo"]:
                # -n: sudo must fail rather than wait for a password on a
                # terminal that is not there.
                argv = ["sudo", "-n"] + list(argv)
            return self.ssh_prefix() + ["--"] + list(argv)
        if argv[:1] == ["wsl"]:
            return list(argv)                       # already wrapped
        prefix = ["wsl", "-d", self.distro]
        if root:
            prefix += ["-u", "root"]
            if argv[:1] == ["sudo"]:
                argv = argv[1:]
        return prefix + ["--"] + list(argv)

    def which(self, binary: str) -> bool:
        if self.kind == "local":
            return bool(shutil.which(binary))
        ok, _ = _run(self.wrap(["sh", "-c", f"command -v {binary}"]),
                     timeout=SSH_TIMEOUT + 5 if self.is_remote else 15.0)
        return ok

    def exists(self, path: str) -> bool:
        if self.kind == "local":
            import os
            return os.path.exists(path)
        ok, _ = _run(self.wrap(["test", "-e", path]))
        return ok

    def reach(self) -> tuple:
        """(ok, message) — can kontainy run a command here at all?

        The message is the reason, in the words a person can act on: no
        key, a changed host key, a closed port, a name that does not
        resolve.
        """
        if self.kind != "ssh":
            return True, ""
        if not shutil.which("ssh"):
            return False, ("There is no ssh command on this machine. Install "
                           "OpenSSH \u2014 on Windows it is an optional "
                           "feature, on Linux the openssh-clients package.")
        ok, text = _run(self.wrap(["true"]), timeout=SSH_TIMEOUT + 5)
        if ok:
            return True, ""
        return False, ssh_reason(text)


LOCAL = Host()


def _run(argv: list, timeout: float = 15.0) -> tuple:
    try:
        proc = subprocess.run(argv, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    raw = proc.stdout or proc.stderr
    if raw.count(b"\x00") > len(raw) // 4:
        text = raw.decode("utf-16-le", errors="replace")
    else:
        text = raw.decode("utf-8", errors="replace")
    return proc.returncode == 0, text.replace("\x00", "").strip()


def on_windows() -> bool:
    return platform.system() == "Windows"


def wsl_available() -> bool:
    return on_windows() and bool(shutil.which("wsl"))


def wsl_distributions() -> list:
    """Every WSL distribution: [(name, state, version, is_default)]."""
    if not wsl_available():
        return []
    ok, text = _run(["wsl", "--list", "--verbose"])
    if not ok:
        return []
    return parse_wsl_list(text)


def parse_wsl_list(text: str) -> list:
    out = []
    for line in text.splitlines():
        if not line.strip() or line.strip().upper().startswith("NAME"):
            continue
        default = line.lstrip().startswith("*")
        parts = line.replace("*", " ").split()
        if len(parts) >= 3:
            out.append((parts[0], parts[1], parts[2], default))
    return out


def usable_for_tools(name: str) -> bool:
    return not name.lower().startswith(RESERVED_PREFIXES)


def linux_tools_distro() -> str:
    """The WSL distribution that carries kontainy's Linux tools, or ""."""
    chosen = (config().get("wsl_distro") or "").strip()
    distros = wsl_distributions()
    names = [d[0] for d in distros]
    if chosen and chosen in names:
        return chosen
    for name, _state, _version, default in distros:
        if default and usable_for_tools(name):
            return name
    for name, *_rest in distros:
        if usable_for_tools(name):
            return name
    return ""


def linux_host() -> Host | None:
    """Where Linux-only tools run: here on Linux, in WSL on Windows."""
    if not on_windows():
        return LOCAL
    distro = linux_tools_distro()
    return Host("wsl", distro) if distro else None


def distro_family(host: Host) -> str:
    """The package family of the Linux a host runs, for install commands."""
    from .registry import OS_FAMILY, family_from_os_release
    if not host.is_wsl:
        return OS_FAMILY
    ok, text = _run(host.wrap(["cat", "/etc/os-release"]))
    return family_from_os_release(text) if ok else ""


# --- remote hosts -------------------------------------------------------------
def ssh_reason(text: str) -> str:
    """Turn ssh's own output into something to act on."""
    lowered = (text or "").lower()
    if "permission denied" in lowered:
        return ("The server refused the key. Add your public key to its "
                "~/.ssh/authorized_keys, or load it into your agent "
                "(ssh-add).")
    if "host key verification failed" in lowered:
        return ("The host key does not match the one in known_hosts. Either "
                "the server was rebuilt, or this is not the server you "
                "think. Check before removing the old entry.")
    if "could not resolve" in lowered or "name or service not known" in lowered:
        return "That name does not resolve from here."
    if "connection refused" in lowered:
        return "Nothing is listening on the SSH port."
    if "connection timed out" in lowered or "timed out" in lowered:
        return "No answer before the timeout — a firewall, or the host is off."
    if "no route to host" in lowered:
        return "No route to that address from here."
    return (text or "ssh failed").strip().splitlines()[-1][:200]


def remote_hosts() -> list:
    """The servers the user has added, from the configuration.

    Stored as dictionaries rather than Host objects so the file stays
    readable and hand-editable:

        [{"name": "prod", "target": "deploy@server", "port": 22,
          "identity": "~/.ssh/id_ed25519", "jump": ""}]
    """
    out = []
    for entry in config().get("ssh_hosts") or []:
        if isinstance(entry, dict) and entry.get("target"):
            out.append(entry)
    return out


def host_from_entry(entry: dict) -> Host:
    return Host("ssh", str(entry.get("target", "")),
                port=int(entry.get("port") or 0),
                identity=str(entry.get("identity") or ""),
                jump=str(entry.get("jump") or ""))


def named_host(name: str) -> Host | None:
    """A host by the name the user gave it, or None."""
    if not name or name in ("local", "localhost"):
        return LOCAL
    for entry in remote_hosts():
        if entry.get("name") == name or entry.get("target") == name:
            return host_from_entry(entry)
    # Not added to kontainy, but ssh may still know it from ~/.ssh/config.
    if name in ssh_config_hosts():
        return Host("ssh", name)
    return None


def ssh_config_hosts() -> list:
    """Host aliases from ~/.ssh/config, so they can be offered directly."""
    import os
    path = os.path.expanduser("~/.ssh/config")
    out = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                key, _, value = line.partition(" ")
                if key.lower() != "host":
                    continue
                for alias in value.split():
                    # A pattern is not a host you can connect to.
                    if alias and not set(alias) & set("*?!"):
                        out.append(alias)
    except OSError:
        return []
    return out


def active_host() -> Host:
    """Where kontainy is currently working: this machine, or a server."""
    chosen = (config().get("active_host") or "").strip()
    if not chosen:
        return LOCAL
    return named_host(chosen) or LOCAL
