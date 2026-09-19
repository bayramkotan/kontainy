"""
kontainy — configuration readers

Answers three questions for every key in the settings catalogue:

    declared   what the configuration file actually says
    effective  what the engine reports it is really using
    source     which layer in the override chain the value came from

The third one matters more than it looks. Podman reads containers.conf from
three places in order — the distribution copy, /etc, then the user's own —
and the value you see in one file may be overridden two layers down. No
other tool shows that chain.

When declared and effective disagree, that is a FINDING, not a display
detail: it usually means the setting is being silently ignored.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

try:                                                        # Python 3.11+
    import tomllib
except ModuleNotFoundError:                                 # pragma: no cover
    tomllib = None

from ..utils.config import log

MISSING = object()          # distinct from None, which is a real value


# ---------------------------------------------------------------------------
#  Layers
# ---------------------------------------------------------------------------
@dataclass
class Layer:
    """One configuration file in an override chain."""

    label: str                  # "distribution" | "system" | "user"
    path: Path
    writable: bool              # can kontainy write here without elevation?
    exists: bool = False
    data: dict = field(default_factory=dict)
    error: str = ""

    @property
    def scope(self) -> str:
        return "user" if self.writable else "root"


def _xdg_config() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def _read_json(path: Path) -> tuple:
    if not path.is_file():
        return {}, ""
    try:
        return json.loads(path.read_text(encoding="utf-8")), ""
    except (OSError, json.JSONDecodeError) as exc:
        return {}, str(exc)


def _read_toml(path: Path) -> tuple:
    if not path.is_file():
        return {}, ""
    if tomllib is None:
        return {}, "tomllib unavailable (needs Python 3.11+)"
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle), ""
    except (OSError, Exception) as exc:                      # noqa: BLE001
        return {}, str(exc)


CHAINS = {
    "docker.daemon": [
        ("system", Path("/etc/docker/daemon.json"), False, _read_json),
    ],
    "docker.cli": [
        ("user", Path.home() / ".docker/config.json", True, _read_json),
    ],
    "podman.containers": [
        ("distribution", Path("/usr/share/containers/containers.conf"),
         False, _read_toml),
        ("system", Path("/etc/containers/containers.conf"), False, _read_toml),
        ("user", _xdg_config() / "containers/containers.conf", True, _read_toml),
    ],
    "podman.storage": [
        ("distribution", Path("/usr/share/containers/storage.conf"),
         False, _read_toml),
        ("system", Path("/etc/containers/storage.conf"), False, _read_toml),
        ("user", _xdg_config() / "containers/storage.conf", True, _read_toml),
    ],
    "podman.registries": [
        ("system", Path("/etc/containers/registries.conf"), False, _read_toml),
        ("user", _xdg_config() / "containers/registries.conf", True, _read_toml),
    ],
    "podman.policy": [
        ("system", Path("/etc/containers/policy.json"), False, _read_json),
        ("user", _xdg_config() / "containers/policy.json", True, _read_json),
    ],
}


def read_chain(file_key: str) -> list:
    """Read every layer of one configuration chain, lowest priority first."""
    layers = []
    for label, path, writable, reader in CHAINS.get(file_key, []):
        data, error = reader(path)
        layers.append(Layer(label=label, path=path, writable=writable,
                            exists=path.is_file(), data=data, error=error))
    return layers


def dig(data: dict, dotted: str):
    """Follow a dotted key path through nested dicts. MISSING if absent."""
    node: Any = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return MISSING
        node = node[part]
    return node


def declared(file_key: str, key: str, layers: list = None) -> tuple:
    """Return (value, Layer) for the winning layer, or (MISSING, None).

    Later layers win, which is how both Docker and Podman resolve these.
    """
    layers = layers if layers is not None else read_chain(file_key)
    winner = (MISSING, None)
    for layer in layers:
        value = dig(layer.data, key)
        if value is not MISSING:
            winner = (value, layer)
    return winner


# ---------------------------------------------------------------------------
#  Effective values — what the engine says it is actually doing
# ---------------------------------------------------------------------------
# Catalogue key -> path inside `docker info` / `podman info` output.
EFFECTIVE_MAP = {
    # Docker — `docker info` is Docker-shaped
    "storage-driver":      ("docker", "Driver"),
    "log-driver":          ("docker", "LoggingDriver"),
    "data-root":           ("docker", "DockerRootDir"),
    "default-runtime":     ("docker", "DefaultRuntime"),
    "live-restore":        ("docker", "LiveRestoreEnabled"),
    "debug":               ("docker", "Debug"),
    "experimental":        ("docker", "ExperimentalBuild"),
    "insecure-registries": ("docker", "RegistryConfig.IndexConfigs"),
    "userns-remap":        ("docker", "SecurityOptions"),

    # Podman — libpod shape
    "containers.cgroup_manager":  ("podman", "host.cgroupManager"),
    "containers.log_driver":      ("podman", "host.logDriver"),
    "engine.runtime":             ("podman", "host.ociRuntime.name"),
    "engine.events_logger":       ("podman", "host.eventLogger"),
    "network.network_backend":    ("podman", "host.networkBackend"),
    "storage.driver":             ("podman", "store.graphDriverName"),
    "storage.graphroot":          ("podman", "store.graphRoot"),
    "storage.runroot":            ("podman", "store.runRoot"),
    "engine.database_backend":    ("podman", "host.databaseBackend"),
}


def _run_json(cmd: list, timeout: float = 8.0):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        log().debug("%s failed: %s", " ".join(cmd), exc)
        return {}
    if result.returncode != 0 or not result.stdout.strip():
        return {}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}


class EffectiveValues:
    """Caches `docker info` and `podman info` for one refresh cycle."""

    def __init__(self):
        self._cache = {}

    def _info(self, engine: str) -> dict:
        if engine not in self._cache:
            binary = "docker" if engine == "docker" else "podman"
            self._cache[engine] = _run_json([binary, "info", "--format", "json"])
        return self._cache[engine]

    def get(self, key: str):
        entry = EFFECTIVE_MAP.get(key)
        if entry is None:
            return MISSING
        engine, path = entry
        value = dig(self._info(engine), path)
        return value

    def available(self, engine: str) -> bool:
        return bool(self._info(engine))


# ---------------------------------------------------------------------------
#  One row per catalogue setting
# ---------------------------------------------------------------------------
@dataclass
class SettingState:
    """Everything the Settings page needs to show and edit one key."""

    key: str
    declared: Any = MISSING
    declared_layer: Optional[Layer] = None
    effective: Any = MISSING
    writable_layer: Optional[Layer] = None

    @property
    def has_declared(self) -> bool:
        return self.declared is not MISSING

    @property
    def has_effective(self) -> bool:
        return self.effective is not MISSING

    @property
    def source_label(self) -> str:
        if self.declared_layer is None:
            return "\u2014"
        return f"{self.declared_layer.label}: {self.declared_layer.path}"

    @property
    def mismatch(self) -> bool:
        """Declared and effective disagree — the setting is being ignored."""
        if not (self.has_declared and self.has_effective):
            return False
        return str(self.declared).strip() != str(self.effective).strip()

    def display(self, value) -> str:
        if value is MISSING:
            return "\u2014"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (list, dict)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)


class StateReader:
    """Builds SettingState for catalogue entries, caching chains and info."""

    def __init__(self):
        self._chains = {}
        self._effective = EffectiveValues()

    def chain(self, file_key: str) -> list:
        if file_key not in self._chains:
            self._chains[file_key] = read_chain(file_key)
        return self._chains[file_key]

    def writable_layer(self, file_key: str) -> Optional[Layer]:
        for layer in reversed(self.chain(file_key)):
            if layer.writable:
                return layer
        return None

    def state(self, setting) -> SettingState:
        state = SettingState(key=setting.key)
        if setting.file in CHAINS:
            layers = self.chain(setting.file)
            state.declared, state.declared_layer = declared(
                setting.file, setting.key, layers)
            state.writable_layer = self.writable_layer(setting.file)
        state.effective = self._effective.get(setting.key)
        return state

    def states(self, settings: list) -> dict:
        return {s.key: self.state(s) for s in settings}

    def mismatches(self, settings: list) -> list:
        out = []
        for setting in settings:
            state = self.state(setting)
            if state.mismatch:
                out.append((setting, state))
        return out
