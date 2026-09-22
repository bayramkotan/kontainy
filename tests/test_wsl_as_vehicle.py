"""WSL is the vehicle on Windows, not a technology of its own.

Bayram, 2026-09-22: "Windows'ta WSL odak değil, araç." It has no page; the
Linux tools run through it and say so, Docker and Podman show the
distribution their engine lives in, and kontainy never changes the user's
own default distribution.
"""

import pytest

from kontainy.core import hosts, registry
from kontainy.core.providers import PROVIDERS, backend, base, platforms
from kontainy.core.providers.platforms import LibvirtProvider

UBUNTU = hosts.Host("wsl", "Ubuntu-24.04")
DISTROS = [("docker-desktop", "Running", "2", True),
           ("Ubuntu-24.04", "Running", "2", False),
           ("podman-machine-default", "Stopped", "2", False)]


@pytest.fixture
def windows_with_wsl(monkeypatch):
    monkeypatch.setattr(registry, "OS_KIND", "windows")
    monkeypatch.setattr(hosts, "on_windows", lambda: True)
    monkeypatch.setattr(hosts, "wsl_available", lambda: True)
    monkeypatch.setattr(hosts, "wsl_distributions", lambda: DISTROS)


# --- the host --------------------------------------------------------------------
def test_local_host_leaves_commands_alone():
    assert hosts.LOCAL.wrap(["virsh", "list"]) == ["virsh", "list"]


def test_wsl_host_prefixes_the_distribution():
    assert UBUNTU.wrap(["virsh", "list"]) == [
        "wsl", "-d", "Ubuntu-24.04", "--", "virsh", "list"]


def test_root_inside_wsl_uses_wsl_u_root_not_sudo():
    assert UBUNTU.wrap(["sudo", "apt", "install", "-y", "qemu-kvm"],
                       root=True) == [
        "wsl", "-d", "Ubuntu-24.04", "-u", "root", "--",
        "apt", "install", "-y", "qemu-kvm"]


def test_an_already_wrapped_command_is_not_wrapped_twice():
    once = UBUNTU.wrap(["virsh", "list"])
    assert UBUNTU.wrap(once) == once
    assert UBUNTU.wrap(["wsl", "--shutdown"]) == ["wsl", "--shutdown"]


def test_docker_desktop_never_carries_the_linux_tools(windows_with_wsl,
                                                       monkeypatch):
    """docker-desktop is the default here, but it belongs to Docker Desktop."""
    from kontainy.utils import config as cfg
    monkeypatch.setattr(cfg.config(), "get",
                        lambda key, default=None: "" if key == "wsl_distro"
                        else default)
    assert hosts.linux_tools_distro() == "Ubuntu-24.04"


def test_the_chosen_distribution_wins(windows_with_wsl, monkeypatch):
    from kontainy.utils import config as cfg
    monkeypatch.setattr(cfg.config(), "get",
                        lambda key, default=None: "podman-machine-default"
                        if key == "wsl_distro" else default)
    # a reserved name is still honoured if the user chose it explicitly
    assert hosts.linux_tools_distro() == "podman-machine-default"


# --- which technologies appear where ---------------------------------------------
def test_wsl_is_not_a_technology():
    assert "wsl" not in {p.id for p in PROVIDERS}


def test_on_windows_linux_tools_appear_through_wsl(windows_with_wsl):
    shown = {p.id for p in PROVIDERS if p.shown_here()}
    assert {"libvirt", "incus", "lxd"} <= shown
    assert {"docker", "podman", "kubernetes", "hyperv"} <= shown


def test_on_windows_without_wsl_linux_tools_are_hidden(monkeypatch):
    monkeypatch.setattr(registry, "OS_KIND", "windows")
    monkeypatch.setattr(hosts, "wsl_available", lambda: False)
    shown = {p.id for p in PROVIDERS if p.shown_here()}
    assert not {"libvirt", "incus", "lxd"} & shown


def test_on_linux_kvm_is_native_and_hyperv_absent(monkeypatch):
    monkeypatch.setattr(registry, "OS_KIND", "linux")
    shown = {p.id for p in PROVIDERS if p.shown_here()}
    assert "libvirt" in shown and "hyperv" not in shown
    assert LibvirtProvider().host() == hosts.LOCAL


# --- commands really go through WSL ------------------------------------------------
def test_libvirt_reads_through_wsl(windows_with_wsl, monkeypatch):
    seen = []
    monkeypatch.setattr(hosts, "linux_host", lambda: UBUNTU)
    monkeypatch.setattr(platforms, "cli_text",
                        lambda argv, timeout=15.0: seen.append(argv) or (True, ""))
    LibvirtProvider().objects(base.Target("system", "qemu:///system"))
    assert seen and seen[0][:4] == ["wsl", "-d", "Ubuntu-24.04", "--"]
    assert "virsh" in seen[0]


def test_libvirt_actions_are_prepared_for_wsl(windows_with_wsl, monkeypatch):
    monkeypatch.setattr(hosts, "linux_host", lambda: UBUNTU)
    provider = LibvirtProvider()
    act = provider.object_actions(base.Target("system", "qemu:///system"),
                                  {"name": "fedora", "state": "shut off"})[0]
    shown = provider.prepare(act).display()
    assert shown.startswith("wsl -d Ubuntu-24.04 -- virsh")


def test_missing_dev_kvm_in_wsl_is_explained(windows_with_wsl, monkeypatch):
    monkeypatch.setattr(hosts, "linux_host", lambda: UBUNTU)
    monkeypatch.setattr(hosts.Host, "which", lambda self, binary: True)
    monkeypatch.setattr(hosts.Host, "exists", lambda self, path: False)
    warning = LibvirtProvider().warning()
    assert "/dev/kvm" in warning and "nestedVirtualization=true" in warning


def test_libvirt_default_in_wsl_does_not_touch_windows_files(windows_with_wsl,
                                                               monkeypatch):
    monkeypatch.setattr(hosts, "linux_host", lambda: UBUNTU)
    act = LibvirtProvider().activate(base.Target("session", "qemu:///session"))
    assert "libvirt.conf" not in act.display()
    assert "wsl -d Ubuntu-24.04" in act.display()


# --- the Backend tab -----------------------------------------------------------------
def test_docker_backend_lists_only_docker_desktop(windows_with_wsl):
    rows = backend.backend_section("docker").listing(None).rows
    assert [r["name"] for r in rows] == ["docker-desktop"]
    assert rows[0]["role"] == "Docker Desktop's engine"


def test_podman_backend_lists_only_podman_machine(windows_with_wsl):
    rows = backend.backend_section("podman").listing(None).rows
    assert [r["name"] for r in rows] == ["podman-machine-default"]


def test_linux_tools_backend_hides_product_distributions(windows_with_wsl):
    rows = backend.backend_section("linux-tools").listing(None).rows
    assert [r["name"] for r in rows] == ["Ubuntu-24.04"]


def test_choosing_a_distribution_never_changes_the_wsl_default(windows_with_wsl):
    acts = backend._row_actions("linux-tools", {"name": "Debian"})
    use = [a for a in acts if a.id == "wsl-use-Debian"][0]
    assert "--set-default" not in use.display()
    assert "not changed" in use.explanation


def test_install_inside_wsl_uses_the_distributions_package_manager():
    from kontainy.gui.pages import tools
    tool = registry.by_id("qemu")
    acts = tools._wsl_tool_actions({"installed": False, "family": "debian"},
                                   tool, UBUNTU)
    shown = acts[0].display()
    assert shown.startswith("wsl -d Ubuntu-24.04 -u root -- apt install")
    assert "sudo" not in shown


def test_windows_tools_are_not_installed_inside_wsl(windows_with_wsl, monkeypatch):
    """VirtualBox, Multipass and Vagrant run on Windows itself. The first
    version of the WSL panel offered to apt-install them inside Ubuntu."""
    from kontainy.gui.pages import tools
    monkeypatch.setattr(hosts, "distro_family", lambda host: "debian")
    monkeypatch.setattr(hosts.Host, "which", lambda self, binary: False)
    rows = tools._probe("", ["libvirt", "qemu", "virtualbox", "multipass"],
                        UBUNTU)
    inside = {r["tool"].id for r in rows if r.get("host")}
    outside = {r["tool"].id for r in rows if not r.get("host")}
    assert inside == {"libvirt", "qemu"}
    assert outside == {"virtualbox", "multipass"}
    assert all(r["where"].startswith("WSL") for r in rows if r.get("host"))
