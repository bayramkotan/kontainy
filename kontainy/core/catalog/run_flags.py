"""kontainy — ayar kataloğu parçası. Tanımlar için base.py'ye bak."""

from .base import (
    S, SURFACE_DAEMON, SURFACE_STORAGE, SURFACE_NETWORK, SURFACE_REGISTRY,
    SURFACE_CONTAINER, SURFACE_SECURITY, SURFACE_RESOURCE, SURFACE_LOGGING,
    SURFACE_BUILD, SURFACE_SYSTEMD,
    DOCS_D, DOCS_DJ, DOCS_RUN, DOCS_CC, DOCS_SC, DOCS_RC, DOCS_PR, DOCS_QD,
)

# ===========================================================================
#  ÇALIŞTIRMA BAYRAKLARI — container başına (her iki motor)
# ===========================================================================
RUN_FLAGS = [
    S("cap-add", "both", SURFACE_SECURITY, "-", "list",
      "Yetenek Ekle", "Container'a ek Linux capability verir (örn. NET_ADMIN, SYS_PTRACE).",
      cli="--cap-add", privilege="user", danger=2,
      gotcha="SYS_ADMIN pratikte privileged'a yakındır; 'sadece mount edebilsin' diye "
             "eklenip izolasyonun tamamını açar.",
      docs=DOCS_RUN, tags=["güvenlik"]),

    S("cap-drop", "both", SURFACE_SECURITY, "-", "list",
      "Yetenek Kaldır", "Varsayılan yeteneklerden çıkarır. `--cap-drop=ALL` + gerekli "
      "olanları eklemek önerilen desendir.",
      cli="--cap-drop", privilege="user", docs=DOCS_RUN, tags=["güvenlik"]),

    S("privileged", "both", SURFACE_SECURITY, "-", "bool",
      "Ayrıcalıklı Mod", "Tüm yetenekleri verir, aygıt erişimini açar, seccomp ve "
      "AppArmor'u devre dışı bırakır.",
      default=False, cli="--privileged", privilege="user", danger=2,
      gotcha="İzolasyonun tamamını kaldırır — container içinden host'un diskleri "
             "mount edilebilir. Neredeyse her kullanım, doğru capability ve aygıt "
             "eşlemesiyle değiştirilebilir.",
      docs=DOCS_RUN, tags=["güvenlik", "tehlikeli"]),

    S("security-opt.no-new-privileges", "both", SURFACE_SECURITY, "-", "bool",
      "Yeni Ayrıcalık Yok", "setuid ikili dosyalarının yetki yükseltmesini engeller.",
      default=False, cli="--security-opt no-new-privileges", privilege="user",
      docs=DOCS_RUN, tags=["güvenlik"]),

    S("security-opt.seccomp", "both", SURFACE_SECURITY, "-", "str",
      "Seccomp Profili", "Container'a özel sistem çağrısı filtresi; `unconfined` kapatır.",
      cli="--security-opt seccomp=", privilege="user", danger=2,
      docs=DOCS_RUN, tags=["güvenlik"]),

    S("security-opt.label", "both", SURFACE_SECURITY, "-", "str",
      "SELinux Etiketi", "`disable`, `type:`, `level:` gibi SELinux ayarları.",
      cli="--security-opt label=", privilege="user", docs=DOCS_RUN,
      tags=["güvenlik", "selinux"]),

    S("userns", "both", SURFACE_SECURITY, "-", "str",
      "Kullanıcı Ad Alanı", "`keep-id`, `nomap`, `auto`, `host` veya açık uidmap.",
      cli="--userns", privilege="user",
      gotcha="Rootless Podman'da ev dizini bind mount edildiğinde dosyalar 'nobody' "
             "görünüyorsa çözüm `--userns=keep-id`.",
      docs=DOCS_PR, tags=["rootless", "izin"]),

    S("read-only", "both", SURFACE_SECURITY, "-", "bool",
      "Salt Okunur Kök", "Kök dosya sistemini yazılamaz yapar.",
      default=False, cli="--read-only", privilege="user",
      gotcha="Çoğu imaj /tmp ve /var/run'a yazmak ister; `--tmpfs /tmp` ile birlikte "
             "kullanılmazsa container başlamaz.",
      docs=DOCS_RUN, tags=["güvenlik"]),

    S("tmpfs", "both", SURFACE_CONTAINER, "-", "list",
      "tmpfs Bağlama", "Bellekte tutulan geçici dosya sistemi bağlar.",
      cli="--tmpfs", privilege="user", docs=DOCS_RUN, tags=["container"]),

    S("cpus", "both", SURFACE_RESOURCE, "-", "str",
      "CPU Sayısı", "Kaç çekirdeklik işlem gücü kullanılabileceği (örn. 1.5).",
      cli="--cpus", privilege="user",
      gotcha="cgroup v2'de cpu.max'a çevrilir. Rootless'ta systemd cgroup yöneticisi "
             "ve delegasyon yoksa SESSİZCE uygulanmaz.",
      docs=DOCS_RUN, tags=["kaynak", "cgroup"]),

    S("cpuset-cpus", "both", SURFACE_RESOURCE, "-", "str",
      "CPU Sabitleme", "Hangi fiziksel çekirdeklerin kullanılacağı (örn. 0-3,8).",
      cli="--cpuset-cpus", privilege="user", docs=DOCS_RUN, tags=["kaynak", "performans"]),

    S("cpu-shares", "both", SURFACE_RESOURCE, "-", "int",
      "CPU Payı", "Çekişme anındaki göreli ağırlık (varsayılan 1024).",
      default=1024, cli="--cpu-shares", privilege="user", docs=DOCS_RUN, tags=["kaynak"]),

    S("memory", "both", SURFACE_RESOURCE, "-", "size",
      "Bellek Sınırı", "Sert bellek üst sınırı; aşılırsa container OOM ile öldürülür.",
      cli="--memory", privilege="user",
      gotcha="JVM ve Node bu sınırı cgroup'tan okur; sınır konmazsa host'un tüm RAM'ini "
             "gördüklerini sanıp heap'i ona göre ayarlarlar.",
      docs=DOCS_RUN, tags=["kaynak", "kritik"]),

    S("memory-swap", "both", SURFACE_RESOURCE, "-", "size",
      "Bellek + Takas Sınırı", "Toplam bellek+swap sınırı; -1 sınırsız swap demektir.",
      cli="--memory-swap", privilege="user", docs=DOCS_RUN, tags=["kaynak"]),

    S("memory-reservation", "both", SURFACE_RESOURCE, "-", "size",
      "Yumuşak Bellek Sınırı", "Baskı altında geri alınmaya çalışılan hedef.",
      cli="--memory-reservation", privilege="user", docs=DOCS_RUN, tags=["kaynak"]),

    S("oom-kill-disable", "both", SURFACE_RESOURCE, "-", "bool",
      "OOM Öldürmeyi Kapat", "Bellek tükendiğinde container'ın öldürülmemesi.",
      default=False, cli="--oom-kill-disable", privilege="user", danger=2,
      gotcha="Bellek sınırı olmadan kullanılırsa host'un tamamını kilitler.",
      docs=DOCS_RUN, tags=["kaynak", "tehlikeli"]),

    S("oom-score-adj", "both", SURFACE_RESOURCE, "-", "int",
      "OOM Puan Ayarı", "Çekirdeğin bu container'ı öldürme önceliği (-1000..1000).",
      default=0, cli="--oom-score-adj", privilege="user", docs=DOCS_RUN, tags=["kaynak"]),

    S("pids-limit", "both", SURFACE_RESOURCE, "-", "int",
      "PID Sınırı", "Azami süreç/iş parçacığı sayısı — fork bombasına karşı.",
      cli="--pids-limit", privilege="user", docs=DOCS_RUN, tags=["kaynak", "güvenlik"]),

    S("device-read-bps", "both", SURFACE_RESOURCE, "-", "list",
      "Aygıt Okuma Hızı", "Blok aygıt başına okuma bant genişliği sınırı.",
      cli="--device-read-bps", privilege="user",
      gotcha="cgroup v2'de yalnızca doğrudan G/Ç için çalışır; sayfa önbelleği "
             "üzerinden yapılan yazmalar sınırlanmaz.",
      docs=DOCS_RUN, tags=["kaynak", "disk"]),

    S("device-write-bps", "both", SURFACE_RESOURCE, "-", "list",
      "Aygıt Yazma Hızı", "Blok aygıt başına yazma bant genişliği sınırı.",
      cli="--device-write-bps", privilege="user", docs=DOCS_RUN, tags=["kaynak", "disk"]),

    S("blkio-weight", "both", SURFACE_RESOURCE, "-", "int",
      "Blok G/Ç Ağırlığı", "Disk çekişmesinde göreli öncelik (10-1000).",
      cli="--blkio-weight", privilege="user", docs=DOCS_RUN, tags=["kaynak", "disk"]),

    S("ulimit", "both", SURFACE_RESOURCE, "-", "list",
      "ulimit", "Container başına kaynak sınırları (nofile, nproc, memlock...).",
      cli="--ulimit", privilege="user", docs=DOCS_RUN, tags=["kaynak"]),

    S("restart", "both", SURFACE_CONTAINER, "-", "choice",
      "Yeniden Başlatma Politikası", "Container durduğunda ne yapılacağı.",
      default="no", choices=["no", "on-failure", "always", "unless-stopped"],
      cli="--restart", privilege="user",
      gotcha="Rootless Podman'da `--restart=always` sistem yeniden başlatıldığında "
             "ÇALIŞMAZ; kalıcı otomatik başlatma için Quadlet veya systemd birimi gerekir.",
      docs=DOCS_RUN, tags=["rootless", "systemd", "kritik"]),

    S("health-cmd", "both", SURFACE_CONTAINER, "-", "str",
      "Sağlık Komutu", "Container'ın sağlıklı olup olmadığını sınayan komut.",
      cli="--health-cmd", privilege="user", docs=DOCS_RUN, tags=["container"]),

    S("health-interval", "both", SURFACE_CONTAINER, "-", "duration",
      "Sağlık Aralığı", "Sağlık kontrolleri arasındaki süre.",
      default="30s", cli="--health-interval", privilege="user", docs=DOCS_RUN),

    S("health-retries", "both", SURFACE_CONTAINER, "-", "int",
      "Sağlık Deneme Sayısı", "Sağlıksız sayılmadan önceki ardışık başarısızlık adedi.",
      default=3, cli="--health-retries", privilege="user", docs=DOCS_RUN),

    S("health-start-period", "both", SURFACE_CONTAINER, "-", "duration",
      "Başlangıç Toleransı", "Başlangıçtaki başarısızlıkların sayılmayacağı süre.",
      default="0s", cli="--health-start-period", privilege="user",
      gotcha="Yavaş açılan veritabanlarında bu değer verilmezse container daha ayağa "
             "kalkmadan sağlıksız işaretlenir ve bağımlı servisler başlamaz.",
      docs=DOCS_RUN, tags=["container"]),

    S("volume.propagation", "both", SURFACE_CONTAINER, "-", "choice",
      "Bağlama Yayılımı", "Host ile container arasındaki mount olaylarının paylaşımı.",
      default="rprivate", choices=["private", "rprivate", "shared", "rshared",
                                    "slave", "rslave"],
      cli="-v ...:rslave", privilege="user",
      gotcha="Container içinde yapılan mount'ların host'ta görünmesi için `rshared` "
             "gerekir; varsayılan rprivate ile sessizce görünmez.",
      docs="https://docs.docker.com/engine/storage/bind-mounts/", tags=["volume"]),

    S("volume.selinux", "both", SURFACE_CONTAINER, "-", "choice",
      "SELinux Etiketi (volume)", "`:z` paylaşılan, `:Z` özel etiket uygular.",
      choices=["z", "Z"], cli="-v ...:z", privilege="user",
      gotcha="SELinux açık sistemlerde bu son ek olmadan bind mount 'Permission denied' "
             "verir. `:Z` volume'u tek container'a kilitler — paylaşılan volume'da "
             "kullanılırsa diğer container erişimini kaybeder.",
      docs=DOCS_PR, tags=["volume", "selinux", "izin"]),
]
