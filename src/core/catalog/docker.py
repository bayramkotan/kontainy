"""kontainy — ayar kataloğu parçası. Tanımlar için base.py'ye bak."""

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
