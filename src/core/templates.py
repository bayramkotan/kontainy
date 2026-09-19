"""
kontainy — container templates

Bayram, 2026-09-19: *"Kullanici ornek kod aramamali!!!"*

Every template carries the things people actually copy off blog posts and get
wrong: the volume that must be named or the database dies with the container,
the environment variable the image refuses to start without, a healthcheck
that waits long enough for the service to come up, and a capability set that
is not simply ``--privileged``.

Each template renders three ways from the same data — ``docker run`` /
``podman run``, a Quadlet unit, and a compose service — so the same choice
works whichever route the user takes.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Template:
    id: str
    name: str
    category: str
    image: str
    description: str
    ports: list = field(default_factory=list)        # ["5432:5432"]
    volumes: list = field(default_factory=list)      # ["pgdata:/var/lib/..."]
    env: dict = field(default_factory=dict)
    env_required: list = field(default_factory=list)  # user must fill these
    cap_drop: list = field(default_factory=lambda: ["ALL"])
    cap_add: list = field(default_factory=list)
    health_cmd: str = ""
    health_start_period: str = "30s"
    memory: str = ""
    restart: str = "unless-stopped"
    read_only: bool = False
    tmpfs: list = field(default_factory=list)
    extra_flags: list = field(default_factory=list)
    docs: str = ""
    note: str = ""

    # --- rendering ---------------------------------------------------------
    def run_command(self, engine: str = "podman", name: str = "") -> str:
        """The `docker run` / `podman run` equivalent, line-wrapped."""
        name = name or self.id
        image = self.image
        if engine == "podman" and "/" not in image.split(":")[0]:
            image = f"docker.io/library/{image}"

        parts = [f"{engine} run -d", f"  --name {name}",
                 f"  --restart={self.restart}"]
        for port in self.ports:
            parts.append(f"  -p {port}")
        for volume in self.volumes:
            parts.append(f"  -v {volume}")
        for key, value in self.env.items():
            parts.append(f"  -e {key}={value}")
        for key in self.env_required:
            parts.append(f"  -e {key}=<CHANGE_ME>")
        for cap in self.cap_drop:
            parts.append(f"  --cap-drop={cap}")
        for cap in self.cap_add:
            parts.append(f"  --cap-add={cap}")
        if self.read_only:
            parts.append("  --read-only")
        for mount in self.tmpfs:
            parts.append(f"  --tmpfs {mount}")
        if self.memory:
            parts.append(f"  --memory={self.memory}")
        if self.health_cmd:
            parts.append(f"  --health-cmd='{self.health_cmd}'")
            parts.append(f"  --health-start-period={self.health_start_period}")
        parts.extend(f"  {flag}" for flag in self.extra_flags)
        parts.append(f"  {image}")
        return " \\\n".join(parts)

    def quadlet(self, name: str = "") -> str:
        """A systemd Quadlet unit — the thing no other GUI generates."""
        name = name or self.id
        lines = ["[Unit]", f"Description={self.name}", "",
                 "[Container]", f"Image={self.image}",
                 f"ContainerName={name}"]
        for port in self.ports:
            lines.append(f"PublishPort={port}")
        for volume in self.volumes:
            lines.append(f"Volume={volume}")
        for key, value in self.env.items():
            lines.append(f"Environment={key}={value}")
        for key in self.env_required:
            lines.append(f"Environment={key}=CHANGE_ME")
        for cap in self.cap_drop:
            lines.append(f"DropCapability={cap}")
        for cap in self.cap_add:
            lines.append(f"AddCapability={cap}")
        if self.read_only:
            lines.append("ReadOnly=true")
        if self.health_cmd:
            lines.append(f"HealthCmd={self.health_cmd}")
            lines.append(f"HealthStartPeriod={self.health_start_period}")
        lines.append("AutoUpdate=registry")
        lines += ["", "[Service]",
                  f"Restart={'always' if self.restart != 'no' else 'no'}",
                  "", "[Install]", "WantedBy=default.target"]
        return "\n".join(lines)

    def compose(self, name: str = "") -> str:
        name = name or self.id
        lines = ["services:", f"  {name}:", f"    image: {self.image}",
                 f"    restart: {self.restart}"]
        if self.ports:
            lines.append("    ports:")
            lines += [f'      - "{p}"' for p in self.ports]
        if self.volumes:
            lines.append("    volumes:")
            lines += [f"      - {v}" for v in self.volumes]
        if self.env or self.env_required:
            lines.append("    environment:")
            lines += [f"      {k}: {v}" for k, v in self.env.items()]
            lines += [f"      {k}: CHANGE_ME" for k in self.env_required]
        if self.cap_drop:
            lines.append("    cap_drop:")
            lines += [f"      - {c}" for c in self.cap_drop]
        if self.cap_add:
            lines.append("    cap_add:")
            lines += [f"      - {c}" for c in self.cap_add]
        named = [v.split(":")[0] for v in self.volumes if "/" not in v.split(":")[0]]
        if named:
            lines.append("")
            lines.append("volumes:")
            lines += [f"  {v}:" for v in named]
        return "\n".join(lines)

    def install_hint(self, name: str = "") -> str:
        """The two commands that make a Quadlet unit actually run."""
        name = name or self.id
        return (f"mkdir -p ~/.config/containers/systemd\n"
                f"# save the unit as ~/.config/containers/systemd/{name}.container\n"
                f"systemctl --user daemon-reload\n"
                f"systemctl --user start {name}\n"
                f"loginctl enable-linger $USER   # survive logout and reboot")


T = Template

TEMPLATES = [
    # --- Databases --------------------------------------------------------
    T("postgres", "PostgreSQL 16", "Databases", "docker.io/library/postgres:16",
      "Relational database. The named volume is what keeps your data when the "
      "container is replaced — without it an upgrade wipes the database.",
      ports=["5432:5432"],
      volumes=["pgdata:/var/lib/postgresql/data"],
      env={"POSTGRES_USER": "postgres", "POSTGRES_DB": "postgres"},
      env_required=["POSTGRES_PASSWORD"],
      cap_add=["CHOWN", "DAC_OVERRIDE", "FOWNER", "SETGID", "SETUID"],
      health_cmd="pg_isready -U postgres", health_start_period="30s",
      memory="1g",
      docs="https://hub.docker.com/_/postgres",
      note="Postgres refuses to start without POSTGRES_PASSWORD. Set a real "
           "memory limit: the JVM-style default of 'all the host RAM' applies "
           "to shared_buffers sizing too."),

    T("mariadb", "MariaDB 11", "Databases", "docker.io/library/mariadb:11",
      "MySQL-compatible database.",
      ports=["3306:3306"], volumes=["mariadb:/var/lib/mysql"],
      env={"MARIADB_DATABASE": "app"},
      env_required=["MARIADB_ROOT_PASSWORD"],
      cap_add=["CHOWN", "DAC_OVERRIDE", "SETGID", "SETUID"],
      health_cmd="healthcheck.sh --connect --innodb_initialized",
      memory="1g", docs="https://hub.docker.com/_/mariadb"),

    T("redis", "Redis 7", "Databases", "docker.io/library/redis:7-alpine",
      "In-memory store. Appendonly is on here so a restart does not lose "
      "everything — the default image does not persist at all.",
      ports=["6379:6379"], volumes=["redis:/data"],
      extra_flags=["--", "redis-server", "--appendonly", "yes"],
      health_cmd="redis-cli ping", memory="512m",
      docs="https://hub.docker.com/_/redis"),

    T("mongo", "MongoDB 7", "Databases", "docker.io/library/mongo:7",
      "Document database.",
      ports=["27017:27017"], volumes=["mongo:/data/db"],
      env={"MONGO_INITDB_ROOT_USERNAME": "root"},
      env_required=["MONGO_INITDB_ROOT_PASSWORD"],
      cap_add=["CHOWN", "SETGID", "SETUID"], memory="1g",
      docs="https://hub.docker.com/_/mongo"),

    # --- Web and proxy ----------------------------------------------------
    T("nginx", "nginx", "Web", "docker.io/library/nginx:alpine",
      "Static web server and reverse proxy.",
      ports=["8080:80"], volumes=["./site:/usr/share/nginx/html:ro,Z"],
      cap_add=["CHOWN", "SETGID", "SETUID", "NET_BIND_SERVICE"],
      tmpfs=["/var/cache/nginx", "/var/run"], read_only=True,
      health_cmd="curl -f http://localhost/ || exit 1",
      docs="https://hub.docker.com/_/nginx",
      note="Rootless Podman cannot bind port 80, hence 8080 on the host. "
           "The :Z suffix is what makes the bind mount readable under SELinux."),

    T("caddy", "Caddy 2", "Web", "docker.io/library/caddy:alpine",
      "Web server with automatic HTTPS.",
      ports=["8080:80", "8443:443"],
      volumes=["caddy_data:/data", "caddy_config:/config",
               "./Caddyfile:/etc/caddy/Caddyfile:ro,Z"],
      cap_add=["NET_BIND_SERVICE"],
      docs="https://hub.docker.com/_/caddy"),

    T("traefik", "Traefik 3", "Web", "docker.io/library/traefik:v3",
      "Reverse proxy that discovers containers automatically.",
      ports=["8080:80", "8081:8080"],
      volumes=["/run/user/1000/podman/podman.sock:/var/run/docker.sock:ro"],
      extra_flags=["--", "--api.insecure=true", "--providers.docker=true"],
      cap_add=["NET_BIND_SERVICE"],
      docs="https://hub.docker.com/_/traefik",
      note="Mounting the engine socket into a container gives it full control "
           "of that engine. Read-only helps a little; treat it as root."),

    # --- Tooling ----------------------------------------------------------
    T("minio", "MinIO", "Tooling", "quay.io/minio/minio:latest",
      "S3-compatible object storage.",
      ports=["9000:9000", "9001:9001"], volumes=["minio:/data"],
      env={"MINIO_ROOT_USER": "minioadmin"},
      env_required=["MINIO_ROOT_PASSWORD"],
      extra_flags=["--", "server", "/data", "--console-address", ":9001"],
      docs="https://hub.docker.com/r/minio/minio"),

    T("gitea", "Gitea", "Tooling", "docker.io/gitea/gitea:latest",
      "Self-hosted Git service.",
      ports=["3000:3000", "2222:22"], volumes=["gitea:/data"],
      env={"USER_UID": "1000", "USER_GID": "1000"},
      cap_add=["CHOWN", "SETGID", "SETUID"],
      docs="https://hub.docker.com/r/gitea/gitea"),

    T("vaultwarden", "Vaultwarden", "Tooling",
      "docker.io/vaultwarden/server:latest",
      "Bitwarden-compatible password server.",
      ports=["8222:80"], volumes=["vaultwarden:/data"],
      env={"SIGNUPS_ALLOWED": "false"},
      env_required=["ADMIN_TOKEN"],
      docs="https://hub.docker.com/r/vaultwarden/server"),

    T("n8n", "n8n", "Tooling", "docker.io/n8nio/n8n:latest",
      "Workflow automation.",
      ports=["5678:5678"], volumes=["n8n:/home/node/.n8n"],
      env={"N8N_SECURE_COOKIE": "false"},
      docs="https://hub.docker.com/r/n8nio/n8n"),

    T("pihole", "Pi-hole", "Tooling", "docker.io/pihole/pihole:latest",
      "Network-wide DNS ad blocking.",
      ports=["5353:53/udp", "5353:53/tcp", "8088:80"],
      volumes=["pihole:/etc/pihole", "pihole_dns:/etc/dnsmasq.d"],
      env={"TZ": "Europe/Istanbul"}, env_required=["WEBPASSWORD"],
      cap_add=["NET_ADMIN", "NET_BIND_SERVICE", "CHOWN", "SETGID", "SETUID"],
      docs="https://hub.docker.com/r/pihole/pihole",
      note="Port 53 needs NET_BIND_SERVICE and, rootless, a lowered "
           "net.ipv4.ip_unprivileged_port_start. The host port is 5353 here "
           "so it does not fight systemd-resolved."),

    # --- Monitoring -------------------------------------------------------
    T("grafana", "Grafana", "Monitoring", "docker.io/grafana/grafana:latest",
      "Dashboards for metrics and logs.",
      ports=["3001:3000"], volumes=["grafana:/var/lib/grafana"],
      env={"GF_SECURITY_ADMIN_USER": "admin"},
      env_required=["GF_SECURITY_ADMIN_PASSWORD"],
      docs="https://hub.docker.com/r/grafana/grafana"),

    T("prometheus", "Prometheus", "Monitoring",
      "docker.io/prom/prometheus:latest",
      "Metrics collection and storage.",
      ports=["9090:9090"],
      volumes=["prometheus:/prometheus",
               "./prometheus.yml:/etc/prometheus/prometheus.yml:ro,Z"],
      docs="https://hub.docker.com/r/prom/prometheus"),

    # --- Development ------------------------------------------------------
    T("jupyter", "JupyterLab", "Development",
      "quay.io/jupyter/scipy-notebook:latest",
      "Notebook environment with the scientific Python stack.",
      ports=["8888:8888"], volumes=["./notebooks:/home/jovyan/work:Z"],
      env={"JUPYTER_ENABLE_LAB": "yes"},
      memory="4g",
      extra_flags=["--shm-size=1g"],
      docs="https://quay.io/repository/jupyter/scipy-notebook",
      note="The default /dev/shm of 64 MB is too small for PyTorch DataLoader "
           "workers; --shm-size=1g avoids silent 'Bus error' crashes."),

    T("code-server", "code-server", "Development",
      "docker.io/codercom/code-server:latest",
      "VS Code in the browser.",
      ports=["8443:8080"],
      volumes=["code_config:/home/coder/.config", "./project:/home/coder/project:Z"],
      env_required=["PASSWORD"],
      docs="https://hub.docker.com/r/codercom/code-server"),

    T("ollama", "Ollama", "Development", "docker.io/ollama/ollama:latest",
      "Run local language models.",
      ports=["11434:11434"], volumes=["ollama:/root/.ollama"],
      memory="16g",
      docs="https://hub.docker.com/r/ollama/ollama",
      note="For NVIDIA GPUs add --device nvidia.com/gpu=all (Podman with CDI) "
           "or --gpus all (Docker with the nvidia runtime)."),
]

CATEGORIES = ["Databases", "Web", "Tooling", "Monitoring", "Development"]


def by_id(template_id: str):
    for template in TEMPLATES:
        if template.id == template_id:
            return template
    return None


def by_category(category: str) -> list:
    return [t for t in TEMPLATES if t.category == category]


def search(text: str) -> list:
    needle = text.casefold()
    return [t for t in TEMPLATES
            if needle in f"{t.id} {t.name} {t.image} {t.description}".casefold()]
