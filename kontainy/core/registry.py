"""
kontainy — engine and tool registry

Every container and virtualisation technology kontainy knows about, with the
three things a page needs to be useful rather than informative:

    status      is it installed, which version, is its service running
    actions     install, remove, start, enable — per operating system
    surface     which catalogue settings, diagnostic rules and Learn topics
                belong to it

Install commands are listed per distribution because there is no portable
answer. `pacman -S docker` and `apt install docker.io` install different
things under the same name, and telling someone the wrong one wastes an
afternoon. Each entry names the package as that distribution ships it.
"""

from __future__ import annotations

import os
import platform
import shutil
from dataclasses import dataclass, field

from ..utils import fs
from .elevate import run

# --- Operating system detection --------------------------------------------
LINUX_FAMILIES = {
    "arch": ("Arch / CachyOS / Manjaro", "pacman -S --needed"),
    "debian": ("Debian / Ubuntu / Mint", "apt install -y"),
    "fedora": ("Fedora / RHEL / Rocky", "dnf install -y"),
    "suse": ("openSUSE / SLES", "zypper install -y"),
    "alpine": ("Alpine", "apk add"),
    "gentoo": ("Gentoo", "emerge"),
    "nixos": ("NixOS", "nix-env -iA nixpkgs."),
    "void": ("Void", "xbps-install -S"),
}


def detect_os() -> tuple:
    """Return (kind, family, label). kind is linux | windows | macos | bsd."""
    system = platform.system().lower()
    if system == "windows":
        return "windows", "", "Windows"
    if system == "darwin":
        return "macos", "", "macOS"
    if "bsd" in system:
        return "bsd", "", platform.system()

    family = family_from_os_release(fs.read_text("/etc/os-release"))
    if family:
        return "linux", family, LINUX_FAMILIES[family][0]
    return "linux", "", "Linux"


def family_from_os_release(text: str) -> str:
    """The package family of a Linux system, from its /etc/os-release.

    Used for this machine and for a WSL distribution on Windows, where the
    install command must be the one for the Linux inside WSL.
    """
    release = (text or "").lower()
    for family in ("arch", "debian", "fedora", "suse", "alpine", "gentoo",
                   "nixos", "void"):
        if family in release:
            return family
    # ID_LIKE covers derivatives that do not name the parent in ID.
    for family, keys in (("arch", ("cachyos", "manjaro", "endeavouros")),
                         ("debian", ("ubuntu", "mint", "pop", "kali")),
                         ("fedora", ("rhel", "centos", "rocky", "alma")),
                         ("suse", ("opensuse", "sles"))):
        if any(key in release for key in keys):
            return family
    return ""


OS_KIND, OS_FAMILY, OS_LABEL = detect_os()


# --- Tool definition --------------------------------------------------------
@dataclass
class Tool:
    """One engine or supporting tool."""

    id: str
    name: str
    group: str                       # sidebar section
    summary: str
    binaries: list = field(default_factory=list)
    version_args: list = field(default_factory=lambda: ["--version"])
    services: list = field(default_factory=list)      # (unit, user_scope)
    config_files: list = field(default_factory=list)
    packages: dict = field(default_factory=dict)      # family -> package name
    windows: str = ""                # winget / scoop line
    macos: str = ""                  # brew line
    bsd: str = ""                    # pkg line
    catalog_engine: str = ""         # "docker" | "podman" | ""
    catalog_tags: list = field(default_factory=list)
    rule_prefixes: list = field(default_factory=list)
    learn_category: str = ""
    docs: str = ""
    note: str = ""
    # Where the tool can run at all. KVM, QEMU's accelerated mode, libvirt,
    # LXC and the systemd tools do not exist on Windows; listing them there
    # offers something that can never work.
    platforms: tuple = ("linux", "macos", "windows", "bsd")

    # --- status ------------------------------------------------------------
    def binary_path(self) -> str:
        for name in self.binaries:
            path = shutil.which(name)
            if path:
                return path
        return ""

    def installed(self) -> bool:
        return bool(self.binary_path())

    def version(self) -> str:
        path = self.binary_path()
        if not path:
            return ""
        result = run([path] + self.version_args, timeout=8.0, record=False)
        text = (result.stdout or result.stderr).strip()
        return text.splitlines()[0] if text else ""

    # --- install -----------------------------------------------------------
    def install_command(self) -> str:
        """The install line for the operating system we are actually on."""
        if OS_KIND == "windows":
            return self.windows
        if OS_KIND == "macos":
            return self.macos
        if OS_KIND == "bsd":
            return self.bsd
        package = self.packages.get(OS_FAMILY)
        if not package:
            return ""
        return f"sudo {LINUX_FAMILIES[OS_FAMILY][1]} {package}"

    def all_install_commands(self) -> list:
        """(label, command) for every platform — the educational view."""
        out = []
        for family, (label, installer) in LINUX_FAMILIES.items():
            package = self.packages.get(family)
            if package:
                out.append((label, f"sudo {installer} {package}"))
        if self.windows:
            out.append(("Windows", self.windows))
        if self.macos:
            out.append(("macOS", self.macos))
        if self.bsd:
            out.append(("FreeBSD", self.bsd))
        return out

    def linux_install_command(self, family: str) -> str:
        """The install line for a given Linux family — a WSL distro's, say."""
        package = self.packages.get(family)
        if not family or not package:
            return ""
        return f"sudo {LINUX_FAMILIES[family][1]} {package}"

    def remove_command(self, family: str = "") -> str:
        family = family or (OS_FAMILY if OS_KIND == "linux" else "")
        if not family:
            return ""
        package = self.packages.get(family)
        if not package:
            return ""
        remover = {
            "arch": "pacman -Rns", "debian": "apt remove -y",
            "fedora": "dnf remove -y", "suse": "zypper remove -y",
            "alpine": "apk del", "gentoo": "emerge --unmerge",
            "nixos": "nix-env -e", "void": "xbps-remove -R",
        }[family]
        return f"sudo {remover} {package}"


T = Tool

# ---------------------------------------------------------------------------
#  Containers
# ---------------------------------------------------------------------------
CONTAINER_TOOLS = [
    T("docker", "Docker Engine", "Containers",
      "The daemon-based container engine. Runs as root by default and owns "
      "/var/lib/docker.",
      binaries=["docker"], services=[("docker.service", False),
                                     ("docker.socket", False)],
      config_files=["/etc/docker/daemon.json", "~/.docker/config.json"],
      packages={"arch": "docker", "debian": "docker.io", "fedora": "docker-ce",
                "suse": "docker", "alpine": "docker", "gentoo": "app-containers/docker",
                "nixos": "docker", "void": "docker"},
      windows="winget install Docker.DockerDesktop",
      macos="brew install --cask docker",
      bsd="pkg install docker",
      catalog_engine="docker", rule_prefixes=["CTX", "DSK", "SVC", "NET"],
      learn_category="docker",
      docs="https://docs.docker.com/engine/",
      note="On Debian and Ubuntu, docker.io is the distribution's package and "
           "docker-ce is Docker's own. They are not interchangeable; mixing "
           "them leaves two daemons fighting over the same socket."),

    T("podman", "Podman", "Containers",
      "Daemonless container engine. Rootless is the natural mode, and its "
      "entire configuration lives under ~/.config.",
      binaries=["podman"], services=[("podman.socket", True),
                                     ("podman.socket", False),
                                     ("podman-auto-update.timer", True)],
      config_files=["~/.config/containers/containers.conf",
                    "~/.config/containers/storage.conf",
                    "~/.config/containers/registries.conf"],
      packages={"arch": "podman", "debian": "podman", "fedora": "podman",
                "suse": "podman", "alpine": "podman",
                "gentoo": "app-containers/podman", "nixos": "podman",
                "void": "podman"},
      windows="winget install RedHat.Podman",
      macos="brew install podman",
      bsd="pkg install podman",
      catalog_engine="podman", rule_prefixes=["POD", "CTX", "RES", "NET"],
      learn_category="podman",
      docs="https://docs.podman.io/",
      note="On Arch you also want podman-compose and netavark; rootless needs "
           "an entry in /etc/subuid and /etc/subgid, which the package does "
           "not always create."),

    T("containerd", "containerd", "Containers",
      "The runtime Docker itself sits on. Manageable directly with nerdctl.",
      binaries=["containerd", "nerdctl"],
      services=[("containerd.service", False)],
      config_files=["/etc/containerd/config.toml"],
      packages={"arch": "containerd", "debian": "containerd",
                "fedora": "containerd", "suse": "containerd",
                "alpine": "containerd", "void": "containerd"},
      macos="brew install containerd",
      docs="https://containerd.io/"),

    T("buildah", "Buildah", "Containers",
      "Builds OCI images without a daemon and without a Dockerfile if you "
      "prefer. No GUI exists for it anywhere.",
      binaries=["buildah"],
      packages={"arch": "buildah", "debian": "buildah", "fedora": "buildah",
                "suse": "buildah", "alpine": "buildah", "void": "buildah"},
      macos="brew install buildah",
      docs="https://buildah.io/"),

    T("skopeo", "Skopeo", "Containers",
      "Copies and inspects images between registries without pulling them "
      "into a local store.",
      binaries=["skopeo"],
      packages={"arch": "skopeo", "debian": "skopeo", "fedora": "skopeo",
                "suse": "skopeo", "alpine": "skopeo", "void": "skopeo"},
      macos="brew install skopeo",
      docs="https://github.com/containers/skopeo"),
]

# ---------------------------------------------------------------------------
#  Orchestration
# ---------------------------------------------------------------------------
KUBERNETES_TOOLS = [
    T("kubectl", "kubectl", "Kubernetes",
      "The Kubernetes client. Everything else here assumes it is present.",
      binaries=["kubectl"], version_args=["version", "--client"],
      config_files=["~/.kube/config"],
      packages={"arch": "kubectl", "debian": "kubectl", "fedora": "kubernetes-client",
                "suse": "kubernetes-client", "alpine": "kubectl", "void": "kubectl"},
      windows="winget install Kubernetes.kubectl",
      macos="brew install kubectl",
      learn_category="kubernetes",
      docs="https://kubernetes.io/docs/reference/kubectl/"),

    T("k3s", "k3s", "Kubernetes",
      "A single-binary Kubernetes distribution. The lightest way to have a "
      "real cluster on one machine.",
      binaries=["k3s"], services=[("k3s.service", False)],
      config_files=["/etc/rancher/k3s/k3s.yaml"],
      packages={"arch": "k3s-bin"},
      learn_category="kubernetes",
      docs="https://k3s.io/",
      note="Not in most distribution repositories. The upstream installer is "
           "`curl -sfL https://get.k3s.io | sh -`, which pipes a script from "
           "the internet into a shell \u2014 read it first."),

    T("kind", "kind", "Kubernetes",
      "Runs Kubernetes nodes as containers. Useful for testing against a "
      "cluster you can throw away.",
      binaries=["kind"],
      packages={"arch": "kind", "fedora": "kind"},
      windows="winget install Kubernetes.kind",
      macos="brew install kind",
      learn_category="kubernetes",
      docs="https://kind.sigs.k8s.io/"),

    T("minikube", "minikube", "Kubernetes",
      "A local cluster in a VM or container, with an addon system.",
      binaries=["minikube"],
      packages={"arch": "minikube", "fedora": "minikube"},
      windows="winget install Kubernetes.minikube",
      macos="brew install minikube",
      learn_category="kubernetes",
      docs="https://minikube.sigs.k8s.io/"),

    T("helm", "Helm", "Kubernetes",
      "Packages Kubernetes manifests into installable charts.",
      binaries=["helm"],
      packages={"arch": "helm", "debian": "helm", "fedora": "helm",
                "suse": "helm", "alpine": "helm"},
      windows="winget install Helm.Helm",
      macos="brew install helm",
      learn_category="kubernetes",
      docs="https://helm.sh/"),
]

# ---------------------------------------------------------------------------
#  Virtual machines
# ---------------------------------------------------------------------------
VM_TOOLS = [
    T("libvirt", "libvirt", "Virtual machines",
      "The management layer over KVM and QEMU. virsh, virt-manager and "
      "everything else talk to it.",
      binaries=["virsh"], services=[("libvirtd.service", False),
                                    ("virtqemud.service", False)],
      config_files=["/etc/libvirt/libvirtd.conf", "/etc/libvirt/qemu.conf"],
      packages={"arch": "libvirt", "debian": "libvirt-daemon-system",
                "fedora": "libvirt", "suse": "libvirt", "alpine": "libvirt",
                "gentoo": "app-emulation/libvirt", "void": "libvirt"},
      macos="brew install libvirt",
      bsd="pkg install libvirt",
      learn_category="kvm",
      docs="https://libvirt.org/",
      note="Your user must be in the libvirt group, and on most systems the "
           "session URI (qemu:///session) and the system URI "
           "(qemu:///system) hold completely separate sets of machines \u2014 "
           "a very common source of 'my VM disappeared'."),

    T("qemu", "QEMU / KVM", "Virtual machines",
      "The emulator that actually runs the guest. With /dev/kvm present it "
      "uses hardware virtualisation instead of emulating.",
      binaries=["qemu-system-x86_64", "qemu-kvm"],
      packages={"arch": "qemu-full", "debian": "qemu-system-x86",
                "fedora": "qemu-kvm", "suse": "qemu", "alpine": "qemu",
                "gentoo": "app-emulation/qemu", "void": "qemu"},
      macos="brew install qemu",
      bsd="pkg install qemu",
      learn_category="kvm",
      docs="https://www.qemu.org/",
      note="Check /dev/kvm exists and is readable. Without it everything "
           "still runs, just emulated and roughly twenty times slower."),

    T("virt-manager", "Virtual Machine Manager", "Virtual machines",
      "The desktop application for libvirt. The one most people mean when "
      "they say they manage VMs on Linux.",
      binaries=["virt-manager"],
      packages={"arch": "virt-manager", "debian": "virt-manager",
                "fedora": "virt-manager", "suse": "virt-manager",
                "alpine": "virt-manager", "void": "virt-manager"},
      learn_category="kvm",
      docs="https://virt-manager.org/"),

    T("hyperv", "Hyper-V", "Virtual machines",
      "Windows' own hypervisor, built into Pro, Enterprise and Education. "
      "Managed entirely from PowerShell.",
      binaries=["vmconnect"],
      windows=("powershell -NoProfile -Command Enable-WindowsOptionalFeature "
               "-Online -FeatureName Microsoft-Hyper-V -All"),
      docs="https://learn.microsoft.com/virtualization/hyper-v-on-windows/",
      note="Not available on Windows Home. Enabling it needs a restart, and "
           "while it is on, VirtualBox and VMware run on top of it through "
           "the Windows Hypervisor Platform — slower, and some older "
           "versions refuse to start at all."),

    T("virtualbox", "VirtualBox", "Virtual machines",
      "Oracle's type-2 hypervisor. Manageable from the command line with "
      "VBoxManage.",
      binaries=["VBoxManage"],
      packages={"arch": "virtualbox", "debian": "virtualbox",
                "fedora": "VirtualBox", "suse": "virtualbox"},
      windows="winget install Oracle.VirtualBox",
      macos="brew install --cask virtualbox",
      docs="https://www.virtualbox.org/",
      note="VirtualBox and KVM cannot both hold the virtualisation extensions "
           "at once on most kernels. Running one usually means unloading the "
           "other's modules."),

    T("multipass", "Multipass", "Virtual machines",
      "Canonical's tool for quick Ubuntu VMs.",
      binaries=["multipass"],
      packages={"arch": "canonical-multipass"},
      windows="winget install Canonical.Multipass",
      macos="brew install --cask multipass",
      docs="https://multipass.run/"),

    T("vagrant", "Vagrant", "Virtual machines",
      "Describes development VMs in a file and brings them up reproducibly.",
      binaries=["vagrant"],
      packages={"arch": "vagrant", "debian": "vagrant", "fedora": "vagrant",
                "suse": "vagrant"},
      windows="winget install Hashicorp.Vagrant",
      macos="brew install --cask vagrant",
      docs="https://www.vagrantup.com/"),
]

# ---------------------------------------------------------------------------
#  System containers
# ---------------------------------------------------------------------------
SYSTEM_CONTAINER_TOOLS = [
    T("incus", "Incus", "System containers",
      "The community continuation of LXD. Runs full operating systems in "
      "containers, and VMs too.",
      binaries=["incus"], services=[("incus.service", False)],
      packages={"arch": "incus", "debian": "incus", "fedora": "incus",
                "suse": "incus", "alpine": "incus", "void": "incus"},
      learn_category="lxc",
      docs="https://linuxcontainers.org/incus/",
      note="A system container is not an application container. It boots an "
           "init system and behaves like a machine, which is why a Docker "
           "mental model does not transfer cleanly."),

    T("lxc", "LXC", "System containers",
      "The low-level system container runtime underneath LXD and Incus.",
      binaries=["lxc-create", "lxc-start"],
      config_files=["/etc/lxc/default.conf", "~/.config/lxc/default.conf"],
      packages={"arch": "lxc", "debian": "lxc", "fedora": "lxc",
                "suse": "lxc", "alpine": "lxc", "void": "lxc"},
      learn_category="lxc",
      docs="https://linuxcontainers.org/lxc/"),

    T("lxd", "LXD", "System containers",
      "Canonical's system container manager. Incus forked from it.",
      binaries=["lxd"], services=[("lxd.service", False)],
      packages={"arch": "lxd", "debian": "lxd"},
      learn_category="lxc",
      docs="https://canonical.com/lxd"),

    T("systemd-nspawn", "systemd-nspawn", "System containers",
      "Ships with systemd itself. No package to install, and no interface "
      "anywhere \u2014 which is precisely why it is worth surfacing.",
      binaries=["systemd-nspawn"],
      config_files=["/etc/systemd/nspawn/"],
      packages={"arch": "systemd-container", "debian": "systemd-container",
                "fedora": "systemd-container"},
      learn_category="lxc",
      docs="https://www.freedesktop.org/software/systemd/man/systemd-nspawn.html"),

    T("distrobox", "Distrobox", "System containers",
      "Runs a full distribution in a container tightly integrated with your "
      "home directory.",
      binaries=["distrobox"],
      packages={"arch": "distrobox", "debian": "distrobox",
                "fedora": "distrobox", "suse": "distrobox",
                "alpine": "distrobox", "void": "distrobox"},
      docs="https://distrobox.it/"),
]

# ---------------------------------------------------------------------------
#  Desktop applications
# ---------------------------------------------------------------------------
DESKTOP_TOOLS = [
    T("docker-desktop", "Docker Desktop", "Desktop applications",
      "Docker's own desktop application. Runs the engine inside a virtual "
      "machine even on Linux.",
      binaries=["docker-desktop"],
      packages={"arch": "docker-desktop"},
      windows="winget install Docker.DockerDesktop",
      macos="brew install --cask docker",
      docs="https://docs.docker.com/desktop/",
      note="Installing it silently changes your docker context to "
           "desktop-linux, which is the single most common reason containers "
           "appear to vanish. kontainy shows both engines regardless."),

    T("podman-desktop", "Podman Desktop", "Desktop applications",
      "Podman's desktop application, with providers for Docker, Lima and "
      "kind as well.",
      binaries=["podman-desktop"],
      packages={"arch": "podman-desktop"},
      windows="winget install RedHat.Podman-Desktop",
      macos="brew install --cask podman-desktop",
      docs="https://podman-desktop.io/"),

    T("lens", "Lens", "Desktop applications",
      "A desktop IDE for Kubernetes clusters.",
      binaries=["lens"],
      packages={"arch": "lens-bin"},
      windows="winget install Mirantis.Lens",
      macos="brew install --cask lens",
      docs="https://k8slens.dev/"),

    T("k9s", "k9s", "Desktop applications",
      "A terminal interface for Kubernetes. Faster than kubectl for reading "
      "a cluster.",
      binaries=["k9s"],
      packages={"arch": "k9s", "fedora": "k9s", "alpine": "k9s"},
      windows="winget install Derailed.k9s",
      macos="brew install k9s",
      docs="https://k9scli.io/"),

    T("cockpit", "Cockpit", "Desktop applications",
      "A web console for the machine, with modules for podman and libvirt.",
      binaries=["cockpit-bridge"],
      services=[("cockpit.socket", False)],
      packages={"arch": "cockpit", "debian": "cockpit", "fedora": "cockpit",
                "suse": "cockpit"},
      docs="https://cockpit-project.org/"),
]

ALL_TOOLS = (CONTAINER_TOOLS + KUBERNETES_TOOLS + VM_TOOLS
             + SYSTEM_CONTAINER_TOOLS + DESKTOP_TOOLS)

# Tools that cannot exist everywhere. KVM acceleration, libvirt, LXC and the
# systemd-based tools are Linux; a few also run on macOS. Anything not listed
# here runs on every platform kontainy supports.
_ONLY_ON = {
    "libvirt": ("linux", "macos"), "qemu": ("linux", "macos"),
    "virt-manager": ("linux",), "incus": ("linux",), "lxc": ("linux",),
    "lxd": ("linux",), "systemd-nspawn": ("linux",), "distrobox": ("linux",),
    "cockpit": ("linux",), "k3s": ("linux",),
    "containerd": ("linux", "macos"), "buildah": ("linux", "macos"),
    "skopeo": ("linux", "macos"),
    "hyperv": ("windows",),
}
for _tool in ALL_TOOLS:
    if _tool.id in _ONLY_ON:
        _tool.platforms = _ONLY_ON[_tool.id]

GROUPS = ["Containers", "Kubernetes", "Virtual machines",
          "System containers", "Desktop applications"]


def by_id(tool_id: str):
    for tool in ALL_TOOLS:
        if tool.id == tool_id:
            return tool
    return None


def available_here(tool) -> bool:
    return OS_KIND in tool.platforms


def by_group(group: str) -> list:
    """Tools in a group that can exist on this operating system."""
    return [t for t in ALL_TOOLS if t.group == group and available_here(t)]


def installed_tools() -> list:
    return [t for t in ALL_TOOLS if t.installed()]


def stats() -> dict:
    installed = installed_tools()
    return {
        "total": len(ALL_TOOLS),
        "installed": len(installed),
        "groups": len(GROUPS),
        "os": OS_LABEL,
    }
