"""
kontainy — Hyper-V

Windows' own hypervisor, and the gap on that platform: kontainy hides KVM on
Windows and until now offered nothing in its place. Hyper-V is managed
entirely through PowerShell — Get-VM, Start-VM, Get-VMSwitch — so the
commands kontainy shows are the ones an administrator would type.

    targets   Hyper-V hosts: this machine, plus hosts added by name
              (every cmdlet takes -ComputerName)
    objects   virtual machines
    section   virtual switches — Hyper-V's counterpart to KVM networks

Two traps, both handled here:

* ConvertTo-Json returns a bare object, not an array, when there is exactly
  one result. One VM would otherwise parse as a dictionary of properties.
* Enum properties such as State serialise as numbers. They are converted to
  strings in the PowerShell pipeline, so 'Running' arrives as 'Running'.

Hyper-V requires Windows Pro, Enterprise or Education. Reading VMs needs
membership of the local "Hyper-V Administrators" group or an elevated shell;
without it every cmdlet fails with a permission error, and kontainy says so.
"""

from __future__ import annotations

import platform

from ...utils.config import config
from ..actions import Action, USER
from .base import (Column, Field, Listing, Provider, Section, Target, action,
                   cli_text, json_value)

POWERSHELL = ["powershell", "-NoProfile", "-NonInteractive", "-Command"]


def _quote(value: str) -> str:
    """A PowerShell single-quoted string: '' escapes a quote inside it."""
    return "'" + str(value).replace("'", "''") + "'"


def as_list(data) -> list:
    """ConvertTo-Json gives an object for one result and an array for more."""
    if data is None:
        return []
    return data if isinstance(data, list) else [data]


#: PowerShell exits 0 even when a cmdlet fails, as long as the error is not
#: terminating — so the exit code says nothing. Errors are caught inside the
#: script and marked, which is the only reliable signal. Without this,
#: "Get-VMHost : You do not have the required permission" counted as success
#: and kontainy reported Hyper-V as installed on a machine without it.
MARK = "KONTAINY-FAILED:"


def ps(script: str, timeout: float = 20.0) -> tuple:
    return cli_text(POWERSHELL + [script], timeout=timeout)


def ps_checked(script: str, timeout: float = 20.0) -> tuple:
    """(ok, text) where ok really means the cmdlet worked."""
    guarded = (f"try {{ {script} }} catch {{ "
               f"Write-Output \"{MARK} $($_.Exception.Message)\" }}")
    ok, text = ps(guarded, timeout=timeout)
    if not ok:
        return False, text
    if MARK in text:
        return False, text.split(MARK, 1)[1].strip()
    return True, text.strip()


def _host_arg(target) -> str:
    if target is None or target.name in ("", "localhost", "(local)"):
        return ""
    return f" -ComputerName {_quote(target.name)}"


def _ps_action(id: str, label: str, script: str, explanation: str,
               destructive: bool = False) -> Action:
    return Action(id=id, label=label, command=POWERSHELL + [script],
                  scope=USER, explanation=explanation, destructive=destructive,
                  shell_text=script)


class HyperVProvider(Provider):
    id = "hyperv"
    name = "Hyper-V"
    icon = "\U0001fa9f"
    binary = "powershell"
    target_noun = "Host"
    target_noun_plural = "Hosts"
    object_noun_plural = "Virtual machines"
    object_key = "Name"
    tool_ids = ["hyperv", "virtualbox", "multipass", "vagrant"]
    platforms = ("windows",)
    summary = ("Windows' own hypervisor. A host is a machine running Hyper-V "
               "— this one, or another you manage remotely; every cmdlet "
               "takes -ComputerName.")

    # --- availability -------------------------------------------------------
    def available(self) -> bool:
        """Hyper-V answers, not merely: the cmdlets exist.

        The Hyper-V PowerShell module is present on machines that never
        enabled Hyper-V — WSL 2 and VMware both turn on the Windows
        hypervisor platform and the module comes with it. Asking only
        whether Get-VM exists reported Hyper-V as installed on a machine
        that has none, which is what Bayram saw on 2026-09-23.
        """
        if platform.system() != "Windows":
            return False
        ok, text = ps_checked("(Get-VMHost -ErrorAction Stop).Name",
                              timeout=20.0)
        self._refusal = "" if ok else text
        return ok and bool(text.strip())

    _refusal = ""

    def start_engine(self):
        from ..actions import Action, ROOT
        return Action(
            id="start-engine-hyperv", label="\u25b6  Start the Hyper-V service",
            command=POWERSHELL + ["Start-Service vmms"], scope=ROOT,
            explanation=(
                "Starts the Hyper-V Virtual Machine Management service. If "
                "Hyper-V itself is not enabled, this fails and the Install "
                "tab is the place to go instead."))

    def unavailable_reason(self) -> str:
        if platform.system() != "Windows":
            return "Hyper-V exists only on Windows."
        refusal = (self._refusal or "").lower()
        if "permission" in refusal or "denied" in refusal:
            return ("Hyper-V is enabled, but you are not a member of the "
                    "local 'Hyper-V Administrators' group. Add yourself with "
                    "Add-LocalGroupMember -Group 'Hyper-V Administrators' "
                    "-Member $env:USERNAME  as administrator, then sign out "
                    "and in again.")
        return ("Hyper-V is not enabled on this machine. Its PowerShell "
                "module can be present without it \u2014 WSL 2 and VMware "
                "turn on the Windows hypervisor platform and the module "
                "comes along. Hyper-V itself needs Windows Pro, Enterprise "
                "or Education; enable it from the Install tab, then restart.")

    def version(self) -> str:
        # Only once Hyper-V itself answers: the module's version on a machine
        # with no Hyper-V is a version of nothing.
        if not self.available():
            return ""
        ok, text = ps_checked("(Get-Module -ListAvailable Hyper-V | "
                              "Select-Object -First 1).Version.ToString()")
        return f"Hyper-V module {text.strip()}" if ok and text.strip() else ""

    # --- hosts ----------------------------------------------------------------
    def _hosts(self) -> list:
        return list(config().get("hyperv_hosts") or [])

    def targets(self) -> list:
        active = config().get("hyperv_active") or "localhost"
        out = [Target("localhost", "this computer", active == "localhost",
                      "the Hyper-V host you are sitting at", removable=False)]
        for host in self._hosts():
            out.append(Target(host, f"\\\\{host}", active == host,
                              "remote Hyper-V host"))
        return out

    def activate(self, target):
        def store():
            config().set("hyperv_active", target.name)
            return f"kontainy now manages {target.name}"
        return Action(
            id=f"hyperv-use-{target.name}",
            label=f"Manage Hyper-V on '{target.name}'",
            command=[], scope=USER,
            shell_text=("Get-VM" + _host_arg(target)),
            explanation=(
                "Hyper-V has no global 'current host' setting: every cmdlet "
                "names its host with -ComputerName, or uses this machine. "
                "kontainy remembers the choice and adds -ComputerName to the "
                "commands it shows and runs."),
            func=store)

    def add_fields(self):
        return [Field("name", "Computer name", "HV-SERVER01",
                      "The remote host needs WinRM enabled "
                      "(Enable-PSRemoting) and you need rights on it.")]

    def add(self, values):
        def store():
            hosts = [h for h in self._hosts() if h != values["name"]]
            hosts.append(values["name"])
            config().set("hyperv_hosts", hosts)
            return f"added {values['name']}"
        return Action(
            id=f"hyperv-add-{values['name']}",
            label=f"Add host '{values['name']}'", command=[], scope=USER,
            shell_text=f"Get-VMHost -ComputerName {_quote(values['name'])}",
            explanation=("Remembers the host in kontainy's preferences. The "
                         "command shown is how you would reach it by hand."),
            func=store)

    def remove(self, target):
        def drop():
            config().set("hyperv_hosts",
                         [h for h in self._hosts() if h != target.name])
            if config().get("hyperv_active") == target.name:
                config().set("hyperv_active", "localhost")
            return f"forgot {target.name}"
        return Action(
            id=f"hyperv-forget-{target.name}",
            label=f"Forget host '{target.name}'", command=[], scope=USER,
            shell_text=f"# forget {target.name} in kontainy",
            explanation="Only forgets the host. Nothing on it is touched.",
            destructive=True, func=drop)

    def test(self, target):
        return _ps_action(
            f"hyperv-test-{target.name}", f"Test '{target.name}'",
            "Get-VMHost" + _host_arg(target) + " | Select-Object Name, "
            "LogicalProcessorCount, MemoryCapacity, VirtualMachinePath",
            "Reads the host's name, processors, memory and default VM path. "
            "A permission error here means you are not in the local "
            "'Hyper-V Administrators' group.")

    # --- virtual machines --------------------------------------------------------
    def objects(self, target) -> Listing:
        script = ("Get-VM" + _host_arg(target) + " | Select-Object Name, "
                  "@{n='State';e={$_.State.ToString()}}, CPUUsage, "
                  "@{n='MemoryMB';e={[int]($_.MemoryAssigned/1MB)}}, "
                  "@{n='Uptime';e={$_.Uptime.ToString()}}, Generation, "
                  "@{n='Status';e={$_.Status}} | ConvertTo-Json -Compress")
        listing = Listing(
            columns=[Column("Name", "Name"), Column("State", "State"),
                     Column("CPUUsage", "CPU %"), Column("MemoryMB", "Memory MB"),
                     Column("Uptime", "Uptime"), Column("Generation", "Gen")],
            command=script)
        ok, text = ps_checked(script)
        if not ok:
            listing.error = self._explain_error(text)
            return listing
        listing.rows = [dict(r) for r in as_list(json_value(text, []))]
        return listing

    @staticmethod
    def _explain_error(text: str) -> str:
        if "required permission" in text or "authorization" in text.lower():
            return ("Hyper-V refused: you are not a member of the local "
                    "'Hyper-V Administrators' group. Add yourself with  "
                    "Add-LocalGroupMember -Group 'Hyper-V Administrators' "
                    "-Member $env:USERNAME  (as administrator), then sign out "
                    "and in again.\n\n" + text)
        return text

    def object_actions(self, target, row):
        name = row.get("Name", "")
        host = _host_arg(target)
        q = _quote(name)
        running = str(row.get("State", "")).lower() == "running"
        out = []
        if running:
            out += [
                _ps_action(f"hv-stop-{name}", "\u23fb  Shut down",
                           f"Stop-VM -Name {q}{host}",
                           "Asks the guest to shut down cleanly through the "
                           "integration services."),
                _ps_action(f"hv-save-{name}", "\U0001f4be  Save state",
                           f"Save-VM -Name {q}{host}",
                           "Suspends the machine to disk, like hibernation; "
                           "it resumes exactly where it was."),
                _ps_action(f"hv-restart-{name}", "\u21bb  Restart",
                           f"Restart-VM -Name {q}{host} -Force",
                           "Restarts the machine."),
                _ps_action(f"hv-off-{name}", "\u26a1  Turn off",
                           f"Stop-VM -Name {q}{host} -TurnOff",
                           "Cuts the power. Unsaved work inside the guest is "
                           "lost; the machine itself is not deleted.",
                           destructive=True),
            ]
        else:
            out.append(_ps_action(f"hv-start-{name}", "\u25b6  Start",
                                  f"Start-VM -Name {q}{host}",
                                  f"Starts {name}."))
        out.append(_ps_action(f"hv-checkpoint-{name}", "\U0001f4f8  Checkpoint",
                              f"Checkpoint-VM -Name {q}{host}",
                              "Takes a checkpoint (snapshot) you can return "
                              "to later."))
        out.append(_ps_action(f"hv-connect-{name}", "\U0001f5a5  Connect",
                              f"vmconnect.exe localhost {q}",
                              "Opens the machine's console window."))
        return out

    def bulk_actions(self, target, rows):
        host = _host_arg(target)
        off = [r["Name"] for r in rows
               if str(r.get("State", "")).lower() != "running"]
        on = [r["Name"] for r in rows
              if str(r.get("State", "")).lower() == "running"]
        out = []
        if off:
            names = ", ".join(_quote(n) for n in off)
            out.append(_ps_action("hv-start-all", f"\u25b6  Start all ({len(off)})",
                                  f"Start-VM -Name {names}{host}",
                                  "Starts every stopped machine in one cmdlet."))
        if on:
            names = ", ".join(_quote(n) for n in on)
            out.append(_ps_action("hv-stop-all",
                                  f"\u23fb  Shut down all ({len(on)})",
                                  f"Stop-VM -Name {names}{host}",
                                  "Asks every running guest to shut down "
                                  "cleanly.", destructive=True))
        return out

    # --- virtual switches ------------------------------------------------------
    def sections(self):
        return [Section(
            id="switches", title="Virtual switches", icon="\U0001f310",
            noun="Switch", key="Name",
            summary=("How machines reach the network. External bridges a "
                     "physical adapter; Internal connects the machines and "
                     "the host; Private connects only the machines. 'Default "
                     "Switch' is Windows' built-in NAT and cannot be removed."),
            listing=self._switch_listing,
            row_actions=self._switch_actions,
            create_fields=[
                Field("name", "Name", "LabSwitch"),
                Field("type", "Type", "Internal",
                      "Internal, Private, or External. External also needs "
                      "the adapter name below."),
                Field("adapter", "Physical adapter", "Ethernet",
                      "Only for External. See Get-NetAdapter.",
                      required=False),
            ],
            create=self._switch_create)]

    def _switch_listing(self, target) -> Listing:
        script = ("Get-VMSwitch" + _host_arg(target) + " | Select-Object Name, "
                  "@{n='SwitchType';e={$_.SwitchType.ToString()}}, "
                  "NetAdapterInterfaceDescription | ConvertTo-Json -Compress")
        listing = Listing(columns=[Column("Name", "Switch"),
                                   Column("SwitchType", "Type"),
                                   Column("NetAdapterInterfaceDescription",
                                          "Adapter")],
                          command=script)
        ok, text = ps_checked(script)
        if not ok:
            listing.error = self._explain_error(text)
        else:
            listing.rows = [dict(r) for r in as_list(json_value(text, []))]
        return listing

    def _switch_actions(self, target, row):
        name = row.get("Name", "")
        if name == "Default Switch":
            return []
        return [_ps_action(
            f"hv-switch-rm-{name}", "\U0001f5d1  Remove",
            f"Remove-VMSwitch -Name {_quote(name)}{_host_arg(target)} -Force",
            "Removes the switch. Machines connected to it lose their "
            "network until attached to another.", destructive=True)]

    def _switch_create(self, target, values):
        kind = (values.get("type") or "Internal").strip().capitalize()
        name = _quote(values["name"])
        host = _host_arg(target)
        if kind == "External":
            script = (f"New-VMSwitch -Name {name} -NetAdapterName "
                      f"{_quote(values.get('adapter') or 'Ethernet')} "
                      f"-AllowManagementOS $true{host}")
            why = ("Creates an External switch bound to the physical "
                   "adapter; the host keeps its own connection through it. "
                   "The network drops for a few seconds while it is built.")
        else:
            if kind not in ("Internal", "Private"):
                kind = "Internal"
            script = f"New-VMSwitch -Name {name} -SwitchType {kind}{host}"
            why = (f"Creates a {kind} switch.")
        return _ps_action(f"hv-switch-new-{values['name']}",
                          f"Create switch {values['name']}", script, why)
