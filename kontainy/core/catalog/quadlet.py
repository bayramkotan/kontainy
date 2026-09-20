"""kontainy — settings catalogue part. See base.py for the field definitions."""

from .base import (
    S, SURFACE_DAEMON, SURFACE_STORAGE, SURFACE_NETWORK, SURFACE_REGISTRY,
    SURFACE_CONTAINER, SURFACE_SECURITY, SURFACE_RESOURCE, SURFACE_LOGGING,
    SURFACE_BUILD, SURFACE_SYSTEMD,
    DOCS_D, DOCS_DJ, DOCS_RUN, DOCS_CC, DOCS_SC, DOCS_RC, DOCS_PR, DOCS_QD,
)

# ===========================================================================
#  QUADLET — systemd integration, Podman only, entirely in user scope
# ===========================================================================
QUADLET = [
    S("Container.Image", "podman", SURFACE_SYSTEMD, "podman.quadlet", "str",
      "Image", "The image this unit runs.", privilege="user", docs=DOCS_QD,
      tags=["quadlet"]),

    S("Container.PublishPort", "podman", SURFACE_SYSTEMD, "podman.quadlet",
      "list",
      "Published ports", "Port mappings in host:container form.",
      privilege="user",
      gotcha="Rootless containers cannot bind host ports below 1024 by "
             "default; the `net.ipv4.ip_unprivileged_port_start` sysctl has "
             "to be lowered first.",
      docs=DOCS_QD, tags=["quadlet", "rootless", "network"]),

    S("Container.Volume", "podman", SURFACE_SYSTEMD, "podman.quadlet", "list",
      "Volumes", "Volumes and bind mounts to attach. A `.volume` unit can be "
      "referenced as `name.volume`.",
      privilege="user", docs=DOCS_QD, tags=["quadlet"]),

    S("Container.AutoUpdate", "podman", SURFACE_SYSTEMD, "podman.quadlet",
      "choice",
      "Auto-update", "With `registry`, podman-auto-update.timer watches this "
      "container for a newer image.",
      choices=["registry", "local"], privilege="user",
      gotcha="The timer must also be enabled: "
             "`systemctl --user enable --now podman-auto-update.timer`. "
             "Without it the label silently does nothing.",
      docs=DOCS_QD, tags=["quadlet", "updates"]),

    S("Container.UserNS", "podman", SURFACE_SYSTEMD, "podman.quadlet", "str",
      "User namespace", "keep-id, auto, or an explicit mapping.",
      privilege="user", docs=DOCS_QD, tags=["quadlet", "rootless"]),

    S("Container.Pod", "podman", SURFACE_SYSTEMD, "podman.quadlet", "str",
      "Pod", "The `.pod` unit this container joins.",
      privilege="user", docs=DOCS_QD, tags=["quadlet", "pod"]),

    S("Service.Restart", "podman", SURFACE_SYSTEMD, "podman.quadlet", "choice",
      "Restart", "systemd's restart policy for the service.",
      default="no", choices=["no", "on-failure", "always", "on-abnormal"],
      privilege="user", docs=DOCS_QD, tags=["quadlet"]),

    S("Install.WantedBy", "podman", SURFACE_SYSTEMD, "podman.quadlet", "str",
      "Enablement target", "Which target starts this unit.",
      default="default.target", privilege="user",
      gotcha="User units only start once the user logs in. For the unit to "
             "come up at boot, `loginctl enable-linger $USER` is required "
             "\u2014 the step most often skipped in a rootless setup.",
      docs=DOCS_QD, tags=["quadlet", "rootless", "critical"]),
]
