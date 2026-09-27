"""Two unified pages from one table: All containers and All machines.

Bayram asked for both, and for Incus and LXD to sit beside Docker and
Podman. The page is the same code: only the list of technologies and a few
labels differ, so a fix to one is a fix to both.
"""

import pytest

from kontainy.core.providers import base, by_id
from kontainy.gui.pages import containers as page

TARGET = base.Target("default", "unix:///var/run/docker.sock", True)


def test_containers_gather_the_four_container_technologies():
    assert page.ContainersPage.ENGINES == ("docker", "podman", "incus", "lxd")


def test_machines_gather_the_three_hypervisors():
    assert page.MachinesPage.ENGINES == ("libvirt", "hyperv", "vmware")


def test_the_machines_page_is_the_same_page():
    assert issubclass(page.MachinesPage, page.ContainersPage)
    assert page.MachinesPage.TITLE == "All machines"
    assert page.ContainersPage.TITLE == "All containers"


def test_a_machine_publishes_no_ports_so_that_tab_is_gone():
    assert page.ContainersPage.SHOW_PORTS
    assert not page.MachinesPage.SHOW_PORTS


def test_creation_stays_with_the_container_engines():
    """New still means docker/podman; Incus and LXD are listed, not created."""
    assert page.ContainersPage.CAN_CREATE
    assert not page.MachinesPage.CAN_CREATE


# --- reading each technology's own column names --------------------------------
@pytest.mark.parametrize("row,expected", [
    ({"Names": "web", "Image": "nginx", "State": "running"}, "web"),
    ({"name": "win11", "state": "running"}, "win11"),
    ({"Name": "dev-box", "State": "Running"}, "dev-box"),
])
def test_a_name_is_found_whatever_the_column_is_called(row, expected):
    assert page._first(row, "Names", "name", "Name") == expected


def test_collecting_uses_the_providers_own_key(monkeypatch):
    """Hyper-V spells it Name, virsh spells it name, Docker spells it Names;
    a page that assumes Docker's showed an empty name for the others."""
    from kontainy.core.providers.hyperv import HyperVProvider
    monkeypatch.setattr(HyperVProvider, "available", lambda self: True)
    monkeypatch.setattr(HyperVProvider, "shown_here", lambda self: True)
    monkeypatch.setattr(HyperVProvider, "targets", lambda self: [
        base.Target("localhost", "this computer", True)])
    monkeypatch.setattr(HyperVProvider, "objects", lambda self, t: base.Listing(
        columns=[], rows=[{"Name": "dev-box", "State": "Running"}],
        command="Get-VM"))
    for other in ("libvirt", "vmware"):
        provider = by_id(other)
        monkeypatch.setattr(type(provider), "available", lambda self: False)
    rows = page._collect_all(("hyperv",))
    assert [r["name"] for r in rows] == ["dev-box"]
    assert rows[0]["state"] == "running"


# --- the command under the table ------------------------------------------------
@pytest.mark.parametrize("provider_id,row,expected", [
    ("docker", {"Names": "web"}, "docker --context default inspect web"),
    ("libvirt", {"name": "win11", "state": "running"}, "virsh"),
    ("incus", {"name": "alpine"}, "incus info alpine"),
    ("lxd", {"name": "u24"}, "lxc info u24"),
])
def test_every_technology_describes_an_object_in_its_own_words(
        provider_id, row, expected):
    """The page used to build "<id> inspect <name>" for everything, which
    produced `libvirt --connection system inspect win11` — not a command."""
    provider = by_id(provider_id)
    target = TARGET if provider_id == "docker" else base.Target(
        "system", "qemu:///system", True)
    assert expected in provider.describe_command(target, row)


def test_hyperv_describes_through_powershell():
    command = by_id("hyperv").describe_command(
        base.Target("localhost", "this computer", True), {"Name": "dev"})
    assert "Get-VM -Name 'dev'" in command and "Format-List" in command


def test_a_technology_with_nothing_to_say_returns_empty():
    assert by_id("vmware").describe_command(
        base.Target("localhost", "vmrun", True), {"name": "lab"}) == ""
