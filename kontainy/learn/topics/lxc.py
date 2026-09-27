"""LXC / LXD / Incus — system containers, which are a different animal."""

TOPICS = [
    {
        "title": "System containers versus application containers",
        "body": (
            "A Docker container runs one process and dies with it. An LXD "
            "or Incus container boots systemd, has users, services, "
            "cron and its own package manager — it behaves like a small "
            "machine, on the host's kernel.\n\n"
            "That makes it the right tool for \"I want a Debian box for an "
            "afternoon\" and the wrong tool for \"I want to ship this "
            "service\"."),
        "snippet": (
            "incus launch images:debian/13 lab\n"
            "incus exec lab -- systemctl status\n"
            "incus exec lab -- bash\n\n"
            "incus list"),
        "language": "bash",
        "note": (
            "Incus is the community fork of LXD after LXD moved under "
            "Canonical's CLA. The commands are the same; `lxc` becomes "
            "`incus`."),
    },
    {
        "title": "LXC, LXD and Incus: which is which",
        "body": (
            "LXC is the low-level library and its tools — `lxc-create`, "
            "`lxc-start`. LXD and Incus are daemons built on top of it that "
            "add an API, images, storage pools, networks and clustering.\n\n"
            "Confusingly, LXD's client command is also called `lxc`. "
            "`lxc-start` is LXC; `lxc start` is LXD."),
        "snippet": (
            "lxc-checkconfig                 # the LXC tools\n"
            "lxc list                        # LXD's client\n"
            "incus list                      # Incus\n\n"
            "systemctl status incus lxd 2>/dev/null"),
        "language": "bash",
    },
    {
        "title": "Images and remotes",
        "body": (
            "Images come from remotes, which are servers with a published "
            "image list. `images:` is the community remote; `ubuntu:` "
            "carries Ubuntu's own.\n\n"
            "An image is cached locally on first use and can be kept "
            "up to date automatically, which is why the second launch of "
            "the same distribution is instant."),
        "snippet": (
            "incus remote list\n"
            "incus image list images: debian | head\n"
            "incus launch images:alpine/3.20 alp\n\n"
            "incus image list                # what is cached here\n"
            "incus image delete <fingerprint>"),
        "language": "bash",
    },
    {
        "title": "Profiles: the settings many containers share",
        "body": (
            "A profile is a named set of configuration and devices. Every "
            "container gets the `default` profile, and profiles stack — the "
            "last one wins where they overlap.\n\n"
            "This is how you give ten containers the same network and disk "
            "without repeating yourself, and how you add a GPU to a group "
            "of them in one edit."),
        "snippet": (
            "incus profile list\n"
            "incus profile show default\n\n"
            "incus profile create gpu\n"
            "incus profile device add gpu mygpu gpu\n"
            "incus launch images:debian/13 ml --profile default --profile gpu"),
        "language": "bash",
    },
    {
        "title": "Storage pools: dir, btrfs, zfs, lvm",
        "body": (
            "The pool backend decides what you can do. `dir` works "
            "anywhere and supports nothing clever. btrfs and zfs give "
            "instant snapshots and copy-on-write clones, which turn "
            "\"give me ten identical test machines\" into a second's work.\n\n"
            "Choose the backend when you create the pool; changing it later "
            "means moving every container in it."),
        "snippet": (
            "incus storage list\n"
            "incus storage create fast zfs source=/dev/nvme0n1p3\n"
            "incus launch images:debian/13 lab -s fast\n\n"
            "incus storage info fast"),
        "language": "bash",
    },
    {
        "title": "Snapshots and copies",
        "body": (
            "A snapshot is a point in time you can return to; a copy is a "
            "new container from that point. On a copy-on-write pool both "
            "are nearly free.\n\n"
            "Snapshots can also be scheduled, which makes a development "
            "container something you can experiment in without fear."),
        "snippet": (
            "incus snapshot create lab before-upgrade\n"
            "incus snapshot list lab\n"
            "incus snapshot restore lab before-upgrade\n\n"
            "incus copy lab lab-clone\n"
            "incus config set lab snapshots.schedule '@daily'"),
        "language": "bash",
    },
    {
        "title": "Unprivileged containers and the idmap",
        "body": (
            "By default containers are unprivileged: root inside is an "
            "ordinary UID outside, taken from the host's subuid range. This "
            "is the security model, and it is also why files on a shared "
            "disk appear with strange ownership.\n\n"
            "`raw.idmap` maps a specific host UID to a specific container "
            "UID, which is how you share a directory with your own user "
            "without giving the container privilege."),
        "snippet": (
            "incus config set lab raw.idmap 'both 1000 1000'\n"
            "incus restart lab\n"
            "incus config device add lab shared disk "
            "source=/home/me/work path=/work\n\n"
            "grep root /etc/subuid /etc/subgid"),
        "language": "bash",
        "warning": (
            "A privileged container (`security.privileged=true`) maps root "
            "to root. It solves permission puzzles and removes the main "
            "barrier between the container and the host; treat it as a last "
            "resort."),
    },
    {
        "title": "Networking: the managed bridge and the alternatives",
        "body": (
            "The default install creates a managed bridge with its own "
            "subnet, DHCP and DNS — containers get addresses and resolve "
            "each other by name without any setup.\n\n"
            "For a container that should be on the LAN, use a macvlan or a "
            "bridged profile instead; for isolation, create a second "
            "managed network and put it there."),
        "snippet": (
            "incus network list\n"
            "incus network show incusbr0\n"
            "incus network create lab ipv4.address=10.20.0.1/24 "
            "ipv4.nat=true\n\n"
            "incus config device add web eth0 nic network=lab\n"
            "incus list -c n4t"),
        "language": "bash",
    },
    {
        "title": "Limits, and the fact that they are live",
        "body": (
            "CPU, memory and disk limits can be changed while the container "
            "runs; there is nothing to restart. Under the hood they are "
            "cgroup values, the same mechanism as everywhere else.\n\n"
            "`limits.cpu` takes a count or a pinned set of cores, and "
            "`limits.memory.enforce=soft` lets a container exceed its "
            "share while memory is free."),
        "snippet": (
            "incus config set lab limits.cpu 2\n"
            "incus config set lab limits.memory 2GiB\n"
            "incus config set lab limits.cpu.allowance 50%\n"
            "incus config device set lab root size=20GiB\n\n"
            "incus info lab --resources | head -20"),
        "language": "bash",
        "rule_id": "RES01",
    },
    {
        "title": "Virtual machines from the same tool",
        "body": (
            "Incus and LXD run virtual machines as well as containers, with "
            "the same commands and the same image names — `--vm` is the "
            "only difference.\n\n"
            "That is the practical answer to \"container or VM\": start with "
            "a container, and if it needs its own kernel, modules or a "
            "different operating system, relaunch the same image as a "
            "machine."),
        "snippet": (
            "incus launch images:debian/13 vm1 --vm\n"
            "incus launch images:debian/13 vm2 --vm "
            "-c limits.cpu=4 -c limits.memory=8GiB\n\n"
            "incus console vm1 --type=vga\n"
            "incus list -c nst4   # name, state, type, address"),
        "language": "bash",
        "note": (
            "A VM needs the agent inside the guest for `exec` and file "
            "transfer to work; the official images ship it."),
    },
]
