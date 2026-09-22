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


@dataclass(frozen=True)
class Host:
    kind: str = "local"          # "local" | "wsl"
    distro: str = ""

    @property
    def is_wsl(self) -> bool:
        return self.kind == "wsl"

    @property
    def label(self) -> str:
        return f"via WSL \u00b7 {self.distro}" if self.is_wsl else ""

    def wrap(self, argv: list, root: bool = False) -> list:
        """argv as it must be run on this host."""
        if not self.is_wsl or not argv:
            return list(argv)
        if argv[:1] == ["wsl"]:
            return list(argv)                       # already wrapped
        prefix = ["wsl", "-d", self.distro]
        if root:
            prefix += ["-u", "root"]
            if argv[:1] == ["sudo"]:
                argv = argv[1:]
        return prefix + ["--"] + list(argv)

    def which(self, binary: str) -> bool:
        if not self.is_wsl:
            return bool(shutil.which(binary))
        ok, _ = _run(self.wrap(["sh", "-c", f"command -v {binary}"]))
        return ok

    def exists(self, path: str) -> bool:
        if not self.is_wsl:
            import os
            return os.path.exists(path)
        ok, _ = _run(self.wrap(["test", "-e", path]))
        return ok


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
