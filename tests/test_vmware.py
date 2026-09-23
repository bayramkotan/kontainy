"""VMware Workstation and Fusion, through vmrun.

The reason VMware was invisible: Workstation does not put vmrun on PATH, so
looking it up the usual way found nothing on a machine that has VMware
installed. (Bayram, 2026-09-23: "Vmware var onu da göstermemişsin".)
"""

import pytest

from kontainy.core.providers import vmware
from kontainy.core.providers.vmware import VMwareProvider

VMRUN_LIST = ("Total running VMs: 2\n"
              "D:\\VMs\\win11\\win11.vmx\n"
              "D:\\VMs\\ubuntu-lab\\ubuntu-lab.vmx\n")

INVENTORY = '''.encoding = "UTF-8"
vmlist1.config = "D:\\VMs\\win11\\win11.vmx"
vmlist1.DisplayName = "win11"
vmlist2.config = "D:\\VMs\\fedora\\fedora.vmx"
vmlist3.config = "D:\\VMs\\ubuntu-lab\\ubuntu-lab.vmx"
'''


def test_vmrun_is_found_where_vmware_installs_it(monkeypatch):
    """Not on PATH, but in Workstation's own directory."""
    monkeypatch.setattr(vmware.shutil, "which", lambda name: None)
    monkeypatch.setattr(vmware.platform, "system", lambda: "Windows")
    installed = r"C:\Program Files (x86)\VMware\VMware Workstation\vmrun.exe"
    monkeypatch.setattr(vmware.fs, "exists", lambda p: str(p) == installed)
    assert vmware.vmrun_path() == installed
    assert VMwareProvider().available() is True


def test_no_vmware_at_all(monkeypatch):
    monkeypatch.setattr(vmware.shutil, "which", lambda name: None)
    monkeypatch.setattr(vmware.fs, "exists", lambda p: False)
    provider = VMwareProvider()
    assert provider.available() is False
    assert "install directories" in provider.unavailable_reason()


def test_running_machines_are_read_from_vmrun():
    assert vmware.parse_running(VMRUN_LIST) == [
        "D:\\VMs\\win11\\win11.vmx", "D:\\VMs\\ubuntu-lab\\ubuntu-lab.vmx"]


def test_the_inventory_gives_the_machines_that_are_not_running():
    paths = vmware.parse_inventory(INVENTORY)
    assert "D:\\VMs\\fedora\\fedora.vmx" in paths
    assert len(paths) == 3


def test_names_come_from_the_vmx_file():
    assert vmware.machine_name("D:\\VMs\\win11\\win11.vmx") == "win11"
    assert vmware.machine_name("/home/b/VMs/lab/lab.vmx") == "lab"


def test_the_listing_marks_running_and_stopped(monkeypatch):
    monkeypatch.setattr(vmware, "vmrun_path", lambda: "vmrun")
    monkeypatch.setattr(vmware, "cli_text",
                        lambda argv, timeout=15.0: (True, VMRUN_LIST))
    monkeypatch.setattr(VMwareProvider, "_inventory",
                        lambda self: vmware.parse_inventory(INVENTORY))
    rows = {r["name"]: r["state"] for r in VMwareProvider().objects(None).rows}
    assert rows == {"win11": "running", "ubuntu-lab": "running",
                    "fedora": "stopped"}


def test_actions_follow_the_state(monkeypatch):
    monkeypatch.setattr(vmware, "vmrun_path", lambda: "vmrun")
    provider = VMwareProvider()
    running = {a.id: a for a in provider.object_actions(
        None, {"name": "win11", "state": "running", "vmx": "w.vmx"})}
    stopped = {a.id: a for a in provider.object_actions(
        None, {"name": "win11", "state": "stopped", "vmx": "w.vmx"})}
    assert "vmware-stop-win11" in running and "vmware-start-win11" not in running
    assert "vmware-start-win11" in stopped
    assert "vmrun stop w.vmx soft" in running["vmware-stop-win11"].display()
    assert running["vmware-off-win11"].destructive


def test_bulk_runs_one_machine_per_command(monkeypatch):
    monkeypatch.setattr(vmware, "vmrun_path", lambda: "vmrun")
    rows = [{"name": "a", "state": "running", "vmx": "a.vmx"},
            {"name": "b", "state": "stopped", "vmx": "b.vmx"}]
    acts = {a.id: a for a in VMwareProvider().bulk_actions(None, rows)}
    assert "vmrun start b.vmx nogui" in acts["vmware-start-all"].display()
    assert "vmrun stop a.vmx soft" in acts["vmware-stop-all"].display()


def test_vmware_is_a_registered_tool():
    from kontainy.core import registry
    tool = registry.by_id("vmware")
    assert tool is not None and "vmrun" in tool.binaries
