"""kontainy — settings catalogue part. See base.py for the field definitions."""

from .base import (
    S, SURFACE_DAEMON, SURFACE_STORAGE, SURFACE_NETWORK, SURFACE_REGISTRY,
    SURFACE_CONTAINER, SURFACE_SECURITY, SURFACE_RESOURCE, SURFACE_LOGGING,
    SURFACE_BUILD, SURFACE_SYSTEMD,
    DOCS_D, DOCS_DJ, DOCS_RUN, DOCS_CC, DOCS_SC, DOCS_RC, DOCS_PR, DOCS_QD,
)

# ===========================================================================
#  RUN FLAGS — set per container, on both engines
# ===========================================================================
RUN_FLAGS = [
    S("cap-add", "both", SURFACE_SECURITY, "-", "list",
      "Add capability", "Grants the container an extra Linux capability, "
      "for example NET_ADMIN or SYS_PTRACE.",
      cli="--cap-add", privilege="user", danger=2,
      gotcha="SYS_ADMIN is close to privileged in practice. It gets added so "
             "a container can 'just mount something' and opens up the whole "
             "isolation boundary.",
      docs=DOCS_RUN, tags=["security"]),

    S("cap-drop", "both", SURFACE_SECURITY, "-", "list",
      "Drop capability", "Removes capabilities from the default set. The "
      "recommended pattern is `--cap-drop=ALL` followed by adding back only "
      "what the workload needs.",
      cli="--cap-drop", privilege="user", docs=DOCS_RUN, tags=["security"]),

    S("privileged", "both", SURFACE_SECURITY, "-", "bool",
      "Privileged mode", "Grants every capability, opens device access, and "
      "disables seccomp and AppArmor.",
      default=False, cli="--privileged", privilege="user", danger=2,
      gotcha="Removes isolation entirely \u2014 the host's disks can be "
             "mounted from inside the container. Almost every real use can "
             "be replaced by the right capability plus a device mapping.",
      docs=DOCS_RUN, tags=["security", "dangerous"]),

    S("security-opt.no-new-privileges", "both", SURFACE_SECURITY, "-", "bool",
      "No new privileges", "Stops setuid binaries from escalating privileges.",
      default=False, cli="--security-opt no-new-privileges", privilege="user",
      docs=DOCS_RUN, tags=["security"]),

    S("security-opt.seccomp", "both", SURFACE_SECURITY, "-", "str",
      "Seccomp profile", "A per-container system call filter; `unconfined` "
      "turns filtering off.",
      cli="--security-opt seccomp=", privilege="user", danger=2,
      docs=DOCS_RUN, tags=["security"]),

    S("security-opt.label", "both", SURFACE_SECURITY, "-", "str",
      "SELinux label", "SELinux settings such as `disable`, `type:` or "
      "`level:`.",
      cli="--security-opt label=", privilege="user", docs=DOCS_RUN,
      tags=["security", "selinux"]),

    S("userns", "both", SURFACE_SECURITY, "-", "str",
      "User namespace", "`keep-id`, `nomap`, `auto`, `host`, or an explicit "
      "uidmap.",
      cli="--userns", privilege="user",
      gotcha="If files in a bind-mounted home directory show as 'nobody' "
             "under rootless Podman, `--userns=keep-id` is the fix.",
      docs=DOCS_PR, tags=["rootless", "permissions"]),

    S("read-only", "both", SURFACE_SECURITY, "-", "bool",
      "Read-only root filesystem", "Makes the root filesystem unwritable.",
      default=False, cli="--read-only", privilege="user",
      gotcha="Most images want to write to /tmp and /var/run; without a "
             "matching `--tmpfs /tmp` the container will not start.",
      docs=DOCS_RUN, tags=["security"]),

    S("tmpfs", "both", SURFACE_CONTAINER, "-", "list",
      "tmpfs mount", "Mounts a temporary filesystem held in memory.",
      cli="--tmpfs", privilege="user", docs=DOCS_RUN, tags=["container"]),

    S("cpus", "both", SURFACE_RESOURCE, "-", "str",
      "CPU count", "How many cores' worth of processing time the container "
      "may use, for example 1.5.",
      cli="--cpus", privilege="user",
      gotcha="Translated to cpu.max on cgroup v2. Under rootless, without "
             "the systemd cgroup manager and delegation, it is SILENTLY not "
             "applied.",
      docs=DOCS_RUN, tags=["resources", "cgroup"]),

    S("cpuset-cpus", "both", SURFACE_RESOURCE, "-", "str",
      "CPU pinning", "Which physical cores may be used, for example 0-3,8.",
      cli="--cpuset-cpus", privilege="user", docs=DOCS_RUN,
      tags=["resources", "performance"]),

    S("cpu-shares", "both", SURFACE_RESOURCE, "-", "int",
      "CPU shares", "Relative weight under contention; the default is 1024.",
      default=1024, cli="--cpu-shares", privilege="user", docs=DOCS_RUN,
      tags=["resources"]),

    S("memory", "both", SURFACE_RESOURCE, "-", "size",
      "Memory limit", "A hard ceiling; exceeding it gets the container "
      "killed by the OOM handler.",
      cli="--memory", privilege="user",
      gotcha="The JVM and Node read this limit from the cgroup. Without a "
             "limit they believe they can see all of the host's RAM and size "
             "their heap accordingly.",
      docs=DOCS_RUN, tags=["resources", "critical"]),

    S("memory-swap", "both", SURFACE_RESOURCE, "-", "size",
      "Memory plus swap limit", "Total memory and swap ceiling; -1 means "
      "unlimited swap.",
      cli="--memory-swap", privilege="user", docs=DOCS_RUN,
      tags=["resources"]),

    S("memory-reservation", "both", SURFACE_RESOURCE, "-", "size",
      "Soft memory limit", "A target the kernel tries to reclaim down to "
      "when the host is under memory pressure.",
      cli="--memory-reservation", privilege="user", docs=DOCS_RUN,
      tags=["resources"]),

    S("oom-kill-disable", "both", SURFACE_RESOURCE, "-", "bool",
      "Disable OOM kill", "Stops the container from being killed when "
      "memory runs out.",
      default=False, cli="--oom-kill-disable", privilege="user", danger=2,
      gotcha="Used without a memory limit, this can lock up the entire host.",
      docs=DOCS_RUN, tags=["resources", "dangerous"]),

    S("oom-score-adj", "both", SURFACE_RESOURCE, "-", "int",
      "OOM score adjustment", "How willing the kernel is to kill this "
      "container first, from -1000 to 1000.",
      default=0, cli="--oom-score-adj", privilege="user", docs=DOCS_RUN,
      tags=["resources"]),

    S("pids-limit", "both", SURFACE_RESOURCE, "-", "int",
      "PID limit", "Maximum number of processes and threads \u2014 the "
      "defence against a fork bomb.",
      cli="--pids-limit", privilege="user", docs=DOCS_RUN,
      tags=["resources", "security"]),

    S("device-read-bps", "both", SURFACE_RESOURCE, "-", "list",
      "Device read rate", "Read bandwidth limit per block device.",
      cli="--device-read-bps", privilege="user",
      gotcha="On cgroup v2 this applies to direct I/O only; writes that go "
             "through the page cache are not limited.",
      docs=DOCS_RUN, tags=["resources", "disk"]),

    S("device-write-bps", "both", SURFACE_RESOURCE, "-", "list",
      "Device write rate", "Write bandwidth limit per block device.",
      cli="--device-write-bps", privilege="user", docs=DOCS_RUN,
      tags=["resources", "disk"]),

    S("blkio-weight", "both", SURFACE_RESOURCE, "-", "int",
      "Block I/O weight", "Relative priority under disk contention, "
      "10 to 1000.",
      cli="--blkio-weight", privilege="user", docs=DOCS_RUN,
      tags=["resources", "disk"]),

    S("ulimit", "both", SURFACE_RESOURCE, "-", "list",
      "ulimit", "Per-container resource limits: nofile, nproc, memlock and "
      "the rest.",
      cli="--ulimit", privilege="user", docs=DOCS_RUN, tags=["resources"]),

    S("restart", "both", SURFACE_CONTAINER, "-", "choice",
      "Restart policy", "What happens when the container stops.",
      default="no", choices=["no", "on-failure", "always", "unless-stopped"],
      cli="--restart", privilege="user",
      gotcha="Under rootless Podman `--restart=always` does NOT survive a "
             "reboot. Persistent auto-start needs a Quadlet unit or a "
             "systemd unit.",
      docs=DOCS_RUN, tags=["rootless", "systemd", "critical"]),

    S("health-cmd", "both", SURFACE_CONTAINER, "-", "str",
      "Health command", "The command that decides whether the container is "
      "healthy.",
      cli="--health-cmd", privilege="user", docs=DOCS_RUN, tags=["container"]),

    S("health-interval", "both", SURFACE_CONTAINER, "-", "duration",
      "Health interval", "Time between health checks.",
      default="30s", cli="--health-interval", privilege="user",
      docs=DOCS_RUN, tags=["container"]),

    S("health-retries", "both", SURFACE_CONTAINER, "-", "int",
      "Health retries", "Consecutive failures before the container counts as "
      "unhealthy.",
      default=3, cli="--health-retries", privilege="user", docs=DOCS_RUN,
      tags=["container"]),

    S("health-start-period", "both", SURFACE_CONTAINER, "-", "duration",
      "Start grace period", "A window at startup during which failures do "
      "not count.",
      default="0s", cli="--health-start-period", privilege="user",
      gotcha="Without this, a slow-starting database is marked unhealthy "
             "before it has finished starting, and anything that depends on "
             "it never comes up.",
      docs=DOCS_RUN, tags=["container"]),

    S("volume.propagation", "both", SURFACE_CONTAINER, "-", "choice",
      "Mount propagation", "How mount events are shared between the host and "
      "the container.",
      default="rprivate", choices=["private", "rprivate", "shared", "rshared",
                                   "slave", "rslave"],
      cli="-v ...:rslave", privilege="user",
      gotcha="For a mount made inside the container to appear on the host "
             "you need `rshared`; with the default rprivate it silently does "
             "not.",
      docs="https://docs.docker.com/engine/storage/bind-mounts/",
      tags=["volume"]),

    S("volume.selinux", "both", SURFACE_CONTAINER, "-", "choice",
      "SELinux label on a volume", "`:z` applies a shared label, `:Z` a "
      "private one.",
      choices=["z", "Z"], cli="-v ...:z", privilege="user",
      gotcha="On SELinux systems a bind mount without this suffix fails with "
             "'Permission denied'. `:Z` locks the volume to one container, so "
             "using it on a shared volume cuts off every other container.",
      docs=DOCS_PR, tags=["volume", "selinux", "permissions"]),
]
