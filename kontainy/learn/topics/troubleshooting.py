"""Troubleshooting — the failures people actually meet, and what to read."""

TOPICS = [
    {
        "title": "\"My containers disappeared\" — the context chain",
        "body": (
            "Where a `docker` command goes is decided by five layers, and "
            "an upper one overrides everything below it:\n\n"
            "1. `-H` / `--host` on the command line\n"
            "2. the `DOCKER_HOST` environment variable\n"
            "3. the `DOCKER_CONTEXT` environment variable\n"
            "4. `currentContext` in ~/.docker/config.json\n"
            "5. the built-in default, unix:///var/run/docker.sock\n\n"
            "The trap is layer two: while `DOCKER_HOST` is set, the context "
            "is IGNORED. `docker context use` reports success and changes "
            "nothing, so the containers stay invisible and the tool insists "
            "everything is fine."),
        "snippet": (
            "echo \"DOCKER_HOST=$DOCKER_HOST\"\n"
            "echo \"DOCKER_CONTEXT=$DOCKER_CONTEXT\"\n"
            "docker context ls\n\n"
            "# Where is that variable coming from?\n"
            "grep -rn DOCKER_HOST ~/.bashrc ~/.zshrc ~/.profile "
            "~/.config/environment.d/ 2>/dev/null\n\n"
            "unset DOCKER_HOST   # this shell only"),
        "language": "bash",
        "tip": (
            "kontainy shows this chain layer by layer on the Docker page "
            "and marks the winner — and its All containers page ignores the "
            "context entirely, listing every engine at once."),
        "rule_id": "CTX01",
    },
    {
        "title": "The exit code dictionary",
        "body": (
            "When a container stops unexpectedly, the exit code is the "
            "first thing to read. Most of them say what happened, and the "
            "ones above 128 say it precisely: the code is 128 plus the "
            "signal number, so 137 is SIGKILL and 143 is SIGTERM.\n\n"
            "The code is kept until the container is removed, so it is "
            "still there tomorrow morning when you come back to it."),
        "table": {
            "headers": ["Code", "Meaning", "Where to look"],
            "rows": [
                ["0", "finished normally", "—"],
                ["1", "the application failed", "`logs`"],
                ["125", "the engine command failed", "flags, image name"],
                ["126", "command could not be run", "permissions, shebang"],
                ["127", "command not found", "PATH, what is in the image"],
                ["137", "SIGKILL (128+9)", "**OOM, or a stop that timed out**"],
                ["139", "SIGSEGV (128+11)", "a crash, or the wrong architecture"],
                ["143", "SIGTERM (128+15)", "a normal stop"],
            ]},
        "snippet": (
            "podman inspect web --format '{{.State.ExitCode}} "
            "{{.State.OOMKilled}}'\n"
            "podman logs --tail 50 web\n"
            "journalctl -k | grep -i 'killed process'   # the OOM evidence"),
        "language": "bash",
        "warning": (
            "137 has two causes: the memory limit was hit, or `stop` gave "
            "up waiting and sent SIGKILL because the application ignored "
            "SIGTERM. The `OOMKilled` field tells them apart."),
    },
    {
        "title": "The disk is full — where it went",
        "body": (
            "Container-related disk use has three main sources and each is "
            "cleared by a different command. The one people miss is the "
            "build cache: `image prune` does not touch it.\n\n"
            "Logs are the other quiet one. With the default json-file "
            "driver and no size limit, a single noisy container can fill a "
            "partition."),
        "snippet": (
            "podman system df -v         # itemised\n"
            "docker system df -v\n\n"
            "# 1) Logs — unbounded by default\n"
            "du -sh /var/lib/docker/containers/*/*-json.log | sort -h | tail\n\n"
            "# 2) Build cache — a world of its own\n"
            "docker builder prune\n\n"
            "# 3) Dead containers, images, volumes\n"
            "podman system prune --volumes"),
        "language": "bash",
        "warning": (
            "`prune --volumes` removes volumes nothing references, which "
            "includes the database volume of a container you just deleted. "
            "Read the list it prints before agreeing."),
        "rule_id": "DSK01",
        "setting_key": "log-opts.max-size",
    },
    {
        "title": "Permission denied on a bind mount",
        "body": (
            "Three different causes wear the same message.\n\n"
            "SELinux: the host directory has no container label, so the "
            "container cannot read it. Add `:z` or `:Z`.\n\n"
            "User namespace: rootless Podman maps your UID to another "
            "number, so files you own look like they belong to `nobody`. "
            "Add `--userns=keep-id`.\n\n"
            "Plain UNIX permissions: the container runs as UID 1000 and the "
            "directory belongs to someone else. Fix the ownership, or run "
            "as the owner with `--user`."),
        "snippet": (
            "# Which of the three is it?\n"
            "getenforce                       # Enforcing -> suspect SELinux\n"
            "ls -lZ /path/on/host             # the label, if any\n"
            "podman unshare ls -l /path       # what the container sees\n\n"
            "podman run -v /data:/data:Z ...          # label it\n"
            "podman run --userns=keep-id -v $HOME/d:/d ...  # keep your UID\n"
            "sudo chown -R 1000:1000 /path            # or just own it"),
        "language": "bash",
        "note": (
            "`audit2why < /var/log/audit/audit.log` turns an SELinux denial "
            "into a sentence, which beats guessing."),
    },
    {
        "title": "\"Address already in use\" when publishing a port",
        "body": (
            "Something already holds the host port. It may be another "
            "container, or an ordinary service — a system nginx on 80 is "
            "the classic.\n\n"
            "On rootless Podman there is a second version of this message "
            "that is not a clash at all: ports below 1024 need a capability "
            "you do not have, and the error says permission denied rather "
            "than saying so."),
        "snippet": (
            "sudo ss -tulpn | grep :8080      # who has it\n"
            "docker ps --format '{{.Names}}\\t{{.Ports}}' | grep 8080\n\n"
            "# Rootless, below 1024\n"
            "sudo sysctl net.ipv4.ip_unprivileged_port_start=80\n"
            "# permanently:\n"
            "echo 'net.ipv4.ip_unprivileged_port_start=80' | "
            "sudo tee /etc/sysctl.d/99-rootless.conf"),
        "language": "bash",
        "rule_id": "NET02",
    },
    {
        "title": "One container cannot reach another by name",
        "body": (
            "On the default bridge network there is no name resolution "
            "between containers. On a user-defined network there is — the "
            "engine runs a small DNS server for it.\n\n"
            "This single difference accounts for most \"connection refused\" "
            "reports between an application and its database. The other "
            "half are localhost: inside a container, localhost is that "
            "container, not the host and not the neighbour."),
        "snippet": (
            "docker network create app\n"
            "docker run -d --network app --name db postgres:16\n"
            "docker run -d --network app --name api myapi\n"
            "# api reaches the database at db:5432\n\n"
            "docker exec api getent hosts db     # does the name resolve?\n"
            "docker network inspect app --format "
            "'{{range .Containers}}{{.Name}} {{end}}'"),
        "language": "bash",
        "tip": (
            "kontainy's create dialog says which network resolves names and "
            "which does not, next to the list, because this is the question "
            "the list cannot answer on its own."),
        "rule_id": "NET01",
    },
    {
        "title": "The container exits immediately",
        "body": (
            "A container lives exactly as long as its main process. If that "
            "process finishes, so does the container — and a service that "
            "daemonises itself finishes immediately by design.\n\n"
            "This is why images run their service in the foreground: "
            "`nginx -g 'daemon off;'`, `httpd -D FOREGROUND`. A command "
            "that forks into the background leaves PID 1 with nothing to "
            "do, and the container stops one moment after it starts."),
        "snippet": (
            "docker ps -a --filter name=web          # it exited, with what?\n"
            "docker logs web\n"
            "docker inspect web --format "
            "'{{.Config.Entrypoint}} {{.Config.Cmd}}'\n\n"
            "# Keep it alive while you look inside\n"
            "docker run -d --name probe myimage sleep infinity\n"
            "docker exec -it probe sh"),
        "language": "bash",
    },
    {
        "title": "exec format error",
        "body": (
            "The image is built for a different CPU architecture. An arm64 "
            "image on an x86_64 machine gives this, and so does the "
            "reverse — common now that many laptops are arm64 and most "
            "servers are not.\n\n"
            "The second cause is a script with CRLF line endings: the "
            "shebang becomes `#!/bin/sh\\r`, which is not a program that "
            "exists."),
        "snippet": (
            "docker image inspect myimage --format "
            "'{{.Architecture}} {{.Os}}'\n"
            "uname -m\n\n"
            "# Pull the right one, or build for both\n"
            "docker pull --platform linux/amd64 myimage\n"
            "docker buildx build --platform linux/amd64,linux/arm64 -t "
            "myimage .\n\n"
            "file entrypoint.sh    # 'CRLF line terminators' is the other "
            "cause\n"
            "sed -i 's/\\r$//' entrypoint.sh"),
        "language": "bash",
        "note": (
            "Emulation through qemu-user-static makes a foreign image run, "
            "slowly. It is a way to test, not a way to deploy."),
    },
    {
        "title": "Cannot connect to the Docker daemon",
        "body": (
            "Four separate situations produce this one sentence: the daemon "
            "is not running; your user is not in the docker group; "
            "DOCKER_HOST points somewhere that is not listening; or, on "
            "Windows and macOS, Docker Desktop is closed.\n\n"
            "They are distinguished in that order, and none of them needs "
            "reinstalling anything."),
        "snippet": (
            "systemctl status docker            # running?\n"
            "id -nG | tr ' ' '\\n' | grep -x docker   # in the group?\n"
            "echo $DOCKER_HOST                  # pointing elsewhere?\n"
            "curl --unix-socket /var/run/docker.sock http://localhost/_ping\n\n"
            "sudo systemctl start docker\n"
            "sudo usermod -aG docker $USER      # then log out and back in"),
        "language": "bash",
        "warning": (
            "Membership of the docker group is equivalent to root: the API "
            "can mount the host filesystem into a container. That is a "
            "deliberate trade, not an oversight — rootless Podman exists "
            "because of it."),
        "rule_id": "SEC01",
    },
    {
        "title": "The image pull fails or is rate limited",
        "body": (
            "Docker Hub limits anonymous pulls by IP address. On a shared "
            "network or a CI runner that budget is spent by other people, "
            "and pulls start failing with 429 for reasons that have nothing "
            "to do with you.\n\n"
            "Logging in raises the limit. A pull-through mirror removes the "
            "problem for everyone behind it."),
        "snippet": (
            "docker login                      # authenticated pulls\n\n"
            "# What the registry says about your budget\n"
            "TOKEN=$(curl -s "
            "'https://auth.docker.io/token?service=registry.docker.io&"
            "scope=repository:ratelimitpreview/test:pull' | "
            "python3 -c 'import sys,json;print(json.load(sys.stdin)[\"token\"])')\n"
            "curl -sI -H \"Authorization: Bearer $TOKEN\" "
            "https://registry-1.docker.io/v2/ratelimitpreview/test/manifests/"
            "latest | grep -i ratelimit"),
        "language": "bash",
        "tip": (
            "A registry mirror in daemon.json, or `unqualified-search-"
            "registries` in registries.conf, is worth setting up once on "
            "any machine that builds often."),
        "setting_key": "registry-mirrors",
    },
    {
        "title": "Podman: short-name resolution and the wrong image",
        "body": (
            "`podman run nginx` has to decide which registry that means. "
            "With `short-name-mode` set to `prompt` it asks; set to "
            "`permissive` it takes the first match from the search list, "
            "which may not be Docker Hub.\n\n"
            "This is how someone ends up running a different project's "
            "image with the same name, with no error anywhere."),
        "snippet": (
            "podman info --format '{{.Registries}}'\n"
            "grep -A5 unqualified-search-registries "
            "/etc/containers/registries.conf\n\n"
            "# Be explicit, always\n"
            "podman pull docker.io/library/nginx:alpine"),
        "language": "bash",
        "setting_key": "short-name-mode",
    },
    {
        "title": "Everything is slow: the build takes minutes it did not",
        "body": (
            "Three usual causes. The storage driver fell back to vfs, which "
            "copies every layer instead of stacking them. The build context "
            "is enormous, because .dockerignore does not exclude .git and "
            "node_modules. Or the cache is being invalidated on the first "
            "line by a COPY that changes every time.\n\n"
            "The third is the one worth fixing properly: copy the "
            "dependency manifest and install dependencies BEFORE copying "
            "the source, so a code change does not reinstall the world."),
        "snippet": (
            "docker info --format '{{.Driver}}'          # not vfs\n"
            "du -sh . && cat .dockerignore\n\n"
            "# Cache-friendly order\n"
            "COPY package*.json ./\n"
            "RUN npm ci\n"
            "COPY . .            # only this layer rebuilds on a code change"),
        "language": "bash",
        "tip": (
            "`docker build --progress=plain` shows which step was taken "
            "from cache and which was rebuilt, which turns this from "
            "guesswork into reading."),
    },
    {
        "title": "Time is wrong inside the container",
        "body": (
            "The clock is the host's — a container has no clock of its "
            "own — but the timezone is whatever the image says, which is "
            "almost always UTC.\n\n"
            "Applications that format timestamps locally then disagree with "
            "everything else on the machine. Set TZ, or mount the host's "
            "zone data, rather than changing the host."),
        "snippet": (
            "docker run -e TZ=Europe/Istanbul alpine date\n"
            "docker run -v /etc/localtime:/etc/localtime:ro alpine date\n\n"
            "# Some images need the tz database installed first\n"
            "# alpine: apk add --no-cache tzdata"),
        "language": "bash",
        "note": (
            "Databases are the exception worth caring about: postgres and "
            "mysql have their own timezone settings, and TZ alone does not "
            "change how they store timestamps."),
    },
    {
        "title": "Reading a failure properly: the order that works",
        "body": (
            "Most container failures are found in the same four steps, and "
            "in this order. Skipping to the fourth is how an afternoon "
            "disappears.\n\n"
            "1. Did it run at all? `ps -a` and the exit code.\n"
            "2. What did it say? `logs`, from the beginning, not the tail.\n"
            "3. What did it actually get? `inspect`: mounts, ports, "
            "environment, limits — as opposed to what the command asked "
            "for.\n"
            "4. What does the engine itself say? `journalctl -u docker`, or "
            "`podman --log-level=debug`."),
        "snippet": (
            "docker ps -a --filter name=web\n"
            "docker logs web 2>&1 | head -50\n"
            "docker inspect web --format "
            "'{{json .HostConfig}}' | python3 -m json.tool | head -40\n"
            "journalctl -u docker --since '10 min ago'\n"
            "podman --log-level=debug run alpine true 2>&1 | tail -30"),
        "language": "bash",
        "tip": (
            "kontainy's Diagnostics page runs these checks as rules and "
            "says what was found, why it happens and how to fix it — the "
            "same three things, without the typing."),
    },
]
