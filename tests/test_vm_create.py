"""`ky kvm create` and `ky hyperv create`.

The same shape as the container half, and the checks are the mistakes that
cost an afternoon: memory given in GiB where MiB was meant, a disk path
that does not exist, a network that is not there, and no ISO at all — a
machine created with an empty disk and nothing to boot.
"""

import pytest

from kontainy.core import vmcreate
from kontainy.core.providers import by_id
from kontainy.core.providers.base import Target

KVM = Target("system", "qemu:///system", True)
HYPERV = Target("localhost", "this computer", True)


def _kvm(values, existing=(), networks=()):
    return vmcreate.build(by_id("libvirt"), KVM, values, list(existing),
                          list(networks))


def _hyperv(values, existing=(), switches=()):
    return vmcreate.build(by_id("hyperv"), HYPERV, values, list(existing),
                          list(switches))


# --- libvirt ------------------------------------------------------------------
def test_a_new_disk_is_created_in_the_pool(tmp_path):
    iso = tmp_path / "debian.iso"
    iso.write_text("")
    plan = _kvm({"name": "lab", "memory": "4096", "cpus": "4", "disk": "40",
                 "iso": str(iso), "os": "debian12"})
    argv = " ".join(plan.argv)
    assert not plan.refused, plan.problems
    assert "--name lab" in argv and "--memory 4096" in argv
    assert "--vcpus 4" in argv
    assert "path=/var/lib/libvirt/images/lab.qcow2,size=40,format=qcow2" in argv
    assert f"--cdrom {iso}" in argv
    assert "--os-variant debian12" in argv
    assert "--noautoconsole" in argv, "a CLI must not wait on a console"


def test_an_existing_disk_is_used_as_it_is(tmp_path):
    disk = tmp_path / "web.qcow2"
    disk.write_text("")
    plan = _kvm({"name": "web", "memory": "2048", "disk": str(disk)})
    assert f"--disk path={disk}" in " ".join(plan.argv)
    assert "--import" in plan.argv, "no ISO: boot what is on the disk"


def test_a_disk_path_that_does_not_exist_is_refused():
    plan = _kvm({"name": "web", "memory": "2048", "disk": "/nope/web.qcow2"})
    assert plan.refused
    assert any("does not exist" in text for _s, text in plan.problems)


def test_the_connection_of_the_target_is_used():
    plan = _kvm({"name": "a", "memory": "2048", "disk": "20"})
    assert "--connect" in plan.argv
    assert plan.argv[plan.argv.index("--connect") + 1] == "qemu:///system"


# --- the mistakes -------------------------------------------------------------
def test_memory_in_gib_is_caught_before_it_is_run():
    """`memory=4` means 4 MiB, which no installer can use."""
    plan = _kvm({"name": "a", "memory": "4", "disk": "40"})
    assert plan.refused
    assert any("MiB, not GiB" in text for _s, text in plan.problems)


def test_a_thousand_times_too_much_is_flagged_too():
    plan = _kvm({"name": "a", "memory": "4096000", "disk": "40"})
    assert any("thousand times" in text for _s, text in plan.problems)


def test_a_name_already_in_use_is_refused():
    plan = _kvm({"name": "lab", "memory": "4096", "disk": "40"},
                existing=["lab"])
    assert plan.refused


def test_a_network_that_is_not_there_names_the_ones_that_are():
    plan = _kvm({"name": "a", "memory": "4096", "disk": "40",
                 "network": "nope"}, networks=["default", "labnet"])
    assert plan.refused
    assert any("default, labnet" in text for _s, text in plan.problems)


def test_no_iso_is_a_warning_with_the_consequence_spelled_out():
    plan = _kvm({"name": "a", "memory": "4096", "disk": "40"})
    assert not plan.refused
    assert any("nothing to boot" in text for _s, text in plan.problems)


def test_an_unknown_field_is_named():
    plan = _kvm({"name": "a", "memory": "4096", "disk": "40", "cpu": "4"})
    assert plan.refused
    assert any("cpu is not a field" in text for _s, text in plan.problems)


def test_a_tiny_disk_is_only_a_warning():
    plan = _kvm({"name": "a", "memory": "4096", "disk": "4"})
    assert not plan.refused
    assert any("installers accept" in text for _s, text in plan.problems)


# --- Hyper-V -------------------------------------------------------------------
def test_hyperv_creates_the_disk_where_hyperv_keeps_them():
    """A bare name would put the VHDX in whatever directory kontainy
    happened to be started from."""
    script = _hyperv({"name": "lab", "memory": "8192", "disk": "60"}).argv[-1]
    assert "(Get-VMHost).VirtualHardDiskPath" in script
    assert "-NewVHDSizeBytes 60GB" in script
    assert "-MemoryStartupBytes 8192MB" in script


def test_hyperv_boots_from_the_iso_on_generation_2(tmp_path):
    iso = tmp_path / "win11.iso"
    iso.write_text("")
    script = _hyperv({"name": "lab", "memory": "8192", "disk": "60",
                      "iso": str(iso)}).argv[-1]
    assert "Add-VMDvdDrive" in script
    assert "Set-VMFirmware" in script, "generation 2 boots UEFI: order it"


def test_generation_1_needs_no_firmware_order(tmp_path):
    iso = tmp_path / "old.iso"
    iso.write_text("")
    script = _hyperv({"name": "old", "memory": "2048", "disk": "40",
                      "generation": "1", "iso": str(iso)}).argv[-1]
    assert "-Generation 1" in script
    assert "Set-VMFirmware" not in script


def test_a_switch_that_is_not_there_is_refused():
    plan = _hyperv({"name": "a", "memory": "2048", "disk": "40",
                    "switch": "Nope"}, switches=["Default Switch"])
    assert plan.refused


def test_a_name_with_a_quote_cannot_break_the_script():
    script = _hyperv({"name": "it's", "memory": "2048", "disk": "40"}).argv[-1]
    assert "$name = 'it''s'" in script


# --- both ----------------------------------------------------------------------
@pytest.mark.parametrize("provider_id", ["libvirt", "hyperv"])
def test_the_fields_are_printable_and_name_the_required_ones(provider_id):
    text = vmcreate.describe_fields(by_id(provider_id))
    assert "memory" in text and "disk" in text and "*" in text
    assert "ky " in text


def test_a_technology_with_no_create_says_so():
    plan = vmcreate.build(by_id("vmware"), Target("localhost", "", True),
                          {"name": "a", "memory": "2048", "disk": "40"}, [], [])
    assert plan.refused
    assert any("cannot create" in text for _s, text in plan.problems)
