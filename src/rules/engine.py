"""
kontainy — Teşhis motoru
=========================

VenvStudio'daki Conflict Manager'ın karşılığı ve projenin üçüncü direği.

Her kural üç şey söyler: **tespit → açıklama → düzeltme komutu.**

Bu projede hataların çoğu SESSİZDİR — yanlış sokete bağlanırsın, hata almazsın,
boş liste görürsün; bir bellek sınırı koyarsın, uygulanmaz, uyarı çıkmaz.
O yüzden "çalıştırmadan önce söyle" ilkesi burada VenvStudio'dakinden daha
kritik.

⚠️ Hiçbir kural root gerektirmez. Tespit her zaman kullanıcı yetkisiyle
yapılır; düzeltme root istiyorsa komut GÖSTERİLİR, çalıştırılmaz.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from ..core import discovery
from ..utils.config import log

# --- Önem düzeyleri --------------------------------------------------------
ERROR = "error"      # bir şey çalışmıyor
WARN = "warn"        # çalışıyor ama ileride ısıracak
INFO = "info"        # hata değil, bilinmezse şaşırtır

SEVERITY_TITLES = {ERROR: "Error", WARN: "Warning", INFO: "Info"}
SEVERITY_ICONS = {ERROR: "🔴", WARN: "🟡", INFO: "🔵"}
SEVERITY_ORDER = {ERROR: 0, WARN: 1, INFO: 2}


# ---------------------------------------------------------------------------
#  Ortam fotoğrafı — kurallar bunu okur, sistemi tekrar tekrar yoklamazlar
# ---------------------------------------------------------------------------
@dataclass
class Environment:
    """Tek seferde toplanan sistem durumu."""

    docker_host: str = ""
    docker_context_env: str = ""
    current_context: str = ""
    contexts: dict = field(default_factory=dict)
    cli_target: Optional[object] = None

    endpoints: list = field(default_factory=list)

    docker_cli_config: dict = field(default_factory=dict)
    daemon_json: dict = field(default_factory=dict)
    daemon_json_path: str = ""

    docker_binary: str = ""
    docker_real_path: str = ""
    podman_binary: str = ""

    user_groups: list = field(default_factory=list)
    uid: int = 0
    username: str = ""

    subuid_ok: bool = False
    subgid_ok: bool = False
    linger: bool = False
    unprivileged_port_start: int = 1024

    units: dict = field(default_factory=dict)
    host_routes: list = field(default_factory=list)
    kvm_present: bool = False
    kvm_readable: bool = False

    cli_plugin_dirs: dict = field(default_factory=dict)

    def engine_kinds(self) -> set:
        return {e.family for e in self.endpoints if e.reachable}


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _run(cmd: list, timeout: float = 5.0) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (r.stdout or "").strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _subid_has_user(path: str, username: str) -> bool:
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.split(":", 1)[0].strip() == username:
                return True
    except OSError:
        pass
    return False


def collect(probe: bool = True) -> Environment:
    """Sistem durumunu bir kez toplar. Ağır iş burada; kurallar ucuzdur."""
    env = Environment()

    env.docker_host = os.environ.get("DOCKER_HOST", "")
    env.docker_context_env = os.environ.get("DOCKER_CONTEXT", "")
    env.docker_cli_config = discovery.docker_cli_config()
    env.current_context = env.docker_cli_config.get("currentContext", "")
    env.contexts = dict(discovery.docker_contexts())
    env.cli_target = discovery.resolve_cli_target()

    env.endpoints = discovery.discover(probe=probe)

    env.daemon_json_path = "/etc/docker/daemon.json"
    env.daemon_json = _read_json(Path(env.daemon_json_path))

    env.docker_binary = shutil.which("docker") or ""
    if env.docker_binary:
        try:
            env.docker_real_path = os.path.realpath(env.docker_binary)
        except OSError:
            env.docker_real_path = env.docker_binary
    env.podman_binary = shutil.which("podman") or ""

    try:
        env.uid = os.getuid()
        env.username = os.environ.get("USER") or os.environ.get("LOGNAME") or ""
    except AttributeError:                                   # Windows
        env.uid = 0
        env.username = os.environ.get("USERNAME", "")

    groups = _run(["id", "-nG"])
    env.user_groups = groups.split() if groups else []

    if env.username:
        env.subuid_ok = _subid_has_user("/etc/subuid", env.username)
        env.subgid_ok = _subid_has_user("/etc/subgid", env.username)

    linger = _run(["loginctl", "show-user", env.username or "", "-p", "Linger"])
    env.linger = linger.endswith("=yes")

    port_start = _run(["sysctl", "-n", "net.ipv4.ip_unprivileged_port_start"])
    if port_start.isdigit():
        env.unprivileged_port_start = int(port_start)

    for unit, user in [("podman.socket", True), ("podman.socket", False),
                       ("docker.socket", False), ("docker.service", False),
                       ("podman-auto-update.timer", True)]:
        env.units[(unit, "user" if user else "system")] = \
            discovery.systemd_unit_state(unit, user)

    routes = _run(["ip", "-4", "route"])
    env.host_routes = [ln.strip() for ln in routes.splitlines() if ln.strip()]

    kvm = Path("/dev/kvm")
    env.kvm_present = kvm.exists()
    env.kvm_readable = os.access("/dev/kvm", os.R_OK | os.W_OK) if env.kvm_present \
        else False

    for label, path in [("user", Path.home() / ".docker/cli-plugins"),
                        ("system", Path("/usr/lib/docker/cli-plugins")),
                        ("libexec", Path("/usr/libexec/docker/cli-plugins"))]:
        if path.is_dir():
            try:
                env.cli_plugin_dirs[label] = sorted(p.name for p in path.iterdir())
            except OSError:
                env.cli_plugin_dirs[label] = []

    log().debug("Teşhis ortamı toplandı: %d endpoint, %d grup",
                len(env.endpoints), len(env.user_groups))
    return env


# ---------------------------------------------------------------------------
#  Kural
# ---------------------------------------------------------------------------
@dataclass
class Rule:
    """Tek bir teşhis kuralı.

    detect(env) -> None (bulgu yok) | dict (bulgu ayrıntısı, biçimlendirmede
    kullanılır). Boş dict de bulgu sayılır.
    """

    id: str
    severity: str
    title: str
    detect: Callable
    explain: str
    fix_command: str = ""
    fix_scope: str = "user"          # "user" | "root" | "none"
    setting_key: str = ""            # Ayarlar sayfasında açılacak katalog anahtarı
    learn_topic: str = ""            # Learn'de açılacak konu
    tags: list = field(default_factory=list)


@dataclass
class Finding:
    """Bir kuralın ürettiği bulgu."""

    rule: Rule
    detail: dict = field(default_factory=dict)

    @property
    def id(self) -> str:
        return self.rule.id

    @property
    def severity(self) -> str:
        return self.rule.severity

    def explain(self) -> str:
        try:
            return self.rule.explain.format(**self.detail)
        except (KeyError, IndexError, ValueError):
            return self.rule.explain

    def fix_command(self) -> str:
        try:
            return self.rule.fix_command.format(**self.detail)
        except (KeyError, IndexError, ValueError):
            return self.rule.fix_command


def run_rules(env: Environment, rules: list) -> list:
    """Tüm kuralları çalıştırır, bulguları önem sırasına göre döndürür.

    ⚠️ Bir kuralın patlaması diğerlerini durdurmaz — ama SESSİZCE de geçmez,
    log'a düşer. Yutulan hata bu projede kural olarak yasak.
    """
    findings = []
    for rule in rules:
        try:
            result = rule.detect(env)
        except Exception as exc:                             # noqa: BLE001
            log().warning("Kural %s çalışırken hata: %s", rule.id, exc)
            continue
        if result is None or result is False:
            continue
        findings.append(Finding(rule, result if isinstance(result, dict) else {}))

    findings.sort(key=lambda f: (SEVERITY_ORDER.get(f.severity, 9), f.id))
    return findings
