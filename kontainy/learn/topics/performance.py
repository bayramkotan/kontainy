"""Performance — measure first; most container slowness has one of six causes."""

TOPICS = [
    {
        "title": "Measure before you tune",
        "body": (
            "Container performance problems are nearly always one of six "
            "things: the storage driver fell back to vfs, a cgroup limit is "
            "throttling, the filesystem crosses a virtualisation boundary, "
            "the network stack is userspace, the image is enormous, or the "
            "application was always this slow.\n\n"
            "Each is visible with a command. Guessing costs more than "
            "looking."),
        "snippet": (
            "docker stats --no-stream\n"
            "docker info --format 'driver={{.Driver}} runtime="
            "{{.DefaultRuntime}}'\n"
            "podman info --format '{{.Host.NetworkBackend}} "
            "{{.Store.GraphDriverName}}'\n"
            "cat /sys/fs/cgroup/cpu.stat        # throttling, counted"),
        "language": "bash",
    },
    {
        "title": "CPU limits throttle, they do not slow gracefully",
        "body": (
            "A CPU limit is a quota per period. When a container uses its "
            "quota, it is stopped until the next period — so a limit of "
            "half a core does not run everything at half speed, it runs at "
            "full speed half the time.\n\n"
            "For latency-sensitive work that is visible as periodic stalls. "
            "`nr_throttled` in cpu.stat is the evidence."),
        "snippet": (
            "docker run --cpus 0.5 myapp\n"
            "cat /sys/fs/cgroup/.../cpu.max      # e.g. '50000 100000'\n"
            "grep -E 'nr_throttled|throttled_usec' "
            "/sys/fs/cgroup/.../cpu.stat\n\n"
            "docker update --cpus 2 web          # live"),
        "language": "bash",
        "rule_id": "RES01",
    },
    {
        "title": "Memory: the limit is a cliff",
        "body": (
            "Crossing a memory limit does not slow anything down: the "
            "kernel kills the process. Exit code 137 with `OOMKilled: true` "
            "is that, and it is distinct from the host running out of "
            "memory.\n\n"
            "Watch the working set before choosing a number, and leave "
            "headroom for page cache — a database with no headroom reads "
            "from disk constantly."),
        "snippet": (
            "docker stats --no-stream --format "
            "'{{.Name}}\\t{{.MemUsage}}\\t{{.MemPerc}}'\n"
            "docker inspect web --format '{{.State.OOMKilled}}'\n"
            "cat /sys/fs/cgroup/.../memory.peak\n\n"
            "dmesg -T | grep -i 'killed process' | tail"),
        "language": "bash",
    },
    {
        "title": "Disk I/O and the storage driver",
        "body": (
            "overlay2 on ext4 or xfs is fast. fuse-overlayfs is userspace "
            "and slower. vfs copies whole layers and is slower again by a "
            "wide margin.\n\n"
            "Data that is written constantly belongs in a volume, not in "
            "the container's writable layer: the layer is copy-on-write, "
            "the volume is a plain directory."),
        "snippet": (
            "docker info --format '{{.Driver}}'\n"
            "docker run --rm -v test:/d alpine dd if=/dev/zero of=/d/f "
            "bs=1M count=512 oflag=direct\n"
            "docker run --rm alpine dd if=/dev/zero of=/f bs=1M count=512 "
            "oflag=direct    # the layer, for comparison"),
        "language": "bash",
        "setting_key": "storage.driver",
    },
    {
        "title": "Bind mounts across a virtual machine boundary",
        "body": (
            "On Docker Desktop and podman machine, a bind mount from the "
            "host crosses a file-sharing layer into the VM. For a few files "
            "it is fine; for node_modules or a large repository it is the "
            "single biggest cost on the machine.\n\n"
            "The fix is to keep the hot data inside the VM: a named volume "
            "for dependencies, and the source bind-mounted read-only."),
        "snippet": (
            "# slow on Desktop\n"
            "docker run -v $PWD:/app node:22 npm ci\n\n"
            "# faster: dependencies in a volume\n"
            "docker run -v $PWD:/app:ro -v node_modules:/app/node_modules "
            "node:22 npm ci\n\n"
            "# and measure\n"
            "time docker run --rm -v $PWD:/app alpine sh -c 'ls -R /app "
            ">/dev/null'"),
        "language": "bash",
    },
    {
        "title": "Network: userspace stacks and published ports",
        "body": (
            "Rootless containers route traffic through pasta or "
            "slirp4netns in userspace. pasta is much faster than "
            "slirp4netns but neither matches a kernel bridge.\n\n"
            "Docker's userland-proxy also adds a hop for published ports; "
            "turning it off makes the kernel do the forwarding, which is "
            "measurably faster and occasionally changes behaviour for "
            "containers talking to their own published port."),
        "snippet": (
            "podman info --format '{{.Host.NetworkBackend}}'\n\n"
            "# daemon.json\n"
            "{\"userland-proxy\": false}\n\n"
            "# a crude but honest comparison\n"
            "docker run --rm --network host alpine wget -qO- localhost:8080 "
            ">/dev/null"),
        "language": "json",
        "setting_key": "userland-proxy",
    },
    {
        "title": "Startup time: what happens before your process runs",
        "body": (
            "Starting a container is pulling (once), creating the "
            "namespaces and cgroup, mounting the layers, and then exec. The "
            "first is network-bound; the rest is milliseconds — unless the "
            "runtime is runc on a large image with many layers.\n\n"
            "crun is faster and lighter than runc, and fewer layers means "
            "less to mount."),
        "snippet": (
            "time docker run --rm alpine true\n"
            "time podman run --rm --runtime crun alpine true\n"
            "time podman run --rm --runtime runc alpine true\n\n"
            "docker image inspect myapp --format "
            "'{{len .RootFS.Layers}} layers'"),
        "language": "bash",
        "setting_key": "containers.runtime",
    },
    {
        "title": "Build speed",
        "body": (
            "Three levers, in order of effect: cache order in the "
            "Dockerfile, a .dockerignore that keeps .git and node_modules "
            "out of the context, and BuildKit cache mounts for package "
            "managers.\n\n"
            "In CI, a registry cache turns a cold runner into a warm one, "
            "which is usually the difference between two minutes and "
            "twenty."),
        "snippet": (
            "du -sh .                      # the context that gets sent\n"
            "docker build --progress=plain . 2>&1 | grep -E 'CACHED|DONE'\n\n"
            "docker buildx build \\\n"
            "  --cache-from type=registry,ref=ghcr.io/me/app:cache \\\n"
            "  --cache-to type=registry,ref=ghcr.io/me/app:cache,mode=max ."),
        "language": "bash",
    },
    {
        "title": "Profiling inside a container",
        "body": (
            "The tools you want are rarely in the image, and installing "
            "them into a running container changes what you are measuring. "
            "Attach a second container to the same namespaces instead.\n\n"
            "perf and eBPF tools need capabilities the container does not "
            "normally have, which is why they usually run on the host "
            "against the container's PID."),
        "snippet": (
            "PID=$(docker inspect -f '{{.State.Pid}}' web)\n"
            "sudo perf top -p $PID\n"
            "sudo strace -f -c -p $PID\n\n"
            "docker run --rm -it --pid=container:web --cap-add=SYS_PTRACE "
            "nicolaka/netshoot"),
        "language": "bash",
    },
    {
        "title": "Virtual machines: the settings that matter",
        "body": (
            "For KVM guests the order is: virtio disks and network, enough "
            "memory that the guest is not swapping, and a CPU model that "
            "exposes the host's features. Cache mode `none` with "
            "`io=native` avoids double caching on the host.\n\n"
            "Hugepages help large, latency-sensitive guests; CPU pinning "
            "helps guests that are otherwise scheduled across sockets."),
        "snippet": (
            "virsh dumpxml lab | grep -E 'driver name|cache|io='\n"
            "virsh dommemstat lab\n"
            "virsh vcpupin lab\n\n"
            "# <driver name='qemu' type='qcow2' cache='none' io='native'/>"),
        "language": "bash",
    },
]
