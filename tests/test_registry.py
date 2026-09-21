"""The tool registry drives install commands, so wrong data wastes an hour."""

import pytest

from kontainy.core import registry as reg


def test_ids_are_unique():
    ids = [t.id for t in reg.ALL_TOOLS]
    assert len(ids) == len(set(ids))


def test_groups_are_known():
    for tool in reg.ALL_TOOLS:
        assert tool.group in reg.GROUPS


@pytest.mark.parametrize("tool", reg.ALL_TOOLS, ids=lambda t: t.id)
def test_tool_has_the_basics(tool):
    assert tool.name and tool.summary
    assert tool.binaries, f"{tool.id} has no binary to look for"
    assert tool.docs or tool.packages or tool.windows or tool.macos


@pytest.mark.parametrize("tool", reg.ALL_TOOLS, ids=lambda t: t.id)
def test_package_families_are_real(tool):
    for family in tool.packages:
        assert family in reg.LINUX_FAMILIES, \
            f"{tool.id} names an unknown distribution family: {family}"


@pytest.mark.parametrize("tool", reg.ALL_TOOLS, ids=lambda t: t.id)
def test_install_commands_are_sudo_prefixed(tool):
    """Linux package installs need root; the command must say so, because a
    user who copies it into a terminal has to see that."""
    for label, command in tool.all_install_commands():
        if label in ("Windows", "macOS", "FreeBSD"):
            continue
        assert command.startswith("sudo "), f"{tool.id}: {command}"


def test_every_group_has_tools():
    """Every group has tools somewhere. Not necessarily on this platform —
    System containers is empty on Windows by design, and checking by_group
    here would fail the Windows CI job for a correct result."""
    for group in reg.GROUPS:
        assert any(t.group == group for t in reg.ALL_TOOLS), f"{group} is empty"


def test_linux_only_tools_are_hidden_on_windows(monkeypatch):
    monkeypatch.setattr(reg, "OS_KIND", "windows")
    names = {t.id for g in reg.GROUPS for t in reg.by_group(g)}
    for linux_only in ("qemu", "libvirt", "virt-manager", "incus", "lxc",
                       "lxd", "systemd-nspawn", "k3s"):
        assert linux_only not in names, f"{linux_only} offered on Windows"
    assert "virtualbox" in names and "docker" in names


def test_kvm_and_lxc_are_present():
    """The complaint that started this page: KVM and LXC were nowhere."""
    ids = {t.id for t in reg.ALL_TOOLS}
    for expected in ("qemu", "libvirt", "virt-manager", "lxc", "incus",
                     "docker", "podman", "kubectl"):
        assert expected in ids


def test_detect_os_returns_a_known_shape():
    kind, family, label = reg.detect_os()
    assert kind in ("linux", "windows", "macos", "bsd")
    assert label
    if family:
        assert family in reg.LINUX_FAMILIES


def test_remove_command_matches_the_install_family(monkeypatch):
    monkeypatch.setattr(reg, "OS_KIND", "linux")
    monkeypatch.setattr(reg, "OS_FAMILY", "arch")
    tool = reg.by_id("podman")
    assert tool.remove_command() == "sudo pacman -Rns podman"


def test_no_package_gives_no_command(monkeypatch):
    monkeypatch.setattr(reg, "OS_KIND", "linux")
    monkeypatch.setattr(reg, "OS_FAMILY", "gentoo")
    assert reg.by_id("k3s").install_command() == ""
