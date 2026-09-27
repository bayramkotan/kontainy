"""Container Internals — what a container actually is, one piece at a time."""

TOPICS = [
    {
        "title": "Namespaces decide what a container can see",
        "body": (
            "Linux has seven namespace types, and each isolates the view of "
            "one kind of resource. A container is a combination of them.\n\n"
            "They are not a container feature: you can make them by hand "
            "with `unshare`. A container engine is the thing that assembles "
            "them, adds a root filesystem, and applies limits."),
        "table": {
            "headers": ["Namespace", "What it isolates", "Flag"],
            "rows": [
                ["pid", "process numbers", "`--pid`"],
                ["net", "interfaces, ports, routes", "`--network`"],
                ["mnt", "mount points", "*(always)*"],
                ["uts", "hostname and domain", "`--uts`"],
                ["ipc", "shared memory, semaphores", "`--ipc`"],
                ["user", "UID and GID mapping", "`--userns`"],
                ["cgroup", "the cgroup tree it can see", "`--cgroupns`"],
            ]},
        "snippet": (
            "# A namespace without any container engine\n"
            "unshare --pid --fork --mount-proc bash\n"
            "ps aux          # only your own processes\n\n"
            "# Step into a running container's network namespace\n"
            "sudo nsenter -t $(podman inspect -f '{{.State.Pid}}' web) -n "
            "ip addr"),
        "language": "bash",
        "tip": (
            "`--network=host` means: do not create a network namespace at "
            "all. The container then has the host's interfaces, and "
            "publishing ports becomes meaningless — they are already open."),
    },
    {
        "title": "cgroup v2 decides how much it can consume",
        "body": (
            "Control groups put limits on CPU, memory, I/O and process "
            "count. Modern systems use v2: a single unified hierarchy under "
            "/sys/fs/cgroup.\n\n"
            "Whether a limit is actually enforced depends on which cgroup "
            "manager the engine uses. Rootless needs systemd delegation; "
            "with cgroupfs selected instead, limits are IGNORED WITHOUT AN "
            "ERROR — the command succeeds and nothing is enforced."),
        "snippet": (
            "# Is this system on cgroup v2?\n"
            "stat -fc %T /sys/fs/cgroup    # expect 'cgroup2fs'\n\n"
            "# Which manager does Podman use?\n"
            "podman info --format '{{.Host.CgroupManager}}'\n\n"
            "# Read the limit that is really in force\n"
            "cat /sys/fs/cgroup/user.slice/user-1000.slice/"
            "user@1000.service/*/memory.max"),
        "language": "bash",
        "warning": (
            "This is the most quietly dangerous failure in the ecosystem: "
            "you set a limit, the command returns success, and the limit "
            "does not exist. kontainy's RES01 rule looks for exactly this."),
        "rule_id": "RES01",
        "setting_key": "containers.cgroup_manager",
    },
    {
        "title": "Capabilities: root, cut into pieces",
        "body": (
            "Linux splits root's power into about forty capabilities. A "
            "container running as root has only the ones it was given.\n\n"
            "Docker and Podman ship DIFFERENT DEFAULT SETS. Docker includes "
            "AUDIT_WRITE and MKNOD; Podman does not. An image that works "
            "under Docker and fails under Podman with a permission error is "
            "usually meeting that difference."),
        "table": {
            "headers": ["Capability", "What it allows", "Risk"],
            "rows": [
                ["`NET_BIND_SERVICE`", "bind ports below 1024", "low"],
                ["`CHOWN`", "change file ownership", "low"],
                ["`NET_ADMIN`", "configure networking", "medium"],
                ["`SYS_PTRACE`", "trace other processes", "medium"],
                ["`SYS_ADMIN`", "mount, namespaces, much else",
                 "**very high**"],
                ["`SYS_MODULE`", "load kernel modules",
                 "**owns the host**"],
            ]},
        "snippet": (
            "# The pattern worth keeping: drop everything, add what is needed\n"
            "podman run --cap-drop=ALL --cap-add=NET_BIND_SERVICE nginx\n\n"
            "# What does a running container actually hold?\n"
            "podman inspect web --format '{{.EffectiveCaps}}'\n"
            "grep Cap /proc/$(pgrep -f nginx | head -1)/status"),
        "language": "bash",
        "tip": (
            "`SYS_ADMIN` is close to `--privileged` in practice. It gets "
            "added so a container \"can just mount something\" and takes the "
            "isolation with it."),
        "setting_key": "cap-add",
    },
    {
        "title": "Layers and copy-on-write",
        "body": (
            "An image is a stack of read-only layers. Starting a container "
            "adds one writable layer on top, and everything the container "
            "changes is written there.\n\n"
            "That is copy-on-write: modifying a file from a lower layer "
            "copies it upward first. Changing one byte of a large file "
            "copies the whole file — which is the answer to why an image or "
            "a container grew far more than the change suggests."),
        "diagram": (
            "  ┌─────────────────────────┐  ← writable layer (container)\n"
            "  ├─────────────────────────┤  ← COPY . /app\n"
            "  ├─────────────────────────┤  ← RUN pip install\n"
            "  ├─────────────────────────┤  ← FROM python:3.12\n"
            "  └─────────────────────────┘  ← base layer"),
        "snippet": (
            "# The layers and what each one cost\n"
            "podman history docker.io/library/python:3.12-slim\n\n"
            "# What has this container changed since it started?\n"
            "podman diff web"),
        "language": "bash",
        "note": (
            "Deleting a file in a Dockerfile does not remove it from the "
            "image: the lower layer still holds it, and the delete only "
            "hides it. A secret added and then removed is still in the "
            "image — which is why multi-stage builds exist."),
        "setting_key": "storage.driver",
    },
    {
        "title": "What an image actually is",
        "body": (
            "An image is a manifest, a config blob and a set of layer "
            "blobs, all addressed by digest. The tag you type is a pointer, "
            "and a pointer can be moved.\n\n"
            "`nginx:1.27` today and `nginx:1.27` in six months can be "
            "different images. Only the digest — `nginx@sha256:...` — names "
            "one exact image forever."),
        "snippet": (
            "# What the tag points at right now\n"
            "docker image inspect nginx:alpine --format '{{.Id}}'\n"
            "docker image inspect nginx:alpine --format "
            "'{{index .RepoDigests 0}}'\n\n"
            "# Pin it, for a build that must be reproducible\n"
            "FROM nginx@sha256:0c6b0a6b0c6a...  # not FROM nginx:latest"),
        "language": "bash",
        "tip": (
            "`:latest` is not a version, it is the tag applied when nobody "
            "gave one. Treat it as \"whatever happened to be pushed last\"."),
    },
    {
        "title": "The entrypoint and the command, and why both exist",
        "body": (
            "ENTRYPOINT is what runs; CMD is the default argument list "
            "given to it. Arguments after the image name on the command "
            "line replace CMD, not ENTRYPOINT.\n\n"
            "That is why `docker run postgres:16 --version` passes "
            "`--version` to postgres rather than running a different "
            "program, and why overriding the entrypoint needs its own flag."),
        "snippet": (
            "# ENTRYPOINT [\"nginx\"], CMD [\"-g\", \"daemon off;\"]\n"
            "docker run nginx                  # nginx -g 'daemon off;'\n"
            "docker run nginx -t               # nginx -t\n"
            "docker run --entrypoint sh nginx  # a shell instead\n\n"
            "docker inspect nginx --format "
            "'entrypoint={{.Config.Entrypoint}} cmd={{.Config.Cmd}}'"),
        "language": "bash",
        "note": (
            "In kontainy's create dialog these two appear as placeholders "
            "filled from the image itself, so an empty box means \"whatever "
            "the image does\"."),
    },
    {
        "title": "PID 1, signals, and why Ctrl+C sometimes does nothing",
        "body": (
            "The first process in a container is PID 1, and the kernel "
            "treats PID 1 specially: signals with a default action are not "
            "delivered unless the process installs a handler.\n\n"
            "A shell script as PID 1 that does not forward signals means "
            "`docker stop` waits ten seconds and then sends SIGKILL — which "
            "is why a clean shutdown turns into exit code 137 and a "
            "corrupted database now and then."),
        "snippet": (
            "# Shell form: the shell becomes PID 1 and swallows signals\n"
            "CMD python app.py\n\n"
            "# Exec form: the program itself is PID 1\n"
            "CMD [\"python\", \"app.py\"]\n\n"
            "# Or give it a real init that reaps children and forwards "
            "signals\n"
            "docker run --init myapp"),
        "language": "bash",
        "warning": (
            "`--init` also solves zombie processes: PID 1 is supposed to "
            "reap orphans, and an application that never expected to be PID "
            "1 does not."),
    },
    {
        "title": "Users, UIDs, and the file that belongs to nobody",
        "body": (
            "The user inside a container is a number. UID 1000 inside is "
            "UID 1000 outside unless a user namespace maps it somewhere "
            "else — names are looked up in each side's own /etc/passwd and "
            "have nothing to do with each other.\n\n"
            "This is why a file written by a container appears as `nobody` "
            "or as a five-digit UID on the host: that number exists inside "
            "the container's mapping and nowhere else."),
        "snippet": (
            "docker run --user 1000:1000 alpine id\n"
            "docker run --user $(id -u):$(id -g) -v $PWD:/work alpine "
            "touch /work/file\n\n"
            "# Rootless Podman: keep your own UID so home files stay yours\n"
            "podman run --userns=keep-id -v $HOME/data:/data alpine ls -l "
            "/data"),
        "language": "bash",
        "tip": (
            "An image that runs as root by default is not automatically "
            "unsafe, but it is one fewer layer of defence. `USER` in the "
            "Dockerfile, or `--user` at run time, costs nothing."),
    },
    {
        "title": "Where the engine keeps everything",
        "body": (
            "Docker keeps images, containers, volumes and networks under "
            "/var/lib/docker. Rootful Podman uses /var/lib/containers; "
            "rootless Podman uses ~/.local/share/containers.\n\n"
            "This matters twice: when the disk fills, and when someone "
            "wonders why `sudo podman ps` shows a different world from "
            "`podman ps`. They are different stores, not different views of "
            "one store."),
        "snippet": (
            "docker info --format '{{.DockerRootDir}}'\n"
            "podman info --format '{{.Store.GraphRoot}}'\n"
            "sudo podman info --format '{{.Store.GraphRoot}}'\n\n"
            "du -sh /var/lib/docker/* 2>/dev/null | sort -h | tail"),
        "language": "bash",
        "note": (
            "Moving Docker's directory is done with `data-root` in "
            "daemon.json, with the daemon stopped. Copying it while the "
            "daemon runs produces a store that looks fine and is not."),
        "setting_key": "data-root",
    },
    {
        "title": "Storage drivers: overlay2, fuse-overlayfs, vfs",
        "body": (
            "The storage driver implements the layering. overlay2 is the "
            "kernel's own and is what you want. fuse-overlayfs is the "
            "userspace stand-in rootless Podman uses where the kernel will "
            "not allow the real thing — correct, and noticeably slower.\n\n"
            "vfs is the fallback that copies every layer instead of "
            "stacking them. If you find yourself on vfs, disk use and build "
            "times explode, and the reason is almost always a filesystem "
            "that does not support overlay."),
        "snippet": (
            "docker info --format '{{.Driver}}'\n"
            "podman info --format '{{.Store.GraphDriverName}}'\n\n"
            "# Does this kernel do rootless overlay natively?\n"
            "podman info --format '{{.Host.Security.Rootless}}'\n"
            "grep -w overlay /proc/filesystems"),
        "language": "bash",
        "warning": (
            "A container store on ZFS, NFS or eCryptfs commonly falls back "
            "to vfs. Put the store on ext4, xfs or btrfs and the problem "
            "disappears."),
        "setting_key": "storage.driver",
    },
    {
        "title": "runc and crun: the thing that actually starts it",
        "body": (
            "Above the runtime is the engine; below it is a small program "
            "that sets up the namespaces, applies the cgroup and execs your "
            "process. runc is written in Go, crun in C.\n\n"
            "crun starts faster and uses less memory per container, and it "
            "supports cgroup v2 features runc took longer to reach. On "
            "Fedora and derivatives it is already the default."),
        "snippet": (
            "podman info --format '{{.Host.OCIRuntime.Name}}'\n"
            "docker info --format '{{.DefaultRuntime}}'\n\n"
            "# Use crun for one container\n"
            "podman run --runtime crun alpine true\n\n"
            "# Measure the difference honestly\n"
            "time podman run --rm --runtime runc alpine true\n"
            "time podman run --rm --runtime crun alpine true"),
        "language": "bash",
        "setting_key": "containers.runtime",
    },
    {
        "title": "conmon, and who holds the container when there is no daemon",
        "body": (
            "Podman has no daemon, but something must stay alive to hold "
            "the container's terminal, write its logs and report its exit "
            "code. That something is conmon: one small process per "
            "container.\n\n"
            "conmon is why a rootless container keeps running after your "
            "shell exits — and why, if lingering is disabled, logging out "
            "takes those processes with it."),
        "snippet": (
            "podman run -d --name web nginx\n"
            "pgrep -a conmon\n\n"
            "# Keep a user's services alive after logout\n"
            "loginctl enable-linger $USER\n"
            "loginctl show-user $USER --property=Linger"),
        "language": "bash",
        "rule_id": "POD02",
    },
    {
        "title": "Seccomp: the system calls a container may make",
        "body": (
            "Both engines apply a default seccomp profile that blocks "
            "around forty of the kernel's system calls — the ones no normal "
            "workload needs and several exploits do.\n\n"
            "It is usually invisible, until it is not: an old binary using "
            "a blocked call fails with EPERM from somewhere that makes no "
            "sense. The fix is a profile that allows that one call, not "
            "`--privileged`."),
        "snippet": (
            "# Turn it off for one container, to confirm the diagnosis only\n"
            "podman run --security-opt seccomp=unconfined myapp\n\n"
            "# Then allow exactly what is needed\n"
            "podman run --security-opt seccomp=/path/to/profile.json myapp\n\n"
            "# Watch what a container calls\n"
            "strace -f -c -p $(podman inspect -f '{{.State.Pid}}' web)"),
        "language": "bash",
        "warning": (
            "`seccomp=unconfined` is a diagnostic step, not a fix. Leaving "
            "it on removes a layer that costs nothing in normal use."),
    },
    {
        "title": "Reading `inspect` without drowning in it",
        "body": (
            "`inspect` returns everything the engine knows, which is far "
            "more than anyone wants at once. The `--format` flag takes a Go "
            "template, and a handful of them answer most questions.\n\n"
            "This is also where you check what a container really got, as "
            "opposed to what the command asked for — the two differ more "
            "often than people expect."),
        "snippet": (
            "docker inspect web --format '{{.State.Status}} "
            "{{.State.ExitCode}}'\n"
            "docker inspect web --format "
            "'{{range $p,$c := .NetworkSettings.Ports}}{{$p}} -> {{$c}}"
            "{{end}}'\n"
            "docker inspect web --format "
            "'{{range .Mounts}}{{.Source}}:{{.Destination}} {{end}}'\n"
            "docker inspect web --format '{{.HostConfig.Memory}}'\n"
            "docker inspect web --format "
            "'{{json .Config.Env}}' | python3 -m json.tool"),
        "language": "bash",
        "tip": (
            "`{{json .}}` piped into `jq` or `python3 -m json.tool` beats "
            "guessing at field names; every kontainy page shows the same "
            "JSON under a Raw tab."),
    },
]
