"""kontainy — ayar kataloğu parçası. Tanımlar için base.py'ye bak."""

from .base import (
    S, SURFACE_DAEMON, SURFACE_STORAGE, SURFACE_NETWORK, SURFACE_REGISTRY,
    SURFACE_CONTAINER, SURFACE_SECURITY, SURFACE_RESOURCE, SURFACE_LOGGING,
    SURFACE_BUILD, SURFACE_SYSTEMD,
    DOCS_D, DOCS_DJ, DOCS_RUN, DOCS_CC, DOCS_SC, DOCS_RC, DOCS_PR, DOCS_QD,
)

# ===========================================================================
#  QUADLET — systemd entegrasyonu (yalnızca Podman, tamamen kullanıcı kapsamı)
# ===========================================================================
QUADLET = [
    S("Container.Image", "podman", SURFACE_SYSTEMD, "podman.quadlet", "str",
      "Imaj", "Birimin çalıştıracağı imaj.", privilege="user", docs=DOCS_QD,
      tags=["quadlet"]),

    S("Container.PublishPort", "podman", SURFACE_SYSTEMD, "podman.quadlet", "list",
      "Yayınlanan Portlar", "host:container biçiminde port eşlemeleri.",
      privilege="user",
      gotcha="Rootless'ta 1024 altı portlar varsayılan olarak bağlanamaz; "
             "`net.ipv4.ip_unprivileged_port_start` sysctl değeri düşürülmelidir.",
      docs=DOCS_QD, tags=["quadlet", "rootless", "ağ"]),

    S("Container.Volume", "podman", SURFACE_SYSTEMD, "podman.quadlet", "list",
      "Volume'lar", "Bağlanacak volume ve bind mount'lar. `.volume` birimine "
      "`ad.volume` ile atıf yapılabilir.",
      privilege="user", docs=DOCS_QD, tags=["quadlet"]),

    S("Container.AutoUpdate", "podman", SURFACE_SYSTEMD, "podman.quadlet", "choice",
      "Otomatik Güncelleme", "`registry` seçildiğinde podman-auto-update.timer bu "
      "container'ı yeni imaj için izler.",
      choices=["registry", "local"], privilege="user",
      gotcha="Timer'ın ayrıca etkinleştirilmesi gerekir: "
             "`systemctl --user enable --now podman-auto-update.timer`.",
      docs=DOCS_QD, tags=["quadlet", "güncelleme"]),

    S("Container.UserNS", "podman", SURFACE_SYSTEMD, "podman.quadlet", "str",
      "Kullanıcı Ad Alanı", "keep-id, auto veya açık eşleme.",
      privilege="user", docs=DOCS_QD, tags=["quadlet", "rootless"]),

    S("Container.Pod", "podman", SURFACE_SYSTEMD, "podman.quadlet", "str",
      "Pod", "Bu container'ın katılacağı `.pod` birimi.",
      privilege="user", docs=DOCS_QD, tags=["quadlet", "pod"]),

    S("Service.Restart", "podman", SURFACE_SYSTEMD, "podman.quadlet", "choice",
      "Yeniden Başlatma", "systemd'nin servis yeniden başlatma politikası.",
      default="no", choices=["no", "on-failure", "always", "on-abnormal"],
      privilege="user", docs=DOCS_QD, tags=["quadlet"]),

    S("Install.WantedBy", "podman", SURFACE_SYSTEMD, "podman.quadlet", "str",
      "Etkinleştirme Hedefi", "Birimin hangi hedefle başlatılacağı.",
      default="default.target", privilege="user",
      gotcha="Kullanıcı birimleri yalnızca kullanıcı oturum açtığında başlar. "
             "Açılışta başlaması için `loginctl enable-linger $USER` şarttır — "
             "rootless'ta en sık atlanan adım.",
      docs=DOCS_QD, tags=["quadlet", "rootless", "kritik"]),
]
