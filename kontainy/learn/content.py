"""
kontainy — Learn içeriği
=========================

VenvStudio'daki Learn sayfasının karşılığı ve EĞİTSEL DİREĞİN kendisi.

⚠️ KURAL: kaldırma yapılmaz, sadece eklenir. Bir konunun `body`si daha sonra
zenginleştirilebilir ama silinmez.

⚠️ KURAL: eğitici metin büyük olur. Taban 18px (≈13pt). "Mevcut kod böyleydi"
gerekçe değildir.

⚠️ KURAL: gösterilen komut, kullanıcının gerçekten yazabileceği komut olmalı.
Uydurma bayrak yok — her bayrak `--help` ile doğrulanır.

Konu alanları
-------------
title    (zorunlu)  başlık
body     (zorunlu)  düz metin, satır satır
snippet             kod örneği
language            snippet dili: bash | toml | ini | json | yaml | python
tip                 💡 yeşil kart — iyi uygulama
note                ℹ mavi kart — ek bağlam
warning             ⚠ turuncu kart — dikkat
table               {"headers": [...], "rows": [[...]]}
diagram             monospace şema
links               [(metin, url), ...]
setting_key         kontainy'ye özel: Ayarlar sayfasında açılacak katalog anahtarı
rule_id             kontainy'ye özel: Teşhis sayfasında ilgili kural
"""

# ---------------------------------------------------------------------------
#  1 — Hızlı Başlangıç
# ---------------------------------------------------------------------------
QUICK_START = [
    {
        "title": "Konteyner nedir, sanal makineden farkı ne?",
        "body": (
            "Bir sanal makine kendi çekirdeğini çalıştırır; konteyner ise host "
            "çekirdeğini paylaşır ve yalnızca YALITILMIŞ bir görünüm alır.\n\n"
            "Bu yalıtım iki çekirdek özelliğinden gelir: namespace (ne "
            "görebiliyorsun) ve cgroup (ne kadar tüketebilirsin). Konteyner "
            "aslında sadece bu ikisiyle kısıtlanmış sıradan bir süreçtir — "
            "host'ta `ps aux` çalıştırdığınızda onu görürsünüz.\n\n"
            "Bu yüzden konteynerler saniyeler yerine milisaniyelerde başlar ve "
            "bu yüzden host çekirdeğinden bağımsız değillerdir."),
        "diagram": (
            "  SANAL MAKİNE                 KONTEYNER\n"
            "  ┌──────────────┐             ┌──────────────┐\n"
            "  │  uygulama    │             │  uygulama    │\n"
            "  │  kütüphane   │             │  kütüphane   │\n"
            "  │  ÇEKİRDEK    │             └──────┬───────┘\n"
            "  ├──────────────┤             ┌──────┴───────┐\n"
            "  │  hipervizör  │             │ namespace +  │\n"
            "  ├──────────────┤             │ cgroup       │\n"
            "  │ host çekirdek│             │ host çekirdek│\n"
            "  └──────────────┘             └──────────────┘"),
        "note": "LXC/LXD ve Incus üçüncü bir noktada durur: konteyner "
                "teknolojisini kullanır ama tam bir işletim sistemi çalıştırır.",
        "links": [("OCI Runtime Spec", "https://github.com/opencontainers/runtime-spec")],
    },
    {
        "title": "İlk container'ı çalıştır",
        "body": (
            "En küçük tam örnek: bir web sunucusu başlat, 8080'den yayınla, "
            "adını ver ve durunca kendini silsin."),
        "snippet": (
            "# Docker\n"
            "docker run --rm --name web -p 8080:80 nginx:alpine\n\n"
            "# Podman — bayraklar birebir aynı\n"
            "podman run --rm --name web -p 8080:80 docker.io/library/nginx:alpine"),
        "language": "bash",
        "tip": "`--rm` container durduğunda onu siler. Denemelerde her zaman "
               "kullanın; yoksa `docker ps -a` yüzlerce ölü kayıtla dolar.",
        "warning": "Podman'da tam imaj adı (`docker.io/library/...`) yazdım. "
                   "Kısa ad `nginx:alpine` çalışmayabilir — sebebi "
                   "`short-name-mode` ayarıdır.",
        "setting_key": "short-name-mode",
    },
    {
        "title": "Port yayınlama gerçekte ne yapıyor",
        "body": (
            "`-p 8080:80` şu demek: host'un 8080 portuna gelen trafiği "
            "container'ın 80 portuna ilet. Sıra HOST:CONTAINER — ters yazmak en "
            "sık yapılan hatadır.\n\n"
            "Arka planda bir NAT kuralı yazılır. Docker'da bunu "
            "`iptables -t nat -L DOCKER` ile görebilirsiniz.\n\n"
            "Host IP'si de belirtilebilir: `-p 127.0.0.1:8080:80` yalnızca yerel "
            "makineden erişilebilir yapar — dışarı açmak istemediğiniz "
            "servisler için doğru olan budur."),
        "snippet": (
            "-p 8080:80                 # tüm arayüzlerde 8080\n"
            "-p 127.0.0.1:8080:80       # yalnızca yerelden\n"
            "-p 8080:80/udp             # UDP\n"
            "-p 80                      # rastgele host portu ata\n"
            "-P                         # EXPOSE edilmiş tüm portları rastgele ata"),
        "language": "bash",
        "warning": "Rootless Podman'da 1024 altı portlara bağlanamazsınız. "
                   "`-p 80:80` izin hatası verir; ya yüksek port kullanın ya "
                   "da `net.ipv4.ip_unprivileged_port_start` değerini düşürün.",
        "rule_id": "NET02",
    },
    {
        "title": "Veriyi kalıcı kılmak: volume ve bind mount",
        "body": (
            "Container silindiğinde yazılabilir katmanı da silinir. Kalması "
            "gereken veri dışarıda tutulur ve bunun iki yolu vardır.\n\n"
            "VOLUME motorun yönettiği bir alandır; adı vardır, yolu sizi "
            "ilgilendirmez, yedeklemesi kolaydır. Veritabanları için doğru "
            "seçim budur.\n\n"
            "BIND MOUNT host'ta belirttiğiniz bir dizini bağlar. Geliştirme "
            "sırasında kaynak kodu container'a vermek için idealdir, ama "
            "izin sorunlarının da kaynağıdır."),
        "snippet": (
            "# Volume — motor yönetir\n"
            "podman volume create pgdata\n"
            "podman run -v pgdata:/var/lib/postgresql/data postgres:16\n\n"
            "# Bind mount — host dizini\n"
            "podman run -v ./src:/app/src:ro,Z node:22"),
        "language": "bash",
        "table": {
            "headers": ["Son ek", "Anlamı", "Ne zaman"],
            "rows": [
                ["`:ro`", "salt okunur", "container yazmamalıysa her zaman"],
                ["`:z`", "paylaşılan SELinux etiketi", "birden çok container erişecekse"],
                ["`:Z`", "özel SELinux etiketi", "tek container erişecekse"],
                ["`:rshared`", "mount yayılımı", "container içi mount host'ta görünsün"],
            ],
        },
        "warning": "SELinux açık sistemlerde `:z` veya `:Z` olmadan bind mount "
                   "`Permission denied` verir. Rootless Podman'da ayrıca ev "
                   "dizini dosyaları `nobody` görünür — çözümü "
                   "`--userns=keep-id`.",
        "setting_key": "volume.selinux",
    },
]

# ---------------------------------------------------------------------------
#  2 — Konteyner Temelleri
# ---------------------------------------------------------------------------
FUNDAMENTALS = [
    {
        "title": "Namespace — konteynerin ne gördüğünü belirler",
        "body": (
            "Linux'ta yedi namespace türü vardır ve her biri bir kaynağın "
            "görünümünü yalıtır. Konteyner bunların bir birleşimidir.\n\n"
            "Bunlar konteyner teknolojisine özel değildir; `unshare` komutuyla "
            "elle de oluşturabilirsiniz. Konteyner motoru sadece bunları bir "
            "araya getiren şeydir."),
        "table": {
            "headers": ["Namespace", "Yalıttığı şey", "Bayrak"],
            "rows": [
                ["pid", "süreç numaraları", "`--pid`"],
                ["net", "ağ arayüzleri, portlar, yönlendirme", "`--network`"],
                ["mnt", "dosya sistemi bağlama noktaları", "*(otomatik)*"],
                ["uts", "hostname ve domain adı", "`--uts`"],
                ["ipc", "paylaşılan bellek, semaforlar", "`--ipc`"],
                ["user", "UID/GID eşlemesi", "`--userns`"],
                ["cgroup", "cgroup ağacı görünümü", "`--cgroupns`"],
            ],
        },
        "snippet": (
            "# Konteyner olmadan namespace denemesi\n"
            "unshare --pid --fork --mount-proc bash\n"
            "ps aux          # yalnızca kendi süreçlerinizi görürsünüz\n\n"
            "# Çalışan bir container'ın namespace'ine girmek\n"
            "sudo nsenter -t $(podman inspect -f '{{.State.Pid}}' web) -n ip addr"),
        "language": "bash",
        "tip": "`--network=host` demek, ağ namespace'ini HİÇ oluşturmamak "
               "demektir. Yalıtımı kaldırır ama port yayınlama gereksiz kalır.",
    },
    {
        "title": "cgroup v2 — ne kadar tüketebileceğini belirler",
        "body": (
            "cgroup süreç gruplarına CPU, bellek, G/Ç ve PID sınırı koyar. "
            "Modern sistemler v2 kullanır: tek bir birleşik hiyerarşi.\n\n"
            "Sınırların gerçekten uygulanıp uygulanmadığı, motorun hangi "
            "cgroup yöneticisini kullandığına bağlıdır. Rootless kullanımda "
            "systemd delegasyonu gerekir; cgroupfs seçilirse sınırlar HATA "
            "VERMEDEN yok sayılır."),
        "snippet": (
            "# Sistem cgroup v2 mi?\n"
            "stat -fc %T /sys/fs/cgroup    # 'cgroup2fs' beklenir\n\n"
            "# Podman hangi yöneticiyi kullanıyor?\n"
            "podman info --format '{{.Host.CgroupManager}}'\n\n"
            "# Bir container'ın gerçek sınırını oku\n"
            "cat /sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/"
            "*/memory.max"),
        "language": "bash",
        "warning": "Bu projede sınıfının en sinsi hatası budur: sınır koyarsınız, "
                   "komut hatasız döner, sınır uygulanmaz. kontainy'nin RES01 "
                   "kuralı tam bunu arar.",
        "rule_id": "RES01",
        "setting_key": "containers.cgroup_manager",
    },
    {
        "title": "Capability — root'u parçalara ayırmak",
        "body": (
            "Linux root yetkisini ~40 parçaya böler. Bir konteyner "
            "'root' çalışsa bile yalnızca verilen capability'lere sahiptir.\n\n"
            "Docker ve Podman'ın VARSAYILAN LİSTELERİ FARKLIDIR. Docker "
            "AUDIT_WRITE ve MKNOD içerir, Podman içermez. Docker'da çalışan bir "
            "imaj Podman'da yetki hatası verebilir ve sebebi budur."),
        "table": {
            "headers": ["Capability", "Ne sağlar", "Risk"],
            "rows": [
                ["`NET_BIND_SERVICE`", "1024 altı porta bağlanma", "düşük"],
                ["`CHOWN`", "dosya sahipliği değiştirme", "düşük"],
                ["`NET_ADMIN`", "ağ yapılandırma", "orta"],
                ["`SYS_PTRACE`", "başka süreci izleme", "orta"],
                ["`SYS_ADMIN`", "mount, namespace, çok şey", "**çok yüksek**"],
                ["`SYS_MODULE`", "çekirdek modülü yükleme", "**host'u ele geçirir**"],
            ],
        },
        "snippet": (
            "# Önerilen desen: hepsini at, gerekeni geri ver\n"
            "podman run --cap-drop=ALL --cap-add=NET_BIND_SERVICE nginx\n\n"
            "# Bir container'ın gerçek capability'lerini gör\n"
            "podman inspect web --format '{{.EffectiveCaps}}'"),
        "language": "bash",
        "tip": "`SYS_ADMIN` pratikte `--privileged`'a yakındır. "
               "\"Sadece mount edebilsin\" diye eklenir ve yalıtımın tamamını açar.",
        "setting_key": "cap-add",
    },
    {
        "title": "Katmanlı dosya sistemi ve overlayfs",
        "body": (
            "Bir imaj salt okunur katmanların yığınıdır. Container "
            "başlatıldığında en üste yazılabilir bir katman eklenir; tüm "
            "değişiklikler oraya yazılır.\n\n"
            "Bu copy-on-write'tır: alttaki bir dosyayı değiştirdiğinizde önce "
            "üst katmana kopyalanır. Büyük bir dosyanın tek baytını "
            "değiştirmek dosyanın tamamını kopyalar — imaj boyutunun neden "
            "beklenmedik şekilde şiştiğinin cevabı budur."),
        "diagram": (
            "  ┌─────────────────────────┐  ← yazılabilir katman (container)\n"
            "  ├─────────────────────────┤  ← COPY . /app\n"
            "  ├─────────────────────────┤  ← RUN pip install\n"
            "  ├─────────────────────────┤  ← FROM python:3.12\n"
            "  └─────────────────────────┘  ← taban katman"),
        "snippet": (
            "# Katmanları ve boyutlarını gör\n"
            "podman history docker.io/library/python:3.12-slim\n\n"
            "# Container'ın yazılabilir katmanında ne değişmiş?\n"
            "podman diff web"),
        "language": "bash",
        "note": "Dockerfile'da bir dosyayı silmek onu imajdan çıkarmaz — "
                "alttaki katmanda kalmaya devam eder, yalnızca görünmez olur. "
                "Gizli bilgi bu yüzden çok aşamalı build ile ayıklanır.",
        "setting_key": "storage.driver",
    },
]

# ---------------------------------------------------------------------------
#  4 — Podman
# ---------------------------------------------------------------------------
PODMAN = [
    {
        "title": "Daemon yok — bu neyi değiştirir",
        "body": (
            "Docker'da `docker` komutu bir daemon'a istek gönderir; container'lar "
            "o daemon'ın çocuklarıdır ve daemon root çalışır.\n\n"
            "Podman'da daemon yoktur. `podman run` container'ı DOĞRUDAN "
            "başlatır ve container sizin sürecinizin çocuğudur. Bunun üç "
            "sonucu var:\n\n"
            "• root gerekmez — rootless doğal durumdur\n"
            "• arada duran tek bir hata noktası yoktur\n"
            "• AMA arka planda container'ı ayakta tutacak bir daemon da yoktur; "
            "`--restart=always` makine yeniden başladığında ÇALIŞMAZ"),
        "snippet": (
            "# Docker: istemci → daemon → container\n"
            "systemctl status docker\n\n"
            "# Podman: doğrudan\n"
            "podman run -d --name web nginx\n"
            "pstree -p $$ | grep conmon"),
        "language": "bash",
        "warning": "Kalıcı servis istiyorsanız Quadlet kullanın. `--restart=always` "
                   "yalnızca oturum boyunca geçerlidir ve linger kapalıysa "
                   "çıkışta da ölür.",
        "rule_id": "POD02",
    },
    {
        "title": "Rootless gerçekte nasıl çalışıyor",
        "body": (
            "Rootless Podman user namespace kullanır. Container içindeki root "
            "(UID 0), host'ta size ayrılmış bir aralığın başına eşlenir.\n\n"
            "Bu aralık `/etc/subuid` ve `/etc/subgid` dosyalarında tanımlıdır. "
            "Kayıt yoksa hiçbir şey çalışmaz ve hata mesajı şudur: "
            "`potentially insufficient UIDs or GIDs available in user namespace`."),
        "snippet": (
            "# Aralığınız var mı?\n"
            "grep $USER /etc/subuid /etc/subgid\n\n"
            "# Eşlemeyi gör\n"
            "podman unshare cat /proc/self/uid_map\n\n"
            "# Ev dizinindeki dosyalar 'nobody' görünüyorsa\n"
            "podman run --userns=keep-id -v $HOME/data:/data alpine ls -l /data"),
        "language": "bash",
        "table": {
            "headers": ["userns modu", "Ne yapar", "Ne zaman"],
            "rows": [
                ["`host`", "eşleme yok (varsayılan)", "genel kullanım"],
                ["`keep-id`", "kendi UID'niz aynı kalır", "ev dizini bind mount"],
                ["`nomap`", "hiçbir host UID eşlenmez", "en sıkı yalıtım"],
                ["`auto`", "her container'a ayrı aralık", "çoklu kiracı"],
            ],
        },
        "tip": "Aralığı değiştirdikten sonra `podman system migrate` şarttır; "
               "yoksa mevcut container'lar eski eşlemeyle kalır.",
        "rule_id": "POD03",
        "setting_key": "containers.userns",
    },
    {
        "title": "Pod — Kubernetes'ten önce gelen fikir",
        "body": (
            "Pod, namespace'leri paylaşan container grubudur. Aynı pod'daki "
            "container'lar birbirini `localhost` üzerinden görür — tıpkı "
            "Kubernetes'teki gibi, çünkü kavram oradan gelir.\n\n"
            "Pod'un ağ namespace'ini tutan görünmez bir 'infra' container'ı "
            "vardır; asıl container'lar gelip gitse de ağ ayakta kalır."),
        "snippet": (
            "podman pod create --name app -p 8080:80\n"
            "podman run -d --pod app --name web nginx\n"
            "podman run -d --pod app --name api my-api\n\n"
            "# web, api'ye localhost:3000 üzerinden ulaşır\n"
            "podman pod ps\n"
            "podman generate kube app > app.yaml   # Kubernetes'e taşı"),
        "language": "bash",
        "note": "Port yayınlama POD seviyesinde yapılır, container seviyesinde "
                "değil — pod'a katılan container'ın kendi `-p` bayrağı yok sayılır.",
    },
]

# ---------------------------------------------------------------------------
#  14 — Sorun Giderme
# ---------------------------------------------------------------------------
TROUBLESHOOTING = [
    {
        "title": "\"Container'larım kayboldu\" — context zinciri",
        "body": (
            "`docker` komutunun hangi motora gittiği beş katmanla belirlenir ve "
            "üstteki alttakini tamamen ezer:\n\n"
            "1. `-H` / `--host` bayrağı\n"
            "2. `DOCKER_HOST` ortam değişkeni\n"
            "3. `DOCKER_CONTEXT` ortam değişkeni\n"
            "4. `~/.docker/config.json` → `currentContext`\n"
            "5. `unix:///var/run/docker.sock`\n\n"
            "Kritik nokta: `DOCKER_HOST` ayarlıysa context YOK SAYILIR. "
            "`docker context use` komutu \"başarılı\" der ve hiçbir şey "
            "değişmez. Kullanıcı context'i değiştirdiğini sanır, container'lar "
            "görünmez kalır."),
        "snippet": (
            "echo \"DOCKER_HOST=$DOCKER_HOST\"\n"
            "echo \"DOCKER_CONTEXT=$DOCKER_CONTEXT\"\n"
            "docker context ls\n\n"
            "# Değişken nereden geliyor?\n"
            "grep -rn DOCKER_HOST ~/.bashrc ~/.zshrc ~/.profile "
            "~/.config/environment.d/ 2>/dev/null\n\n"
            "unset DOCKER_HOST   # yalnızca bu kabuk için"),
        "language": "bash",
        "tip": "kontainy bu zinciri Motorlar sayfasında katman katman gösterir "
               "ve kazananı işaretler — ve context'e hiç güvenmeyip bulduğu "
               "her motoru aynı anda listeler.",
        "rule_id": "CTX01",
    },
    {
        "title": "Exit code sözlüğü",
        "body": (
            "Bir container beklenmedik şekilde durduğunda ilk bakılacak yer "
            "çıkış kodudur. Çoğu koda anlamı doğrudan yazılıdır."),
        "table": {
            "headers": ["Kod", "Anlamı", "İlk bakılacak yer"],
            "rows": [
                ["0", "normal çıkış", "—"],
                ["1", "uygulama hatası", "`podman logs`"],
                ["125", "motor komutu başarısız", "bayraklar, imaj adı"],
                ["126", "komut çalıştırılamadı", "izinler, shebang"],
                ["127", "komut bulunamadı", "PATH, imaj içeriği"],
                ["137", "SIGKILL (128+9)", "**OOM veya `stop` zaman aşımı**"],
                ["139", "SIGSEGV (128+11)", "uygulama çökmesi, qemu/mimari"],
                ["143", "SIGTERM (128+15)", "normal durdurma"],
            ],
        },
        "snippet": (
            "podman inspect web --format '{{.State.ExitCode}} {{.State.OOMKilled}}'\n"
            "podman logs --tail 50 web\n"
            "journalctl -k | grep -i 'killed process'   # OOM kanıtı"),
        "language": "bash",
        "warning": "137 gördüğünüzde iki ihtimal var: bellek sınırı aşıldı "
                   "(OOM) ya da `stop` sırasında uygulama SIGTERM'e cevap "
                   "vermediği için SIGKILL yedi. `OOMKilled` alanı ayırt eder.",
    },
    {
        "title": "Disk doldu — nereye gitti",
        "body": (
            "Konteyner kaynaklı disk dolmasının üç ana sebebi var ve üçü de "
            "farklı komutla temizlenir. En sık atlanan build önbelleğidir: "
            "`image prune` onu SİLMEZ."),
        "snippet": (
            "podman system df -v         # ayrıntılı döküm\n"
            "docker system df -v\n\n"
            "# 1) Loglar — json-file varsayılanda SINIRSIZDIR\n"
            "du -sh /var/lib/docker/containers/*/*-json.log | sort -h | tail\n\n"
            "# 2) Build önbelleği — ayrı bir dünya\n"
            "docker builder prune\n\n"
            "# 3) Ölü container, imaj, volume\n"
            "podman system prune --volumes"),
        "language": "bash",
        "warning": "`prune --volumes` kullanılmayan volume'ları siler — içinde "
                   "veritabanı olabilir. Önce `-v` ile ne silineceğine bakın.",
        "rule_id": "DSK01",
        "setting_key": "log-opts.max-size",
    },
]


# ---------------------------------------------------------------------------
#  Kategoriler — Handoff'taki plana göre; hedefler sabit, içerik büyüyecek
# ---------------------------------------------------------------------------
LEARN_CATEGORIES = [
    {"id": "quickstart", "title": "Quick Start", "icon": "⚡",
     "color": "#f9e2af", "target": 8,
     "desc": "Your first container, ports, volumes and cleanup.",
     "topics": QUICK_START},
    {"id": "fundamentals", "title": "Container Internals", "icon": "📦",
     "color": "#89b4fa", "target": 14,
     "desc": "Namespaces, cgroups, capabilities and layered filesystems.",
     "topics": FUNDAMENTALS},
    {"id": "docker", "title": "Docker", "icon": "🐳",
     "color": "#89dceb", "target": 18,
     "desc": "Architecture, run flags, contexts, daemon.json, BuildKit.",
     "topics": []},
    {"id": "podman", "title": "Podman", "icon": "🦭",
     "color": "#a6e3a1", "target": 18,
     "desc": "Daemonless design, rootless, pods, containers.conf.",
     "topics": PODMAN},
    {"id": "systemd", "title": "systemd & Quadlet", "icon": "⚙️",
     "color": "#f5c2e7", "target": 10,
     "desc": "Units, linger, socket activation, .container files.",
     "topics": []},
    {"id": "kubernetes", "title": "Kubernetes", "icon": "☸️",
     "color": "#74c7ec", "target": 20,
     "desc": "Pods, deployments, services, kubeconfig, probes, RBAC.",
     "topics": []},
    {"id": "kvm", "title": "KVM / QEMU / libvirt", "icon": "🖥️",
     "color": "#cba6f7", "target": 12,
     "desc": "Hardware virtualisation, domain XML, virtio, snapshots, VFIO.",
     "topics": []},
    {"id": "lxc", "title": "LXC / LXD / Incus", "icon": "🧱",
     "color": "#fab387", "target": 10,
     "desc": "System containers, idmap, storage pools, clustering.",
     "topics": []},
    {"id": "network", "title": "Networking", "icon": "🌐",
     "color": "#94e2d5", "target": 14,
     "desc": "Bridges, macvlan, DNS, nftables, MTU, subnet clashes.",
     "topics": []},
    {"id": "storage", "title": "Storage", "icon": "💾",
     "color": "#f2cdcd", "target": 12,
     "desc": "Volumes, bind mounts, overlay2, quotas, SELinux labels.",
     "topics": []},
    {"id": "security", "title": "Security", "icon": "🔐",
     "color": "#f38ba8", "target": 14,
     "desc": "Rootless, capabilities, seccomp, signing, scanning, SBOM.",
     "topics": []},
    {"id": "images", "title": "Images & Registries", "icon": "🏗️",
     "color": "#eba0ac", "target": 12,
     "desc": "Manifests, digests, multi-arch, buildah, skopeo, mirrors.",
     "topics": []},
    {"id": "compose", "title": "Compose & Orchestration", "icon": "🎼",
     "color": "#b4befe", "target": 10,
     "desc": "Compose schema, profiles, healthchecks, when you need more.",
     "topics": []},
    {"id": "troubleshooting", "title": "Troubleshooting", "icon": "🔍",
     "color": "#f9e2af", "target": 14,
     "desc": "Lost containers, permissions, full disks, exit codes.",
     "topics": TROUBLESHOOTING},
    {"id": "performance", "title": "Performance", "icon": "🚀",
     "color": "#a6e3a1", "target": 10,
     "desc": "crun vs runc, overlay vs fuse, cache strategy, measuring.",
     "topics": []},
    {"id": "migration", "title": "Migration & Interop", "icon": "🔄",
     "color": "#89b4fa", "target": 8,
     "desc": "Docker to Podman, the shim, Desktop leftovers, WSL2, CI.",
     "topics": []},
]


def learn_stats() -> dict:
    written = sum(len(c["topics"]) for c in LEARN_CATEGORIES)
    target = sum(c["target"] for c in LEARN_CATEGORIES)
    return {
        "categories": len(LEARN_CATEGORIES),
        "written": written,
        "target": target,
        "percent": round(100 * written / target) if target else 0,
    }


def search_topics(text: str) -> list:
    """(kategori, konu) çiftleri döndürür."""
    t = text.casefold()
    hits = []
    for cat in LEARN_CATEGORIES:
        for topic in cat["topics"]:
            blob = " ".join(str(topic.get(k, "")) for k in
                            ("title", "body", "snippet", "tip", "note", "warning"))
            if t in blob.casefold():
                hits.append((cat, topic))
    return hits
