"""Docker — the architecture, the flags, and the parts that surprise people."""

TOPICS = [
    {
        "title": "Client, daemon, containerd, runc",
        "body": (
            "`docker` is a client. It speaks HTTP to dockerd over a socket; "
            "dockerd asks containerd to manage the container's lifecycle; "
            "containerd starts a shim which calls runc, which does the "
            "actual namespace and cgroup work and then execs your process.\n\n"
            "The shim is why containers survive a daemon restart: their "
            "parent is the shim, not dockerd."),
        "diagram": (
            "  docker ──socket──▶ dockerd ──▶ containerd ──▶ shim ──▶ runc\n"
            "                                                  │\n"
            "                                                  └─▶ your process"),
        "snippet": (
            "systemctl status docker containerd\n"
            "docker info --format '{{.DefaultRuntime}} {{.ContainerdCommit."
            "ID}}'\n"
            "ps -ef | grep containerd-shim | head"),
        "language": "bash",
    },
    {
        "title": "daemon.json: where the daemon's own settings live",
        "body": (
            "/etc/docker/daemon.json holds everything that belongs to the "
            "daemon rather than to one container: the storage driver, log "
            "limits, registry mirrors, default address pools, the "
            "cgroup driver.\n\n"
            "It is JSON, so a trailing comma stops the daemon from "
            "starting; and most keys only take effect on restart."),
        "snippet": (
            "{\n"
            "  \"log-driver\": \"json-file\",\n"
            "  \"log-opts\": {\"max-size\": \"10m\", \"max-file\": \"3\"},\n"
            "  \"storage-driver\": \"overlay2\",\n"
            "  \"default-address-pools\": [\n"
            "    {\"base\": \"10.200.0.0/16\", \"size\": 24}\n"
            "  ]\n"
            "}"),
        "language": "json",
        "warning": (
            "Check it before restarting: `dockerd --validate "
            "--config-file /etc/docker/daemon.json`. A daemon that will not "
            "start takes every container with it."),
        "setting_key": "log-opts.max-size",
    },
    {
        "title": "Contexts: one CLI, several engines",
        "body": (
            "A context names one endpoint — the local daemon, Docker "
            "Desktop's VM, a remote host over SSH. The active one is where "
            "every command goes.\n\n"
            "A context over SSH needs no daemon port open: the client tunnels "
            "to the remote socket. That is the safe way to manage a server, "
            "and the reason exposing 2375 is almost never necessary."),
        "snippet": (
            "docker context create prod --docker "
            "host=ssh://deploy@server.example\n"
            "docker context use prod\n"
            "docker context ls\n\n"
            "docker --context default ps      # one command elsewhere"),
        "language": "bash",
        "warning": (
            "While `DOCKER_HOST` is set, the context is ignored and "
            "`context use` changes nothing while reporting success."),
        "rule_id": "CTX01",
    },
    {
        "title": "The run flags that matter, in one place",
        "body": (
            "Most of `docker run` is five decisions: what to publish, what "
            "to mount, what to set, how much it may use, and what happens "
            "when it stops."),
        "table": {
            "headers": ["Flag", "Decides", "Note"],
            "rows": [
                ["`-d`", "run in the background", "without it, Ctrl+C stops it"],
                ["`-p H:C`", "publish a port", "host first"],
                ["`-v NAME:/path`", "volume or bind mount", "`:ro` when it should not write"],
                ["`-e K=V`", "an environment variable", "`--env-file` for many"],
                ["`--memory`, `--cpus`", "limits", "not set by default"],
                ["`--restart`", "what happens after a crash or reboot", "`unless-stopped` is usually right"],
                ["`--rm`", "delete on exit", "for anything temporary"],
                ["`--name`", "a name you can type", "otherwise a random one"],
            ]},
        "snippet": (
            "docker run -d --name api \\\n"
            "  -p 127.0.0.1:3000:3000 \\\n"
            "  -v api-data:/data \\\n"
            "  --env-file .env \\\n"
            "  --memory 512m --cpus 1.5 \\\n"
            "  --restart unless-stopped \\\n"
            "  myapi:1.4"),
        "language": "bash",
    },
    {
        "title": "restart policies, and what survives a reboot",
        "body": (
            "`no` is the default. `on-failure[:n]` restarts only on a "
            "non-zero exit. `always` restarts whatever happened, including "
            "after a reboot — and also restarts a container you stopped by "
            "hand once the daemon restarts. `unless-stopped` is `always` "
            "except that it remembers you stopped it.\n\n"
            "None of them helps if the daemon itself is not enabled at "
            "boot."),
        "snippet": (
            "docker update --restart unless-stopped web\n"
            "docker inspect web --format '{{.HostConfig.RestartPolicy.Name}}'\n"
            "systemctl is-enabled docker"),
        "language": "bash",
        "tip": (
            "`unless-stopped` is the right default for a service you run on "
            "your own machine; `always` is the one that keeps resurrecting "
            "something you deliberately stopped."),
    },
    {
        "title": "Images, tags and digests",
        "body": (
            "A tag is a moving pointer; a digest names one exact image. "
            "`docker pull nginx:1.27` today and tomorrow may give different "
            "bytes, and nothing warns you.\n\n"
            "For anything reproducible — a base image in a Dockerfile, a "
            "deployment — pin the digest. For local work, tags are fine and "
            "far more readable."),
        "snippet": (
            "docker images --digests nginx\n"
            "docker inspect nginx:alpine --format '{{index .RepoDigests 0}}'\n\n"
            "docker pull nginx@sha256:4ba4...\n"
            "docker image ls --filter dangling=true    # untagged leftovers"),
        "language": "bash",
    },
    {
        "title": "Writing a Dockerfile that caches well",
        "body": (
            "Each instruction is a layer, and a layer is rebuilt when its "
            "inputs change — together with every layer after it. So the "
            "order decides the speed of every later build.\n\n"
            "Copy the dependency manifest, install dependencies, and only "
            "then copy the source. A code change then rebuilds one layer "
            "instead of reinstalling the world."),
        "snippet": (
            "FROM node:22-slim\n"
            "WORKDIR /app\n\n"
            "COPY package*.json ./\n"
            "RUN npm ci --omit=dev        # cached until the manifest changes\n\n"
            "COPY . .                     # only this rebuilds on a code change\n"
            "USER node\n"
            "CMD [\"node\", \"server.js\"]"),
        "language": "bash",
        "tip": (
            "`docker build --progress=plain` shows which steps were cached "
            "and which were rebuilt — reading beats guessing."),
    },
    {
        "title": "Multi-stage builds",
        "body": (
            "Build tools do not belong in the image you ship. A multi-stage "
            "build compiles in one stage and copies only the result into a "
            "small final stage.\n\n"
            "It also removes secrets properly: anything in a discarded "
            "stage is not in the final image at all, whereas a file deleted "
            "in a later layer is still in the earlier one."),
        "snippet": (
            "FROM golang:1.23 AS build\n"
            "WORKDIR /src\n"
            "COPY . .\n"
            "RUN CGO_ENABLED=0 go build -o /app ./cmd/server\n\n"
            "FROM gcr.io/distroless/static\n"
            "COPY --from=build /app /app\n"
            "USER nonroot\n"
            "ENTRYPOINT [\"/app\"]"),
        "language": "bash",
        "note": (
            "`--target build` stops at a named stage, which is how you get "
            "a debug image with the toolchain still in it."),
    },
    {
        "title": "BuildKit: what changed",
        "body": (
            "BuildKit is the default builder in current Docker. It runs "
            "independent stages in parallel, skips stages nothing needs, "
            "and adds mounts that keep caches and secrets out of layers.\n\n"
            "`--mount=type=cache` keeps a package cache between builds "
            "without shipping it. `--mount=type=secret` gives a file to one "
            "RUN step and leaves no trace in the image."),
        "snippet": (
            "# syntax=docker/dockerfile:1.7\n"
            "RUN --mount=type=cache,target=/root/.cache/pip \\\n"
            "    pip install -r requirements.txt\n\n"
            "RUN --mount=type=secret,id=npmrc,target=/root/.npmrc \\\n"
            "    npm ci\n\n"
            "# docker build --secret id=npmrc,src=$HOME/.npmrc ."),
        "language": "bash",
        "warning": (
            "`ARG` and `ENV` are NOT secrets: both are visible in "
            "`docker history`. Build secrets exist because of that."),
    },
    {
        "title": ".dockerignore, and why the build is slow before it starts",
        "body": (
            "The build context is everything in the directory, sent to the "
            "builder before the first instruction runs. With .git and "
            "node_modules included, that is hundreds of megabytes copied "
            "for nothing every time.\n\n"
            "It also changes correctness: a stray .env in the context can "
            "be copied by `COPY . .` into the image."),
        "snippet": (
            ".git\n"
            "node_modules\n"
            "__pycache__\n"
            "*.log\n"
            ".env\n"
            "dist\n"
            "**/.terraform"),
        "language": "bash",
        "tip": (
            "`du -sh .` next to the first line of build output tells you "
            "immediately whether this is your problem."),
    },
    {
        "title": "Networks: bridge, host, none, macvlan",
        "body": (
            "The default bridge gives addresses and NAT but no name "
            "resolution. A user-defined bridge adds DNS between its "
            "containers, which is why it is the right default for anything "
            "with more than one part.\n\n"
            "`host` removes the network namespace entirely — fast, and no "
            "isolation. `macvlan` gives the container its own MAC and an "
            "address on your LAN, as if it were another machine."),
        "snippet": (
            "docker network create app\n"
            "docker network create -d macvlan \\\n"
            "  --subnet 192.168.1.0/24 --gateway 192.168.1.1 \\\n"
            "  -o parent=eth0 lan\n\n"
            "docker network inspect app --format "
            "'{{range .Containers}}{{.Name}} {{end}}'"),
        "language": "bash",
        "rule_id": "NET01",
    },
    {
        "title": "Volumes, and moving data between machines",
        "body": (
            "A named volume is a directory the engine owns. You rarely need "
            "its path, but you do need to back it up, and the way to do "
            "that is a throwaway container that mounts it.\n\n"
            "The same trick restores it elsewhere, which is the simplest "
            "migration there is."),
        "snippet": (
            "# Back up\n"
            "docker run --rm -v pgdata:/data -v $PWD:/backup alpine \\\n"
            "  tar czf /backup/pgdata.tar.gz -C /data .\n\n"
            "# Restore on another machine\n"
            "docker volume create pgdata\n"
            "docker run --rm -v pgdata:/data -v $PWD:/backup alpine \\\n"
            "  tar xzf /backup/pgdata.tar.gz -C /data"),
        "language": "bash",
        "warning": (
            "Back up a database by stopping it or by using its own dump "
            "tool. A tar of a live data directory is a copy of a file "
            "system mid-write."),
    },
    {
        "title": "Resource limits and what happens at the edge",
        "body": (
            "Without limits a container may use everything, and the first "
            "sign is usually the host swapping or the OOM killer choosing a "
            "victim that is not the culprit.\n\n"
            "`--memory` is a hard ceiling: crossing it kills the process "
            "with SIGKILL, which shows up as exit code 137. `--cpus` is a "
            "share of time, not a ceiling on speed — a limited container is "
            "throttled, not killed."),
        "snippet": (
            "docker run --memory 512m --memory-swap 512m --cpus 1.5 myapp\n"
            "docker stats --no-stream\n"
            "docker inspect web --format "
            "'{{.HostConfig.Memory}} {{.HostConfig.NanoCpus}}'"),
        "language": "bash",
        "tip": (
            "Setting `--memory-swap` to the same value as `--memory` "
            "disables swap for that container, which turns a slow death "
            "into an honest failure."),
        "rule_id": "RES01",
    },
    {
        "title": "Healthchecks, and what depends on them",
        "body": (
            "A healthcheck is a command the engine runs inside the "
            "container on a schedule. Its result is a state — starting, "
            "healthy, unhealthy — that other things can wait for.\n\n"
            "Docker does not restart an unhealthy container on its own. "
            "Compose's `depends_on: condition: service_healthy` does wait, "
            "which is how you stop an application starting before its "
            "database is ready."),
        "snippet": (
            "HEALTHCHECK --interval=10s --timeout=3s --start-period=30s "
            "--retries=3 \\\n"
            "  CMD wget -qO- http://localhost:8080/health || exit 1\n\n"
            "docker inspect web --format '{{.State.Health.Status}}'\n"
            "docker inspect web --format "
            "'{{range .State.Health.Log}}{{.Output}}{{end}}'"),
        "language": "bash",
    },
    {
        "title": "Logging drivers",
        "body": (
            "json-file is the default and, with no options, unbounded: the "
            "log grows until the disk is full. Two lines of daemon.json fix "
            "that for every container.\n\n"
            "journald hands logs to systemd, which rotates them for you and "
            "lets `journalctl` search them alongside everything else on the "
            "machine."),
        "snippet": (
            "# per container\n"
            "docker run --log-opt max-size=10m --log-opt max-file=3 nginx\n\n"
            "# for all of them, in daemon.json\n"
            "{\"log-driver\": \"json-file\",\n"
            " \"log-opts\": {\"max-size\": \"10m\", \"max-file\": \"3\"}}"),
        "language": "json",
        "warning": (
            "With a driver other than json-file or journald, `docker logs` "
            "stops working entirely — the logs went somewhere else on "
            "purpose."),
        "setting_key": "log-opts.max-size",
        "rule_id": "DSK01",
    },
    {
        "title": "Docker Desktop is a virtual machine",
        "body": (
            "On Windows and macOS the engine runs inside a Linux VM that "
            "Desktop manages. Its CPU, memory and disk are settings of that "
            "VM, and its disk is a single large image file.\n\n"
            "This explains the things that look strange from outside: bind "
            "mounts cross a file-sharing boundary and are slower, localhost "
            "means the VM in some directions, and reclaiming disk needs the "
            "image to be compacted, not just files deleted."),
        "snippet": (
            "docker context ls          # desktop-linux is the VM\n"
            "docker run --rm alpine uname -a\n"
            "docker system df"),
        "language": "bash",
        "tip": (
            "kontainy's App Settings page edits Desktop's own settings file "
            "directly, with the application closed — which is the only time "
            "it does not overwrite your change."),
    },
    {
        "title": "docker cp, and getting things in and out",
        "body": (
            "`cp` copies between the host and a container, and it works on "
            "a stopped container too — which makes it the right tool for "
            "retrieving a file from something that will not start.\n\n"
            "It is not a substitute for a volume: what you copy in becomes "
            "part of the writable layer and disappears with the container."),
        "snippet": (
            "docker cp web:/etc/nginx/nginx.conf ./nginx.conf\n"
            "docker cp ./nginx.conf web:/etc/nginx/nginx.conf\n"
            "docker cp $(docker create myimage):/app/dist ./dist   # from an "
            "image, without running it"),
        "language": "bash",
    },
    {
        "title": "The socket is root, and what to do about it",
        "body": (
            "Anything that can reach /var/run/docker.sock can start a "
            "container that mounts the host's root filesystem. Membership "
            "of the docker group is therefore equivalent to root, and "
            "mounting the socket into a container hands that container the "
            "machine.\n\n"
            "Rootless Docker exists for this reason, and so does Podman's "
            "design."),
        "snippet": (
            "# What this actually grants — do not run on a machine you care "
            "about\n"
            "# docker run -v /:/host -it alpine chroot /host sh\n\n"
            "# Rootless Docker\n"
            "dockerd-rootless-setuptool.sh install\n"
            "export DOCKER_HOST=unix://$XDG_RUNTIME_DIR/docker.sock\n\n"
            "# If a tool must see the API, give it a read-only proxy instead\n"
            "# of the socket itself."),
        "language": "bash",
        "rule_id": "SEC01",
    },
]
