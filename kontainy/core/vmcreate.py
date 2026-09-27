"""
kontainy — creating a virtual machine from named values

The container half of `create` builds a `run` command; this builds the
equivalent for the hypervisors, each in its own words:

    ky kvm create lab memory=4096 cpus=2 disk=40 iso=/srv/iso/debian.iso
    ky hyperv create lab memory=4096 disk=40 switch=Default

What the two have in common is everything that makes a virtual machine go
wrong: memory in the wrong unit, a disk that already exists and would be
overwritten, no installation source so the machine boots to nothing, and a
network that does not exist. Those are checked here, before the command
runs, for both.

Qt-free: the command line uses it today and the window will use the same
builder rather than writing a second one.
"""

from __future__ import annotations

from dataclasses import dataclass

#: (field, help, required) per technology.
LIBVIRT_FIELDS = [
    ("memory", "Memory in MiB \u2014 4096", True),
    ("cpus", "How many virtual CPUs (default 2)", False),
    ("disk", "New disk size in GiB, or a path to an existing qcow2", True),
    ("iso", "Installation ISO to boot from", False),
    ("network", "Network to attach \u2014 default is the 'default' NAT "
                "network", False),
    ("os", "Guest OS variant for sensible defaults \u2014 debian12, "
           "win11, generic", False),
    ("graphics", "spice (default), vnc or none", False),
    ("pool", "Where a new disk is created (default /var/lib/libvirt/images)",
     False),
]

HYPERV_FIELDS = [
    ("memory", "Startup memory in MiB \u2014 4096", True),
    ("cpus", "How many virtual processors (default 2)", False),
    ("disk", "New VHDX size in GiB, or a path to an existing .vhdx", True),
    ("iso", "Installation ISO to attach", False),
    ("switch", "Virtual switch to attach \u2014 Default Switch", False),
    ("generation", "2 (UEFI, default) or 1 (BIOS, for old guests)", False),
    ("path", "Where the VHDX is created", False),
]

VMWARE_FIELDS = [
    ("memory", "Memory in MiB", True),
    ("cpus", "How many processors (default 2)", False),
    ("disk", "New disk size in GiB", True),
    ("iso", "Installation ISO", False),
    ("path", "Folder for the new machine", False),
]

FIELDS = {"libvirt": LIBVIRT_FIELDS, "hyperv": HYPERV_FIELDS,
          "vmware": VMWARE_FIELDS}

DEFAULT_POOL = "/var/lib/libvirt/images"


@dataclass
class Plan:
    argv: list
    values: dict
    problems: list
    note: str = ""

    @property
    def refused(self) -> bool:
        return any(severity == "error" for severity, _ in self.problems)


def fields_for(provider) -> list:
    return FIELDS.get(provider.id, [])


def supported(provider) -> bool:
    return provider.id in FIELDS


def describe_fields(provider) -> str:
    lines = [f"usage: ky {provider.id} create NAME key=value ...", "",
             "fields:"]
    for key, help_text, required in fields_for(provider):
        lines.append(f"  {key:11}{' *' if required else '  '} {help_text}")
    lines += ["", "examples:"]
    if provider.id == "libvirt":
        lines += ["  ky kvm create lab memory=4096 cpus=2 disk=40 "
                  "iso=/srv/iso/debian-13.iso os=debian12",
                  "  ky kvm create web memory=2048 "
                  "disk=/var/lib/libvirt/images/web.qcow2"]
    elif provider.id == "hyperv":
        lines += ["  ky hyperv create lab memory=4096 disk=40 "
                  "switch='Default Switch' iso=D:\\\\iso\\\\win11.iso"]
    else:
        lines += [f"  ky {provider.id} create lab memory=4096 disk=40"]
    return "\n".join(lines)


# --- checks -------------------------------------------------------------------
def _number(value, name: str, problems: list, minimum: int = 1):
    text = str(value).strip().rstrip("gGmM")
    if not text.isdigit():
        problems.append(("error", f"{name} must be a number; got {value!r}"))
        return 0
    number = int(text)
    if number < minimum:
        problems.append(("error", f"{name} of {number} is too small"))
    return number


def check(provider, values: dict, existing_names: list,
          networks: list = None) -> list:
    """Everything kontainy can see is wrong, in the same shape as containers."""
    problems = []
    name = values.get("name", "").strip()
    if not name:
        problems.append(("error", "A virtual machine needs a name."))
    elif name in set(existing_names or []):
        problems.append(("error", f"There is already a machine called {name} "
                                  f"on this host."))

    memory = _number(values.get("memory", 0), "memory", problems, 256)
    if memory and memory < 1024:
        problems.append(("warning",
                         f"{memory} MiB is very little; most installers need "
                         f"at least 1024 and a desktop guest wants 4096. "
                         f"Memory here is MiB, not GiB."))
    if memory > 1024 * 1024:
        problems.append(("warning",
                         f"{memory} MiB is {memory // 1024} GiB \u2014 if you "
                         f"meant GiB, this is a thousand times too much."))
    if values.get("cpus"):
        _number(values["cpus"], "cpus", problems, 1)

    disk = str(values.get("disk", "")).strip()
    if not disk:
        problems.append(("error", "Say the disk: a size in GiB for a new one, "
                                  "or the path of an existing image."))
    elif any(character in disk for character in "/\\"):
        from ..utils import fs
        if not fs.exists(disk):
            problems.append(("error", f"{disk} does not exist. Give a size in "
                                      f"GiB to create a new disk instead."))
    else:
        size = _number(disk, "disk", problems, 1)
        if size and size < 8:
            problems.append(("warning",
                             f"{size} GiB is smaller than most installers "
                             f"accept; 20 or more is usual."))

    iso = str(values.get("iso", "")).strip()
    if iso:
        from ..utils import fs
        if not fs.exists(iso):
            problems.append(("error", f"The ISO {iso} was not found."))
    else:
        problems.append(("warning",
                         "No ISO, so the machine will be created with an "
                         "empty disk and nothing to boot. Add iso=... to "
                         "install an operating system."))

    network = str(values.get("network") or values.get("switch") or "").strip()
    if network and networks and network not in set(networks):
        problems.append(("error",
                         f"There is no network called {network} here. "
                         f"Available: {', '.join(networks)}"))

    known = {field for field, _help, _required in fields_for(provider)}
    for key in values:
        if key not in known and key != "name":
            problems.append(("error", f"{key} is not a field of create; run "
                                      f"`ky {provider.id} create` to see them"))
    return problems


# --- builders -----------------------------------------------------------------
def _libvirt_argv(provider, target, values: dict) -> list:
    uri = target.address if target else "qemu:///system"
    disk = str(values.get("disk", "")).strip()
    pool = str(values.get("pool") or DEFAULT_POOL).rstrip("/")
    name = values["name"]
    if any(character in disk for character in "/\\"):
        disk_arg = f"path={disk}"
    else:
        disk_arg = f"path={pool}/{name}.qcow2,size={disk},format=qcow2"

    argv = ["virt-install", "--connect", uri, "--name", name,
            "--memory", str(values["memory"]),
            "--vcpus", str(values.get("cpus", 2)),
            "--disk", disk_arg,
            "--network", f"network={values.get('network', 'default')}",
            "--graphics", str(values.get("graphics", "spice")),
            "--noautoconsole"]
    if values.get("os"):
        argv += ["--os-variant", values["os"]]
    if values.get("iso"):
        argv += ["--cdrom", values["iso"]]
    else:
        argv += ["--import"]
    return argv


def _hyperv_script(values: dict) -> str:
    name = values["name"]
    disk = str(values.get("disk", "")).strip()
    path = str(values.get("path") or "").strip()
    quoted = name.replace("'", "''")
    lines = [f"$name = '{quoted}'"]
    new_vm = [f"New-VM -Name $name",
              f"-MemoryStartupBytes {int(values['memory'])}MB",
              f"-Generation {values.get('generation', 2)}"]
    if any(character in disk for character in "/\\"):
        new_vm.append(f"-VHDPath '{disk}'")
    else:
        if path:
            lines.append(f"$vhd = Join-Path '{path}' \"$name.vhdx\"")
        else:
            # Hyper-V's own disk folder, not the shell's current directory:
            # a bare name would put the VHDX wherever kontainy happened to
            # be running from.
            lines.append("$vhd = Join-Path (Get-VMHost).VirtualHardDiskPath "
                         "\"$name.vhdx\"")
        new_vm += ["-NewVHDPath $vhd", f"-NewVHDSizeBytes {int(disk)}GB"]
    if values.get("switch"):
        new_vm.append(f"-SwitchName '{values['switch']}'")
    lines.append(" ".join(new_vm))
    lines.append(f"Set-VMProcessor -VMName $name -Count "
                 f"{values.get('cpus', 2)}")
    if values.get("iso"):
        lines.append(f"Add-VMDvdDrive -VMName $name -Path '{values['iso']}'")
        if str(values.get("generation", 2)) == "2":
            lines.append("$dvd = Get-VMDvdDrive -VMName $name")
            lines.append("Set-VMFirmware -VMName $name -FirstBootDevice $dvd")
    return "; ".join(lines)


def build(provider, target, values: dict, existing_names: list = None,
          networks: list = None) -> Plan:
    """The command that would create the machine, and what is wrong with it."""
    values = {key: str(value).strip() for key, value in values.items()}
    problems = check(provider, values, existing_names, networks)
    note = ""
    if provider.id == "libvirt":
        argv = _libvirt_argv(provider, target, values) if not any(
            severity == "error" for severity, _ in problems) else []
        note = ("virt-install creates the machine and starts it; the console "
                "is not opened, which is what --noautoconsole means. Open it "
                "from the page or with virt-viewer.")
    elif provider.id == "hyperv":
        from .providers.hyperv import POWERSHELL
        script = _hyperv_script(values) if not any(
            severity == "error" for severity, _ in problems) else ""
        argv = POWERSHELL + [script] if script else []
        note = ("New-VM creates the machine stopped. Generation 2 is UEFI and "
                "cannot boot older guests; generation 1 is the fallback.")
    else:
        argv = []
        problems.append(("error", f"kontainy cannot create a machine for "
                                  f"{provider.name} yet."))
    return Plan(argv=argv, values=values, problems=problems, note=note)
