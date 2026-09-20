"""
kontainy — Ayar Kataloğu
=========================

Bu paket projenin KALBİDİR. Docker ve Podman'ın tüm yapılandırma yüzeyi
burada yapısal veri olarak durur; arayüz bu katalogtan ÜRETİLİR, hiçbir ayar
GUI'ye elle gömülmez.

VenvStudio'daki CONFLICT_RULES ile aynı rolü oynar: tek kaynak, GUI onu okur.

Parçalar
--------
base.py        Setting dataclass'ı, yüzey sabitleri, dosya yolları, bağlantılar
docker.py      daemon.json + ~/.docker/config.json
podman.py      containers.conf + storage.conf + registries.conf
run_flags.py   container başına çalıştırma bayrakları (her iki motor)
quadlet.py     systemd birim anahtarları (yalnızca Podman)

Yeni ayar eklerken zorunlu alanlar: key, engine, surface, file, vtype, title,
desc. Kuvvetle önerilen: default, cli, restart, privilege, danger, gotcha,
docs, tags.

`gotcha` bu ürünün farkıdır. Bir ayarı listelemek kolaydır; bilinmediğinde
saat yakan ayrıntıyı yazmak zordur ve rakiplerin hiçbirinde yoktur.
"""

from .base import (                                          # noqa: F401
    Setting, S, FILES,
    SURFACE_DAEMON, SURFACE_STORAGE, SURFACE_NETWORK, SURFACE_REGISTRY,
    SURFACE_CONTAINER, SURFACE_SECURITY, SURFACE_RESOURCE, SURFACE_LOGGING,
    SURFACE_BUILD, SURFACE_SYSTEMD,
)
from .docker import DOCKER_DAEMON, DOCKER_CLI
from .podman import PODMAN_CONTAINERS, PODMAN_STORAGE, PODMAN_REGISTRIES
from .run_flags import RUN_FLAGS
from .quadlet import QUADLET

ALL_SETTINGS: list = (
    DOCKER_DAEMON + DOCKER_CLI
    + PODMAN_CONTAINERS + PODMAN_STORAGE + PODMAN_REGISTRIES
    + RUN_FLAGS + QUADLET
)

SURFACE_TITLES = {
    SURFACE_DAEMON:    "Engine / Daemon",
    SURFACE_STORAGE:   "Storage",
    SURFACE_NETWORK:   "Networking",
    SURFACE_REGISTRY:  "Registry",
    SURFACE_CONTAINER: "Container",
    SURFACE_SECURITY:  "Security",
    SURFACE_RESOURCE:  "Resource limits",
    SURFACE_LOGGING:   "Logging",
    SURFACE_BUILD:     "Build",
    SURFACE_SYSTEMD:   "systemd / Quadlet",
}

SURFACE_ICONS = {
    SURFACE_DAEMON:    "⚙",
    SURFACE_STORAGE:   "💾",
    SURFACE_NETWORK:   "🌐",
    SURFACE_REGISTRY:  "📦",
    SURFACE_CONTAINER: "🧱",
    SURFACE_SECURITY:  "🔐",
    SURFACE_RESOURCE:  "📊",
    SURFACE_LOGGING:   "📝",
    SURFACE_BUILD:     "🏗",
    SURFACE_SYSTEMD:   "🔧",
}

DANGER_TITLES = {0: "Safe", 1: "Careful", 2: "Dangerous"}


# ---------------------------------------------------------------------------
#  Sorgular
# ---------------------------------------------------------------------------
def by_key(key: str):
    """Anahtara göre tek bir ayar döndürür (yoksa None)."""
    for s in ALL_SETTINGS:
        if s.key == key:
            return s
    return None


def by_engine(engine: str) -> list:
    """Bir motora ait ayarlar ('both' olanlar her zaman dahil)."""
    return [s for s in ALL_SETTINGS if s.engine in (engine, "both")]


def by_surface(surface: str, engine: str = None) -> list:
    """Bir yüzeye ait ayarlar, istenirse motora göre süzülmüş."""
    out = [s for s in ALL_SETTINGS if s.surface == surface]
    if engine:
        out = [s for s in out if s.engine in (engine, "both")]
    return out


def by_file(file_key: str) -> list:
    """Belirli bir yapılandırma dosyasına yazılan ayarlar."""
    return [s for s in ALL_SETTINGS if s.file == file_key]


def search(text: str) -> list:
    """Anahtar, başlık, açıklama, tuzak, CLI bayrağı ve etiketlerde arama."""
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
    """Bilinmediğinde saat yakan ayarlar — Tuzaklar panelini besler."""
    return [s for s in ALL_SETTINGS if s.gotcha]


def dangerous() -> list:
    """İzolasyonu veya kararlılığı zayıflatan ayarlar."""
    return [s for s in ALL_SETTINGS if s.danger >= 2]


def user_scoped() -> list:
    """Root gerektirmeyen, kontainy'nin doğrudan yazabileceği ayarlar."""
    return [s for s in ALL_SETTINGS if s.privilege == "user"]


def all_tags() -> list:
    """Katalogda geçen tüm etiketler, alfabetik."""
    tags = set()
    for s in ALL_SETTINGS:
        tags.update(s.tags)
    return sorted(tags)


def stats() -> dict:
    """Katalog özeti — durum çubuğunda ve Hakkında panelinde gösterilir."""
    return {
        "toplam": len(ALL_SETTINGS),
        "docker": len([s for s in ALL_SETTINGS if s.engine == "docker"]),
        "podman": len([s for s in ALL_SETTINGS if s.engine == "podman"]),
        "ortak": len([s for s in ALL_SETTINGS if s.engine == "both"]),
        "kullanici_kapsami": len(user_scoped()),
        "tuzakli": len(with_gotchas()),
        "tehlikeli": len(dangerous()),
        "yuzey": len({s.surface for s in ALL_SETTINGS}),
    }


if __name__ == "__main__":
    for k, v in stats().items():
        print(f"{k:22} {v}")
