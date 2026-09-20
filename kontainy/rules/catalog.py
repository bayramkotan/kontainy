"""
kontainy — Kural seti
======================

Her kural gerçek bir belirtiye karşılık gelir. Uydurma kontrol eklenmez —
VenvStudio'daki Code Map dersinin aynısı: **her kural bu ekosistemin
gerçekten ürettiği bir hata sınıfına karşılık gelmeli.**

Kural kimliği önekleri:
    CTX  context ve terminal hedefi
    PERM izinler
    POD  Podman / rootless
    NET  ağ
    DSK  disk
    RES  kaynak sınırları
    SVC  servis ve systemd
    DKR  Docker Desktop / sanallaştırma
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .engine import ERROR, INFO, WARN, Rule

# ---------------------------------------------------------------------------
#  CTX — context ve terminal hedefi
# ---------------------------------------------------------------------------


def _ctx01(env):
    if env.docker_host and env.current_context:
        return {"host": env.docker_host, "context": env.current_context}
    return None


def _ctx02(env):
    docker_eps = [e for e in env.endpoints if e.reachable and e.family == "docker"]
    if len(docker_eps) < 2:
        return None
    versions = {e.info.version for e in docker_eps if e.info}
    if len(versions) < 2:
        return None
    return {"count": len(docker_eps), "versions": ", ".join(sorted(versions))}


def _ctx03(env):
    store = env.docker_cli_config.get("credsStore", "")
    if not store:
        return None
    if shutil.which(f"docker-credential-{store}"):
        return None
    return {"store": store}


def _ctx04(env):
    user = set(env.cli_plugin_dirs.get("user", []))
    system = set(env.cli_plugin_dirs.get("system", [])) | \
        set(env.cli_plugin_dirs.get("libexec", []))
    shadowed = sorted(user & system)
    if not shadowed:
        return None
    return {"plugins": ", ".join(shadowed)}


def _ctx05(env):
    if env.docker_real_path and "podman" in env.docker_real_path:
        return {"link": env.docker_binary, "target": env.docker_real_path}
    return None


def _ctx06(env):
    """Terminalin gittiği hedef erişilebilir mi?"""
    target = getattr(env.cli_target, "winner", "")
    if not target:
        return None
    wanted = target.replace("unix://", "")
    for ep in env.endpoints:
        if ep.address.replace("unix://", "") == wanted:
            return None if ep.reachable else {"target": target, "error": ep.error}
    return {"target": target, "error": "hiç bulunamadı"}


# ---------------------------------------------------------------------------
#  PERM — izinler
# ---------------------------------------------------------------------------
def _perm01(env):
    unreachable = [e for e in env.endpoints
                   if not e.reachable and "denied" in (e.error or "").lower()]
    if not unreachable:
        return None
    if "docker" in env.user_groups:
        return {"sockets": ", ".join(e.address for e in unreachable),
                "note": "Kullanıcı `docker` grubunda görünüyor — grup üyeliği "
                        "bu oturuma henüz yansımamış olabilir."}
    return {"sockets": ", ".join(e.address for e in unreachable),
            "note": "Kullanıcı `docker` grubunda değil."}


# ---------------------------------------------------------------------------
#  POD — Podman ve rootless
# ---------------------------------------------------------------------------
def _pod01(env):
    if not env.podman_binary:
        return None
    has_socket = any("podman" in e.address for e in env.endpoints if e.reachable)
    if has_socket:
        return None
    state = env.units.get(("podman.socket", "user"), "bilinmiyor")
    return {"state": state}


def _pod02(env):
    if not env.podman_binary or not env.username:
        return None
    if env.linger:
        return None
    return {"user": env.username}


def _pod03(env):
    if not env.podman_binary or not env.username:
        return None
    if env.subuid_ok and env.subgid_ok:
        return None
    missing = []
    if not env.subuid_ok:
        missing.append("/etc/subuid")
    if not env.subgid_ok:
        missing.append("/etc/subgid")
    return {"user": env.username, "files": " ve ".join(missing)}


def _pod04(env):
    """Rootless Podman var ama auto-update timer kapalı — sadece bilgi."""
    if not env.podman_binary:
        return None
    state = env.units.get(("podman-auto-update.timer", "user"), "")
    if state == "active":
        return None
    return {"state": state or "bulunamadı"}


# ---------------------------------------------------------------------------
#  NET — ağ
# ---------------------------------------------------------------------------
def _docker_pools(env) -> list:
    pools = []
    for entry in env.daemon_json.get("default-address-pools") or []:
        base = entry.get("base") if isinstance(entry, dict) else None
        if base:
            pools.append(base)
    if not pools:
        pools = ["172.17.0.0/16", "172.18.0.0/16"]
    bip = env.daemon_json.get("bip")
    if bip:
        pools.append(bip)
    return pools


def _prefix16(cidr: str) -> str:
    return ".".join(cidr.split("/")[0].split(".")[:2])


def _net01(env):
    if not env.host_routes:
        return None
    docker_prefixes = {_prefix16(p) for p in _docker_pools(env)}
    clashes = []
    for route in env.host_routes:
        if "docker" in route or "podman" in route or "cni" in route:
            continue
        dest = route.split()[0]
        if "/" not in dest:
            continue
        if _prefix16(dest) in docker_prefixes:
            clashes.append(route)
    if not clashes:
        return None
    return {"routes": "; ".join(clashes[:3])}


def _net02(env):
    if env.unprivileged_port_start <= 80:
        return None
    if not env.podman_binary:
        return None
    return {"value": env.unprivileged_port_start}


def _net03(env):
    """Arch/CachyOS'ta nftables var, iptables-nft köprüsü yok."""
    if not shutil.which("nft"):
        return None
    if shutil.which("iptables"):
        return None
    if not any(e.reachable for e in env.endpoints):
        return None
    return {}


# ---------------------------------------------------------------------------
#  DSK — disk
# ---------------------------------------------------------------------------
def _dsk01(env):
    driver = env.daemon_json.get("log-driver", "json-file")
    opts = env.daemon_json.get("log-opts") or {}
    if driver != "json-file":
        return None
    if opts.get("max-size"):
        return None
    if not any(e.reachable and e.family == "docker" for e in env.endpoints):
        return None
    return {"path": env.daemon_json_path}


def _dsk02(env):
    gc = (env.daemon_json.get("builder") or {}).get("gc") or {}
    if not any(e.reachable and e.family == "docker" for e in env.endpoints):
        return None
    if gc.get("defaultKeepStorage") or gc.get("enabled") is False:
        return None
    return {}


# ---------------------------------------------------------------------------
#  RES — kaynak sınırları
# ---------------------------------------------------------------------------
def _res01(env):
    """cgroup v2 + rootless + cgroupfs = sınırlar sessizce yok sayılır."""
    if not Path("/sys/fs/cgroup/cgroup.controllers").exists():
        return None
    rootless = [e for e in env.endpoints
                if e.reachable and e.info and e.info.rootless]
    if not rootless:
        return None
    user_conf = Path.home() / ".config/containers/containers.conf"
    try:
        text = user_conf.read_text(encoding="utf-8") if user_conf.is_file() else ""
    except OSError:
        text = ""
    if "cgroupfs" not in text:
        return None
    return {"path": str(user_conf)}


# ---------------------------------------------------------------------------
#  SVC — servis ve systemd
# ---------------------------------------------------------------------------
def _svc01(env):
    sock = env.units.get(("docker.socket", "system"), "")
    svc = env.units.get(("docker.service", "system"), "")
    if sock == "active" and svc == "active":
        return {}
    return None


# ---------------------------------------------------------------------------
#  DKR — Docker Desktop ve sanallaştırma
# ---------------------------------------------------------------------------
def _dkr01(env):
    desktop = [e for e in env.endpoints if "desktop" in e.address]
    if not desktop:
        return None
    if env.kvm_present and env.kvm_readable:
        return None
    if not env.kvm_present:
        return {"reason": "/dev/kvm yok — sanallaştırma BIOS'ta kapalı olabilir"}
    return {"reason": "/dev/kvm var ama okunamıyor — kullanıcı `kvm` grubunda değil"}


# ---------------------------------------------------------------------------
#  Kural tablosu
# ---------------------------------------------------------------------------
RULES = [
    Rule(
        id="CTX01", severity=ERROR,
        title="DOCKER_HOST context'i eziyor",
        detect=_ctx01,
        explain=(
            "`DOCKER_HOST` ortam değişkeni `{host}` olarak ayarlı. Bu değişken "
            "varken `~/.docker/config.json` içindeki context (`{context}`) "
            "TAMAMEN yok sayılır.\n\n"
            "Sonuç: `docker context use` komutu \"başarılı\" der ve hiçbir şey "
            "değişmez. Bu, \"container'larım kayboldu\" şikayetinin bir numaralı "
            "sebebidir.\n\n"
            "Değişkenin nereden geldiğini bulmak için kabuk başlangıç "
            "dosyalarına bakın: ~/.bashrc, ~/.zshrc, ~/.profile, "
            "~/.config/environment.d/*.conf"),
        fix_command="unset DOCKER_HOST",
        fix_scope="user",
        setting_key="currentContext",
        learn_topic="troubleshooting/context-chain",
        tags=["context", "kritik"],
    ),
    Rule(
        id="CTX02", severity=INFO,
        title="Aynı anda birden çok Docker motoru çalışıyor",
        detect=_ctx02,
        explain=(
            "{count} ayrı Docker motoru erişilebilir durumda ve sürümleri "
            "farklı: {versions}.\n\n"
            "Bu bir hata değil — ama CLI aynı anda yalnızca birine bakar. "
            "Bir container'ı terminalde göremiyorsanız muhtemelen öteki "
            "motordadır. kontainy hepsini Container'lar sayfasında Motor "
            "sütunuyla birlikte gösterir."),
        fix_scope="none",
        learn_topic="troubleshooting/multiple-engines",
        tags=["context"],
    ),
    Rule(
        id="CTX03", severity=ERROR,
        title="Kimlik yardımcısı eksik: docker-credential-{store}",
        detect=_ctx03,
        explain=(
            "`~/.docker/config.json` içinde `credsStore: \"{store}\"` yazıyor "
            "ama `docker-credential-{store}` programı PATH'te yok.\n\n"
            "Bu genellikle Docker Desktop kaldırıldığında olur: ayar geride "
            "kalır ve her `docker` komutu "
            "`docker-credential-{store} not found in $PATH` hatası verir.\n\n"
            "Çözüm anahtarı silmektir; kayıtlı registry parolaları "
            "`~/.docker/config.json` içinde düz metne döner, tekrar "
            "`docker login` yapmanız gerekebilir."),
        fix_command=(
            "python -c \"import json,pathlib;"
            "p=pathlib.Path.home()/'.docker/config.json';"
            "d=json.loads(p.read_text());d.pop('credsStore',None);"
            "p.write_text(json.dumps(d,indent=2))\""),
        fix_scope="user",
        setting_key="credsStore",
        learn_topic="migration/desktop-leftovers",
        tags=["desktop", "kritik"],
    ),
    Rule(
        id="CTX04", severity=WARN,
        title="CLI eklentileri gölgeleniyor",
        detect=_ctx04,
        explain=(
            "Şu eklentiler hem `~/.docker/cli-plugins` hem sistem dizininde "
            "var: {plugins}.\n\n"
            "Kullanıcı dizini önce gelir, yani distro paketinin sürümü "
            "gölgelenir. `docker compose version` ile `docker-compose version` "
            "farklı çıkabilir ve hangisinin çalıştığı belirsizleşir.\n\n"
            "Docker Desktop kurulumu bu dizini kendi eklentileriyle doldurur."),
        fix_command="ls -l ~/.docker/cli-plugins /usr/lib/docker/cli-plugins",
        fix_scope="user",
        setting_key="cliPluginsExtraDirs",
        learn_topic="migration/desktop-leftovers",
        tags=["desktop", "compose"],
    ),
    Rule(
        id="CTX05", severity=INFO,
        title="`docker` komutu aslında Podman'a gidiyor",
        detect=_ctx05,
        explain=(
            "`{link}` → `{target}`. Sisteme `podman-docker` paketi kurulu ve "
            "`docker` komutu Podman'ın uyumluluk sarmalayıcısı.\n\n"
            "Bu bir hata değil, ama bilinmezse saatler yakar: `docker run` "
            "çalışır, `docker ps` boş döner (Podman'ın kendi deposuna bakar), "
            "ve Docker'a özel bazı bayraklar sessizce farklı davranır."),
        fix_scope="none",
        learn_topic="migration/podman-docker-shim",
        tags=["podman", "uyumluluk"],
    ),
    Rule(
        id="CTX06", severity=ERROR,
        title="Terminalin gittiği hedefe ulaşılamıyor",
        detect=_ctx06,
        explain=(
            "`docker` komutu `{target}` adresine gidiyor ama oraya "
            "bağlanılamıyor: {error}\n\n"
            "Terminalde çalıştıracağınız her `docker` komutu bu hatayı "
            "verecek. kontainy diğer motorları göstermeye devam eder."),
        fix_command="docker context ls",
        fix_scope="user",
        learn_topic="troubleshooting/context-chain",
        tags=["context", "kritik"],
    ),

    Rule(
        id="PERM01", severity=ERROR,
        title="Sokete erişim reddedildi",
        detect=_perm01,
        explain=(
            "Şu soket(ler)e izin hatasıyla bağlanılamadı: {sockets}\n\n{note}\n\n"
            "Gruba eklendikten sonra **yeniden giriş yapılması** gerekir; "
            "`newgrp docker` yalnızca o kabuk için geçerlidir ve GUI "
            "uygulamaları etkilenmez."),
        fix_command="sudo usermod -aG docker $USER   # sonra oturumu kapatıp açın",
        fix_scope="root",
        learn_topic="troubleshooting/permissions",
        tags=["izin", "kritik"],
    ),

    Rule(
        id="POD01", severity=WARN,
        title="Podman kurulu ama soketi çalışmıyor",
        detect=_pod01,
        explain=(
            "`podman` kurulu fakat API soketi bulunamadı "
            "(`podman.socket` --user durumu: {state}).\n\n"
            "Soket olmadan kontainy Podman container'larını API üzerinden "
            "listeleyemez. Soket systemd tarafından talep üzerine başlatılır; "
            "kalıcı olması için etkinleştirilmelidir."),
        fix_command="systemctl --user enable --now podman.socket",
        fix_scope="user",
        learn_topic="systemd/socket-activation",
        tags=["podman", "systemd"],
    ),
    Rule(
        id="POD02", severity=WARN,
        title="Linger kapalı — rootless container'lar çıkışta ölecek",
        detect=_pod02,
        explain=(
            "`{user}` kullanıcısı için linger kapalı. Kullanıcı systemd "
            "birimleri yalnızca oturum açıkken çalışır; oturumu kapattığınızda "
            "veya SSH bağlantısı düştüğünde **rootless container'lar durur** ve "
            "makine yeniden başladığında geri gelmez.\n\n"
            "Quadlet birimlerinin ve `--restart=always` beklentisinin çalışması "
            "için bu şarttır — rootless kurulumlarda en sık atlanan adım."),
        fix_command="loginctl enable-linger $USER",
        fix_scope="user",
        setting_key="Install.WantedBy",
        learn_topic="systemd/linger",
        tags=["podman", "rootless", "systemd", "kritik"],
    ),
    Rule(
        id="POD03", severity=ERROR,
        title="subuid/subgid kaydı yok — rootless Podman çalışmaz",
        detect=_pod03,
        explain=(
            "`{user}` kullanıcısı için {files} dosyasında kayıt bulunamadı.\n\n"
            "Rootless Podman container içindeki kullanıcıları host'ta bir UID "
            "aralığına eşler; bu aralık olmadan imaj çekilemez ve container "
            "başlatılamaz. Tipik belirti: "
            "`potentially insufficient UIDs or GIDs available in user namespace`.\n\n"
            "⚠️ Kayıt eklendikten sonra `podman system migrate` çalıştırılmalıdır, "
            "yoksa mevcut container'lar eski eşlemeyle kalır."),
        fix_command=(
            "sudo usermod --add-subuids 100000-165535 "
            "--add-subgids 100000-165535 $USER && podman system migrate"),
        fix_scope="root",
        learn_topic="podman/rootless-subuid",
        tags=["podman", "rootless", "kritik"],
    ),
    Rule(
        id="POD04", severity=INFO,
        title="Otomatik güncelleme zamanlayıcısı kapalı",
        detect=_pod04,
        explain=(
            "`podman-auto-update.timer` durumu: {state}.\n\n"
            "Bir container'a `AutoUpdate=registry` etiketi koymak tek başına "
            "yetmez; güncellemeyi yapan bu zamanlayıcıdır. Kapalıyken etiket "
            "sessizce hiçbir şey yapmaz."),
        fix_command="systemctl --user enable --now podman-auto-update.timer",
        fix_scope="user",
        setting_key="Container.AutoUpdate",
        learn_topic="systemd/auto-update",
        tags=["podman", "systemd"],
    ),

    Rule(
        id="NET01", severity=ERROR,
        title="Docker adres havuzu yerel ağla çakışıyor",
        detect=_net01,
        explain=(
            "Docker'ın kullandığı IP bloğuyla aynı /16 önekine sahip bir yerel "
            "rota var: {routes}\n\n"
            "Bu, Docker kurulduğunda kurumsal ağın veya VPN'in tamamen "
            "erişilemez olmasının klasik sebebidir. Çözüm Docker'ı "
            "kullanılmayan bir bloğa taşımaktır (örneğin 10.200.0.0/16).\n\n"
            "⚠️ `default-address-pools` yalnızca YENİ ağları etkiler; "
            "`docker0` köprüsünün kendisi için `bip` anahtarı gerekir."),
        fix_command="sudo $EDITOR /etc/docker/daemon.json   # default-address-pools",
        fix_scope="root",
        setting_key="default-address-pools",
        learn_topic="network/subnet-clash",
        tags=["ağ", "vpn", "kritik"],
    ),
    Rule(
        id="NET02", severity=INFO,
        title="Rootless'ta 1024 altı portlar bağlanamaz",
        detect=_net02,
        explain=(
            "`net.ipv4.ip_unprivileged_port_start` = {value}. Rootless "
            "container'lar bu değerin altındaki portlara bağlanamaz — "
            "80 ve 443 dahil.\n\n"
            "Bir web sunucusunu rootless çalıştırmak istiyorsanız ya yüksek "
            "port kullanın (8080) ya da bu sysctl değerini düşürün. "
            "Kalıcı yapmak için /etc/sysctl.d/ altına bir dosya gerekir."),
        fix_command="sudo sysctl net.ipv4.ip_unprivileged_port_start=80",
        fix_scope="root",
        setting_key="Container.PublishPort",
        learn_topic="network/rootless-ports",
        tags=["podman", "rootless", "ağ"],
    ),
    Rule(
        id="NET03", severity=WARN,
        title="nftables var, iptables uyumluluk katmanı yok",
        detect=_net03,
        explain=(
            "Sistemde `nft` var ama `iptables` komutu bulunamadı. Docker ve "
            "netavark port yayınlama kurallarını iptables arayüzü üzerinden "
            "yazar; bu katman yoksa **port yayınlama sessizce çalışmaz** — "
            "container ayağa kalkar, porta erişilemez.\n\n"
            "Arch/CachyOS'ta `iptables-nft` paketi bu köprüyü sağlar."),
        fix_command="sudo pacman -S iptables-nft",
        fix_scope="root",
        setting_key="network.firewall_driver",
        learn_topic="network/firewall-backends",
        tags=["ağ", "arch", "güvenlik duvarı"],
    ),

    Rule(
        id="DSK01", severity=WARN,
        title="Docker logları sınırsız büyüyor",
        detect=_dsk01,
        explain=(
            "`{path}` içinde log döndürme ayarlanmamış. `json-file` sürücüsü "
            "varsayılan olarak SINIRSIZDIR: uzun çalışan bir container'ın log "
            "dosyası gigabaytlara çıkıp kök diski doldurur.\n\n"
            "Bu, Docker kaynaklı disk dolmasının bir numaralı sebebidir. "
            "Önerilen başlangıç: `max-size: 10m`, `max-file: 3`."),
        fix_command="sudo $EDITOR /etc/docker/daemon.json   # log-opts.max-size",
        fix_scope="root",
        setting_key="log-opts.max-size",
        learn_topic="storage/log-rotation",
        tags=["disk", "log", "kritik"],
    ),
    Rule(
        id="DSK02", severity=INFO,
        title="BuildKit önbelleği sınırsız",
        detect=_dsk02,
        explain=(
            "`builder.gc` yapılandırılmamış. Sık build yapılan makinelerde "
            "build önbelleği imajlardan daha çok yer kaplayabilir.\n\n"
            "⚠️ `docker image prune` bu önbelleği SİLMEZ — `docker system df` "
            "çıktısında ayrı bir satırdır ve `docker builder prune` gerekir."),
        fix_command="docker system df && docker builder prune",
        fix_scope="user",
        setting_key="builder.gc.defaultKeepStorage",
        learn_topic="performance/build-cache",
        tags=["disk", "buildkit"],
    ),

    Rule(
        id="RES01", severity=WARN,
        title="cgroupfs seçili — kaynak sınırları sessizce uygulanmayabilir",
        detect=_res01,
        explain=(
            "`{path}` içinde `cgroupfs` geçiyor ve sistem cgroup v2 kullanıyor.\n\n"
            "Rootless + cgroup v2 birleşiminde `--memory`, `--cpus` ve "
            "`--pids-limit` gibi sınırların uygulanabilmesi için "
            "`cgroup_manager = \"systemd\"` gerekir. cgroupfs ile sınırlar "
            "**hata vermeden yok sayılır** — sınır koyduğunuzu sanırsınız, "
            "container tüm makineyi kullanır."),
        fix_command="podman info --format '{{.Host.CgroupManager}}'",
        fix_scope="user",
        setting_key="containers.cgroup_manager",
        learn_topic="troubleshooting/silent-limits",
        tags=["cgroup", "rootless", "kritik"],
    ),

    Rule(
        id="SVC01", severity=INFO,
        title="docker.socket açık — servisi durdurmak yetmez",
        detect=_svc01,
        explain=(
            "Hem `docker.service` hem `docker.socket` etkin. Socket activation "
            "açıkken `systemctl stop docker.service` komutundan sonra ilk "
            "`docker` komutu daemon'ı **yeniden başlatır**.\n\n"
            "Daemon'ı gerçekten durdurmak için ikisinin birden durdurulması "
            "gerekir."),
        fix_command="sudo systemctl stop docker.socket docker.service",
        fix_scope="root",
        learn_topic="systemd/socket-activation",
        tags=["systemd", "docker"],
    ),

    Rule(
        id="DKR01", severity=ERROR,
        title="Docker Desktop için sanallaştırma hazır değil",
        detect=_dkr01,
        explain=(
            "Docker Desktop soketi bulundu ama {reason}.\n\n"
            "Docker Desktop for Linux bir sanal makine içinde çalışır ve "
            "KVM'e erişemezse hiç açılmaz."),
        fix_command="sudo usermod -aG kvm $USER   # sonra oturumu kapatıp açın",
        fix_scope="root",
        learn_topic="kvm/basics",
        tags=["desktop", "kvm"],
    ),
]


def rule_by_id(rule_id: str):
    for rule in RULES:
        if rule.id == rule_id:
            return rule
    return None


def rule_stats() -> dict:
    from .engine import ERROR as E, INFO as I, WARN as W
    return {
        "toplam": len(RULES),
        "hata": len([r for r in RULES if r.severity == E]),
        "uyari": len([r for r in RULES if r.severity == W]),
        "bilgi": len([r for r in RULES if r.severity == I]),
    }
