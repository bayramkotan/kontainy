"""Compose & Orchestration — several containers as one thing."""

TOPICS = [
    {
        "title": "What Compose actually is",
        "body": (
            "Compose is a file that describes containers, networks and "
            "volumes, and a command that makes reality match the file. It "
            "is not a scheduler and not a cluster: everything runs on one "
            "machine.\n\n"
            "`compose.yaml` is the current name; docker-compose.yml still "
            "works. The `version:` key at the top is obsolete and modern "
            "versions warn about it."),
        "snippet": (
            "services:\n"
            "  web:\n"
            "    image: nginx:alpine\n"
            "    ports: [\"8080:80\"]\n"
            "    depends_on: [api]\n"
            "  api:\n"
            "    build: ./api\n"
            "    environment:\n"
            "      DATABASE_URL: postgres://db/app\n"
            "  db:\n"
            "    image: postgres:16\n"
            "    volumes: [\"pgdata:/var/lib/postgresql/data\"]\n\n"
            "volumes:\n"
            "  pgdata:"),
        "language": "yaml",
    },
    {
        "title": "The project name decides what belongs together",
        "body": (
            "Compose prefixes everything it creates with a project name, "
            "which defaults to the directory. Two checkouts of the same "
            "repository in differently named directories are therefore two "
            "separate stacks, and `down` in one does not touch the other.\n\n"
            "It is also how the same file runs twice on one machine: set "
            "`-p` and the names, networks and volumes do not collide."),
        "snippet": (
            "docker compose -p staging up -d\n"
            "docker compose -p staging ps\n"
            "docker compose ls              # every project running here\n\n"
            "# or in the file\n"
            "name: myapp"),
        "language": "bash",
    },
    {
        "title": "depends_on waits for the container, not the service",
        "body": (
            "Plain `depends_on` only orders startup: the database container "
            "is started first, but postgres inside it may need another ten "
            "seconds. The application starts, cannot connect, and exits.\n\n"
            "`condition: service_healthy` waits for the healthcheck instead, "
            "which is what people expect `depends_on` to mean."),
        "snippet": (
            "services:\n"
            "  db:\n"
            "    image: postgres:16\n"
            "    healthcheck:\n"
            "      test: [\"CMD-SHELL\", \"pg_isready -U postgres\"]\n"
            "      interval: 5s\n"
            "      retries: 10\n"
            "  api:\n"
            "    depends_on:\n"
            "      db:\n"
            "        condition: service_healthy"),
        "language": "yaml",
    },
    {
        "title": "Environment: the file, the shell, and precedence",
        "body": (
            "Values come from four places, and a later one overrides an "
            "earlier: the image's own ENV, `env_file`, the `environment` "
            "key, and the shell that ran `compose up`.\n\n"
            "Separately, `.env` next to the file fills `${VARIABLES}` in the "
            "YAML itself — that is substitution, not environment, and the "
            "two are easy to confuse."),
        "snippet": (
            "# .env — substituted into the YAML\n"
            "TAG=1.4\n"
            "HOST_PORT=8080\n\n"
            "# compose.yaml\n"
            "services:\n"
            "  api:\n"
            "    image: myapi:${TAG}\n"
            "    ports: [\"${HOST_PORT}:3000\"]\n"
            "    env_file: [app.env]     # goes into the container"),
        "language": "yaml",
        "tip": (
            "`docker compose config` prints the file after substitution, "
            "which answers \"what did it actually read\" in one command."),
    },
    {
        "title": "Profiles: optional parts of the same stack",
        "body": (
            "A service with a profile is not started unless that profile is "
            "asked for. This is how debugging tools, seeders and admin UIs "
            "live in the same file as the application without running all "
            "the time."),
        "snippet": (
            "services:\n"
            "  adminer:\n"
            "    image: adminer\n"
            "    profiles: [tools]\n\n"
            "# docker compose up -d                # without adminer\n"
            "# docker compose --profile tools up -d  # with it"),
        "language": "yaml",
    },
    {
        "title": "override files and several environments",
        "body": (
            "compose.override.yaml is merged on top of compose.yaml "
            "automatically. Named files with `-f` replace that: they are "
            "merged left to right, so the last one wins.\n\n"
            "The usual arrangement is a base file with what is true "
            "everywhere and a small file per environment, rather than one "
            "file full of conditionals."),
        "snippet": (
            "docker compose -f compose.yaml -f compose.prod.yaml up -d\n\n"
            "# compose.prod.yaml\n"
            "services:\n"
            "  api:\n"
            "    restart: always\n"
            "    deploy:\n"
            "      resources:\n"
            "        limits: {memory: 512M, cpus: '1.5'}"),
        "language": "yaml",
    },
    {
        "title": "Rebuilding, recreating and what up actually does",
        "body": (
            "`up` recreates a container when its configuration or its image "
            "changed, and leaves it alone otherwise. It does NOT rebuild an "
            "image because the source changed — that is `build`.\n\n"
            "Hence the two commands people confuse: `up --build` rebuilds "
            "first, `up --force-recreate` replaces containers even when "
            "nothing changed."),
        "snippet": (
            "docker compose up -d --build        # rebuild, then apply\n"
            "docker compose up -d --force-recreate\n"
            "docker compose up -d --no-deps api  # this service only\n\n"
            "docker compose down                 # containers and networks\n"
            "docker compose down -v              # ... and the volumes"),
        "language": "bash",
        "warning": (
            "`down -v` removes the named volumes of the project. That is "
            "the database."),
    },
    {
        "title": "Podman and Compose",
        "body": (
            "Two routes. `podman compose` drives an external tool "
            "(docker-compose or podman-compose). Or run the Podman API "
            "socket and point the real Docker Compose at it, which is the "
            "more compatible option today.\n\n"
            "Either way, features that assume a daemon — some volume "
            "drivers, `docker compose watch` — may not behave identically."),
        "snippet": (
            "systemctl --user enable --now podman.socket\n"
            "export DOCKER_HOST=unix://$XDG_RUNTIME_DIR/podman/podman.sock\n"
            "docker compose up -d\n\n"
            "podman compose version   # which provider it found"),
        "language": "bash",
    },
    {
        "title": "From Compose to Kubernetes, honestly",
        "body": (
            "Compose describes containers on one machine; Kubernetes "
            "describes desired state in a cluster. The translation tools "
            "produce something that runs, not something idiomatic.\n\n"
            "`podman generate kube` from a pod, or `kompose convert` from a "
            "Compose file, is a starting draft — health probes, resources, "
            "storage classes and ingress still have to be written by "
            "someone who knows the target."),
        "snippet": (
            "kompose convert -f compose.yaml -o k8s/\n"
            "podman generate kube app > app.yaml\n"
            "podman play kube app.yaml       # and back again"),
        "language": "bash",
    },
    {
        "title": "When one machine is no longer enough",
        "body": (
            "Compose stops being the answer when you need more than one "
            "machine, rolling updates without downtime, or scheduling that "
            "survives a node failing.\n\n"
            "Before jumping to Kubernetes, the honest middle ground is a "
            "single node with systemd units or Quadlet: it restarts things, "
            "orders them, logs them and survives reboots, with none of the "
            "cluster to operate."),
        "table": {
            "headers": ["Need", "Reasonable answer"],
            "rows": [
                ["Several containers, one machine", "Compose or Quadlet"],
                ["Survive reboots, ordered startup", "systemd units"],
                ["Several machines, rolling updates", "Kubernetes, Nomad"],
                ["One machine, but zero downtime", "two containers and a "
                                                    "reverse proxy"],
            ]},
    },
]
