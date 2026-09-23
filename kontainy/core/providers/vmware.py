"""
kontainy — VMware Workstation and Fusion

Driven by `vmrun`, VMware's own command-line tool. The catch that hid VMware
from kontainy entirely: Workstation does not put `vmrun` on PATH, so looking
it up the usual way finds nothing on a machine that plainly has VMware
installed. The known install locations are checked as well.

A virtual machine here is a .vmx file, not a name in a registry, so that is
what the commands take. `vmrun list` reports only the running ones; the ones
that are merely known come from the inventory file the interface keeps.
"""

from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path

from ...utils import fs
from ..actions import Action, USER
from .base import Column, Field, Listing, Provider, Target, action, cli_text

#: Where Workstation and Fusion put vmrun when it is not on PATH.
KNOWN_PATHS = {
    "Windows": [
        r"C:\Program Files (x86)\VMware\VMware Workstation\vmrun.exe",
        r"C:\Program Files\VMware\VMware Workstation\vmrun.exe",
        r"C:\Program Files (x86)\VMware\VMware VIX\vmrun.exe",
        r"C:\Program Files\VMware\VMware Player\vmrun.exe",
    ],
    "Darwin": ["/Applications/VMware Fusion.app/Contents/Public/vmrun"],
    "Linux": ["/usr/bin/vmrun", "/usr/local/bin/vmrun"],
}

#: The interface's list of machines it knows about, running or not.
INVENTORY = {
    "Windows": [Path(os.environ.get("APPDATA", "")) / "VMware" / "inventory.vmls"],
    "Darwin": [Path.home() / "Library" / "Application Support" / "VMware Fusion"
               / "vmInventory"],
    "Linux": [Path.home() / ".vmware" / "inventory.vmls"],
}


def vmrun_path() -> str:
    """Where vmrun is, or "". PATH first, then where VMware installs it."""
    found = shutil.which("vmrun")
    if found:
        return found
    for candidate in KNOWN_PATHS.get(platform.system(), []):
        if fs.exists(candidate):
            return str(candidate)
    return ""


def parse_running(text: str) -> list:
    """The .vmx paths from `vmrun list`."""
    out = []
    for line in text.splitlines():
        line = line.strip()
        if line.lower().startswith("total running vms") or not line:
            continue
        out.append(line)
    return out


def parse_inventory(text: str) -> list:
    """The .vmx paths from an inventory file: lines like

        vmlist1.config = "D:\\VMs\\win11\\win11.vmx"
    """
    out = []
    for line in text.splitlines():
        if ".config" not in line or "=" not in line:
            continue
        value = line.split("=", 1)[1].strip().strip('"')
        if value.lower().endswith(".vmx"):
            out.append(value)
    return out


def machine_name(vmx: str) -> str:
    """The folder-and-file name a person recognises, not the whole path."""
    stem = Path(vmx.replace("\\", "/")).stem
    return stem or vmx


class VMwareProvider(Provider):
    id = "vmware"
    name = "VMware"
    icon = "\U0001f5a5"
    binary = "vmrun"
    target_noun = "Host"
    target_noun_plural = "Hosts"
    object_noun_plural = "Virtual machines"
    object_key = "name"
    tool_ids = ["vmware", "virtualbox", "multipass", "vagrant"]
    platforms = ("linux", "macos", "windows")
    runs_in_wsl = False
    summary = ("VMware Workstation, Player and Fusion, through their own "
               "vmrun tool. A machine here is a .vmx file; the running ones "
               "come from vmrun, the rest from the inventory the interface "
               "keeps.")

    # --- availability ------------------------------------------------------
    def available(self) -> bool:
        return bool(vmrun_path())

    def unavailable_reason(self) -> str:
        return ("`vmrun` was not found, on PATH or in VMware's own install "
                "directories. It comes with VMware Workstation, Player and "
                "Fusion.")

    def version(self) -> str:
        if not self.available():
            return ""
        ok, text = cli_text([vmrun_path()], timeout=10.0)
        for line in (text or "").splitlines():
            if "version" in line.lower():
                return line.strip()
        return "vmrun"

    # --- hosts -------------------------------------------------------------
    def targets(self) -> list:
        path = vmrun_path()
        return [Target("localhost", path or "this computer", True,
                       "VMware on this machine", removable=False)]

    def activate(self, target):
        return Action(id="vmware-local", label="Already the active host",
                      command=[], scope="none",
                      shell_text=f"{vmrun_path() or 'vmrun'} list",
                      explanation="vmrun drives the VMware installed on this "
                                  "machine; there is nothing to switch to.")

    def add_fields(self):
        return [Field("name", "Host", "not supported",
                      "Remote hosts need vCenter or ESXi, which vmrun "
                      "reaches only with -T and credentials; kontainy does "
                      "not manage those yet.")]

    def add(self, values):
        return Action(id="vmware-add", label="Remote hosts are not supported",
                      command=[], scope="none",
                      shell_text="# vmrun -T vc ... needs vCenter credentials",
                      explanation="Only the VMware on this machine, for now.")

    def remove(self, target):
        return Action(id="vmware-remove", label="Nothing to remove",
                      command=[], scope="none",
                      shell_text="# nothing to remove",
                      explanation="This host is not something kontainy added.")

    def test(self, target):
        return action("vmware-test", "Test VMware",
                      [vmrun_path() or "vmrun", "list"],
                      "Lists the running machines — the quickest proof that "
                      "vmrun can talk to VMware.")

    # --- machines ----------------------------------------------------------
    def _inventory(self) -> list:
        for path in INVENTORY.get(platform.system(), []):
            text = fs.read_text(path)
            if text:
                return parse_inventory(text)
        return []

    def objects(self, target) -> Listing:
        vmrun = vmrun_path()
        listing = Listing(
            columns=[Column("name", "Name"), Column("state", "State"),
                     Column("vmx", "Configuration file")],
            command=f"{vmrun} list" if vmrun else "vmrun list")
        if not vmrun:
            listing.error = self.unavailable_reason()
            return listing
        ok, text = cli_text([vmrun, "list"], timeout=20.0)
        if not ok:
            listing.error = text
            return listing
        running = parse_running(text)
        seen = {}
        for vmx in running:
            seen[vmx.lower()] = {"name": machine_name(vmx), "state": "running",
                                 "vmx": vmx}
        for vmx in self._inventory():
            if vmx.lower() not in seen:
                seen[vmx.lower()] = {"name": machine_name(vmx),
                                     "state": "stopped", "vmx": vmx}
        listing.rows = sorted(seen.values(), key=lambda r: r["name"].lower())
        return listing

    def object_actions(self, target, row):
        vmrun = vmrun_path() or "vmrun"
        vmx = row.get("vmx", "")
        name = row.get("name", vmx)
        if str(row.get("state", "")).lower() == "running":
            return [
                action(f"vmware-stop-{name}", "\u23fb  Shut down",
                       [vmrun, "stop", vmx, "soft"],
                       "Asks the guest to shut down, through VMware Tools."),
                action(f"vmware-suspend-{name}", "\U0001f4be  Suspend",
                       [vmrun, "suspend", vmx],
                       "Writes the machine's memory to disk and stops it; it "
                       "resumes where it left off."),
                action(f"vmware-reset-{name}", "\u21bb  Restart",
                       [vmrun, "reset", vmx, "soft"],
                       "Asks the guest to reboot."),
                action(f"vmware-off-{name}", "\u26a1  Power off",
                       [vmrun, "stop", vmx, "hard"],
                       "Cuts the power. Unsaved work in the guest is lost; "
                       "the machine itself is not deleted.",
                       destructive=True),
                action(f"vmware-snapshot-{name}", "\U0001f4f8  Snapshot",
                       [vmrun, "snapshot", vmx, "kontainy"],
                       "Takes a snapshot named kontainy you can return to."),
            ]
        return [
            action(f"vmware-start-{name}", "\u25b6  Start",
                   [vmrun, "start", vmx, "nogui"],
                   f"Starts {name} without opening the VMware window; use "
                   f"gui instead of nogui to see it."),
            action(f"vmware-startgui-{name}", "\U0001f5a5  Start with window",
                   [vmrun, "start", vmx, "gui"],
                   f"Starts {name} and shows VMware's own window."),
        ]

    def bulk_actions(self, target, rows):
        vmrun = vmrun_path() or "vmrun"
        running = [r for r in rows if str(r.get("state")).lower() == "running"]
        stopped = [r for r in rows if str(r.get("state")).lower() != "running"]
        out = []
        if stopped:
            out.append(_sequence(
                "vmware-start-all", f"\u25b6  Start all ({len(stopped)})",
                [[vmrun, "start", r["vmx"], "nogui"] for r in stopped],
                "Starts every stopped machine. vmrun takes one machine per "
                "command, so they run in turn."))
        if running:
            out.append(_sequence(
                "vmware-stop-all", f"\u23fb  Shut down all ({len(running)})",
                [[vmrun, "stop", r["vmx"], "soft"] for r in running],
                "Asks every running guest to shut down cleanly.",
                destructive=True))
        return out


def _sequence(id: str, label: str, commands: list, explanation: str,
              destructive: bool = False) -> Action:
    from ..elevate import run as _run

    def execute():
        failures = []
        for argv in commands:
            result = _run(argv, note=id)
            if not result.ok:
                failures.append(f"{' '.join(argv)}: {result.output}")
        if failures:
            raise RuntimeError("\n".join(failures))
        return f"{len(commands)} commands succeeded"

    return Action(id=id, label=label, command=[], scope=USER,
                  shell_text="\n".join(" ".join(c) for c in commands),
                  explanation=explanation, destructive=destructive,
                  func=execute)
