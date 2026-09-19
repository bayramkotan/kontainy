"""
kontainy — Ayar Kataloğu
==============================

Bu dosya kontainy'in KALBİDİR. Docker ve Podman'ın tüm yapılandırma
yüzeyi burada yapısal veri olarak tanımlanır. GUI bu katalogtan üretilir;
hiçbir ayar arayüze elle gömülmez.

VenvStudio'daki CONFLICT_RULES ile aynı rolü oynar: tek kaynak, GUI onu okur.

Alanlar
-------
key              : Yapılandırma dosyasındaki gerçek anahtar (noktalı yol)
engine           : "docker" | "podman" | "both"
surface          : Ayarın yaşadığı yüzey (SURFACE_* sabitleri)
file             : Ayarın yazıldığı dosya (scope'a göre çözülür)
vtype            : bool | int | str | choice | list | dict | size | duration
choices          : vtype == "choice" ise geçerli değerler
default          : Üreticinin varsayılanı (None = tanımsız/dinamik)
cli              : Eşdeğer CLI bayrağı (öğretici panelde gösterilir)
restart          : Değişiklik sonrası yeniden başlatma gerekir mi
privilege        : "user" | "root" — root olanlar salt-okunur + komut gösterilir
danger           : 0 güvenli, 1 dikkat, 2 tehlikeli (izolasyonu zayıflatır)
title            : Kısa başlık (TR)
desc             : Ne işe yarar, ne zaman değiştirilir (TR)
gotcha           : Bilinmediğinde saat yakan ayrıntı (TR) — None olabilir
docs             : Resmî dokümantasyon bağlantısı
"""

from dataclasses import dataclass, field
from typing import Any, Optional

# --- Yüzeyler ---------------------------------------------------------------
SURFACE_DAEMON = "daemon"        # daemon.json / containers.conf [engine]
SURFACE_STORAGE = "storage"      # storage-driver / storage.conf
SURFACE_NETWORK = "network"      # ağ yapılandırması
SURFACE_REGISTRY = "registry"    # registries.conf / registry-mirrors
SURFACE_CONTAINER = "container"  # container başına çalıştırma bayrakları
SURFACE_SECURITY = "security"    # capabilities, seccomp, userns
SURFACE_RESOURCE = "resource"    # cgroup limitleri
SURFACE_LOGGING = "logging"      # log sürücüsü ve rotasyon
SURFACE_BUILD = "build"          # BuildKit / buildah
SURFACE_SYSTEMD = "systemd"      # Quadlet / servis entegrasyonu

# --- Yapılandırma dosyası yolları ------------------------------------------
FILES = {
    "docker.daemon":      {"root": "/etc/docker/daemon.json",
                           "user": "~/.config/docker/daemon.json"},
    "docker.cli":         {"user": "~/.docker/config.json"},
    "podman.containers":  {"root": "/etc/containers/containers.conf",
                           "user": "~/.config/containers/containers.conf",
                           "vendor": "/usr/share/containers/containers.conf"},
    "podman.storage":     {"root": "/etc/containers/storage.conf",
                           "user": "~/.config/containers/storage.conf",
                           "vendor": "/usr/share/containers/storage.conf"},
    "podman.registries":  {"root": "/etc/containers/registries.conf",
                           "user": "~/.config/containers/registries.conf",
                           "vendor": "/etc/containers/registries.conf.d/"},
    "podman.policy":      {"root": "/etc/containers/policy.json",
                           "user": "~/.config/containers/policy.json"},
    "podman.quadlet":     {"root": "/etc/containers/systemd/",
                           "user": "~/.config/containers/systemd/"},
}


@dataclass
class Setting:
    key: str
    engine: str
    surface: str
    file: str
    vtype: str
    title: str
    desc: str
    default: Any = None
    choices: Optional[list] = None
    cli: Optional[str] = None
    restart: bool = False
    privilege: str = "root"
    danger: int = 0
    gotcha: Optional[str] = None
    docs: Optional[str] = None
    tags: list = field(default_factory=list)


S = Setting
DOCS_D = "https://docs.docker.com/reference/cli/dockerd/"
DOCS_DJ = "https://docs.docker.com/engine/daemon/"
DOCS_RUN = "https://docs.docker.com/reference/cli/docker/container/run/"
DOCS_CC = "https://github.com/containers/common/blob/main/docs/containers.conf.5.md"
DOCS_SC = "https://github.com/containers/storage/blob/main/docs/containers-storage.conf.5.md"
DOCS_RC = "https://github.com/containers/image/blob/main/docs/containers-registries.conf.5.md"
DOCS_PR = "https://docs.podman.io/en/latest/markdown/podman-run.1.html"
DOCS_QD = "https://docs.podman.io/en/latest/markdown/podman-systemd.unit.5.html"


# ===========================================================================
#  DOCKER — daemon.json
# ===========================================================================
DOCKER_DAEMON = [
    S("data-root", "docker", SURFACE_STORAGE, "docker.daemon", "str",
      "Veri Kökü", "Imajların, container katmanlarının ve volume'ların tutulduğu dizin. "
      "Kök disk dolmaya başladığında imaj deposunu başka bir diske taşımanın tek yolu.",
      default="/var/lib/docker", cli="--data-root", restart=True, danger=1,
      gotcha="Taşımadan önce daemon durdurulmalı ve mevcut içerik rsync ile kopyalanmalı; "
             "sadece anahtarı değiştirmek eski verileri görünmez yapar.",
      docs=DOCS_DJ, tags=["disk", "taşıma"]),

    S("storage-driver", "docker", SURFACE_STORAGE, "docker.daemon", "choice",
      "Depolama Sürücüsü", "Katmanlı dosya sistemini hangi mekanizmanın yürüteceği. "
      "overlay2 modern varsayılandır; btrfs ve zfs ana dosya sisteminin yeteneklerini kullanır.",
      default="overlay2", choices=["overlay2", "btrfs", "zfs", "vfs", "fuse-overlayfs"],
      cli="--storage-driver", restart=True, danger=2,
      gotcha="Sürücü değiştirildiğinde eski sürücüdeki TÜM imaj ve container'lar görünmez olur "
             "(silinmez, sadece erişilemez). CachyOS/btrfs kurulumlarında overlay2 çalışır ama "
             "btrfs sürücüsü snapshot avantajı sağlar.",
      docs="https://docs.docker.com/engine/storage/drivers/", tags=["btrfs", "disk"]),

    S("storage-opts", "docker", SURFACE_STORAGE, "docker.daemon", "list",
      "Depolama Seçenekleri", "Sürücüye özel seçenekler, örneğin overlay2 için "
      "`overlay2.size=20G` container başına yazılabilir katman boyutu sınırı.",
      default=[], restart=True, danger=1,
      gotcha="overlay2.size yalnızca xfs üzerinde pquota ile çalışır; ext4'te sessizce yok sayılır.",
      docs="https://docs.docker.com/engine/storage/drivers/overlayfs-driver/"),

    S("log-driver", "docker", SURFACE_LOGGING, "docker.daemon", "choice",
      "Log Sürücüsü", "Container stdout/stderr çıktısının nereye yazılacağı.",
      default="json-file",
      choices=["json-file", "local", "journald", "syslog", "fluentd", "gelf",
               "awslogs", "splunk", "etwlogs", "none"],
      cli="--log-driver", restart=True,
      gotcha="json-file VARSAYILAN OLARAK SINIRSIZDIR. Log dosyaları GB'lara çıkıp kök diski "
             "doldurur — en sık görülen Docker kaynaklı disk dolma sebebi. `local` sürücüsü "
             "varsayılan olarak döndürme yapar ve daha verimlidir.",
      docs="https://docs.docker.com/engine/logging/configure/", tags=["disk", "kritik"]),

    S("log-opts.max-size", "docker", SURFACE_LOGGING, "docker.daemon", "size",
      "Log Dosya Boyutu", "Tek bir log dosyasının döndürülmeden önceki azami boyutu.",
      default=None, cli="--log-opt max-size", restart=True,
      gotcha="Ayarlanmazsa sınır yoktur. Önerilen başlangıç: 10m.",
      docs="https://docs.docker.com/engine/logging/drivers/json-file/", tags=["disk", "kritik"]),

    S("log-opts.max-file", "docker", SURFACE_LOGGING, "docker.daemon", "int",
      "Log Dosya Sayısı", "Döndürmede saklanacak dosya adedi. Toplam disk kullanımı "
      "max-size × max-file kadardır.",
      default=1, cli="--log-opt max-file", restart=True,
      docs="https://docs.docker.com/engine/logging/drivers/json-file/", tags=["disk"]),

    S("log-opts.compress", "docker", SURFACE_LOGGING, "docker.daemon", "bool",
      "Log Sıkıştırma", "Döndürülmüş log dosyalarını gzip ile sıkıştırır.",
      default=False, cli="--log-opt compress", restart=True, docs=DOCS_DJ),

    S("log-level", "docker", SURFACE_DAEMON, "docker.daemon", "choice",
      "Daemon Log Seviyesi", "dockerd'nin kendi günlük ayrıntı düzeyi.",
      default="info", choices=["debug", "info", "warn", "error", "fatal"],
      cli="--log-level", restart=True, docs=DOCS_D),

    S("default-address-pools", "docker", SURFACE_NETWORK, "docker.daemon", "list",
      "Varsayılan Adres Havuzları", "Docker'ın kendi ağlarını hangi IP bloklarından "
      "üreteceği. Her giriş `{\"base\": \"10.200.0.0/16\", \"size\": 24}` biçimindedir.",
      default=[{"base": "172.17.0.0/16", "size": 16},
               {"base": "172.18.0.0/16", "size": 16}],
      restart=True, danger=1,
      gotcha="KURUMSAL AĞ ÇAKIŞMASI: varsayılan 172.17.0.0/16 birçok VPN ve şirket ağıyla "
             "çakışır; Docker kurulunca VPN'in tamamı erişilemez olur. Belirti: 'Docker "
             "kurdum, şirket ağım gitti'. Çözüm bu anahtarı 10.200.0.0/16 gibi kullanılmayan "
             "bir bloğa taşımaktır.",
      docs=DOCS_DJ, tags=["ağ", "vpn", "kritik"]),

    S("bip", "docker", SURFACE_NETWORK, "docker.daemon", "str",
      "docker0 Köprü IP'si", "Varsayılan docker0 köprüsünün IP/maske değeri (CIDR).",
      default="172.17.0.1/16", cli="--bip", restart=True, danger=1,
      gotcha="default-address-pools yalnızca YENİ ağları etkiler; docker0'ın kendisini "
             "değiştirmek için bu anahtar gerekir. İkisi karıştırıldığında çakışma çözülmez.",
      docs=DOCS_D, tags=["ağ", "vpn"]),

    S("fixed-cidr", "docker", SURFACE_NETWORK, "docker.daemon", "str",
      "Sabit CIDR", "docker0 üzerinde container'lara dağıtılacak alt aralık.",
      cli="--fixed-cidr", restart=True, docs=DOCS_D, tags=["ağ"]),

    S("default-network-opts", "docker", SURFACE_NETWORK, "docker.daemon", "dict",
      "Varsayılan Ağ Seçenekleri", "Sürücü başına varsayılan ağ seçenekleri, "
      "örneğin tüm bridge ağları için MTU.",
      restart=True, docs=DOCS_DJ, tags=["ağ", "mtu"]),

    S("mtu", "docker", SURFACE_NETWORK, "docker.daemon", "int",
      "MTU", "Container ağ arayüzlerinin azami paket boyutu.",
      default=1500, cli="--mtu", restart=True,
      gotcha="VPN (WireGuard/OpenVPN) altında 1500 fazla gelir; belirti 'küçük istekler "
             "çalışıyor, büyük indirmeler donuyor'. 1420 veya 1360 denenmelidir.",
      docs=DOCS_D, tags=["ağ", "vpn"]),

    S("dns", "docker", SURFACE_NETWORK, "docker.daemon", "list",
      "DNS Sunucuları", "Container'lara verilecek DNS sunucuları.",
      cli="--dns", restart=True,
      gotcha="systemd-resolved kullanan sistemlerde host /etc/resolv.conf 127.0.0.53 "
             "gösterir; container bu adrese erişemez, Docker bunu tespit edip 8.8.8.8'e "
             "düşer. Kapalı ağlarda bu sessiz düşüş DNS'i tamamen bozar.",
      docs=DOCS_D, tags=["ağ", "dns"]),

    S("dns-search", "docker", SURFACE_NETWORK, "docker.daemon", "list",
      "DNS Arama Alanları", "Container'ların resolv.conf'una yazılacak arama alanları.",
      cli="--dns-search", restart=True, docs=DOCS_D, tags=["ağ", "dns"]),

    S("dns-opts", "docker", SURFACE_NETWORK, "docker.daemon", "list",
      "DNS Seçenekleri", "resolv.conf options satırı, örneğin `ndots:1`.",
      cli="--dns-opt", restart=True,
      gotcha="Kubernetes ortamlarından gelen `ndots:5` alışkanlığı Docker'da gereksiz DNS "
             "sorgusu üretir ve her isteği yavaşlatır.",
      docs=DOCS_D, tags=["ağ", "dns", "performans"]),

    S("iptables", "docker", SURFACE_NETWORK, "docker.daemon", "bool",
      "iptables Kurallarını Yönet", "Docker'ın NAT ve yönlendirme kurallarını kendisinin "
      "yazıp yazmayacağı.",
      default=True, cli="--iptables", restart=True, danger=2,
      gotcha="Arch/CachyOS'ta nftables + firewalld ile birlikte kullanıldığında Docker'ın "
             "kuralları firewalld tarafından silinebilir; belirti 'container'lar dışarıya "
             "çıkamıyor'. Kapatmak container ağını tamamen bozar — kapatmadan önce kuralları "
             "elle yazacak biri olmalı.",
      docs=DOCS_D, tags=["ağ", "güvenlik duvarı", "arch"]),

    S("ip6tables", "docker", SURFACE_NETWORK, "docker.daemon", "bool",
      "ip6tables Kurallarını Yönet", "IPv6 için aynı işlevi görür.",
      default=False, restart=True, danger=1, docs=DOCS_D, tags=["ağ", "ipv6"]),

    S("ipv6", "docker", SURFACE_NETWORK, "docker.daemon", "bool",
      "IPv6 Desteği", "Container ağlarında IPv6'yı etkinleştirir.",
      default=False, cli="--ipv6", restart=True,
      gotcha="Tek başına yetmez; `fixed-cidr-v6` veya IPv6'lı bir adres havuzu da gerekir.",
      docs="https://docs.docker.com/engine/daemon/ipv6/", tags=["ağ", "ipv6"]),

    S("ip-forward", "docker", SURFACE_NETWORK, "docker.daemon", "bool",
      "IP Yönlendirme", "net.ipv4.ip_forward sysctl değerini Docker'ın açıp açmayacağı.",
      default=True, restart=True, danger=1, docs=DOCS_D, tags=["ağ"]),

    S("ip-masq", "docker", SURFACE_NETWORK, "docker.daemon", "bool",
      "IP Maskeleme", "Container trafiğinin host IP'si arkasına NAT'lanması.",
      default=True, restart=True, danger=1, docs=DOCS_D, tags=["ağ"]),

    S("icc", "docker", SURFACE_NETWORK, "docker.daemon", "bool",
      "Container Arası İletişim", "Varsayılan köprüdeki container'ların birbirine "
      "doğrudan erişip erişemeyeceği.",
      default=True, cli="--icc", restart=True, danger=1,
      docs=DOCS_D, tags=["ağ", "güvenlik"]),

    S("userland-proxy", "docker", SURFACE_NETWORK, "docker.daemon", "bool",
      "Kullanıcı Alanı Proxy'si", "Port yayınlamada docker-proxy sürecinin kullanılması.",
      default=True, cli="--userland-proxy", restart=True,
      gotcha="Yayınlanan her port için ayrı bir docker-proxy süreci başlar; yüzlerce portta "
             "ciddi RAM tüketir. Kapatmak performansı artırır ama hairpin NAT gerektiren "
             "bazı senaryoları bozar.",
      docs=DOCS_D, tags=["ağ", "performans"]),

    S("live-restore", "docker", SURFACE_DAEMON, "docker.daemon", "bool",
      "Canlı Yeniden Başlatma", "Daemon yeniden başlarken container'ların çalışmaya "
      "devam etmesi.",
      default=False, cli="--live-restore", restart=True,
      gotcha="Swarm modunda desteklenmez. Ayrıca daemon güncellemesi sırasında büyük "
             "sürüm atlamalarında kapatılması önerilir.",
      docs="https://docs.docker.com/engine/daemon/live-restore/", tags=["kararlılık"]),

    S("userns-remap", "docker", SURFACE_SECURITY, "docker.daemon", "str",
      "Kullanıcı Ad Alanı Eşleme", "Container içindeki root'un host'ta ayrıcalıksız bir "
      "kullanıcıya eşlenmesi. `default` değeri dockremap kullanıcısını otomatik üretir.",
      cli="--userns-remap", restart=True, danger=2,
      gotcha="Etkinleştirildiğinde tüm mevcut imaj ve container'lar erişilemez olur "
             "(data-root altında ayrı bir alt dizin kullanılır). Ayrıca `--net=host`, "
             "`--pid=host` ve bazı volume senaryoları çalışmaz hale gelir.",
      docs="https://docs.docker.com/engine/security/userns-remap/",
      tags=["güvenlik", "izolasyon"]),

    S("no-new-privileges", "docker", SURFACE_SECURITY, "docker.daemon", "bool",
      "Yeni Ayrıcalık Yok (varsayılan)", "Tüm container'lar için setuid yükselmesini "
      "varsayılan olarak engeller.",
      default=False, restart=True, docs=DOCS_DJ, tags=["güvenlik"]),

    S("selinux-enabled", "docker", SURFACE_SECURITY, "docker.daemon", "bool",
      "SELinux Desteği", "SELinux etiketlemesini etkinleştirir.",
      default=False, cli="--selinux-enabled", restart=True,
      gotcha="Etkinken bind mount'lar `:z` veya `:Z` son eki olmadan container içinden "
             "okunamaz — 'Permission denied' hatasının Fedora/RHEL'deki en yaygın sebebi.",
      docs=DOCS_D, tags=["güvenlik", "selinux"]),

    S("seccomp-profile", "docker", SURFACE_SECURITY, "docker.daemon", "str",
      "Varsayılan Seccomp Profili", "Tüm container'lara uygulanacak sistem çağrısı "
      "filtre profilinin dosya yolu.",
      restart=True, danger=2, docs="https://docs.docker.com/engine/security/seccomp/",
      tags=["güvenlik"]),

    S("default-ulimits", "docker", SURFACE_RESOURCE, "docker.daemon", "dict",
      "Varsayılan ulimit Değerleri", "Container'lara varsayılan olarak uygulanacak "
      "kaynak sınırları, örneğin `nofile`.",
      default={}, cli="--default-ulimit", restart=True,
      gotcha="Birçok veritabanı imajı düşük nofile değerinde sessizce yavaşlar; "
             "`nofile: {Hard: 65536, Soft: 65536}` yaygın düzeltmedir.",
      docs=DOCS_D, tags=["kaynak", "performans"]),

    S("default-shm-size", "docker", SURFACE_RESOURCE, "docker.daemon", "size",
      "Varsayılan /dev/shm Boyutu", "Paylaşılan bellek alanının varsayılan boyutu.",
      default="64m", restart=True,
      gotcha="64 MB Chrome/Selenium ve PyTorch DataLoader için yetersizdir; "
             "'Bus error' veya sessiz çökme üretir.",
      docs=DOCS_DJ, tags=["kaynak", "ml"]),

    S("default-runtime", "docker", SURFACE_DAEMON, "docker.daemon", "str",
      "Varsayılan Çalışma Zamanı", "OCI runtime seçimi (runc, crun, nvidia).",
      default="runc", cli="--default-runtime", restart=True,
      gotcha="NVIDIA GPU kullanımı için `nvidia` yapılması gerekir; aksi halde her "
             "container'da `--runtime=nvidia` yazmak zorunda kalınır.",
      docs=DOCS_D, tags=["gpu", "runtime"]),

    S("runtimes", "docker", SURFACE_DAEMON, "docker.daemon", "dict",
      "Ek Çalışma Zamanları", "İsimlendirilmiş OCI runtime tanımları.",
      default={}, restart=True, docs=DOCS_D, tags=["gpu", "runtime"]),

    S("exec-opts", "docker", SURFACE_DAEMON, "docker.daemon", "list",
      "Çalıştırma Seçenekleri", "En sık kullanılanı `native.cgroupdriver=systemd`.",
      default=[], restart=True, danger=1,
      gotcha="Kubernetes/kubelet systemd cgroup sürücüsü bekler; cgroupfs ile çalışan "
             "Docker kubelet'i başlatmaz. cgroup v2 sistemlerinde systemd zorunludur.",
      docs=DOCS_D, tags=["kubernetes", "cgroup"]),

    S("cgroup-parent", "docker", SURFACE_RESOURCE, "docker.daemon", "str",
      "Üst cgroup", "Tüm container'ların altına yerleştirileceği cgroup.",
      cli="--cgroup-parent", restart=True, docs=DOCS_D, tags=["cgroup"]),

    S("oom-score-adjust", "docker", SURFACE_RESOURCE, "docker.daemon", "int",
      "Daemon OOM Puanı", "Bellek tükendiğinde çekirdeğin dockerd'yi öldürme eğilimi.",
      default=0, restart=True, docs=DOCS_D, tags=["kaynak"]),

    S("registry-mirrors", "docker", SURFACE_REGISTRY, "docker.daemon", "list",
      "Registry Aynaları", "Docker Hub istekleri önce bu adreslere yönlendirilir.",
      default=[], cli="--registry-mirror", restart=True,
      gotcha="Yalnızca Docker Hub için çalışır; ghcr.io veya quay.io istekleri "
             "aynalanmaz. Ayrıca hız sınırı (rate limit) sorunlarını çözmez, "
             "yalnızca gecikmeyi azaltır.",
      docs=DOCS_DJ, tags=["registry", "hız"]),

    S("insecure-registries", "docker", SURFACE_REGISTRY, "docker.daemon", "list",
      "Güvensiz Registry'ler", "TLS doğrulaması yapılmadan erişilecek registry adresleri.",
      default=[], cli="--insecure-registry", restart=True, danger=2,
      gotcha="Yerel geliştirme registry'si (localhost:5000) için gereklidir ama üretimde "
             "trafiği ortadaki adam saldırısına açar.",
      docs=DOCS_DJ, tags=["registry", "güvenlik"]),

    S("max-concurrent-downloads", "docker", SURFACE_REGISTRY, "docker.daemon", "int",
      "Eşzamanlı İndirme", "Aynı anda çekilecek azami katman sayısı.",
      default=3, restart=True, docs=DOCS_D, tags=["registry", "hız"]),

    S("max-concurrent-uploads", "docker", SURFACE_REGISTRY, "docker.daemon", "int",
      "Eşzamanlı Yükleme", "Aynı anda gönderilecek azami katman sayısı.",
      default=5, restart=True, docs=DOCS_D, tags=["registry", "hız"]),

    S("max-download-attempts", "docker", SURFACE_REGISTRY, "docker.daemon", "int",
      "İndirme Deneme Sayısı", "Başarısız katman indirmesinde tekrar deneme adedi.",
      default=5, restart=True, docs=DOCS_D, tags=["registry"]),

    S("shutdown-timeout", "docker", SURFACE_DAEMON, "docker.daemon", "duration",
      "Kapanma Zaman Aşımı", "Daemon kapanırken container'lara verilen süre (saniye).",
      default=15, restart=True, docs=DOCS_D),

    S("hosts", "docker", SURFACE_DAEMON, "docker.daemon", "list",
      "Dinlenecek Adresler", "Daemon'ın API'yi hangi soket/adreslerde açacağı.",
      default=["unix:///var/run/docker.sock"], cli="-H", restart=True, danger=2,
      gotcha="systemd ile kurulmuş Docker'da bu anahtar `docker.service` içindeki "
             "-H bayrağıyla ÇAKIŞIR ve daemon hiç başlamaz. Doğru yol systemd drop-in "
             "dosyasını düzenlemektir.",
      docs=DOCS_D, tags=["kritik", "systemd"]),

    S("tls", "docker", SURFACE_SECURITY, "docker.daemon", "bool",
      "TLS", "Uzak API erişiminde TLS kullanımı.",
      default=False, restart=True, docs=DOCS_D, tags=["güvenlik", "uzak"]),

    S("tlsverify", "docker", SURFACE_SECURITY, "docker.daemon", "bool",
      "TLS İstemci Doğrulama", "İstemci sertifikasının doğrulanması.",
      default=False, restart=True, docs=DOCS_D, tags=["güvenlik", "uzak"]),

    S("features", "docker", SURFACE_BUILD, "docker.daemon", "dict",
      "Özellik Bayrakları", "Örneğin `{\"buildkit\": true}` veya "
      "`{\"containerd-snapshotter\": true}`.",
      default={}, restart=True,
      gotcha="containerd-snapshotter açıldığında imaj deposu tamamen değişir; "
             "mevcut imajlar listede görünmez (silinmez, farklı depodadır).",
      docs=DOCS_DJ, tags=["buildkit", "containerd"]),

    S("builder.gc.enabled", "docker", SURFACE_BUILD, "docker.daemon", "bool",
      "Build Cache Temizliği", "BuildKit önbelleğinin otomatik toplanması.",
      default=True, restart=True, docs="https://docs.docker.com/build/cache/garbage-collection/",
      tags=["buildkit", "disk"]),

    S("builder.gc.defaultKeepStorage", "docker", SURFACE_BUILD, "docker.daemon", "size",
      "Build Cache Sınırı", "Saklanacak azami build önbelleği boyutu.",
      default="10GB", restart=True,
      gotcha="Sık build yapılan makinelerde build cache imajlardan daha çok yer kaplar; "
             "`docker system df` çıktısında ayrı satırdadır ve `docker image prune` onu silmez.",
      docs="https://docs.docker.com/build/cache/garbage-collection/", tags=["buildkit", "disk"]),

    S("metrics-addr", "docker", SURFACE_DAEMON, "docker.daemon", "str",
      "Metrik Adresi", "Prometheus metriklerinin sunulacağı adres.",
      restart=True, docs=DOCS_DJ, tags=["izleme"]),

    S("debug", "docker", SURFACE_DAEMON, "docker.daemon", "bool",
      "Hata Ayıklama", "Daemon'ı ayrıntılı günlük moduna alır.",
      default=False, cli="--debug", restart=True, docs=DOCS_D),

    S("experimental", "docker", SURFACE_DAEMON, "docker.daemon", "bool",
      "Deneysel Özellikler", "Kararlı sayılmayan daemon özelliklerini açar.",
      default=False, restart=True, danger=1, docs=DOCS_D),
]

# ===========================================================================
#  DOCKER — CLI yapılandırması (~/.docker/config.json) — root GEREKMEZ
# ===========================================================================
DOCKER_CLI = [
    S("currentContext", "docker", SURFACE_DAEMON, "docker.cli", "str",
      "Etkin Context", "docker CLI'ın varsayılan olarak hangi motora bağlanacağı.",
      privilege="user",
      gotcha="DOCKER_HOST ortam değişkeni AYARLIYSA bu değer tamamen yok sayılır. "
             "`docker context use` başarılı der ama hiçbir şey değişmez — "
             "'container'larım kayboldu' şikayetinin bir numaralı sebebi.",
      docs="https://docs.docker.com/engine/manage-resources/contexts/",
      tags=["context", "kritik"]),

    S("credsStore", "docker", SURFACE_REGISTRY, "docker.cli", "str",
      "Kimlik Deposu", "Registry parolalarının saklanacağı yardımcı program "
      "(`secretservice`, `pass`, `desktop`).",
      privilege="user",
      gotcha="Docker Desktop kaldırıldığında bu anahtar `desktop` olarak kalır ve her "
             "komut `docker-credential-desktop not found in $PATH` hatası verir. "
             "Anahtarın silinmesi gerekir.",
      docs="https://docs.docker.com/reference/cli/docker/login/", tags=["kritik", "desktop"]),

    S("credHelpers", "docker", SURFACE_REGISTRY, "docker.cli", "dict",
      "Registry Başına Kimlik Yardımcısı", "Belirli registry'ler için ayrı kimlik programı.",
      privilege="user", docs="https://docs.docker.com/reference/cli/docker/login/",
      tags=["registry"]),

    S("cliPluginsExtraDirs", "docker", SURFACE_DAEMON, "docker.cli", "list",
      "Ek Eklenti Dizinleri", "`docker compose`, `docker buildx` gibi eklentilerin "
      "aranacağı ek dizinler.",
      privilege="user",
      gotcha="Docker Desktop kendi eklentilerini `~/.docker/cli-plugins` altına koyar ve "
             "distro paketinin `/usr/lib/docker/cli-plugins` sürümünü gölgeler — "
             "`docker compose version` ile `docker-compose version` farklı çıkar.",
      docs="https://docs.docker.com/engine/cli/plugins/", tags=["desktop", "compose"]),

    S("proxies", "docker", SURFACE_NETWORK, "docker.cli", "dict",
      "Proxy Ayarları", "Build ve run işlemlerine otomatik geçirilecek proxy değişkenleri.",
      privilege="user", docs="https://docs.docker.com/engine/daemon/proxy/",
      tags=["ağ", "proxy"]),

    S("detachKeys", "docker", SURFACE_DAEMON, "docker.cli", "str",
      "Ayrılma Tuşları", "attach edilmiş container'dan çıkış tuş dizisi.",
      default="ctrl-p,ctrl-q", privilege="user", docs=DOCS_RUN),
]

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

# ===========================================================================
#  Toplu katalog ve yardımcılar
# ===========================================================================
ALL_SETTINGS: list = (
    DOCKER_DAEMON + DOCKER_CLI +
    PODMAN_CONTAINERS + PODMAN_STORAGE + PODMAN_REGISTRIES +
    RUN_FLAGS + QUADLET
)

SURFACE_TITLES = {
    SURFACE_DAEMON:    "Motor / Daemon",
    SURFACE_STORAGE:   "Depolama",
    SURFACE_NETWORK:   "Ağ",
    SURFACE_REGISTRY:  "Registry",
    SURFACE_CONTAINER: "Container",
    SURFACE_SECURITY:  "Güvenlik",
    SURFACE_RESOURCE:  "Kaynak Sınırları",
    SURFACE_LOGGING:   "Günlükleme",
    SURFACE_BUILD:     "Derleme",
    SURFACE_SYSTEMD:   "systemd / Quadlet",
}

DANGER_TITLES = {0: "Güvenli", 1: "Dikkat", 2: "Tehlikeli"}


def by_engine(engine: str) -> list:
    """Bir motora ait ayarlar ('both' olanlar her zaman dahil)."""
    return [s for s in ALL_SETTINGS if s.engine in (engine, "both")]


def by_surface(surface: str, engine: str = None) -> list:
    """Bir yüzeye ait ayarlar, istenirse motora göre süzülmüş."""
    out = [s for s in ALL_SETTINGS if s.surface == surface]
    if engine:
        out = [s for s in out if s.engine in (engine, "both")]
    return out


def search(text: str) -> list:
    """Anahtar, başlık, açıklama, gotcha ve etiketlerde serbest metin araması."""
    t = text.casefold()
    hits = []
    for s in ALL_SETTINGS:
        haystack = " ".join(filter(None, [
            s.key, s.title, s.desc, s.gotcha or "", s.cli or "", " ".join(s.tags)
        ])).casefold()
        if t in haystack:
            hits.append(s)
    return hits


def with_gotchas() -> list:
    """Bilinmediğinde saat yakan ayarlar — 'Tuzaklar' panelini besler."""
    return [s for s in ALL_SETTINGS if s.gotcha]


def dangerous() -> list:
    """İzolasyonu veya kararlılığı zayıflatan ayarlar."""
    return [s for s in ALL_SETTINGS if s.danger >= 2]


def user_scoped() -> list:
    """Root gerektirmeyen, kontainy'in doğrudan yazabileceği ayarlar."""
    return [s for s in ALL_SETTINGS if s.privilege == "user"]


def stats() -> dict:
    """Katalog özeti — Hakkında panelinde gösterilir."""
    return {
        "toplam": len(ALL_SETTINGS),
        "docker": len([s for s in ALL_SETTINGS if s.engine == "docker"]),
        "podman": len([s for s in ALL_SETTINGS if s.engine == "podman"]),
        "ortak": len([s for s in ALL_SETTINGS if s.engine == "both"]),
        "kullanici_kapsami": len(user_scoped()),
        "tuzakli": len(with_gotchas()),
        "tehlikeli": len(dangerous()),
    }


if __name__ == "__main__":
    for k, v in stats().items():
        print(f"{k:22} {v}")
