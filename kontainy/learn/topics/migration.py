"""Migration & Interop — moving between engines, hosts and formats."""

TOPICS = [
    {
        "title": "Docker to Podman: what is the same and what is not",
        "body": (
            "The command line is deliberately compatible: `alias "
            "docker=podman` carries most people through a working day. The "
            "differences are architectural rather than syntactic.\n\n"
            "No daemon means `--restart=always` does not survive a reboot. "
            "Rootless by default means ports below 1024 and some volume "
            "permissions behave differently. And the default capability set "
            "is smaller, so an image that assumed Docker's may need one "
            "added back."),
        "table": {
            "headers": ["Docker", "Podman", "Note"],
            "rows": [
                ["daemon", "none", "conmon per container"],
                ["root by default", "rootless by default", "user namespace"],
                ["`--restart=always`", "Quadlet or systemd",
                 "reboot survival"],
                ["`docker-compose`", "compose over the API socket",
                 "or podman-compose"],
                ["short names resolve to Hub", "search list",
                 "`short-name-mode`"],
            ]},
        "snippet": (
            "podman --version\n"
            "alias docker=podman\n"
            "podman run --rm docker.io/library/alpine echo works"),
        "language": "bash",
    },
    {
        "title": "Moving images without a registry",
        "body": (
            "`save` and `load` move an image as a tar file, layers and all. "
            "`export` and `import` move a container's filesystem and lose "
            "the history, the entrypoint and the environment — which is why "
            "an imported image often starts and immediately exits.\n\n"
            "skopeo copies between stores and registries without pulling "
            "anything into a local engine at all."),
        "snippet": (
            "docker save myapp:1.4 -o myapp.tar\n"
            "podman load -i myapp.tar            # the other engine reads it\n\n"
            "skopeo copy docker-daemon:myapp:1.4 "
            "containers-storage:myapp:1.4\n"
            "skopeo copy docker://nginx:alpine "
            "oci-archive:nginx.tar"),
        "language": "bash",
        "warning": (
            "`export` is for a container, `save` for an image. Using export "
            "where save was meant is the usual cause of \"it works on the "
            "old machine\"."),
    },
    {
        "title": "Moving volumes between machines",
        "body": (
            "A volume is a directory, so moving it is a tar in a throwaway "
            "container on each end. The subtlety is consistency: a database "
            "should be stopped, or dumped with its own tool, before its "
            "files are copied.\n\n"
            "For a live system, use the database's dump and restore; for "
            "everything else, the tar is fine."),
        "snippet": (
            "# on the old machine\n"
            "docker run --rm -v pgdata:/d -v $PWD:/b alpine "
            "tar czf /b/pgdata.tgz -C /d .\n"
            "scp pgdata.tgz new-host:\n\n"
            "# on the new one\n"
            "docker volume create pgdata\n"
            "docker run --rm -v pgdata:/d -v $PWD:/b alpine "
            "tar xzf /b/pgdata.tgz -C /d"),
        "language": "bash",
    },
    {
        "title": "Disk images between hypervisors",
        "body": (
            "`qemu-img convert` reads and writes every common format, so "
            "the file itself is never the hard part.\n\n"
            "The guest is. A Windows machine moved from VMware to KVM "
            "without virtio drivers blue-screens on boot; a Linux guest "
            "usually survives because the drivers are in the kernel. "
            "virt-v2v does the conversion AND fixes the drivers, which "
            "qemu-img cannot."),
        "table": {
            "headers": ["From", "To", "Tool"],
            "rows": [
                ["`.vmdk` (VMware)", "`.qcow2`", "`qemu-img convert -O qcow2`"],
                ["`.vdi` (VirtualBox)", "`.qcow2`", "`qemu-img` or "
                                                     "`VBoxManage clonemedium`"],
                ["`.vhdx` (Hyper-V)", "`.qcow2`", "`qemu-img convert`"],
                ["`.qcow2`", "`.vhdx`", "`qemu-img convert -O vhdx`"],
                ["a whole machine", "libvirt", "`virt-v2v`"],
            ]},
        "snippet": (
            "qemu-img info disk.vmdk\n"
            "qemu-img convert -p -O qcow2 disk.vmdk disk.qcow2\n"
            "virt-v2v -i ova machine.ova -o libvirt -os default"),
        "language": "bash",
    },
    {
        "title": "WSL as a way in and out",
        "body": (
            "A WSL distribution exports to a tar and imports from one, "
            "which makes it both a backup and a way to move a whole "
            "development environment to another Windows machine.\n\n"
            "The same tar is a rootfs: it can become a container image, "
            "which is the quickest route from \"my WSL setup\" to something "
            "reproducible."),
        "snippet": (
            "wsl --export Ubuntu-24.04 D:\\backup\\ubuntu.tar\n"
            "wsl --import Ubuntu-copy D:\\wsl\\copy D:\\backup\\ubuntu.tar\n\n"
            "# and into a container image\n"
            "docker import D:\\backup\\ubuntu.tar my-wsl:1"),
        "language": "bash",
    },
    {
        "title": "Docker Desktop leftovers",
        "body": (
            "Removing Docker Desktop leaves three things behind: the "
            "contexts it created, the CLI plugins in ~/.docker/cli-plugins, "
            "and the large disk image of its virtual machine.\n\n"
            "The contexts are the confusing ones — `docker` keeps pointing "
            "at a socket that no longer exists, with an error that does not "
            "mention Desktop at all."),
        "snippet": (
            "docker context ls\n"
            "docker context use default\n"
            "docker context rm desktop-linux\n\n"
            "ls ~/.docker/cli-plugins\n"
            "du -sh ~/.docker/desktop 2>/dev/null"),
        "language": "bash",
        "rule_id": "CTX01",
    },
    {
        "title": "CI: the same image, built once",
        "body": (
            "The habit worth keeping is to build once, tag by digest and "
            "promote the same artefact — rather than rebuilding per "
            "environment and hoping the results match.\n\n"
            "In CI, `docker/build-push-action` or a plain buildx call with "
            "a registry cache gives cache reuse between runs, which is "
            "usually the difference between a two-minute and a "
            "twenty-minute pipeline."),
        "snippet": (
            "docker buildx build \\\n"
            "  --platform linux/amd64,linux/arm64 \\\n"
            "  --cache-from type=registry,ref=ghcr.io/me/app:cache \\\n"
            "  --cache-to   type=registry,ref=ghcr.io/me/app:cache,mode=max \\\n"
            "  -t ghcr.io/me/app:$GIT_SHA --push ."),
        "language": "bash",
        "tip": (
            "Podman and Buildah run rootless in CI, which is why many "
            "pipelines use them instead of a privileged Docker daemon."),
    },
    {
        "title": "Rootful to rootless, on the same machine",
        "body": (
            "The two are separate stores: rootless Podman cannot see images "
            "or containers created with sudo, and copying the directory "
            "does not work because the UIDs differ.\n\n"
            "The supported route is to move images through a tar or a "
            "registry and recreate the containers, which is also a good "
            "moment to write them as Quadlet units."),
        "snippet": (
            "sudo podman save myapp:1.4 -o /tmp/myapp.tar\n"
            "podman load -i /tmp/myapp.tar\n\n"
            "sudo podman info --format '{{.Store.GraphRoot}}'\n"
            "podman info --format '{{.Store.GraphRoot}}'\n\n"
            "grep $USER /etc/subuid /etc/subgid   # needed for rootless"),
        "language": "bash",
        "rule_id": "POD03",
    },
]
