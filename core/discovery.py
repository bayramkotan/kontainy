"""
kontainy — Motor Keşfi
============================

TEMEL İLKE: kontainy context sistemine GÜVENMEZ.

`docker` CLI hedefini şu öncelikle belirler:

    1. -H / --host bayrağı
    2. DOCKER_HOST ortam değişkeni
    3. DOCKER_CONTEXT ortam değişkeni
    4. ~/.docker/config.json → currentContext
    5. unix:///var/run/docker.sock

DOCKER_HOST ayarlıysa context TAMAMEN yok sayılır — `docker context use`
"başarılı" der ve hiçbir şey değişmez. Kullanıcının "container'larım kayboldu"
dediği durumun birinci sebebi budur.

Bu yüzden burada bulunan HER endpoint'e ayrı ayrı bağlanılır ve hepsi aynı
anda listelenir. Context değiştirme yalnızca TERMİNALİN hedefini ayarlayan
bir kolaylıktır; kontainy'in kendi görüşünü etkilemez.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .api import EngineClient, EngineError, EngineInfo


@dataclass
class Endpoint:
    """Keşfedilmiş tek bir motor adresi."""
    address: str                   # unix:///... veya tcp://...
    source: str                    # nereden bulundu (insan okunur)
    family: str                    # "docker" | "podman" | "bilinmiyor"
    name: str = ""                 # context adı varsa
    reachable: bool = False
    info: Optional[EngineInfo] = None
    error: str = ""
    is_cli_default: bool = False   # terminalin şu an gideceği yer burası mı

    @property
    def title(self) -> str:
        if self.info:
            tag = "rootless" if self.info.rootless else "rootful"
            return f"{self.info.kind} {self.info.version} ({tag})"
        return self.name or self.address


@dataclass
class CliTarget:
    """Terminalin ŞU AN hangi motora gittiğinin çözümlenmiş hâli.

    Katmanlar sırayla değerlendirilir; kazanan `winner` alanındadır.
    Ayar panelinde bu zincir olduğu gibi gösterilir.
    """
    layers: list = field(default_factory=list)   # (katman, değer, kazandı mı)
    winner: str = ""
    winner_layer: str = ""

    def as_rows(self) -> list:
        return self.layers


# ---------------------------------------------------------------------------
#  Aday soketler
# ---------------------------------------------------------------------------
def _xdg_runtime() -> str:
    return os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"


DOCKER_SOCKET_CANDIDATES = [
    ("/run/docker.sock",                      "yerel daemon"),
    ("/var/run/docker.sock",                  "yerel daemon (eski yol)"),
    (str(Path.home() / ".docker/desktop/docker.sock"), "Docker Desktop for Linux"),
    (str(Path.home() / ".docker/run/docker.sock"),     "Docker Desktop (yeni yol)"),
    (str(Path.home() / ".rd/docker.sock"),    "Rancher Desktop"),
    (str(Path.home() / ".colima/default/docker.sock"), "Colima"),
]


def podman_socket_candidates() -> list:
    return [
        (f"{_xdg_runtime()}/podman/podman.sock", "Podman rootless (user soketi)"),
        ("/run/podman/podman.sock",              "Podman rootful (sistem soketi)"),
    ]


# ---------------------------------------------------------------------------
#  Context dosyaları
# ---------------------------------------------------------------------------
def docker_cli_config() -> dict:
    path = Path.home() / ".docker" / "config.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def docker_contexts() -> list:
    """~/.docker/contexts/meta/*/meta.json içindeki tüm context'ler.

    Docker Desktop kurulumu kendi context'ini buraya yazar; GUI'de görünmeyen
    ama CLI'ı yönlendiren asıl kayıt budur.
    """
    out = []
    meta_dir = Path.home() / ".docker" / "contexts" / "meta"
    if not meta_dir.is_dir():
        return out
    for meta in meta_dir.glob("*/meta.json"):
        try:
            data = json.loads(meta.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        name = data.get("Name", "?")
        host = (data.get("Endpoints", {}).get("docker", {}) or {}).get("Host", "")
        if host:
            out.append((name, host))
    return out


def kube_contexts() -> list:
    """KUBECONFIG ve ~/.kube/config içindeki context adları."""
    paths = []
    env = os.environ.get("KUBECONFIG")
    if env:
        paths.extend(Path(p).expanduser() for p in env.split(":") if p)
    default = Path.home() / ".kube" / "config"
    if default.is_file():
        paths.append(default)

    names = []
    for path in paths:
        if not path.is_file():
            continue
        try:
            text = path.read_text()
        except OSError:
            continue
        # Küçük bir YAML alt kümesi — pyyaml bağımlılığı eklemeden context adlarını al.
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("- name:") and "contexts" in text[:text.find(line)]:
                names.append((stripped.split(":", 1)[1].strip(), str(path)))
    return names


# ---------------------------------------------------------------------------
#  Terminal hedefi çözümlemesi
# ---------------------------------------------------------------------------
def resolve_cli_target() -> CliTarget:
    """`docker` komutunun şu an nereye gideceğini katman katman çözer."""
    target = CliTarget()
    winner = None
    winner_layer = ""

    docker_host = os.environ.get("DOCKER_HOST", "")
    docker_context = os.environ.get("DOCKER_CONTEXT", "")
    cfg = docker_cli_config()
    current_context = cfg.get("currentContext", "")
    contexts = dict(docker_contexts())

    layers = [
        ("DOCKER_HOST (ortam değişkeni)", docker_host, bool(docker_host)),
        ("DOCKER_CONTEXT (ortam değişkeni)", docker_context,
         bool(docker_context) and not docker_host),
        ("config.json → currentContext", current_context,
         bool(current_context) and not docker_host and not docker_context),
        ("yerleşik varsayılan", "unix:///var/run/docker.sock",
         not docker_host and not docker_context and not current_context),
    ]

    for name, value, won in layers:
        target.layers.append((name, value or "—", won))
        if won and winner is None:
            winner_layer = name
            if name.startswith("DOCKER_HOST"):
                winner = value
            elif "CONTEXT" in name.upper() or "currentContext" in name:
                winner = contexts.get(value, f"(context bulunamadı: {value})")
            else:
                winner = value

    target.winner = winner or ""
    target.winner_layer = winner_layer
    return target


def docker_shim_warning() -> Optional[str]:
    """`/usr/bin/docker` aslında Podman'ın shim'i mi?"""
    docker = shutil.which("docker")
    if not docker:
        return None
    try:
        real = os.path.realpath(docker)
    except OSError:
        return None
    if "podman" in real:
        return (f"`docker` komutu aslında Podman'a gidiyor "
                f"({docker} → {real}). podman-docker paketi kurulu.")
    return None


def systemd_unit_state(unit: str, user: bool = True) -> str:
    """Bir systemd biriminin durumu ('active', 'inactive', 'bulunamadı')."""
    cmd = ["systemctl"]
    if user:
        cmd.append("--user")
    cmd += ["is-active", unit]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        return (result.stdout or result.stderr).strip() or "bilinmiyor"
    except (OSError, subprocess.TimeoutExpired):
        return "bulunamadı"


# ---------------------------------------------------------------------------
#  Ana keşif
# ---------------------------------------------------------------------------
def discover(probe: bool = True) -> list:
    """Sistemdeki tüm motor endpoint'lerini bulur ve (istenirse) yoklar.

    Aynı adrese birden çok kaynaktan ulaşılıyorsa tek girdi olur, kaynak
    bilgileri birleştirilir.
    """
    found: dict = {}

    def add(address: str, source: str, family: str, name: str = ""):
        address = address if "://" in address else f"unix://{address}"
        if address in found:
            if source not in found[address].source:
                found[address].source += f", {source}"
            if name and not found[address].name:
                found[address].name = name
            return
        found[address] = Endpoint(address=address, source=source,
                                  family=family, name=name)

    # 1) Ortam değişkeni
    env_host = os.environ.get("DOCKER_HOST")
    if env_host:
        add(env_host, "DOCKER_HOST ortam değişkeni", "bilinmiyor")

    # 2) Docker context'leri (Desktop dahil)
    for name, host in docker_contexts():
        add(host, f"docker context: {name}", "docker", name=name)

    # 3) Bilinen Docker soketleri
    for path, label in DOCKER_SOCKET_CANDIDATES:
        if Path(path).exists():
            add(path, label, "docker")

    # 4) Bilinen Podman soketleri
    for path, label in podman_socket_candidates():
        if Path(path).exists():
            add(path, label, "podman")

    endpoints = list(found.values())

    # 5) Terminalin gideceği hedefi işaretle
    target = resolve_cli_target()
    for ep in endpoints:
        if target.winner and ep.address.replace("unix://", "") == \
                target.winner.replace("unix://", ""):
            ep.is_cli_default = True

    if not probe:
        return endpoints

    # 6) Her endpoint'e ayrı ayrı bağlan — context'e bakma
    for ep in endpoints:
        client = EngineClient(ep.address, label=ep.name or ep.address, timeout=4.0)
        try:
            ep.info = client.identify()
            ep.reachable = True
            ep.family = ep.info.kind
        except EngineError as exc:
            ep.reachable = False
            ep.error = str(exc)

    return endpoints


def client_for(endpoint: Endpoint, timeout: float = 15.0) -> EngineClient:
    return EngineClient(endpoint.address, label=endpoint.title, timeout=timeout)


if __name__ == "__main__":
    print("=== Terminal hedefi ===")
    t = resolve_cli_target()
    for layer, value, won in t.as_rows():
        print(f"  {'>>' if won else '  '} {layer:38} {value}")
    print(f"  KAZANAN: {t.winner}  ({t.winner_layer})\n")

    warn = docker_shim_warning()
    if warn:
        print(f"!! {warn}\n")

    print("=== Bulunan motorlar ===")
    for ep in discover():
        mark = "*" if ep.is_cli_default else " "
        state = ep.title if ep.reachable else f"ERİŞİLEMİYOR — {ep.error}"
        print(f" {mark} {ep.address}")
        print(f"     kaynak : {ep.source}")
        print(f"     durum  : {state}")
