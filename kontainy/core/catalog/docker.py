"""kontainy — settings catalogue part. See base.py for the field definitions."""

from .base import (
    S, SURFACE_DAEMON, SURFACE_STORAGE, SURFACE_NETWORK, SURFACE_REGISTRY,
    SURFACE_CONTAINER, SURFACE_SECURITY, SURFACE_RESOURCE, SURFACE_LOGGING,
    SURFACE_BUILD, SURFACE_SYSTEMD,
    DOCS_D, DOCS_DJ, DOCS_RUN, DOCS_CC, DOCS_SC, DOCS_RC, DOCS_PR, DOCS_QD,
)

# ===========================================================================
#  DOCKER — daemon.json
# ===========================================================================
DOCKER_DAEMON = [
    S("data-root", "docker", SURFACE_STORAGE, "docker.daemon", "str",
      "Data root", "Where images, container layers and volumes are kept. "
      "The only way to move the image store to another disk when the root "
      "filesystem starts filling up.",
      default="/var/lib/docker", cli="--data-root", restart=True, danger=1,
      gotcha="Stop the daemon and rsync the existing content across before "
             "changing this. Editing the key alone makes the old data "
             "invisible rather than moving it.",
      docs=DOCS_DJ, tags=["disk", "migration"]),

    S("storage-driver", "docker", SURFACE_STORAGE, "docker.daemon", "choice",
      "Storage driver", "Which mechanism implements the layered filesystem. "
      "overlay2 is the modern default; btrfs and zfs hand the work to the "
      "underlying filesystem.",
      default="overlay2", choices=["overlay2", "btrfs", "zfs", "vfs",
                                   "fuse-overlayfs"],
      cli="--storage-driver", restart=True, danger=2,
      gotcha="Changing the driver makes EVERY existing image and container "
             "invisible \u2014 not deleted, just unreachable. overlay2 works "
             "fine on a btrfs root, though the btrfs driver gains snapshot "
             "support.",
      docs="https://docs.docker.com/engine/storage/drivers/",
      tags=["btrfs", "disk"]),

    S("storage-opts", "docker", SURFACE_STORAGE, "docker.daemon", "list",
      "Storage options", "Driver-specific options, for example "
      "`overlay2.size=20G` to cap each container's writable layer.",
      default=[], restart=True, danger=1,
      gotcha="overlay2.size only works on xfs with pquota; on ext4 it is "
             "silently ignored.",
      docs="https://docs.docker.com/engine/storage/drivers/overlayfs-driver/"),

    S("log-driver", "docker", SURFACE_LOGGING, "docker.daemon", "choice",
      "Log driver", "Where container stdout and stderr are written.",
      default="json-file",
      choices=["json-file", "local", "journald", "syslog", "fluentd", "gelf",
               "awslogs", "splunk", "etwlogs", "none"],
      cli="--log-driver", restart=True,
      gotcha="json-file is UNLIMITED by default. Log files grow into "
             "gigabytes and fill the root disk \u2014 the most common cause "
             "of Docker-related disk exhaustion. The `local` driver rotates "
             "by default and is more efficient.",
      docs="https://docs.docker.com/engine/logging/configure/",
      tags=["disk", "critical"]),

    S("log-opts.max-size", "docker", SURFACE_LOGGING, "docker.daemon", "size",
      "Log file size", "Maximum size of a single log file before it rotates.",
      default=None, cli="--log-opt max-size", restart=True,
      gotcha="With nothing set there is no limit at all. 10m is a reasonable "
             "starting point.",
      docs="https://docs.docker.com/engine/logging/drivers/json-file/",
      tags=["disk", "critical"]),

    S("log-opts.max-file", "docker", SURFACE_LOGGING, "docker.daemon", "int",
      "Log file count", "How many rotated files to keep. Total disk use is "
      "max-size multiplied by max-file.",
      default=1, cli="--log-opt max-file", restart=True,
      docs="https://docs.docker.com/engine/logging/drivers/json-file/",
      tags=["disk"]),

    S("log-opts.compress", "docker", SURFACE_LOGGING, "docker.daemon", "bool",
      "Compress logs", "gzip rotated log files.",
      default=False, cli="--log-opt compress", restart=True, docs=DOCS_DJ),

    S("log-level", "docker", SURFACE_DAEMON, "docker.daemon", "choice",
      "Daemon log level", "How verbose dockerd's own logging is.",
      default="info", choices=["debug", "info", "warn", "error", "fatal"],
      cli="--log-level", restart=True, docs=DOCS_D),

    S("default-address-pools", "docker", SURFACE_NETWORK, "docker.daemon",
      "list",
      "Default address pools", "Which IP blocks Docker draws its own "
      "networks from. Each entry looks like "
      "`{\"base\": \"10.200.0.0/16\", \"size\": 24}`.",
      default=[{"base": "172.17.0.0/16", "size": 16},
               {"base": "172.18.0.0/16", "size": 16}],
      restart=True, danger=1,
      gotcha="CORPORATE NETWORK CLASH: the default 172.17.0.0/16 overlaps "
             "with many VPNs and office networks, so installing Docker makes "
             "the whole VPN unreachable. The symptom is 'I installed Docker "
             "and lost the company network'. The fix is to move this key to "
             "an unused block such as 10.200.0.0/16.",
      docs=DOCS_DJ, tags=["network", "vpn", "critical"]),

    S("bip", "docker", SURFACE_NETWORK, "docker.daemon", "str",
      "docker0 bridge IP", "The IP and mask of the default docker0 bridge, "
      "in CIDR form.",
      default="172.17.0.1/16", cli="--bip", restart=True, danger=1,
      gotcha="default-address-pools affects NEW networks only; changing "
             "docker0 itself needs this key. Confusing the two leaves the "
             "clash unresolved.",
      docs=DOCS_D, tags=["network", "vpn"]),

    S("fixed-cidr", "docker", SURFACE_NETWORK, "docker.daemon", "str",
      "Fixed CIDR", "The sub-range handed out to containers on docker0.",
      cli="--fixed-cidr", restart=True, docs=DOCS_D, tags=["network"]),

    S("default-network-opts", "docker", SURFACE_NETWORK, "docker.daemon",
      "dict",
      "Default network options", "Per-driver network defaults, for example "
      "an MTU applied to every bridge network.",
      restart=True, docs=DOCS_DJ, tags=["network", "mtu"]),

    S("mtu", "docker", SURFACE_NETWORK, "docker.daemon", "int",
      "MTU", "Maximum packet size on container network interfaces.",
      default=1500, cli="--mtu", restart=True,
      gotcha="Under a VPN such as WireGuard or OpenVPN, 1500 is too large. "
             "The symptom is 'small requests work, large downloads hang'. "
             "Try 1420 or 1360.",
      docs=DOCS_D, tags=["network", "vpn"]),

    S("dns", "docker", SURFACE_NETWORK, "docker.daemon", "list",
      "DNS servers", "DNS servers handed to containers.",
      cli="--dns", restart=True,
      gotcha="On systems using systemd-resolved the host's /etc/resolv.conf "
             "points at 127.0.0.53, which containers cannot reach. Docker "
             "detects this and falls back to 8.8.8.8 \u2014 on an air-gapped "
             "network that silent fallback breaks DNS completely.",
      docs=DOCS_D, tags=["network", "dns"]),

    S("dns-search", "docker", SURFACE_NETWORK, "docker.daemon", "list",
      "DNS search domains", "Search domains written into each container's "
      "resolv.conf.",
      cli="--dns-search", restart=True, docs=DOCS_D, tags=["network", "dns"]),

    S("dns-opts", "docker", SURFACE_NETWORK, "docker.daemon", "list",
      "DNS options", "The resolv.conf options line, for example `ndots:1`.",
      cli="--dns-opt", restart=True,
      gotcha="The `ndots:5` habit carried over from Kubernetes produces "
             "pointless DNS lookups under Docker and slows down every "
             "request.",
      docs=DOCS_D, tags=["network", "dns", "performance"]),

    S("iptables", "docker", SURFACE_NETWORK, "docker.daemon", "bool",
      "Manage iptables rules", "Whether Docker writes its own NAT and "
      "forwarding rules.",
      default=True, cli="--iptables", restart=True, danger=2,
      gotcha="On Arch and CachyOS with nftables plus firewalld, firewalld can "
             "wipe Docker's rules; the symptom is 'containers cannot reach "
             "the outside'. Turning this off breaks container networking "
             "entirely unless someone writes the rules by hand.",
      docs=DOCS_D, tags=["network", "firewall", "arch"]),

    S("ip6tables", "docker", SURFACE_NETWORK, "docker.daemon", "bool",
      "Manage ip6tables rules", "The same thing for IPv6.",
      default=False, restart=True, danger=1, docs=DOCS_D,
      tags=["network", "ipv6"]),

    S("ipv6", "docker", SURFACE_NETWORK, "docker.daemon", "bool",
      "IPv6 support", "Enables IPv6 on container networks.",
      default=False, cli="--ipv6", restart=True,
      gotcha="Not sufficient on its own; `fixed-cidr-v6` or an IPv6 address "
             "pool is also needed.",
      docs="https://docs.docker.com/engine/daemon/ipv6/",
      tags=["network", "ipv6"]),

    S("ip-forward", "docker", SURFACE_NETWORK, "docker.daemon", "bool",
      "IP forwarding", "Whether Docker turns on the net.ipv4.ip_forward "
      "sysctl.",
      default=True, restart=True, danger=1, docs=DOCS_D, tags=["network"]),

    S("ip-masq", "docker", SURFACE_NETWORK, "docker.daemon", "bool",
      "IP masquerading", "NATs container traffic behind the host's IP.",
      default=True, restart=True, danger=1, docs=DOCS_D, tags=["network"]),

    S("icc", "docker", SURFACE_NETWORK, "docker.daemon", "bool",
      "Inter-container communication", "Whether containers on the default "
      "bridge can reach each other directly.",
      default=True, cli="--icc", restart=True, danger=1,
      docs=DOCS_D, tags=["network", "security"]),

    S("userland-proxy", "docker", SURFACE_NETWORK, "docker.daemon", "bool",
      "Userland proxy", "Whether a docker-proxy process is used for port "
      "publishing.",
      default=True, cli="--userland-proxy", restart=True,
      gotcha="Every published port starts its own docker-proxy process; with "
             "hundreds of ports that is significant RAM. Turning it off "
             "improves performance but breaks scenarios that rely on hairpin "
             "NAT.",
      docs=DOCS_D, tags=["network", "performance"]),

    S("live-restore", "docker", SURFACE_DAEMON, "docker.daemon", "bool",
      "Live restore", "Keeps containers running while the daemon restarts.",
      default=False, cli="--live-restore", restart=True,
      gotcha="Not supported in Swarm mode, and worth turning off across "
             "large daemon version jumps.",
      docs="https://docs.docker.com/engine/daemon/live-restore/",
      tags=["stability"]),

    S("userns-remap", "docker", SURFACE_SECURITY, "docker.daemon", "str",
      "User namespace remapping", "Maps root inside the container to an "
      "unprivileged user on the host. The value `default` creates the "
      "dockremap user automatically.",
      cli="--userns-remap", restart=True, danger=2,
      gotcha="Turning this on makes every existing image and container "
             "unreachable, because a separate subdirectory under data-root is "
             "used. `--net=host`, `--pid=host` and some volume arrangements "
             "also stop working.",
      docs="https://docs.docker.com/engine/security/userns-remap/",
      tags=["security", "isolation"]),

    S("no-new-privileges", "docker", SURFACE_SECURITY, "docker.daemon", "bool",
      "No new privileges by default", "Blocks setuid escalation for every "
      "container.",
      default=False, restart=True, docs=DOCS_DJ, tags=["security"]),

    S("selinux-enabled", "docker", SURFACE_SECURITY, "docker.daemon", "bool",
      "SELinux support", "Enables SELinux labelling.",
      default=False, cli="--selinux-enabled", restart=True,
      gotcha="With this on, a bind mount without a `:z` or `:Z` suffix cannot "
             "be read from inside the container \u2014 the most common cause "
             "of 'Permission denied' on Fedora and RHEL.",
      docs=DOCS_D, tags=["security", "selinux"]),

    S("seccomp-profile", "docker", SURFACE_SECURITY, "docker.daemon", "str",
      "Default seccomp profile", "Path to the system call filter applied to "
      "every container.",
      restart=True, danger=2,
      docs="https://docs.docker.com/engine/security/seccomp/",
      tags=["security"]),

    S("default-ulimits", "docker", SURFACE_RESOURCE, "docker.daemon", "dict",
      "Default ulimits", "Resource limits applied to containers by default, "
      "`nofile` being the usual one.",
      default={}, cli="--default-ulimit", restart=True,
      gotcha="Many database images slow down silently at a low nofile value; "
             "`nofile: {Hard: 65536, Soft: 65536}` is the common fix.",
      docs=DOCS_D, tags=["resources", "performance"]),

    S("default-shm-size", "docker", SURFACE_RESOURCE, "docker.daemon", "size",
      "Default /dev/shm size", "Default size of the shared memory area.",
      default="64m", restart=True,
      gotcha="64 MB is too small for Chrome, Selenium and PyTorch "
             "DataLoader workers; it produces 'Bus error' or a silent crash.",
      docs=DOCS_DJ, tags=["resources", "ml"]),

    S("default-runtime", "docker", SURFACE_DAEMON, "docker.daemon", "str",
      "Default runtime", "Which OCI runtime to use: runc, crun or nvidia.",
      default="runc", cli="--default-runtime", restart=True,
      gotcha="NVIDIA GPU use needs this set to `nvidia`, otherwise every "
             "container has to pass `--runtime=nvidia` explicitly.",
      docs=DOCS_D, tags=["gpu", "runtime"]),

    S("runtimes", "docker", SURFACE_DAEMON, "docker.daemon", "dict",
      "Additional runtimes", "Named OCI runtime definitions.",
      default={}, restart=True, docs=DOCS_D, tags=["gpu", "runtime"]),

    S("exec-opts", "docker", SURFACE_DAEMON, "docker.daemon", "list",
      "Exec options", "Most often `native.cgroupdriver=systemd`.",
      default=[], restart=True, danger=1,
      gotcha="kubelet expects the systemd cgroup driver; a Docker running "
             "cgroupfs will not let kubelet start. On cgroup v2 systems "
             "systemd is mandatory.",
      docs=DOCS_D, tags=["kubernetes", "cgroup"]),

    S("cgroup-parent", "docker", SURFACE_RESOURCE, "docker.daemon", "str",
      "Parent cgroup", "The cgroup every container is placed under.",
      cli="--cgroup-parent", restart=True, docs=DOCS_D, tags=["cgroup"]),

    S("oom-score-adjust", "docker", SURFACE_RESOURCE, "docker.daemon", "int",
      "Daemon OOM score", "How willing the kernel is to kill dockerd when "
      "memory runs out.",
      default=0, restart=True, docs=DOCS_D, tags=["resources"]),

    S("registry-mirrors", "docker", SURFACE_REGISTRY, "docker.daemon", "list",
      "Registry mirrors", "Docker Hub requests are sent to these addresses "
      "first.",
      default=[], cli="--registry-mirror", restart=True,
      gotcha="Works for Docker Hub only; requests to ghcr.io or quay.io are "
             "not mirrored. It also does not solve rate limiting, it only "
             "reduces latency.",
      docs=DOCS_DJ, tags=["registry", "speed"]),

    S("insecure-registries", "docker", SURFACE_REGISTRY, "docker.daemon",
      "list",
      "Insecure registries", "Registries reachable without TLS verification.",
      default=[], cli="--insecure-registry", restart=True, danger=2,
      gotcha="Needed for a local development registry on localhost:5000, but "
             "in production it opens the traffic to a man-in-the-middle.",
      docs=DOCS_DJ, tags=["registry", "security"]),

    S("max-concurrent-downloads", "docker", SURFACE_REGISTRY, "docker.daemon",
      "int",
      "Concurrent downloads", "Maximum layers pulled at once.",
      default=3, restart=True, docs=DOCS_D, tags=["registry", "speed"]),

    S("max-concurrent-uploads", "docker", SURFACE_REGISTRY, "docker.daemon",
      "int",
      "Concurrent uploads", "Maximum layers pushed at once.",
      default=5, restart=True, docs=DOCS_D, tags=["registry", "speed"]),

    S("max-download-attempts", "docker", SURFACE_REGISTRY, "docker.daemon",
      "int",
      "Download attempts", "How often a failed layer download is retried.",
      default=5, restart=True, docs=DOCS_D, tags=["registry"]),

    S("shutdown-timeout", "docker", SURFACE_DAEMON, "docker.daemon",
      "duration",
      "Shutdown timeout", "Seconds containers are given while the daemon "
      "shuts down.",
      default=15, restart=True, docs=DOCS_D),

    S("hosts", "docker", SURFACE_DAEMON, "docker.daemon", "list",
      "Listen addresses", "Which sockets and addresses the daemon exposes "
      "the API on.",
      default=["unix:///var/run/docker.sock"], cli="-H", restart=True,
      danger=2,
      gotcha="On a systemd-installed Docker this key CONFLICTS with the -H "
             "flag in docker.service and the daemon will not start at all. "
             "The correct route is a systemd drop-in file.",
      docs=DOCS_D, tags=["critical", "systemd"]),

    S("tls", "docker", SURFACE_SECURITY, "docker.daemon", "bool",
      "TLS", "Use TLS for remote API access.",
      default=False, restart=True, docs=DOCS_D, tags=["security", "remote"]),

    S("tlsverify", "docker", SURFACE_SECURITY, "docker.daemon", "bool",
      "TLS client verification", "Verify the client certificate.",
      default=False, restart=True, docs=DOCS_D, tags=["security", "remote"]),

    S("features", "docker", SURFACE_BUILD, "docker.daemon", "dict",
      "Feature flags", "For example `{\"buildkit\": true}` or "
      "`{\"containerd-snapshotter\": true}`.",
      default={}, restart=True,
      gotcha="Turning on containerd-snapshotter changes the image store "
             "entirely; existing images vanish from the list \u2014 not "
             "deleted, just in a different store.",
      docs=DOCS_DJ, tags=["buildkit", "containerd"]),

    S("builder.gc.enabled", "docker", SURFACE_BUILD, "docker.daemon", "bool",
      "Build cache collection", "Whether the BuildKit cache is garbage "
      "collected automatically.",
      default=True, restart=True,
      docs="https://docs.docker.com/build/cache/garbage-collection/",
      tags=["buildkit", "disk"]),

    S("builder.gc.defaultKeepStorage", "docker", SURFACE_BUILD,
      "docker.daemon", "size",
      "Build cache limit", "Maximum build cache to retain.",
      default="10GB", restart=True,
      gotcha="On machines that build often the cache takes more space than "
             "the images. It is a separate line in `docker system df` and "
             "`docker image prune` does not remove it.",
      docs="https://docs.docker.com/build/cache/garbage-collection/",
      tags=["buildkit", "disk"]),

    S("metrics-addr", "docker", SURFACE_DAEMON, "docker.daemon", "str",
      "Metrics address", "Where Prometheus metrics are served.",
      restart=True, docs=DOCS_DJ, tags=["monitoring"]),

    S("debug", "docker", SURFACE_DAEMON, "docker.daemon", "bool",
      "Debug", "Puts the daemon into verbose logging mode.",
      default=False, cli="--debug", restart=True, docs=DOCS_D),

    S("experimental", "docker", SURFACE_DAEMON, "docker.daemon", "bool",
      "Experimental features", "Enables daemon features not considered "
      "stable.",
      default=False, restart=True, danger=1, docs=DOCS_D),
]

# ===========================================================================
#  DOCKER — CLI configuration (~/.docker/config.json), no root required
# ===========================================================================
DOCKER_CLI = [
    S("currentContext", "docker", SURFACE_DAEMON, "docker.cli", "str",
      "Active context", "Which engine the docker CLI connects to by default.",
      privilege="user",
      gotcha="If the DOCKER_HOST environment variable is set, this value is "
             "ignored entirely. `docker context use` reports success and "
             "changes nothing \u2014 the number one cause of the complaint "
             "that containers have disappeared.",
      docs="https://docs.docker.com/engine/manage-resources/contexts/",
      tags=["context", "critical"]),

    S("credsStore", "docker", SURFACE_REGISTRY, "docker.cli", "str",
      "Credential store", "The helper program that stores registry "
      "passwords: `secretservice`, `pass` or `desktop`.",
      privilege="user",
      gotcha="When Docker Desktop is removed this key stays behind as "
             "`desktop`, and every command then fails with "
             "`docker-credential-desktop not found in $PATH`. The key has to "
             "be deleted.",
      docs="https://docs.docker.com/reference/cli/docker/login/",
      tags=["critical", "desktop"]),

    S("credHelpers", "docker", SURFACE_REGISTRY, "docker.cli", "dict",
      "Per-registry credential helper", "A separate credential program for "
      "specific registries.",
      privilege="user",
      docs="https://docs.docker.com/reference/cli/docker/login/",
      tags=["registry"]),

    S("cliPluginsExtraDirs", "docker", SURFACE_DAEMON, "docker.cli", "list",
      "Extra plugin directories", "Additional directories searched for "
      "plugins such as `docker compose` and `docker buildx`.",
      privilege="user",
      gotcha="Docker Desktop installs its own plugins into "
             "`~/.docker/cli-plugins`, shadowing the distribution's copies in "
             "`/usr/lib/docker/cli-plugins` \u2014 which is why "
             "`docker compose version` and `docker-compose version` can "
             "disagree.",
      docs="https://docs.docker.com/engine/cli/plugins/",
      tags=["desktop", "compose"]),

    S("proxies", "docker", SURFACE_NETWORK, "docker.cli", "dict",
      "Proxy settings", "Proxy variables passed automatically into build and "
      "run operations.",
      privilege="user", docs="https://docs.docker.com/engine/daemon/proxy/",
      tags=["network", "proxy"]),

    S("detachKeys", "docker", SURFACE_DAEMON, "docker.cli", "str",
      "Detach keys", "Key sequence that detaches from an attached container.",
      default="ctrl-p,ctrl-q", privilege="user", docs=DOCS_RUN),
]
