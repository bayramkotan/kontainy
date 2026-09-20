"""kontainy — ayar kataloğu parçası. Tanımlar için base.py'ye bak."""

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
    S("containers.log_driver", "podman", SURFACE_LOGGING, "podman.containers", "choice",
      "Log Sürücüsü", "Container çıktısının nereye yazılacağı.",
      default="journald", choices=["journald", "k8s-file", "json-file", "none", "passthrough"],
      privilege="user", cli="--log-driver",
      gotcha="journald varsayılanı `podman logs` çıktısını systemd journal'ına bağlar; "
             "rootless'ta journal boyut sınırları devreye girer ve eski loglar sessizce silinir.",
      docs=DOCS_CC, tags=["log"]),

    S("containers.log_size_max", "podman", SURFACE_LOGGING, "podman.containers", "size",
      "Azami Log Boyutu", "Container başına log boyut sınırı (-1 = sınırsız).",
      default=-1, privilege="user", cli="--log-opt max-size", docs=DOCS_CC, tags=["log", "disk"]),

    S("containers.cgroup_manager", "podman", SURFACE_RESOURCE, "podman.containers", "choice",
      "cgroup Yöneticisi", "Kaynak sınırlarının hangi mekanizmayla uygulanacağı.",
      default="systemd", choices=["systemd", "cgroupfs"], privilege="user", danger=1,
      gotcha="Rootless + cgroup v2 için systemd gereklidir; cgroupfs seçilirse bellek ve "
             "CPU sınırları SESSİZCE uygulanmaz — hata verilmez, sınır yok sayılır.",
      docs=DOCS_CC, tags=["cgroup", "rootless", "kritik"]),

    S("containers.cgroupns", "podman", SURFACE_RESOURCE, "podman.containers", "choice",
      "cgroup Ad Alanı", "Container'ın kendi cgroup ağacını nasıl göreceği.",
      default="private", choices=["private", "host"], privilege="user",
      cli="--cgroupns", docs=DOCS_CC, tags=["cgroup"]),

    S("containers.cgroups", "podman", SURFACE_RESOURCE, "podman.containers", "choice",
      "cgroup Kullanımı", "Podman'ın cgroup oluşturup oluşturmayacağı.",
      default="enabled", choices=["enabled", "disabled", "no-conmon", "split"],
      privilege="user", danger=1, docs=DOCS_CC, tags=["cgroup"]),

    S("containers.default_capabilities", "podman", SURFACE_SECURITY, "podman.containers", "list",
      "Varsayılan Yetenekler", "Her container'a verilecek Linux capability listesi.",
      default=["CHOWN", "DAC_OVERRIDE", "FOWNER", "FSETID", "KILL", "NET_BIND_SERVICE",
               "SETFCAP", "SETGID", "SETPCAP", "SETUID", "SYS_CHROOT"],
      privilege="user", cli="--cap-add / --cap-drop", danger=2,
      gotcha="Docker'ın varsayılan listesi Podman'ınkinden farklıdır (Docker AUDIT_WRITE ve "
             "MKNOD içerir). Docker'da çalışan bir imaj Podman'da yetki hatası verebilir.",
      docs=DOCS_CC, tags=["güvenlik", "uyumluluk"]),

    S("containers.default_sysctls", "podman", SURFACE_SECURITY, "podman.containers", "list",
      "Varsayılan sysctl Değerleri", "Her container'a uygulanacak çekirdek parametreleri.",
      default=["net.ipv4.ping_group_range=0 0"], privilege="user", cli="--sysctl",
      docs=DOCS_CC, tags=["güvenlik"]),

    S("containers.default_ulimits", "podman", SURFACE_RESOURCE, "podman.containers", "list",
      "Varsayılan ulimit", "Kaynak sınırları, örneğin `nofile=65536:65536`.",
      default=[], privilege="user", cli="--ulimit", docs=DOCS_CC, tags=["kaynak"]),

    S("containers.pids_limit", "podman", SURFACE_RESOURCE, "podman.containers", "int",
      "PID Sınırı", "Container içindeki azami süreç sayısı (0 = sınırsız).",
      default=2048, privilege="user", cli="--pids-limit",
      gotcha="Rootless'ta cgroup v2 ve systemd yoksa uygulanmaz.",
      docs=DOCS_CC, tags=["kaynak"]),

    S("containers.shm_size", "podman", SURFACE_RESOURCE, "podman.containers", "size",
      "/dev/shm Boyutu", "Paylaşılan bellek alanı.",
      default="65536k", privilege="user", cli="--shm-size", docs=DOCS_CC, tags=["kaynak", "ml"]),

    S("containers.userns", "podman", SURFACE_SECURITY, "podman.containers", "choice",
      "Kullanıcı Ad Alanı Modu", "Container içindeki kullanıcıların host'a nasıl eşleneceği.",
      default="host", choices=["host", "keep-id", "nomap", "auto", "private"],
      privilege="user", cli="--userns", danger=1,
      gotcha="`keep-id` bind mount edilen ev dizini dosyalarının sahipliğinin doğru "
             "görünmesini sağlar; rootless'ta volume izin hatalarının standart çözümüdür.",
      docs=DOCS_PR, tags=["rootless", "izin", "kritik"]),

    S("containers.netns", "podman", SURFACE_NETWORK, "podman.containers", "choice",
      "Ağ Ad Alanı", "Varsayılan ağ yalıtımı modu.",
      default="private", choices=["private", "host", "none", "bridge", "slirp4netns", "pasta"],
      privilege="user", cli="--network", docs=DOCS_CC, tags=["ağ"]),

    S("containers.ipcns", "podman", SURFACE_SECURITY, "podman.containers", "choice",
      "IPC Ad Alanı", "Paylaşılan bellek ad alanı modu.",
      default="shareable", choices=["host", "private", "shareable", "none"],
      privilege="user", cli="--ipc", docs=DOCS_CC),

    S("containers.pidns", "podman", SURFACE_SECURITY, "podman.containers", "choice",
      "PID Ad Alanı", "Süreç ad alanı modu.",
      default="private", choices=["private", "host"], privilege="user",
      cli="--pid", docs=DOCS_CC),

    S("containers.utsns", "podman", SURFACE_SECURITY, "podman.containers", "choice",
      "UTS Ad Alanı", "Hostname ad alanı modu.",
      default="private", choices=["private", "host"], privilege="user",
      cli="--uts", docs=DOCS_CC),

    S("containers.init", "podman", SURFACE_CONTAINER, "podman.containers", "bool",
      "init Süreci", "PID 1 olarak zombi süreçleri toplayan bir init eklenmesi.",
      default=False, privilege="user", cli="--init",
      gotcha="Uygulamanın sinyalleri doğru işlemediği imajlarda `podman stop` 10 saniye "
             "bekleyip SIGKILL'e düşer; init bunu çözer.",
      docs=DOCS_CC, tags=["container"]),

    S("containers.tz", "podman", SURFACE_CONTAINER, "podman.containers", "str",
      "Saat Dilimi", "Container'ın saat dilimi; `local` host'unkini kullanır.",
      privilege="user", cli="--tz", docs=DOCS_CC, tags=["container"]),

    S("containers.umask", "podman", SURFACE_CONTAINER, "podman.containers", "str",
      "umask", "Container içindeki varsayılan dosya izin maskesi.",
      default="0022", privilege="user", cli="--umask", docs=DOCS_CC),

    S("containers.no_hosts", "podman", SURFACE_NETWORK, "podman.containers", "bool",
      "/etc/hosts Üretme", "Podman'ın /etc/hosts dosyasını yönetmemesi.",
      default=False, privilege="user", cli="--no-hosts", docs=DOCS_CC, tags=["ağ"]),

    S("containers.dns_servers", "podman", SURFACE_NETWORK, "podman.containers", "list",
      "DNS Sunucuları", "Container'lara verilecek DNS adresleri.",
      default=[], privilege="user", cli="--dns", docs=DOCS_CC, tags=["ağ", "dns"]),

    S("containers.env", "podman", SURFACE_CONTAINER, "podman.containers", "list",
      "Varsayılan Ortam Değişkenleri", "Her container'a otomatik eklenecek değişkenler.",
      default=["PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin", "TERM=xterm"],
      privilege="user", cli="--env", docs=DOCS_CC),

    S("containers.apparmor_profile", "podman", SURFACE_SECURITY, "podman.containers", "str",
      "AppArmor Profili", "Container'lara uygulanacak AppArmor profili.",
      default="containers-default-0.50.1", privilege="user",
      cli="--security-opt apparmor=", danger=1, docs=DOCS_CC, tags=["güvenlik"]),

    S("containers.seccomp_profile", "podman", SURFACE_SECURITY, "podman.containers", "str",
      "Seccomp Profili", "Sistem çağrısı filtre profilinin yolu.",
      default="/usr/share/containers/seccomp.json", privilege="user",
      cli="--security-opt seccomp=", danger=2, docs=DOCS_CC, tags=["güvenlik"]),

    S("containers.read_only", "podman", SURFACE_SECURITY, "podman.containers", "bool",
      "Salt Okunur Kök", "Container kök dosya sisteminin yazılamaz olması.",
      default=False, privilege="user", cli="--read-only", docs=DOCS_CC, tags=["güvenlik"]),

    S("containers.volumes", "podman", SURFACE_CONTAINER, "podman.containers", "list",
      "Varsayılan Volume'lar", "Her container'a otomatik bağlanacak volume'lar.",
      default=[], privilege="user", cli="--volume", docs=DOCS_CC),

    # --- [engine] ---
    S("engine.runtime", "podman", SURFACE_DAEMON, "podman.containers", "choice",
      "OCI Çalışma Zamanı", "Container'ı gerçekte başlatan program.",
      default="crun", choices=["crun", "runc", "kata", "runsc"], privilege="user",
      gotcha="crun C ile yazılmıştır ve rootless + cgroup v2'de runc'tan belirgin hızlıdır; "
             "Arch/CachyOS'ta varsayılandır.",
      docs=DOCS_CC, tags=["runtime", "performans"]),

    S("engine.events_logger", "podman", SURFACE_DAEMON, "podman.containers", "choice",
      "Olay Günlükçüsü", "`podman events` akışının nereden okunacağı.",
      default="journald", choices=["journald", "file", "none"], privilege="user",
      gotcha="`none` seçilirse kontainy'in olay akışı çalışmaz ve tablo yalnızca "
             "yoklama (polling) ile güncellenir.",
      docs=DOCS_CC, tags=["olay"]),

    S("engine.pull_policy", "podman", SURFACE_REGISTRY, "podman.containers", "choice",
      "Çekme Politikası", "Imaj yereldeyken yine de çekilip çekilmeyeceği.",
      default="missing", choices=["always", "missing", "never", "newer"],
      privilege="user", cli="--pull", docs=DOCS_CC, tags=["registry"]),

    S("engine.image_default_transport", "podman", SURFACE_REGISTRY, "podman.containers", "str",
      "Varsayılan Taşıyıcı", "Imaj adlarına ön ek olarak eklenecek taşıyıcı.",
      default="docker://", privilege="user", docs=DOCS_CC, tags=["registry"]),

    S("engine.infra_image", "podman", SURFACE_DAEMON, "podman.containers", "str",
      "Infra Imajı", "Pod'ların ad alanlarını tutan altyapı container'ının imajı.",
      privilege="user", docs=DOCS_CC, tags=["pod"]),

    S("engine.compression_format", "podman", SURFACE_REGISTRY, "podman.containers", "choice",
      "Sıkıştırma Biçimi", "Imaj gönderirken kullanılacak katman sıkıştırması.",
      default="gzip", choices=["gzip", "zstd", "zstd:chunked"], privilege="user",
      gotcha="zstd:chunked kısmi katman çekmeyi mümkün kılar ama eski registry'ler "
             "ve eski Docker sürümleri bu katmanları okuyamaz.",
      docs=DOCS_CC, tags=["registry", "hız"]),

    S("engine.database_backend", "podman", SURFACE_DAEMON, "podman.containers", "choice",
      "Veritabanı Arka Ucu", "Podman'ın durum deposu.",
      default="sqlite", choices=["sqlite", "boltdb"], privilege="user", danger=1,
      gotcha="Değiştirmek mevcut container kayıtlarını görünmez yapar; geçiş "
             "otomatik değildir.",
      docs=DOCS_CC, tags=["kritik"]),

    S("engine.stop_timeout", "podman", SURFACE_CONTAINER, "podman.containers", "duration",
      "Durdurma Zaman Aşımı", "SIGTERM sonrası SIGKILL'e kadar beklenecek saniye.",
      default=10, privilege="user", cli="--stop-timeout", docs=DOCS_CC),

    S("engine.service_timeout", "podman", SURFACE_DAEMON, "podman.containers", "duration",
      "Servis Zaman Aşımı", "API servisinin boşta kapanma süresi (0 = kapanma).",
      default=5, privilege="user", docs=DOCS_CC, tags=["soket"]),

    S("engine.volume_path", "podman", SURFACE_STORAGE, "podman.containers", "str",
      "Volume Dizini", "Adlandırılmış volume'ların tutulduğu yer.",
      privilege="user", docs=DOCS_CC, tags=["disk"]),

    S("engine.helper_binaries_dir", "podman", SURFACE_DAEMON, "podman.containers", "list",
      "Yardımcı Program Dizinleri", "catatonit, slirp4netns, pasta gibi yardımcıların "
      "aranacağı dizinler.",
      privilege="user",
      gotcha="Bu liste eksikse rootless ağ sessizce çalışmaz — 'container ayakta ama "
             "internete çıkamıyor' belirtisi.",
      docs=DOCS_CC, tags=["rootless", "ağ"]),

    # --- [network] ---
    S("network.network_backend", "podman", SURFACE_NETWORK, "podman.containers", "choice",
      "Ağ Arka Ucu", "Container ağlarını kuran alt sistem.",
      default="netavark", choices=["netavark", "cni"], privilege="user", danger=2,
      gotcha="Geçiş yapıldığında mevcut ağ tanımları TAŞINMAZ; eski CNI ağları "
             "netavark tarafından görülmez. `podman system reset` gerekebilir.",
      docs=DOCS_CC, tags=["ağ", "kritik"]),

    S("network.default_rootless_network_cmd", "podman", SURFACE_NETWORK,
      "podman.containers", "choice",
      "Rootless Ağ Programı", "Rootless container'ların dış ağa nasıl bağlanacağı.",
      default="pasta", choices=["pasta", "slirp4netns"], privilege="user",
      gotcha="pasta daha hızlıdır ve gerçek kaynak IP'yi korur; slirp4netns tüm trafiği "
             "10.0.2.100 gibi görünür yapar. Kaynak IP'ye bakan uygulamalarda fark eder.",
      docs=DOCS_CC, tags=["rootless", "ağ", "performans"]),

    S("network.default_subnet", "podman", SURFACE_NETWORK, "podman.containers", "str",
      "Varsayılan Alt Ağ", "Podman'ın varsayılan ağının CIDR bloğu.",
      default="10.88.0.0/16", privilege="user",
      gotcha="Docker'ın 172.17'siyle çakışmaz ama kurumsal 10.x ağlarıyla çakışabilir.",
      docs=DOCS_CC, tags=["ağ", "vpn"]),

    S("network.default_subnet_pools", "podman", SURFACE_NETWORK, "podman.containers", "list",
      "Alt Ağ Havuzları", "Yeni ağların üretileceği bloklar.",
      privilege="user", docs=DOCS_CC, tags=["ağ"]),

    S("network.firewall_driver", "podman", SURFACE_NETWORK, "podman.containers", "choice",
      "Güvenlik Duvarı Sürücüsü", "netavark'ın kural yazacağı arka uç.",
      choices=["iptables", "nftables", "firewalld", "none"], privilege="user", danger=1,
      gotcha="Arch/CachyOS nftables kullanır; iptables-nft uyumluluk katmanı yoksa "
             "kurallar yazılamaz ve port yayınlama sessizce çalışmaz.",
      docs=DOCS_CC, tags=["ağ", "arch", "güvenlik duvarı"]),

    S("network.dns_bind_port", "podman", SURFACE_NETWORK, "podman.containers", "int",
      "aardvark-dns Portu", "Container DNS sunucusunun dinleyeceği port.",
      default=53, privilege="user", docs=DOCS_CC, tags=["ağ", "dns"]),
]

# ===========================================================================
#  PODMAN — storage.conf
# ===========================================================================
PODMAN_STORAGE = [
    S("storage.driver", "podman", SURFACE_STORAGE, "podman.storage", "choice",
      "Depolama Sürücüsü", "Katmanlı dosya sistemi arka ucu.",
      default="overlay", choices=["overlay", "vfs", "btrfs", "zfs"],
      privilege="user", danger=2,
      gotcha="Değiştirildiğinde eski sürücüdeki imajlar erişilemez olur. vfs her yerde "
             "çalışır ama her katmanı tam kopyalar — disk kullanımı katlanır.",
      docs=DOCS_SC, tags=["disk", "kritik"]),

    S("storage.graphroot", "podman", SURFACE_STORAGE, "podman.storage", "str",
      "Imaj Deposu Dizini", "Imaj ve container katmanlarının kalıcı olarak tutulduğu yer.",
      default="~/.local/share/containers/storage", privilege="user", danger=1,
      gotcha="Rootless'ta ev dizinindedir; ev dizini NFS üzerindeyse overlay çalışmaz "
             "ve Podman sessizce vfs'e düşer.",
      docs=DOCS_SC, tags=["disk", "taşıma"]),

    S("storage.runroot", "podman", SURFACE_STORAGE, "podman.storage", "str",
      "Çalışma Zamanı Dizini", "Çalışan container durumunun tutulduğu geçici alan.",
      default="$XDG_RUNTIME_DIR/containers", privilege="user", docs=DOCS_SC, tags=["disk"]),

    S("storage.transient_store", "podman", SURFACE_STORAGE, "podman.storage", "bool",
      "Geçici Depo", "Container meta verisinin yeniden başlatmada silinmesi.",
      default=False, privilege="user", danger=1, docs=DOCS_SC),

    S("storage.options.mount_program", "podman", SURFACE_STORAGE, "podman.storage", "str",
      "Bağlama Programı", "Rootless overlay için kullanılacak program "
      "(genellikle fuse-overlayfs).",
      privilege="user",
      gotcha="Modern çekirdeklerde rootless native overlay desteklenir ve fuse-overlayfs "
             "gereksiz yere yavaşlatır; bu satır eski kurulumlardan kalıntı olarak sık görülür.",
      docs=DOCS_SC, tags=["rootless", "performans"]),

    S("storage.options.mountopt", "podman", SURFACE_STORAGE, "podman.storage", "str",
      "Bağlama Seçenekleri", "Örneğin `nodev,metacopy=on`.",
      default="nodev", privilege="user", docs=DOCS_SC),

    S("storage.options.additionalimagestores", "podman", SURFACE_STORAGE,
      "podman.storage", "list",
      "Ek Imaj Depoları", "Salt okunur olarak eklenecek imaj depoları.",
      default=[], privilege="user",
      gotcha="Birden çok kullanıcının aynı imajları paylaşması için tek yol; her kullanıcının "
             "aynı imajı ayrıca çekmesini önler.",
      docs=DOCS_SC, tags=["disk", "paylaşım"]),

    S("storage.options.ignore_chown_errors", "podman", SURFACE_STORAGE, "podman.storage", "bool",
      "chown Hatalarını Yok Say", "Rootless'ta yetersiz UID aralığında imaj çekilebilmesi.",
      default=False, privilege="user", danger=1,
      gotcha="Belirti: 'potentially insufficient UIDs or GIDs available in user namespace'. "
             "Asıl çözüm /etc/subuid aralığını büyütmektir; bu anahtar sorunu gizler.",
      docs=DOCS_SC, tags=["rootless", "izin"]),

    S("storage.options.size", "podman", SURFACE_STORAGE, "podman.storage", "size",
      "Katman Boyut Sınırı", "Container yazılabilir katmanı için kota.",
      privilege="user", docs=DOCS_SC, tags=["disk", "kota"]),

    S("storage.options.pull_options", "podman", SURFACE_REGISTRY, "podman.storage", "dict",
      "Çekme Seçenekleri", "`enable_partial_images`, `use_hard_links`, `convert_images`.",
      privilege="user", docs=DOCS_SC, tags=["registry", "hız"]),
]

# ===========================================================================
#  PODMAN — registries.conf
# ===========================================================================
PODMAN_REGISTRIES = [
    S("unqualified-search-registries", "podman", SURFACE_REGISTRY,
      "podman.registries", "list",
      "Niteliksiz Arama Registry'leri", "`podman pull nginx` gibi kısa adların hangi "
      "registry'lerde bu sırayla aranacağı.",
      default=["docker.io"], privilege="user",
      gotcha="Docker her zaman docker.io varsayar; Podman varsaymaz. Bu liste boşsa "
             "kısa adlı her pull başarısız olur — Docker'dan gelenlerin ilk çarptığı duvar.",
      docs=DOCS_RC, tags=["registry", "kritik", "uyumluluk"]),

    S("short-name-mode", "podman", SURFACE_REGISTRY, "podman.registries", "choice",
      "Kısa Ad Modu", "Kısa imaj adı çözümlenirken nasıl davranılacağı.",
      default="enforcing", choices=["enforcing", "permissive", "disabled"],
      privilege="user",
      gotcha="`enforcing` etkileşimli terminalde kullanıcıya seçim listesi sunar; "
             "ETKİLEŞİMSİZ ortamda (script, systemd, GUI) doğrudan hata verir. "
             "kontainy gibi bir arayüzden pull yapılırken bu ayar mutlaka "
             "dikkate alınmalıdır.",
      docs=DOCS_RC, tags=["registry", "kritik", "gui"]),

    S("credential-helpers", "podman", SURFACE_REGISTRY, "podman.registries", "list",
      "Kimlik Yardımcıları", "Registry parolalarının okunacağı yardımcı programlar.",
      default=["containers-auth.json"], privilege="user", docs=DOCS_RC, tags=["registry"]),

    S("registry.mirror", "podman", SURFACE_REGISTRY, "podman.registries", "list",
      "Registry Aynaları", "Bir registry için denenecek alternatif konumlar "
      "(`[[registry.mirror]]` blokları).",
      privilege="user",
      gotcha="Docker'ın registry-mirrors'ından farklı olarak HER registry için ayrı ayrı "
             "tanımlanabilir, sadece Docker Hub için değil.",
      docs=DOCS_RC, tags=["registry", "hız"]),

    S("registry.insecure", "podman", SURFACE_REGISTRY, "podman.registries", "bool",
      "Güvensiz Registry", "Bu registry için TLS doğrulamasını atlar.",
      default=False, privilege="user", danger=2, docs=DOCS_RC,
      tags=["registry", "güvenlik"]),

    S("registry.blocked", "podman", SURFACE_REGISTRY, "podman.registries", "bool",
      "Engelli Registry", "Bu registry'den imaj çekilmesini tamamen yasaklar.",
      default=False, privilege="user", docs=DOCS_RC, tags=["registry", "güvenlik"]),

    S("registry.prefix", "podman", SURFACE_REGISTRY, "podman.registries", "str",
      "Yeniden Yazma Ön Eki", "Bir imaj yolunu başka bir konuma yönlendirir "
      "(hava boşluklu ortamlarda temel araç).",
      privilege="user", docs=DOCS_RC, tags=["registry"]),
]
