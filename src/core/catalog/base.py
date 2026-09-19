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


