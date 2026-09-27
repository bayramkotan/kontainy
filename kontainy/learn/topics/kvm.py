"""KVM / QEMU / libvirt — real virtualisation, and the three layers of it."""

TOPICS = [
    {
        "title": "Three layers: KVM, QEMU, libvirt",
        "body": (
            "KVM is the kernel module that lets a guest run its "
            "instructions directly on the CPU. QEMU is the process that "
            "emulates everything around them — disks, network cards, a "
            "BIOS. libvirt is the management layer that stores machine "
            "definitions and gives every tool the same API.\n\n"
            "`virsh`, virt-manager and kontainy all talk to libvirt; libvirt "
            "starts QEMU; QEMU uses KVM."),
        "snippet": (
            "lsmod | grep kvm                 # the module\n"
            "ls -l /dev/kvm                   # and permission to use it\n"
            "virsh version\n"
            "qemu-system-x86_64 --version"),
        "language": "bash",
        "warning": (
            "No /dev/kvm means no hardware acceleration: QEMU still runs, "
            "in software, perhaps twenty times slower. Inside WSL it needs "
            "`nestedVirtualization=true` in .wslconfig."),
    },
    {
        "title": "system versus session: two different libvirts",
        "body": (
            "`qemu:///system` is the machine-wide daemon: root owns the "
            "machines, they start at boot, and they use the system's "
            "networks and storage pools.\n\n"
            "`qemu:///session` is yours alone: no root needed, no "
            "networking beyond user-mode NAT, and machines that only exist "
            "for your user. A machine created in one is invisible in the "
            "other, which is behind most \"my VM disappeared\" reports."),
        "snippet": (
            "virsh -c qemu:///system list --all\n"
            "virsh -c qemu:///session list --all\n"
            "echo $LIBVIRT_DEFAULT_URI\n\n"
            "virsh uri                     # which one am I talking to?"),
        "language": "bash",
        "setting_key": "LIBVIRT_DEFAULT_URI",
    },
    {
        "title": "The domain XML is the machine",
        "body": (
            "libvirt stores each machine as XML: CPU, memory, disks, "
            "network interfaces, graphics. Everything a GUI shows is a view "
            "of that file, and everything a GUI cannot do can be done by "
            "editing it.\n\n"
            "Edit it through libvirt, not with a text editor in "
            "/etc/libvirt/qemu — the daemon caches definitions and will "
            "overwrite your file."),
        "snippet": (
            "virsh dumpxml win11 > win11.xml\n"
            "virsh edit win11                 # validated, and reloaded\n"
            "virsh define win11.xml           # from a file\n\n"
            "virsh dominfo win11\n"
            "virsh domblklist win11"),
        "language": "bash",
    },
    {
        "title": "virtio: the drivers that make it fast",
        "body": (
            "QEMU can emulate a real SATA controller and a real network "
            "card, and a guest will use them without any driver. It is also "
            "slow, because every operation is emulated.\n\n"
            "virtio devices are paravirtualised: the guest knows it is a "
            "guest and talks to the hypervisor directly. Linux has the "
            "drivers built in; Windows needs the virtio-win ISO at install "
            "time, and installing without it is why a Windows guest is "
            "sluggish."),
        "snippet": (
            "virsh domblklist win11\n"
            "virsh dumpxml win11 | grep -A3 '<disk'\n\n"
            "# disk: bus='virtio'   network: model type='virtio'"),
        "language": "bash",
        "warning": (
            "Switching an installed Windows guest from SATA to virtio "
            "without loading the driver first gives an unbootable machine. "
            "Add a second virtio disk, let Windows find the driver, then "
            "switch."),
    },
    {
        "title": "Storage pools and disk formats",
        "body": (
            "A pool is a place libvirt keeps disk images: a directory, an "
            "LVM group, a ZFS dataset. The default pool is "
            "/var/lib/libvirt/images.\n\n"
            "qcow2 supports snapshots, compression and thin allocation; raw "
            "is a plain block image, marginally faster and without any of "
            "that. Use qcow2 unless you have measured a reason not to."),
        "snippet": (
            "virsh pool-list --all\n"
            "virsh vol-list default\n\n"
            "qemu-img create -f qcow2 /var/lib/libvirt/images/lab.qcow2 40G\n"
            "qemu-img info /var/lib/libvirt/images/lab.qcow2\n"
            "qemu-img convert -O qcow2 disk.vmdk disk.qcow2   # from VMware"),
        "language": "bash",
    },
    {
        "title": "Networks: NAT, bridged, isolated",
        "body": (
            "The default network is NAT: guests reach the world, the world "
            "does not reach them. A bridged network puts the guest on your "
            "LAN with its own address, which is what a server guest usually "
            "wants. An isolated network has no route out at all.\n\n"
            "Bridging needs a bridge interface on the host, and most "
            "wireless adapters cannot do it."),
        "snippet": (
            "virsh net-list --all\n"
            "virsh net-dumpxml default\n"
            "virsh net-start default && virsh net-autostart default\n\n"
            "# who got which address\n"
            "virsh net-dhcp-leases default"),
        "language": "bash",
        "rule_id": "NET01",
    },
    {
        "title": "Snapshots: internal, external, and the memory state",
        "body": (
            "An internal snapshot lives inside the qcow2 file; an external "
            "one starts a new overlay file and leaves the original "
            "untouched. Only external snapshots are safe to back up while "
            "the guest runs.\n\n"
            "With `--memspec` the RAM is saved too, so reverting returns to "
            "a running machine rather than a cold boot."),
        "snippet": (
            "virsh snapshot-create-as win11 before-update --atomic\n"
            "virsh snapshot-list win11\n"
            "virsh snapshot-revert win11 before-update\n"
            "virsh snapshot-delete win11 before-update\n\n"
            "# external, safer for backups\n"
            "virsh snapshot-create-as win11 snap1 --disk-only --atomic"),
        "language": "bash",
        "warning": (
            "Snapshots are not backups: they live on the same disk as the "
            "machine and a chain of them makes every write slower."),
    },
    {
        "title": "CPU model, host-passthrough and migration",
        "body": (
            "The CPU a guest sees is a model libvirt chooses. "
            "`host-passthrough` shows the real CPU, gives the best "
            "performance and the guest can then only be moved to an "
            "identical machine. A named model is portable and slightly "
            "slower.\n\n"
            "Nested virtualisation — running a hypervisor inside a guest, "
            "which WSL and Docker Desktop need — requires passthrough or a "
            "model with the right flags."),
        "snippet": (
            "virsh capabilities | grep -A5 '<cpu>'\n"
            "virsh dumpxml lab | grep -A2 '<cpu'\n\n"
            "# nested, on Intel\n"
            "cat /sys/module/kvm_intel/parameters/nested\n"
            "# on AMD\n"
            "cat /sys/module/kvm_amd/parameters/nested"),
        "language": "bash",
    },
    {
        "title": "Memory: ballooning, hugepages, overcommit",
        "body": (
            "The balloon driver lets the host reclaim memory a guest is not "
            "using, which is how you overcommit safely. Hugepages do the "
            "opposite: pin memory and reduce translation overhead for large "
            "guests, at the cost of that memory being unavailable to "
            "anything else.\n\n"
            "Databases and anything latency-sensitive benefit from "
            "hugepages; general-purpose guests benefit from the balloon."),
        "snippet": (
            "virsh dommemstat lab\n"
            "virsh setmem lab 4G --live\n\n"
            "grep Huge /proc/meminfo\n"
            "virsh dumpxml lab | grep -A3 memoryBacking"),
        "language": "bash",
    },
    {
        "title": "VFIO and GPU passthrough",
        "body": (
            "VFIO hands a real PCI device to a guest. The device must be in "
            "its own IOMMU group and bound to vfio-pci instead of its normal "
            "driver, and the host loses it entirely while the guest runs.\n\n"
            "It is the only way to get real GPU performance in a virtual "
            "machine, and it is also the configuration most likely to leave "
            "a machine without a display if a step is missed."),
        "snippet": (
            "# is IOMMU on? (kernel line: intel_iommu=on or amd_iommu=on)\n"
            "dmesg | grep -i -e DMAR -e IOMMU | head\n\n"
            "for g in /sys/kernel/iommu_groups/*/devices/*; do\n"
            "  echo \"${g##*/} $(lspci -nns ${g##*/})\"\n"
            "done | sort | head -20\n\n"
            "lspci -nnk -d 10de:              # the card and its driver"),
        "language": "bash",
        "warning": (
            "Bind the card to vfio-pci before the host's driver claims it, "
            "and keep a second GPU or serial console: a mistake here leaves "
            "no screen to fix it from."),
    },
    {
        "title": "cloud-init: a guest that configures itself",
        "body": (
            "Cloud images have no password and no user. cloud-init reads a "
            "small ISO attached at first boot and creates the user, plants "
            "the SSH key, sets the hostname and runs whatever you asked.\n\n"
            "This turns \"install an operating system\" into \"boot an image\", "
            "and it is how virt-install's `--cloud-init` option works."),
        "snippet": (
            "cat > user-data <<'EOF'\n"
            "#cloud-config\n"
            "users:\n"
            "  - name: bayram\n"
            "    sudo: ALL=(ALL) NOPASSWD:ALL\n"
            "    ssh_authorized_keys:\n"
            "      - ssh-ed25519 AAAA...\n"
            "package_update: true\n"
            "EOF\n\n"
            "virt-install --name lab --memory 4096 --vcpus 2 \\\n"
            "  --disk path=/var/lib/libvirt/images/lab.qcow2,size=40 \\\n"
            "  --cloud-init user-data=user-data \\\n"
            "  --os-variant debian12 --import --noautoconsole"),
        "language": "bash",
    },
    {
        "title": "Consoles: spice, VNC and the serial line",
        "body": (
            "SPICE gives clipboard sharing, USB redirection and a resizing "
            "display; VNC is simpler and works from anything. Both need a "
            "graphical guest.\n\n"
            "The serial console needs none of that, and it is the one that "
            "still works when the guest fails to boot — which is exactly "
            "when a graphical console shows a black rectangle."),
        "snippet": (
            "virsh console lab            # serial; Ctrl+] to leave\n"
            "virt-viewer --connect qemu:///system lab\n"
            "virsh domdisplay lab         # the spice:// or vnc:// address\n\n"
            "# the guest needs console=ttyS0 on its kernel line"),
        "language": "bash",
    },
]
