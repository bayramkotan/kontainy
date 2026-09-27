"""Quick Start — the first day, in the order it actually happens."""

TOPICS = [
    {
        "title": "What a container is, and how it differs from a virtual machine",
        "body": (
            "A virtual machine runs its own kernel. A container shares the "
            "host's kernel and is given an ISOLATED VIEW of it.\n\n"
            "That isolation comes from two kernel features: namespaces "
            "decide what a process can see, and cgroups decide how much it "
            "can consume. A container is an ordinary process with those two "
            "restrictions applied — run `ps aux` on the host and you will "
            "find it there, alongside everything else.\n\n"
            "This is why containers start in milliseconds rather than "
            "seconds, and why they are not independent of the host kernel: "
            "a Linux container needs a Linux kernel, which is exactly why "
            "Docker Desktop on Windows and macOS runs a small Linux virtual "
            "machine underneath."),
        "diagram": (
            "  VIRTUAL MACHINE              CONTAINER\n"
            "  ┌──────────────┐             ┌──────────────┐\n"
            "  │  app         │             │  app         │\n"
            "  │  libraries   │             │  libraries   │\n"
            "  │  KERNEL      │             └──────┬───────┘\n"
            "  ├──────────────┤             ┌──────┴───────┐\n"
            "  │  hypervisor  │             │ namespaces + │\n"
            "  ├──────────────┤             │ cgroups      │\n"
            "  │  host kernel │             │ host kernel  │\n"
            "  └──────────────┘             └──────────────┘"),
        "note": (
            "LXC, LXD and Incus sit at a third point: container technology, "
            "but running a full operating system with its own init, users "
            "and services. They are closer to a light virtual machine in "
            "how you use them, and to a container in how they run."),
        "links": [("OCI Runtime Spec",
                   "https://github.com/opencontainers/runtime-spec")],
    },
    {
        "title": "Run your first container",
        "body": (
            "The smallest complete example: start a web server, publish it "
            "on port 8080, give it a name, and have it delete itself when "
            "it stops.\n\n"
            "Open http://localhost:8080 and the nginx welcome page is "
            "there. Press Ctrl+C and the container is gone — because of "
            "`--rm`, nothing is left behind to clean up."),
        "snippet": (
            "# Docker\n"
            "docker run --rm --name web -p 8080:80 nginx:alpine\n\n"
            "# Podman — the flags are identical\n"
            "podman run --rm --name web -p 8080:80 "
            "docker.io/library/nginx:alpine"),
        "language": "bash",
        "tip": (
            "Use `--rm` for everything you are only trying out. Without it, "
            "`docker ps -a` fills with dead records and the disk fills with "
            "their writable layers."),
        "warning": (
            "The Podman line spells the image out in full "
            "(`docker.io/library/...`). A short name may fail or, worse, "
            "resolve to a different registry; `short-name-mode` decides "
            "which."),
        "setting_key": "short-name-mode",
    },
    {
        "title": "What publishing a port really does",
        "body": (
            "`-p 8080:80` means: send traffic arriving on the host's port "
            "8080 to port 80 inside the container. The order is "
            "HOST:CONTAINER, and writing it backwards is the most common "
            "mistake there is.\n\n"
            "Underneath, a NAT rule is written. On Docker you can see it "
            "with `iptables -t nat -L DOCKER`.\n\n"
            "You can also name the host address. `-p 127.0.0.1:8080:80` "
            "publishes only to the local machine, which is what you want "
            "for anything that has no business being reachable from the "
            "network."),
        "snippet": (
            "-p 8080:80                 # every interface, port 8080\n"
            "-p 127.0.0.1:8080:80       # this machine only\n"
            "-p 8080:80/udp             # UDP instead of TCP\n"
            "-p 80                      # a random free host port\n"
            "-P                         # publish everything the image "
            "EXPOSEs, randomly"),
        "language": "bash",
        "warning": (
            "Rootless Podman cannot bind ports below 1024. `-p 80:80` fails "
            "with a permission error; use a high port, or lower "
            "`net.ipv4.ip_unprivileged_port_start`."),
        "rule_id": "NET02",
    },
    {
        "title": "Keeping data: volumes and bind mounts",
        "body": (
            "When a container is removed, its writable layer goes with it. "
            "Anything that must survive lives outside the container, and "
            "there are two ways to arrange that.\n\n"
            "A VOLUME is managed by the engine. It has a name, its location "
            "is not your problem, and it is easy to back up and move. This "
            "is the right choice for databases.\n\n"
            "A BIND MOUNT attaches a directory you name on the host. It is "
            "ideal for handing source code to a container during "
            "development, and it is also where permission problems come "
            "from."),
        "snippet": (
            "# Volume — the engine manages it\n"
            "podman volume create pgdata\n"
            "podman run -v pgdata:/var/lib/postgresql/data postgres:16\n\n"
            "# Bind mount — a directory of yours\n"
            "podman run -v ./src:/app/src:ro,Z node:22"),
        "language": "bash",
        "table": {
            "headers": ["Suffix", "Meaning", "When"],
            "rows": [
                ["`:ro`", "read only",
                 "always, when the container should not write"],
                ["`:z`", "shared SELinux label",
                 "several containers use the same path"],
                ["`:Z`", "private SELinux label", "one container only"],
                ["`:rslave`", "mount propagation",
                 "host mounts must appear inside"],
            ]},
        "warning": (
            "On a system with SELinux enforcing, a bind mount without `:z` "
            "or `:Z` gives `Permission denied`. Under rootless Podman, "
            "files in your home directory may also appear as `nobody` — the "
            "fix for that one is `--userns=keep-id`."),
        "setting_key": "volume.selinux",
    },
    {
        "title": "Finding what is running, and what is left behind",
        "body": (
            "`ps` shows what is running. `ps -a` shows what exists, which "
            "is a different and usually longer list: every container that "
            "has ever exited without `--rm` is still there, holding its "
            "writable layer.\n\n"
            "The count that matters is the second one. A machine that feels "
            "full of nothing is usually full of exited containers, their "
            "layers, and images nobody references any more."),
        "snippet": (
            "docker ps              # running\n"
            "docker ps -a           # everything that exists\n"
            "docker ps -a --filter status=exited --format "
            "'{{.Names}}\\t{{.Status}}'\n\n"
            "docker system df       # where the disk went\n"
            "docker system df -v    # the same, itemised"),
        "language": "bash",
        "tip": (
            "kontainy's All containers page does this across every engine "
            "and every context at once, which is the one view neither CLI "
            "gives you."),
    },
    {
        "title": "Reading logs, and what --follow costs",
        "body": (
            "A container's logs are whatever it wrote to standard output "
            "and standard error. If an application writes to a file inside "
            "the container instead, `logs` shows nothing — and that is the "
            "answer to \"why are my logs empty\".\n\n"
            "`--follow` keeps the stream open. It is the right tool while "
            "something is starting up; it is the wrong thing to leave open "
            "in a script, because it never ends on its own."),
        "snippet": (
            "docker logs web                  # everything so far\n"
            "docker logs --tail 50 web        # the last 50 lines\n"
            "docker logs -f --timestamps web  # follow, with times\n"
            "docker logs --since 10m web      # the last ten minutes"),
        "language": "bash",
        "warning": (
            "With the default json-file driver and no limit, a chatty "
            "container can fill the disk on its own. `max-size` and "
            "`max-file` are not set by default."),
        "setting_key": "log-opts.max-size",
        "rule_id": "DSK01",
    },
    {
        "title": "Getting a shell inside a running container",
        "body": (
            "`exec` starts another process inside an existing container. "
            "`-it` gives it a terminal, which is what makes a shell usable.\n\n"
            "The shell has to exist in the image. Alpine images have `sh` "
            "and no `bash`; distroless and scratch images have neither, on "
            "purpose — for those, debug from the outside with `inspect` and "
            "`logs`, or start a second container that shares the first "
            "one's namespaces."),
        "snippet": (
            "docker exec -it web sh          # alpine, busybox, distroless-ish\n"
            "docker exec -it web bash        # debian, ubuntu, fedora\n"
            "docker exec -u root -it web sh  # as root, when the image runs "
            "as someone else\n\n"
            "# No shell in the image? Borrow one:\n"
            "docker run -it --pid=container:web --network=container:web "
            "--cap-add=SYS_PTRACE nicolaka/netshoot"),
        "language": "bash",
        "note": (
            "`exec` runs INSIDE the container but it is not the container's "
            "main process. Killing your shell does not stop the container, "
            "and the container stopping does kill your shell."),
    },
    {
        "title": "Cleaning up without losing anything you wanted",
        "body": (
            "`prune` removes what the engine considers unused, and its idea "
            "of unused is wider than most people expect. Each kind of thing "
            "is pruned by its own command, and the build cache is the one "
            "everybody forgets: `image prune` does not touch it.\n\n"
            "The dangerous one is `--volumes`. An unused volume is any "
            "volume no container currently references — including the "
            "database volume of a container you removed five minutes ago "
            "intending to recreate it."),
        "snippet": (
            "docker container prune        # exited containers\n"
            "docker image prune            # dangling images\n"
            "docker image prune -a         # every image nothing uses\n"
            "docker builder prune          # the build cache\n"
            "docker network prune          # networks with no containers\n\n"
            "docker system prune           # the first four, at once\n"
            "docker system prune --volumes # ... and your data. Read the "
            "list first."),
        "language": "bash",
        "warning": (
            "kontainy's Remove stopped names every container it will remove "
            "before it removes any, precisely because `prune` does not."),
    },
]
