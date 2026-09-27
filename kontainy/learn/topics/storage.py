"""Storage — where the bytes go, and why the disk filled up."""

TOPICS = [
    {
        "title": "Volume, bind mount, tmpfs",
        "body": (
            "Three ways to get data in and out, with three different "
            "owners. A volume is managed by the engine and is the right "
            "answer for anything that must survive. A bind mount attaches a "
            "path you name — perfect for source code, and the source of "
            "most permission trouble. A tmpfs lives in memory and is gone "
            "when the container stops.\n\n"
            "`--mount` says all of this explicitly; `-v` is shorter and "
            "guesses."),
        "snippet": (
            "docker run -v pgdata:/var/lib/postgresql/data postgres:16\n"
            "docker run -v ./src:/app/src:ro node:22\n"
            "docker run --tmpfs /tmp:rw,noexec,nosuid,size=64m alpine\n\n"
            "# the explicit form\n"
            "docker run --mount type=volume,src=pgdata,dst=/var/lib/"
            "postgresql/data postgres:16"),
        "language": "bash",
        "warning": (
            "`-v ./src:/app` creates a DIRECTORY on the host if the path "
            "does not exist. `--mount` fails instead, which is usually what "
            "you wanted."),
    },
    {
        "title": "Anonymous volumes, and the disk that fills quietly",
        "body": (
            "An image with a VOLUME instruction gets a fresh anonymous "
            "volume every time a container is created without a named one. "
            "The volume outlives the container, and nothing refers to it "
            "afterwards.\n\n"
            "A few weeks of recreating a database container leaves a "
            "directory of unnamed volumes holding real data that nobody can "
            "identify."),
        "snippet": (
            "docker volume ls -f dangling=true\n"
            "docker volume ls --format '{{.Name}}\\t{{.Mountpoint}}' | head\n"
            "du -sh /var/lib/docker/volumes/* | sort -h | tail\n\n"
            "docker volume prune       # removes every unreferenced one"),
        "language": "bash",
        "tip": (
            "Always name the volume of anything that stores state. "
            "kontainy's create dialog does this for you from the image's "
            "own VOLUME list, precisely to avoid this."),
        "rule_id": "DSK01",
    },
    {
        "title": "Where the engine keeps everything",
        "body": (
            "Docker uses /var/lib/docker; rootful Podman /var/lib/"
            "containers; rootless Podman ~/.local/share/containers. That "
            "last one counts against a home quota and is invisible to "
            "anything tidying /var.\n\n"
            "Moving the location is a daemon setting, done with the engine "
            "stopped — copying it while it runs produces a store that looks "
            "fine and is not."),
        "snippet": (
            "docker info --format '{{.DockerRootDir}}'\n"
            "podman info --format '{{.Store.GraphRoot}}'\n\n"
            "# daemon.json\n"
            "{\"data-root\": \"/mnt/big/docker\"}\n\n"
            "sudo systemctl stop docker && sudo rsync -aHAX "
            "/var/lib/docker/ /mnt/big/docker/"),
        "language": "bash",
        "setting_key": "data-root",
    },
    {
        "title": "overlay2 and how a layer is assembled",
        "body": (
            "overlay2 stacks directories: lower layers are read-only, an "
            "upper layer holds changes, and a merged view is what the "
            "container sees. A file modified from a lower layer is copied "
            "up first.\n\n"
            "That copy-up is why changing one byte of a 2 GB file costs 2 "
            "GB of disk, and why a container that rewrites a large file "
            "grows unexpectedly."),
        "snippet": (
            "docker info --format '{{.Driver}}'\n"
            "docker inspect web --format '{{.GraphDriver.Data.UpperDir}}'\n"
            "sudo du -sh $(docker inspect web --format "
            "'{{.GraphDriver.Data.UpperDir}}')\n\n"
            "docker diff web       # what this container changed"),
        "language": "bash",
        "setting_key": "storage.driver",
    },
    {
        "title": "When the driver falls back to vfs",
        "body": (
            "vfs copies every layer instead of stacking them. It is correct "
            "and it is enormously wasteful: an image with ten layers takes "
            "ten times its size.\n\n"
            "The usual cause is a store on a filesystem that cannot do "
            "overlay — ZFS, NFS, eCryptfs — or a rootless setup without "
            "fuse-overlayfs installed."),
        "snippet": (
            "podman info --format '{{.Store.GraphDriverName}}'\n"
            "stat -f -c %T ~/.local/share/containers/storage\n"
            "which fuse-overlayfs\n\n"
            "grep -w overlay /proc/filesystems"),
        "language": "bash",
        "warning": (
            "If `podman info` says vfs, fix that before anything else: "
            "build times and disk use are several times worse than they "
            "need to be."),
    },
    {
        "title": "Backing up a volume properly",
        "body": (
            "A volume is a directory, so a throwaway container with tar "
            "copies it out. The catch is consistency: tarring a running "
            "database copies files mid-write.\n\n"
            "Stop the container, or use the database's own dump tool, and "
            "keep the result somewhere that is not the same disk."),
        "snippet": (
            "docker stop db\n"
            "docker run --rm -v pgdata:/d -v $PWD:/b alpine "
            "tar czf /b/pgdata.tgz -C /d .\n"
            "docker start db\n\n"
            "# or, live and consistent\n"
            "docker exec db pg_dumpall -U postgres | gzip > dump.sql.gz"),
        "language": "bash",
    },
    {
        "title": "Volume drivers and network storage",
        "body": (
            "The local driver is a directory. Other drivers mount NFS, "
            "CIFS or cloud storage as a volume, which is how several hosts "
            "share one dataset.\n\n"
            "Latency changes everything: a database on NFS behaves very "
            "differently from one on local disk, and file locking over the "
            "network is where the surprises live."),
        "snippet": (
            "docker volume create --driver local \\\n"
            "  --opt type=nfs --opt o=addr=10.0.0.5,rw \\\n"
            "  --opt device=:/export/data nfsdata\n\n"
            "docker volume inspect nfsdata"),
        "language": "bash",
    },
    {
        "title": "Permissions on a bind mount",
        "body": (
            "Ownership is by UID, and the UID inside the container has "
            "nothing to do with the name on either side. Three fixes, in "
            "order of preference: run as the owner with `--user`, map your "
            "own UID with `--userns=keep-id` under rootless Podman, or "
            "change the ownership on the host.\n\n"
            "On a labelled system add `:Z` as well, or every read is "
            "refused."),
        "snippet": (
            "docker run --user $(id -u):$(id -g) -v $PWD:/work alpine "
            "touch /work/f\n"
            "podman run --userns=keep-id -v $HOME/data:/data alpine ls -l "
            "/data\n"
            "podman unshare chown -R 1000:1000 ./data"),
        "language": "bash",
    },
    {
        "title": "Logs are storage too",
        "body": (
            "With the default json-file driver and no limits, container "
            "logs grow until the partition is full — and they are not in "
            "/var/log, so log rotation never sees them.\n\n"
            "Two keys in daemon.json fix it for everything, and journald "
            "hands the problem to systemd which already solved it."),
        "snippet": (
            "du -sh /var/lib/docker/containers/*/*-json.log | sort -h | tail\n\n"
            "{\"log-driver\": \"json-file\",\n"
            " \"log-opts\": {\"max-size\": \"10m\", \"max-file\": \"3\"}}\n\n"
            "# truncate one, right now\n"
            "sudo truncate -s 0 $(docker inspect --format='{{.LogPath}}' web)"),
        "language": "json",
        "setting_key": "log-opts.max-size",
        "rule_id": "DSK01",
    },
    {
        "title": "The build cache",
        "body": (
            "BuildKit keeps its cache separately from images, and "
            "`image prune` does not touch it. On a machine that builds "
            "often it becomes the largest single consumer of disk.\n\n"
            "Prune it with a size cap rather than emptying it: the point of "
            "a cache is to still be there tomorrow."),
        "snippet": (
            "docker system df -v | head -20\n"
            "docker builder prune --keep-storage 10GB\n"
            "docker buildx du --verbose | tail\n\n"
            "podman system df"),
        "language": "bash",
    },
    {
        "title": "Disk quotas per container",
        "body": (
            "A container's writable layer is unbounded by default: a "
            "runaway log inside the container fills the host. `--storage-opt "
            "size=` caps it, on the drivers that support quotas — overlay2 "
            "on xfs with pquota, or btrfs.\n\n"
            "Where quotas are unavailable, the practical substitute is a "
            "read-only root filesystem with a sized tmpfs."),
        "snippet": (
            "docker run --storage-opt size=10G myapp        # xfs pquota\n"
            "docker run --read-only --tmpfs /tmp:size=100m myapp\n\n"
            "mount | grep -w /var/lib/docker"),
        "language": "bash",
    },
    {
        "title": "Reading `system df` and acting on it",
        "body": (
            "`system df` splits usage into images, containers, volumes and "
            "the build cache, with a reclaimable column. That column is the "
            "one to read: it is what would be freed without touching "
            "anything in use.\n\n"
            "The order of cleanup that rarely surprises anyone: build "
            "cache, dangling images, exited containers, and only then "
            "volumes — with the list read first."),
        "snippet": (
            "docker system df\n"
            "docker system df -v | less\n\n"
            "docker builder prune -f\n"
            "docker image prune -f\n"
            "docker container prune -f\n"
            "docker volume ls -f dangling=true      # read before removing"),
        "language": "bash",
        "tip": (
            "kontainy's Remove stopped names every container it will remove "
            "before removing any, and its Diagnostics page carries the "
            "disk rule that finds unbounded logs."),
    },
]
