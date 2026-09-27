"""Podman — what is different when there is no daemon."""

TOPICS = [
    {
        "title": "No daemon — what that actually changes",
        "body": (
            "With Docker, the `docker` command sends a request to a daemon; "
            "containers are that daemon's children and the daemon runs as "
            "root.\n\n"
            "Podman has no daemon. `podman run` starts the container "
            "DIRECTLY, as a child of your own process. Three consequences "
            "follow:\n\n"
            "• root is not required — rootless is the normal case\n"
            "• there is no single process whose failure takes everything "
            "with it\n"
            "• but there is also nothing in the background to bring "
            "containers back: `--restart=always` does NOT survive a reboot"),
        "snippet": (
            "# Docker: client -> daemon -> container\n"
            "systemctl status docker\n\n"
            "# Podman: straight there\n"
            "podman run -d --name web nginx\n"
            "pstree -p $$ | grep conmon"),
        "language": "bash",
        "warning": (
            "For anything that must come back after a reboot, use Quadlet "
            "or a systemd unit. `--restart=always` lasts as long as the "
            "session, and with lingering disabled it does not even last "
            "that."),
        "rule_id": "POD02",
    },
    {
        "title": "How rootless really works",
        "body": (
            "Rootless Podman uses a user namespace. Root inside the "
            "container (UID 0) maps to the start of a range of UIDs "
            "allocated to you on the host.\n\n"
            "That range is declared in /etc/subuid and /etc/subgid. With no "
            "entry, nothing works, and the message is "
            "`potentially insufficient UIDs or GIDs available in user "
            "namespace` — which names the cause without naming the file."),
        "snippet": (
            "# Do you have a range?\n"
            "grep $USER /etc/subuid /etc/subgid\n\n"
            "# See the mapping in force\n"
            "podman unshare cat /proc/self/uid_map\n\n"
            "# Files in your home showing as 'nobody'?\n"
            "podman run --userns=keep-id -v $HOME/data:/data alpine ls -l "
            "/data"),
        "language": "bash",
        "table": {
            "headers": ["userns mode", "What it does", "When"],
            "rows": [
                ["`host`", "no mapping (the default)", "general use"],
                ["`keep-id`", "your own UID stays itself",
                 "bind mounts from home"],
                ["`nomap`", "no host UID is mapped at all",
                 "the strictest isolation"],
                ["`auto`", "a fresh range per container", "multi-tenant"],
            ]},
        "tip": (
            "After changing the range, `podman system migrate` is required; "
            "existing containers otherwise keep the old mapping and their "
            "files become unreadable."),
        "rule_id": "POD03",
        "setting_key": "containers.userns",
    },
    {
        "title": "Pods — the idea Kubernetes took",
        "body": (
            "A pod is a group of containers that share namespaces. "
            "Containers in one pod reach each other over `localhost`, "
            "exactly as in Kubernetes, because that is where the concept "
            "comes from.\n\n"
            "An invisible infra container holds the pod's network "
            "namespace, so the network survives while the real containers "
            "come and go."),
        "snippet": (
            "podman pod create --name app -p 8080:80\n"
            "podman run -d --pod app --name web nginx\n"
            "podman run -d --pod app --name api my-api\n\n"
            "# web reaches the api at localhost:3000\n"
            "podman pod ps\n"
            "podman generate kube app > app.yaml   # take it to Kubernetes"),
        "language": "bash",
        "note": (
            "Ports are published at the POD level, not per container: a "
            "`-p` flag on a container that joins a pod is ignored."),
    },
    {
        "title": "The Docker compatibility socket",
        "body": (
            "Podman can answer the Docker API, which is how tools that only "
            "speak Docker — testcontainers, IDE plugins, some CI runners — "
            "work against it.\n\n"
            "It is a socket activated systemd unit: nothing runs until "
            "something connects, and then a short-lived service answers. "
            "Point DOCKER_HOST at it and the tool cannot tell the "
            "difference."),
        "snippet": (
            "systemctl --user enable --now podman.socket\n"
            "export DOCKER_HOST=unix://$XDG_RUNTIME_DIR/podman/podman.sock\n\n"
            "docker ps        # the docker CLI, talking to podman\n"
            "curl --unix-socket $XDG_RUNTIME_DIR/podman/podman.sock "
            "http://d/v1.41/version"),
        "language": "bash",
        "warning": (
            "Rootful and rootless sockets are different paths and different "
            "worlds: /run/podman/podman.sock is not the same store as the "
            "one in your XDG_RUNTIME_DIR."),
        "rule_id": "POD01",
    },
    {
        "title": "containers.conf: where Podman's defaults live",
        "body": (
            "Podman reads three layers of configuration, each overriding "
            "the last: the package default in /usr/share/containers, the "
            "system file in /etc/containers, and yours in "
            "~/.config/containers.\n\n"
            "This is where the defaults that surprise people are set — the "
            "runtime, the cgroup manager, the default capabilities, the DNS "
            "servers a new network gets."),
        "snippet": (
            "# Which files are actually being read?\n"
            "podman info --format '{{.Store.ConfigFile}}'\n"
            "ls /usr/share/containers/containers.conf "
            "/etc/containers/containers.conf "
            "~/.config/containers/containers.conf 2>/dev/null\n\n"
            "# A minimal override of your own\n"
            "mkdir -p ~/.config/containers\n"
            "printf '[containers]\\nlog_driver = \"journald\"\\n' > "
            "~/.config/containers/containers.conf"),
        "language": "toml",
        "tip": (
            "kontainy's catalogue explains these keys one by one, with what "
            "breaks when each is wrong, and writes them with a backup."),
        "setting_key": "containers.log_driver",
    },
    {
        "title": "Quadlet: containers as systemd units, properly",
        "body": (
            "`podman generate systemd` is deprecated. Quadlet is the "
            "replacement: you write a small .container file, systemd "
            "generates the unit at boot, and the container becomes an "
            "ordinary service with dependencies, restarts and logs in the "
            "journal.\n\n"
            "For a user service, the file goes in "
            "~/.config/containers/systemd/ and lingering must be enabled if "
            "it should run without you logged in."),
        "snippet": (
            "# ~/.config/containers/systemd/web.container\n"
            "[Unit]\n"
            "Description=nginx\n\n"
            "[Container]\n"
            "Image=docker.io/library/nginx:alpine\n"
            "PublishPort=8080:80\n"
            "Volume=web-data:/usr/share/nginx/html:Z\n\n"
            "[Service]\n"
            "Restart=always\n\n"
            "[Install]\n"
            "WantedBy=default.target"),
        "language": "ini",
        "note": (
            "After writing the file: `systemctl --user daemon-reload` and "
            "`systemctl --user start web`. The unit name is the file name "
            "without its extension."),
        "rule_id": "POD02",
    },
    {
        "title": "podman machine: Podman off Linux",
        "body": (
            "On Windows and macOS there is no Linux kernel, so Podman runs "
            "its containers inside a virtual machine it manages itself — "
            "WSL on Windows, Apple's hypervisor on macOS.\n\n"
            "`podman machine set` changes CPU, memory and disk. The machine "
            "must be stopped for most of them, and `podman machine reset` "
            "removes everything including the images."),
        "snippet": (
            "podman machine init --cpus 4 --memory 8192 --disk-size 60\n"
            "podman machine start\n"
            "podman machine list\n"
            "podman machine ssh\n\n"
            "podman machine stop && podman machine set --memory 12288"),
        "language": "bash",
    },
    {
        "title": "Auto-updating containers",
        "body": (
            "With a label on the container and a timer enabled, Podman "
            "checks the registry, pulls a newer image and restarts the "
            "unit — and rolls back automatically if the new one fails its "
            "healthcheck.\n\n"
            "It only works for containers managed by systemd, which is one "
            "more reason to write them as Quadlet units."),
        "snippet": (
            "# in the .container file\n"
            "Label=io.containers.autoupdate=registry\n\n"
            "systemctl --user enable --now podman-auto-update.timer\n"
            "podman auto-update --dry-run\n"
            "podman auto-update"),
        "language": "bash",
    },
    {
        "title": "Building without a daemon: Buildah",
        "body": (
            "`podman build` is Buildah underneath. Buildah on its own goes "
            "further: it can build an image step by step with shell "
            "commands, with no Dockerfile at all, and it works rootless in "
            "CI where a Docker daemon would need privileges.\n\n"
            "The result is an ordinary OCI image that any engine can run."),
        "snippet": (
            "ctr=$(buildah from docker.io/library/alpine:3.20)\n"
            "buildah run $ctr -- apk add --no-cache curl\n"
            "buildah config --entrypoint '[\"curl\"]' $ctr\n"
            "buildah commit $ctr my-curl:1\n"
            "buildah push my-curl:1 docker://ghcr.io/me/my-curl:1"),
        "language": "bash",
    },
    {
        "title": "Moving images with skopeo",
        "body": (
            "skopeo copies images between registries, local stores and tar "
            "files without a running engine and without pulling anything "
            "you did not ask for. It also inspects a remote image — its "
            "tags, its digest, its architectures — before downloading "
            "hundreds of megabytes."),
        "snippet": (
            "skopeo inspect docker://docker.io/library/nginx:alpine | head\n"
            "skopeo list-tags docker://docker.io/library/postgres | tail\n\n"
            "skopeo copy docker://nginx:alpine "
            "containers-storage:localhost/nginx:alpine\n"
            "skopeo copy --all docker://nginx:alpine "
            "oci-archive:nginx.tar"),
        "language": "bash",
    },
    {
        "title": "Running Kubernetes YAML locally",
        "body": (
            "`podman kube play` takes a pod or deployment manifest and runs "
            "it on this machine as a pod. `podman kube generate` goes the "
            "other way, from what is running to YAML.\n\n"
            "It is not a cluster: no scheduler, no services, no scaling. "
            "What it gives is a way to run the same manifest on a laptop "
            "that the cluster will run later."),
        "snippet": (
            "podman kube generate app > app.yaml\n"
            "podman kube play app.yaml\n"
            "podman kube down app.yaml\n\n"
            "# as a systemd unit: app.kube next to your .container files"),
        "language": "bash",
    },
    {
        "title": "Volumes, and the ones Podman mounts for you",
        "body": (
            "Named volumes work as they do elsewhere. What is different is "
            "the SELinux labelling and the user namespace: a bind mount "
            "needs `:Z` on a labelled system, and `--userns=keep-id` when "
            "the files belong to you.\n\n"
            "`podman volume export` and `import` move a volume without the "
            "throwaway-container trick."),
        "snippet": (
            "podman volume create pgdata\n"
            "podman volume inspect pgdata --format '{{.Mountpoint}}'\n"
            "podman volume export pgdata -o pgdata.tar\n"
            "podman volume import pgdata pgdata.tar\n\n"
            "podman run -v ./src:/app:ro,Z --userns=keep-id node:22"),
        "language": "bash",
    },
    {
        "title": "Networks: netavark and aardvark-dns",
        "body": (
            "Podman 4 replaced CNI with netavark for networking and "
            "aardvark-dns for name resolution between containers. Both are "
            "written for this job and are the default on new installs.\n\n"
            "A machine upgraded from an older Podman may still be on CNI, "
            "which is worth knowing when a network behaves differently from "
            "the documentation."),
        "snippet": (
            "podman info --format '{{.Host.NetworkBackend}}'\n"
            "podman network create app\n"
            "podman network inspect app\n\n"
            "# migrate an old install\n"
            "podman system reset   # destructive: images and containers go"),
        "language": "bash",
    },
    {
        "title": "Health checks and what Podman does with them",
        "body": (
            "Podman runs healthchecks with a systemd timer per container, "
            "and unlike Docker it can act on the result: "
            "`--health-on-failure=restart` restarts the container itself, "
            "with no orchestrator involved.\n\n"
            "That covers most of what people install a supervisor for."),
        "snippet": (
            "podman run -d --name web \\\n"
            "  --health-cmd 'curl -f http://localhost/ || exit 1' \\\n"
            "  --health-interval 30s --health-retries 3 \\\n"
            "  --health-on-failure restart nginx\n\n"
            "podman healthcheck run web\n"
            "podman inspect web --format '{{.State.Health.Status}}'"),
        "language": "bash",
    },
    {
        "title": "Secrets",
        "body": (
            "Podman stores secrets outside the image and mounts them as "
            "files at /run/secrets, so they are not in `history`, not in "
            "`inspect` and not in an environment variable that every child "
            "process inherits.\n\n"
            "For a cluster the driver can be an external store; locally the "
            "file driver is enough."),
        "snippet": (
            "printf 's3cr3t' | podman secret create db-password -\n"
            "podman secret list\n"
            "podman run --secret db-password postgres:16\n"
            "# inside: /run/secrets/db-password\n\n"
            "podman run --secret db-password,type=env,target=PGPASSWORD "
            "postgres:16"),
        "language": "bash",
    },
    {
        "title": "System pruning and where rootless keeps things",
        "body": (
            "Rootless Podman stores everything under "
            "~/.local/share/containers, which means it counts against a "
            "home directory quota and is not cleaned by anything that tidies "
            "/var.\n\n"
            "`podman system df` shows the split, and `podman system reset` "
            "is the nuclear option — it removes images, containers, volumes "
            "and networks in one go."),
        "snippet": (
            "podman system df -v\n"
            "du -sh ~/.local/share/containers/storage\n\n"
            "podman system prune --volumes\n"
            "podman image prune -a\n"
            "podman system reset      # everything, no undo"),
        "language": "bash",
        "rule_id": "DSK01",
    },
    {
        "title": "Rootful Podman, and when it is the answer",
        "body": (
            "Some things genuinely need root: binding a low port without a "
            "sysctl, macvlan on a physical interface, devices, and a few "
            "storage drivers.\n\n"
            "`sudo podman` is a separate store with separate images and "
            "containers. Running one command with sudo and the next without "
            "is why a container \"disappears\"."),
        "snippet": (
            "podman info --format '{{.Store.GraphRoot}}'\n"
            "sudo podman info --format '{{.Store.GraphRoot}}'\n\n"
            "sudo podman ps -a\n"
            "systemctl enable --now podman.socket   # the rootful socket"),
        "language": "bash",
    },
    {
        "title": "Podman Desktop and the API for other tools",
        "body": (
            "Podman Desktop is a graphical front end that speaks to the "
            "same engine; nothing it does is unavailable from the command "
            "line. Tools that expect Docker talk to Podman through the "
            "compatibility socket.\n\n"
            "The rule that saves time: whatever a graphical tool did, there "
            "is a command that does the same, and knowing it is what makes "
            "the result reproducible."),
        "snippet": (
            "systemctl --user status podman.socket\n"
            "export DOCKER_HOST=unix://$XDG_RUNTIME_DIR/podman/podman.sock\n"
            "docker ps        # the docker CLI against podman\n\n"
            "podman --log-level=debug ps 2>&1 | head"),
        "language": "bash",
        "tip": (
            "kontainy shows the command for every button precisely so the "
            "graphical route teaches the command-line one."),
    },
]
