"""Hyper-V parses PowerShell JSON. These tests feed it real output shapes,
so they run on any platform."""

import json

import pytest

from kontainy.core.providers import base, hyperv

TWO_VMS = json.dumps([
    {"Name": "win11-dev", "State": "Running", "CPUUsage": 3, "MemoryMB": 4096,
     "Uptime": "02:14:00", "Generation": 2, "Status": "Operating normally"},
    {"Name": "ubuntu 24.04", "State": "Off", "CPUUsage": 0, "MemoryMB": 0,
     "Uptime": "00:00:00", "Generation": 2, "Status": "Operating normally"}])

# PowerShell's ConvertTo-Json emits a bare object, not an array, for one VM.
ONE_VM = json.dumps({"Name": "only", "State": "Running", "CPUUsage": 1,
                     "MemoryMB": 2048, "Uptime": "00:05:00", "Generation": 2})


def fake_ps(output, ok=True):
    return lambda argv, timeout=20.0: (ok, output)


def test_two_vms_are_listed(monkeypatch):
    monkeypatch.setattr(hyperv, "cli_text", fake_ps(TWO_VMS))
    rows = hyperv.HyperVProvider().objects(None).rows
    assert [r["Name"] for r in rows] == ["win11-dev", "ubuntu 24.04"]


def test_a_single_vm_is_not_mistaken_for_a_list_of_properties(monkeypatch):
    monkeypatch.setattr(hyperv, "cli_text", fake_ps(ONE_VM))
    rows = hyperv.HyperVProvider().objects(None).rows
    assert len(rows) == 1 and rows[0]["Name"] == "only"


def test_no_vms_is_an_empty_list(monkeypatch):
    monkeypatch.setattr(hyperv, "cli_text", fake_ps(""))
    assert hyperv.HyperVProvider().objects(None).rows == []


def test_permission_error_explains_the_group(monkeypatch):
    monkeypatch.setattr(hyperv, "cli_text", fake_ps(
        "Get-VM : You do not have the required permission to complete this task.",
        ok=False))
    listing = hyperv.HyperVProvider().objects(None)
    assert "Hyper-V Administrators" in listing.error
    assert "Add-LocalGroupMember" in listing.error


def test_names_with_quotes_and_spaces_are_escaped():
    acts = hyperv.HyperVProvider().object_actions(
        None, {"Name": "Bob's VM", "State": "Off"})
    start = [a for a in acts if "Start-VM" in a.display()][0]
    assert "-Name 'Bob''s VM'" in start.display()


def test_remote_host_adds_computer_name():
    acts = hyperv.HyperVProvider().object_actions(
        base.Target("HV01", ""), {"Name": "x", "State": "Running"})
    assert all("-ComputerName 'HV01'" in a.display() for a in acts
               if "vmconnect" not in a.display())


def test_local_host_adds_no_computer_name():
    acts = hyperv.HyperVProvider().object_actions(
        base.Target("localhost", ""), {"Name": "x", "State": "Running"})
    assert not any("-ComputerName" in a.display() for a in acts)


def test_running_vm_offers_shutdown_save_and_turn_off():
    ids = [a.id for a in hyperv.HyperVProvider().object_actions(
        None, {"Name": "x", "State": "Running"})]
    assert {"hv-stop-x", "hv-save-x", "hv-off-x"} <= set(ids)
    assert "hv-start-x" not in ids


def test_turn_off_is_destructive_and_says_nothing_is_deleted():
    off = [a for a in hyperv.HyperVProvider().object_actions(
        None, {"Name": "x", "State": "Running"}) if a.id == "hv-off-x"][0]
    assert off.destructive and "not deleted" in off.explanation


def test_bulk_uses_one_cmdlet_for_all():
    rows = json.loads(TWO_VMS)
    acts = {a.id: a for a in hyperv.HyperVProvider().bulk_actions(None, rows)}
    assert "Start-VM -Name 'ubuntu 24.04'" in acts["hv-start-all"].display()
    assert "Stop-VM -Name 'win11-dev'" in acts["hv-stop-all"].display()


def test_default_switch_cannot_be_removed():
    section = hyperv.HyperVProvider().sections()[0]
    assert section.row_actions(None, {"Name": "Default Switch"}) == []
    assert section.row_actions(None, {"Name": "Lab"})


@pytest.mark.parametrize("kind,expected", [
    ("Internal", "-SwitchType Internal"), ("private", "-SwitchType Private"),
    ("External", "-NetAdapterName 'Ethernet'")])
def test_switch_creation_per_type(kind, expected):
    section = hyperv.HyperVProvider().sections()[0]
    act = section.create(None, {"name": "Lab", "type": kind,
                                "adapter": "Ethernet"})
    assert expected in act.display()


def test_hyperv_is_windows_only():
    from kontainy.core import registry
    assert hyperv.HyperVProvider.platforms == ("windows",)
    assert registry.by_id("hyperv").platforms == ("windows",)


def test_a_cmdlet_error_is_a_failure_even_though_powershell_exits_zero(monkeypatch):
    """PowerShell returns 0 for a non-terminating error, so the exit code
    said the probe had worked while the text said permission denied — and
    kontainy showed Hyper-V as installed on a machine without it."""
    import platform as _platform
    monkeypatch.setattr(_platform, "system", lambda: "Windows")
    monkeypatch.setattr(hyperv, "cli_text", fake_ps(
        f"{hyperv.MARK} You do not have the required permission.", ok=True))
    provider = hyperv.HyperVProvider()
    assert provider.available() is False
    assert provider.version() == ""
    assert "Hyper-V Administrators" in provider.unavailable_reason()


def test_the_module_alone_is_not_hyperv(monkeypatch):
    """WSL 2 and VMware turn on the Windows hypervisor platform and the
    Hyper-V PowerShell module comes with it. A machine with the module but
    no Hyper-V reported itself as installed, in green, with a version."""
    import platform as _platform
    monkeypatch.setattr(_platform, "system", lambda: "Windows")
    monkeypatch.setattr(hyperv, "cli_text", fake_ps(
        "Get-VMHost : The operation failed because the file was not found.",
        ok=False))
    provider = hyperv.HyperVProvider()
    assert provider.available() is False
    assert "not enabled" in provider.unavailable_reason()


def test_a_permission_refusal_is_told_apart_from_a_missing_feature(monkeypatch):
    import platform as _platform
    monkeypatch.setattr(_platform, "system", lambda: "Windows")
    monkeypatch.setattr(hyperv, "cli_text", fake_ps(
        "You do not have the required permission to complete this task.",
        ok=False))
    provider = hyperv.HyperVProvider()
    assert provider.available() is False
    assert "Hyper-V Administrators" in provider.unavailable_reason()


def test_hyperv_that_answers_is_available(monkeypatch):
    import platform as _platform
    monkeypatch.setattr(_platform, "system", lambda: "Windows")
    monkeypatch.setattr(hyperv, "cli_text", fake_ps("DESKTOP-ABC"))
    assert hyperv.HyperVProvider().available() is True
