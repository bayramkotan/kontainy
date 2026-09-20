"""kontainy — settings catalogue part. See base.py for the field definitions."""

from .base import (
    S, SURFACE_DAEMON, SURFACE_STORAGE, SURFACE_NETWORK, SURFACE_REGISTRY,
    SURFACE_CONTAINER, SURFACE_SECURITY, SURFACE_RESOURCE, SURFACE_LOGGING,
    SURFACE_BUILD, SURFACE_SYSTEMD,
    DOCS_D, DOCS_DJ, DOCS_RUN, DOCS_CC, DOCS_SC, DOCS_RC, DOCS_PR, DOCS_QD,
)

# ===========================================================================
#  PODMAN — containers.conf
# ===========================================================================
PODMAN_CONTAINERS = [
    S("containers.log_driver", "podman", SURFACE_LOGGING, "podman.containers",
      "choice",
      "Log driver", "Where container output is written.",
      default="journald",
      choices=["journald", "k8s-file", "json-file", "none", "passthrough"],
      privilege="user", cli="--log-driver",
      gotcha="The journald default routes `podman logs` through the systemd "
             "journal; under rootless the journal's size limits apply and "
             "older logs are dropped silently.",
      docs=DOCS_CC, tags=["logging"]),

    S("containers.log_size_max", "podman", SURFACE_LOGGING,
      "podman.containers", "size",
      "Maximum log size", "Per-container log size limit; -1 means unlimited.",
      default=-1, privilege="user", cli="--log-opt max-size", docs=DOCS_CC,
      tags=["logging", "disk"]),

    S("containers.cgroup_manager", "podman", SURFACE_RESOURCE,
      "podman.containers", "choice",
      "cgroup manager", "Which mechanism applies resource limits.",
      default="systemd", choices=["systemd", "cgroupfs"], privilege="user",
      danger=1,
      gotcha="Rootless with cgroup v2 requires systemd. With cgroupfs, "
             "memory and CPU limits are SILENTLY not applied \u2014 no error "
             "is raised, the limit is simply ignored.",
      docs=DOCS_CC, tags=["cgroup", "rootless", "critical"]),

    S("containers.cgroupns", "podman", SURFACE_RESOURCE, "podman.containers",
      "choice",
      "cgroup namespace", "How the container sees its own cgroup tree.",
      default="private", choices=["private", "host"], privilege="user",
      cli="--cgroupns", docs=DOCS_CC, tags=["cgroup"]),

    S("containers.cgroups", "podman", SURFACE_RESOURCE, "podman.containers",
      "choice",
      "cgroup usage", "Whether Podman creates cgroups at all.",
      default="enabled", choices=["enabled", "disabled", "no-conmon", "split"],
      privilege="user", danger=1, docs=DOCS_CC, tags=["cgroup"]),

    S("containers.default_capabilities", "podman", SURFACE_SECURITY,
      "podman.containers", "list",
      "Default capabilities", "The Linux capabilities given to every "
      "container.",
      default=["CHOWN", "DAC_OVERRIDE", "FOWNER", "FSETID", "KILL",
               "NET_BIND_SERVICE", "SETFCAP", "SETGID", "SETPCAP", "SETUID",
               "SYS_CHROOT"],
      privilege="user", cli="--cap-add / --cap-drop", danger=2,
      gotcha="Docker's default list differs from Podman's \u2014 Docker "
             "includes AUDIT_WRITE and MKNOD. An image that runs under Docker "
             "can fail with a permission error under Podman for this reason.",
      docs=DOCS_CC, tags=["security", "compatibility"]),

    S("containers.default_sysctls", "podman", SURFACE_SECURITY,
      "podman.containers", "list",
      "Default sysctls", "Kernel parameters applied to every container.",
      default=["net.ipv4.ping_group_range=0 0"], privilege="user",
      cli="--sysctl", docs=DOCS_CC, tags=["security"]),

    S("containers.default_ulimits", "podman", SURFACE_RESOURCE,
      "podman.containers", "list",
      "Default ulimits", "Resource limits such as `nofile=65536:65536`.",
      default=[], privilege="user", cli="--ulimit", docs=DOCS_CC,
      tags=["resources"]),

    S("containers.pids_limit", "podman", SURFACE_RESOURCE,
      "podman.containers", "int",
      "PID limit", "Maximum number of processes inside a container; "
      "0 means unlimited.",
      default=2048, privilege="user", cli="--pids-limit",
      gotcha="Not applied under rootless without cgroup v2 and systemd.",
      docs=DOCS_CC, tags=["resources"]),

    S("containers.shm_size", "podman", SURFACE_RESOURCE, "podman.containers",
      "size",
      "/dev/shm size", "Size of the shared memory area.",
      default="65536k", privilege="user", cli="--shm-size", docs=DOCS_CC,
      tags=["resources", "ml"]),

    S("containers.userns", "podman", SURFACE_SECURITY, "podman.containers",
      "choice",
      "User namespace mode", "How users inside the container map onto the "
      "host.",
      default="host", choices=["host", "keep-id", "nomap", "auto", "private"],
      privilege="user", cli="--userns", danger=1,
      gotcha="`keep-id` makes ownership of bind-mounted home directory files "
             "appear correctly; it is the standard fix for volume permission "
             "errors under rootless.",
      docs=DOCS_PR, tags=["rootless", "permissions", "critical"]),

    S("containers.netns", "podman", SURFACE_NETWORK, "podman.containers",
      "choice",
      "Network namespace", "The default network isolation mode.",
      default="private",
      choices=["private", "host", "none", "bridge", "slirp4netns", "pasta"],
      privilege="user", cli="--network", docs=DOCS_CC, tags=["network"]),

    S("containers.ipcns", "podman", SURFACE_SECURITY, "podman.containers",
      "choice",
      "IPC namespace", "Shared memory namespace mode.",
      default="shareable", choices=["host", "private", "shareable", "none"],
      privilege="user", cli="--ipc", docs=DOCS_CC),

    S("containers.pidns", "podman", SURFACE_SECURITY, "podman.containers",
      "choice",
      "PID namespace", "Process namespace mode.",
      default="private", choices=["private", "host"], privilege="user",
      cli="--pid", docs=DOCS_CC),

    S("containers.utsns", "podman", SURFACE_SECURITY, "podman.containers",
      "choice",
      "UTS namespace", "Hostname namespace mode.",
      default="private", choices=["private", "host"], privilege="user",
      cli="--uts", docs=DOCS_CC),

    S("containers.init", "podman", SURFACE_CONTAINER, "podman.containers",
      "bool",
      "init process", "Adds an init as PID 1 to reap zombie processes.",
      default=False, privilege="user", cli="--init",
      gotcha="For images whose application does not handle signals properly, "
             "`podman stop` waits ten seconds and then falls back to "
             "SIGKILL; an init fixes that.",
      docs=DOCS_CC, tags=["container"]),

    S("containers.tz", "podman", SURFACE_CONTAINER, "podman.containers", "str",
      "Timezone", "The container's timezone; `local` uses the host's.",
      privilege="user", cli="--tz", docs=DOCS_CC, tags=["container"]),

    S("containers.umask", "podman", SURFACE_CONTAINER, "podman.containers",
      "str",
      "umask", "Default file permission mask inside the container.",
      default="0022", privilege="user", cli="--umask", docs=DOCS_CC),

    S("containers.no_hosts", "podman", SURFACE_NETWORK, "podman.containers",
      "bool",
      "Do not generate /etc/hosts", "Stops Podman managing the /etc/hosts "
      "file.",
      default=False, privilege="user", cli="--no-hosts", docs=DOCS_CC,
      tags=["network"]),

    S("containers.dns_servers", "podman", SURFACE_NETWORK,
      "podman.containers", "list",
      "DNS servers", "DNS addresses handed to containers.",
      default=[], privilege="user", cli="--dns", docs=DOCS_CC,
      tags=["network", "dns"]),

    S("containers.env", "podman", SURFACE_CONTAINER, "podman.containers",
      "list",
      "Default environment variables", "Variables added to every container "
      "automatically.",
      default=["PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:"
               "/sbin:/bin", "TERM=xterm"],
      privilege="user", cli="--env", docs=DOCS_CC),

    S("containers.apparmor_profile", "podman", SURFACE_SECURITY,
      "podman.containers", "str",
      "AppArmor profile", "The AppArmor profile applied to containers.",
      default="containers-default-0.50.1", privilege="user",
      cli="--security-opt apparmor=", danger=1, docs=DOCS_CC,
      tags=["security"]),

    S("containers.seccomp_profile", "podman", SURFACE_SECURITY,
      "podman.containers", "str",
      "Seccomp profile", "Path to the system call filter profile.",
      default="/usr/share/containers/seccomp.json", privilege="user",
      cli="--security-opt seccomp=", danger=2, docs=DOCS_CC,
      tags=["security"]),

    S("containers.read_only", "podman", SURFACE_SECURITY, "podman.containers",
      "bool",
      "Read-only root", "Makes the container root filesystem unwritable.",
      default=False, privilege="user", cli="--read-only", docs=DOCS_CC,
      tags=["security"]),

    S("containers.volumes", "podman", SURFACE_CONTAINER, "podman.containers",
      "list",
      "Default volumes", "Volumes attached to every container automatically.",
      default=[], privilege="user", cli="--volume", docs=DOCS_CC),

    # --- [engine] ---
    S("engine.runtime", "podman", SURFACE_DAEMON, "podman.containers",
      "choice",
      "OCI runtime", "The program that actually starts the container.",
      default="crun", choices=["crun", "runc", "kata", "runsc"],
      privilege="user",
      gotcha="crun is written in C and is noticeably faster than runc under "
             "rootless cgroup v2; it is the default on Arch and CachyOS.",
      docs=DOCS_CC, tags=["runtime", "performance"]),

    S("engine.events_logger", "podman", SURFACE_DAEMON, "podman.containers",
      "choice",
      "Events logger", "Where the `podman events` stream is read from.",
      default="journald", choices=["journald", "file", "none"],
      privilege="user",
      gotcha="With `none`, kontainy's event stream does not work and the "
             "table only refreshes by polling.",
      docs=DOCS_CC, tags=["events"]),

    S("engine.pull_policy", "podman", SURFACE_REGISTRY, "podman.containers",
      "choice",
      "Pull policy", "Whether an image is pulled even when it is already "
      "local.",
      default="missing", choices=["always", "missing", "never", "newer"],
      privilege="user", cli="--pull", docs=DOCS_CC, tags=["registry"]),

    S("engine.image_default_transport", "podman", SURFACE_REGISTRY,
      "podman.containers", "str",
      "Default transport", "The transport prefixed to image names.",
      default="docker://", privilege="user", docs=DOCS_CC, tags=["registry"]),

    S("engine.infra_image", "podman", SURFACE_DAEMON, "podman.containers",
      "str",
      "Infra image", "The image for the infrastructure container that holds "
      "a pod's namespaces.",
      privilege="user", docs=DOCS_CC, tags=["pod"]),

    S("engine.compression_format", "podman", SURFACE_REGISTRY,
      "podman.containers", "choice",
      "Compression format", "Layer compression used when pushing images.",
      default="gzip", choices=["gzip", "zstd", "zstd:chunked"],
      privilege="user",
      gotcha="zstd:chunked enables partial layer pulls, but older registries "
             "and older Docker versions cannot read those layers.",
      docs=DOCS_CC, tags=["registry", "speed"]),

    S("engine.database_backend", "podman", SURFACE_DAEMON, "podman.containers",
      "choice",
      "Database backend", "Podman's state store.",
      default="sqlite", choices=["sqlite", "boltdb"], privilege="user",
      danger=1,
      gotcha="Changing it makes existing container records invisible; the "
             "migration is not automatic.",
      docs=DOCS_CC, tags=["critical"]),

    S("engine.stop_timeout", "podman", SURFACE_CONTAINER, "podman.containers",
      "duration",
      "Stop timeout", "Seconds to wait after SIGTERM before sending SIGKILL.",
      default=10, privilege="user", cli="--stop-timeout", docs=DOCS_CC),

    S("engine.service_timeout", "podman", SURFACE_DAEMON, "podman.containers",
      "duration",
      "Service timeout", "How long the API service stays up while idle; "
      "0 disables the shutdown.",
      default=5, privilege="user", docs=DOCS_CC, tags=["socket"]),

    S("engine.volume_path", "podman", SURFACE_STORAGE, "podman.containers",
      "str",
      "Volume directory", "Where named volumes are stored.",
      privilege="user", docs=DOCS_CC, tags=["disk"]),

    S("engine.helper_binaries_dir", "podman", SURFACE_DAEMON,
      "podman.containers", "list",
      "Helper binary directories", "Directories searched for helpers such as "
      "catatonit, slirp4netns and pasta.",
      privilege="user",
      gotcha="If this list is incomplete, rootless networking silently fails "
             "\u2014 the symptom is 'the container is up but has no internet'.",
      docs=DOCS_CC, tags=["rootless", "network"]),

    # --- [network] ---
    S("network.network_backend", "podman", SURFACE_NETWORK,
      "podman.containers", "choice",
      "Network backend", "The subsystem that builds container networks.",
      default="netavark", choices=["netavark", "cni"], privilege="user",
      danger=2,
      gotcha="Existing network definitions are NOT migrated when you switch; "
             "old CNI networks are invisible to netavark. A "
             "`podman system reset` may be required.",
      docs=DOCS_CC, tags=["network", "critical"]),

    S("network.default_rootless_network_cmd", "podman", SURFACE_NETWORK,
      "podman.containers", "choice",
      "Rootless network program", "How rootless containers reach the outside "
      "network.",
      default="pasta", choices=["pasta", "slirp4netns"], privilege="user",
      gotcha="pasta is faster and preserves the real source IP; slirp4netns "
             "makes all traffic appear to come from something like "
             "10.0.2.100, which matters to any application that inspects the "
             "source address.",
      docs=DOCS_CC, tags=["rootless", "network", "performance"]),

    S("network.default_subnet", "podman", SURFACE_NETWORK,
      "podman.containers", "str",
      "Default subnet", "The CIDR block of Podman's default network.",
      default="10.88.0.0/16", privilege="user",
      gotcha="It does not clash with Docker's 172.17, but it can clash with "
             "corporate 10.x networks.",
      docs=DOCS_CC, tags=["network", "vpn"]),

    S("network.default_subnet_pools", "podman", SURFACE_NETWORK,
      "podman.containers", "list",
      "Subnet pools", "The blocks new networks are generated from.",
      privilege="user", docs=DOCS_CC, tags=["network"]),

    S("network.firewall_driver", "podman", SURFACE_NETWORK,
      "podman.containers", "choice",
      "Firewall driver", "The backend netavark writes its rules through.",
      choices=["iptables", "nftables", "firewalld", "none"], privilege="user",
      danger=1,
      gotcha="Arch and CachyOS use nftables; without the iptables-nft "
             "compatibility layer the rules cannot be written and port "
             "publishing silently does nothing.",
      docs=DOCS_CC, tags=["network", "arch", "firewall"]),

    S("network.dns_bind_port", "podman", SURFACE_NETWORK, "podman.containers",
      "int",
      "aardvark-dns port", "The port the container DNS server listens on.",
      default=53, privilege="user", docs=DOCS_CC, tags=["network", "dns"]),
]

# ===========================================================================
#  PODMAN — storage.conf
# ===========================================================================
PODMAN_STORAGE = [
    S("storage.driver", "podman", SURFACE_STORAGE, "podman.storage", "choice",
      "Storage driver", "The layered filesystem backend.",
      default="overlay", choices=["overlay", "vfs", "btrfs", "zfs"],
      privilege="user", danger=2,
      gotcha="Changing it makes images under the old driver unreachable. vfs "
             "works everywhere but copies every layer in full, so disk usage "
             "multiplies.",
      docs=DOCS_SC, tags=["disk", "critical"]),

    S("storage.graphroot", "podman", SURFACE_STORAGE, "podman.storage", "str",
      "Image store directory", "Where image and container layers live "
      "permanently.",
      default="~/.local/share/containers/storage", privilege="user", danger=1,
      gotcha="Under rootless this sits in the home directory; if that home "
             "is on NFS, overlay does not work and Podman falls back to vfs "
             "without saying so.",
      docs=DOCS_SC, tags=["disk", "migration"]),

    S("storage.runroot", "podman", SURFACE_STORAGE, "podman.storage", "str",
      "Runtime directory", "The temporary area holding running container "
      "state.",
      default="$XDG_RUNTIME_DIR/containers", privilege="user", docs=DOCS_SC,
      tags=["disk"]),

    S("storage.transient_store", "podman", SURFACE_STORAGE, "podman.storage",
      "bool",
      "Transient store", "Discards container metadata on reboot.",
      default=False, privilege="user", danger=1, docs=DOCS_SC),

    S("storage.options.mount_program", "podman", SURFACE_STORAGE,
      "podman.storage", "str",
      "Mount program", "The program used for rootless overlay, usually "
      "fuse-overlayfs.",
      privilege="user",
      gotcha="Modern kernels support native rootless overlay, and "
             "fuse-overlayfs only slows things down. This line is often a "
             "leftover from an older installation.",
      docs=DOCS_SC, tags=["rootless", "performance"]),

    S("storage.options.mountopt", "podman", SURFACE_STORAGE, "podman.storage",
      "str",
      "Mount options", "For example `nodev,metacopy=on`.",
      default="nodev", privilege="user", docs=DOCS_SC),

    S("storage.options.additionalimagestores", "podman", SURFACE_STORAGE,
      "podman.storage", "list",
      "Additional image stores", "Read-only image stores to add.",
      default=[], privilege="user",
      gotcha="The only way for several users to share the same images; it "
             "stops each of them pulling their own copy.",
      docs=DOCS_SC, tags=["disk", "sharing"]),

    S("storage.options.ignore_chown_errors", "podman", SURFACE_STORAGE,
      "podman.storage", "bool",
      "Ignore chown errors", "Lets images be pulled under rootless with an "
      "insufficient UID range.",
      default=False, privilege="user", danger=1,
      gotcha="The symptom is 'potentially insufficient UIDs or GIDs "
             "available in user namespace'. The real fix is to widen the "
             "/etc/subuid range; this key only hides the problem.",
      docs=DOCS_SC, tags=["rootless", "permissions"]),

    S("storage.options.size", "podman", SURFACE_STORAGE, "podman.storage",
      "size",
      "Layer size limit", "A quota on the container's writable layer.",
      privilege="user", docs=DOCS_SC, tags=["disk", "quota"]),

    S("storage.options.pull_options", "podman", SURFACE_REGISTRY,
      "podman.storage", "dict",
      "Pull options", "`enable_partial_images`, `use_hard_links` and "
      "`convert_images`.",
      privilege="user", docs=DOCS_SC, tags=["registry", "speed"]),
]

# ===========================================================================
#  PODMAN — registries.conf
# ===========================================================================
PODMAN_REGISTRIES = [
    S("unqualified-search-registries", "podman", SURFACE_REGISTRY,
      "podman.registries", "list",
      "Unqualified search registries", "Which registries a short name such "
      "as `podman pull nginx` is searched for, in this order.",
      default=["docker.io"], privilege="user",
      gotcha="Docker always assumes docker.io; Podman does not. If this list "
             "is empty, every short-name pull fails \u2014 the first wall "
             "people hit when coming from Docker.",
      docs=DOCS_RC, tags=["registry", "critical", "compatibility"]),

    S("short-name-mode", "podman", SURFACE_REGISTRY, "podman.registries",
      "choice",
      "Short name mode", "How a short image name is resolved.",
      default="enforcing", choices=["enforcing", "permissive", "disabled"],
      privilege="user",
      gotcha="`enforcing` offers a selection list in an interactive "
             "terminal, but in a NON-INTERACTIVE context \u2014 a script, a "
             "systemd unit, a GUI \u2014 it fails outright. Anything pulling "
             "from an interface like kontainy has to account for this.",
      docs=DOCS_RC, tags=["registry", "critical", "gui"]),

    S("credential-helpers", "podman", SURFACE_REGISTRY, "podman.registries",
      "list",
      "Credential helpers", "Helper programs registry passwords are read "
      "from.",
      default=["containers-auth.json"], privilege="user", docs=DOCS_RC,
      tags=["registry"]),

    S("registry.mirror", "podman", SURFACE_REGISTRY, "podman.registries",
      "list",
      "Registry mirrors", "Alternative locations tried for a registry, "
      "written as `[[registry.mirror]]` blocks.",
      privilege="user",
      gotcha="Unlike Docker's registry-mirrors, this can be defined per "
             "registry rather than for Docker Hub alone.",
      docs=DOCS_RC, tags=["registry", "speed"]),

    S("registry.insecure", "podman", SURFACE_REGISTRY, "podman.registries",
      "bool",
      "Insecure registry", "Skips TLS verification for this registry.",
      default=False, privilege="user", danger=2, docs=DOCS_RC,
      tags=["registry", "security"]),

    S("registry.blocked", "podman", SURFACE_REGISTRY, "podman.registries",
      "bool",
      "Blocked registry", "Forbids pulling images from this registry "
      "entirely.",
      default=False, privilege="user", docs=DOCS_RC,
      tags=["registry", "security"]),

    S("registry.prefix", "podman", SURFACE_REGISTRY, "podman.registries",
      "str",
      "Rewrite prefix", "Redirects an image path to another location \u2014 "
      "the basic tool for air-gapped environments.",
      privilege="user", docs=DOCS_RC, tags=["registry"]),
]
