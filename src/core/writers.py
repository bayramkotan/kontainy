"""
kontainy — configuration writers

Rules, in order of importance:

1. **User scope only.** kontainy never elevates. A write to a root-owned file
   is refused here, not somewhere deep in the UI.
2. **Back up first.** Every write leaves a ``.bak`` next to the original.
3. **Atomic.** Write to a temp file in the same directory, then ``os.replace``.
   A half-written ``daemon.json`` stops the daemon from starting at all.
4. **Preserve comments.** TOML files are edited line by line rather than
   parsed and re-serialised. ``tomllib`` only reads, and a round trip through
   any writer would strip every comment the distribution shipped — including
   the ones explaining the very setting being changed.
5. **Verify after.** The caller re-reads and compares; a write that did not
   land must not look like one that did.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..utils.config import log


class WriteRefused(Exception):
    """The write was not attempted, and why."""


@dataclass
class WriteResult:
    path: Path
    backup: Path | None
    created: bool
    old_value: Any
    new_value: Any

    def summary(self) -> str:
        what = "created" if self.created else "updated"
        return f"{what} {self.path}"


# ---------------------------------------------------------------------------
#  Value formatting
# ---------------------------------------------------------------------------
def _toml_literal(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_toml_literal(v) for v in value) + "]"
    text = str(value)
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def coerce(value: str, vtype: str) -> Any:
    """Turn the text a user typed into the type the catalogue declares."""
    text = str(value).strip()
    if vtype == "bool":
        return text.lower() in ("1", "true", "yes", "on")
    if vtype == "int":
        return int(text)
    if vtype in ("list", "dict"):
        return json.loads(text) if text else ([] if vtype == "list" else {})
    if vtype == "duration" and text.isdigit():
        return int(text)
    return text


# ---------------------------------------------------------------------------
#  Guards
# ---------------------------------------------------------------------------
def ensure_writable(path: Path) -> None:
    """Refuse anything kontainy cannot write without elevation."""
    if path.exists():
        if not os.access(path, os.W_OK):
            raise WriteRefused(
                f"{path} is not writable by this user. kontainy never "
                f"elevates — change it with a command instead.")
        return
    parent = path.parent
    if parent.exists() and not os.access(parent, os.W_OK):
        raise WriteRefused(
            f"{parent} is not writable by this user. kontainy never elevates.")
    if not parent.exists():
        try:
            parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise WriteRefused(f"Cannot create {parent}: {exc}") from exc


def _backup(path: Path) -> Path | None:
    if not path.is_file():
        return None
    backup = path.with_suffix(path.suffix + ".bak")
    try:
        shutil.copy2(path, backup)
        return backup
    except OSError as exc:
        raise WriteRefused(f"Cannot back up {path}: {exc}") from exc


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".kontainy-tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise WriteRefused(f"Cannot write {path}: {exc}") from exc


# ---------------------------------------------------------------------------
#  JSON writer — daemon.json, ~/.docker/config.json, policy.json
# ---------------------------------------------------------------------------
def write_json_key(path: Path, dotted_key: str, value: Any) -> WriteResult:
    ensure_writable(path)
    created = not path.is_file()
    data = {}
    if not created:
        try:
            data = json.loads(path.read_text(encoding="utf-8") or "{}")
        except json.JSONDecodeError as exc:
            raise WriteRefused(
                f"{path} is not valid JSON, refusing to overwrite it: {exc}"
            ) from exc

    parts = dotted_key.split(".")
    node = data
    for part in parts[:-1]:
        node = node.setdefault(part, {})
        if not isinstance(node, dict):
            raise WriteRefused(
                f"{dotted_key}: '{part}' is not an object in {path}")
    old = node.get(parts[-1], None)
    node[parts[-1]] = value

    backup = _backup(path)
    _atomic_write(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    log().info("wrote %s = %r to %s", dotted_key, value, path)
    return WriteResult(path, backup, created, old, value)


def delete_json_key(path: Path, dotted_key: str) -> WriteResult:
    ensure_writable(path)
    if not path.is_file():
        raise WriteRefused(f"{path} does not exist")
    data = json.loads(path.read_text(encoding="utf-8") or "{}")
    parts = dotted_key.split(".")
    node = data
    for part in parts[:-1]:
        node = node.get(part)
        if not isinstance(node, dict):
            raise WriteRefused(f"{dotted_key} not found in {path}")
    old = node.pop(parts[-1], None)
    backup = _backup(path)
    _atomic_write(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    log().info("removed %s from %s", dotted_key, path)
    return WriteResult(path, backup, False, old, None)


# ---------------------------------------------------------------------------
#  TOML writer — containers.conf, storage.conf, registries.conf
# ---------------------------------------------------------------------------
def write_toml_key(path: Path, dotted_key: str, value: Any) -> WriteResult:
    """Set ``[section] key = value`` while keeping every comment intact.

    The catalogue stores keys as ``section.key`` (``containers.log_driver``)
    or ``section.sub.key`` (``storage.options.mount_program``). Anything
    before the final dot is the TOML table.
    """
    ensure_writable(path)
    if "." in dotted_key:
        section, _, leaf = dotted_key.rpartition(".")
    else:
        section, leaf = "", dotted_key

    created = not path.is_file()
    lines = [] if created else path.read_text(encoding="utf-8").splitlines()

    literal = _toml_literal(value)
    new_line = f"{leaf} = {literal}"
    header = f"[{section}]" if section else ""

    old_value = None
    in_section = not section          # no section means top level
    section_start = -1
    section_end = len(lines)
    replaced = False

    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_section and section_start >= 0:
                section_end = index
                break
            in_section = stripped == header
            if in_section:
                section_start = index
            continue
        if not in_section:
            continue
        match = re.match(rf"^\s*#?\s*{re.escape(leaf)}\s*=", line)
        if match and not replaced:
            old_value = stripped.split("=", 1)[1].strip() \
                if "=" in stripped else None
            indent = line[:len(line) - len(line.lstrip())]
            lines[index] = f"{indent}{new_line}"
            replaced = True

    if not replaced:
        if section_start < 0 and section:
            # The table does not exist yet: append it at the end of the file.
            if lines and lines[-1].strip():
                lines.append("")
            lines.append(header)
            lines.append(new_line)
        else:
            # Insert at the end of the table, but BEFORE any trailing blank
            # lines — otherwise the new key lands in the gap just above the
            # next [section] header and reads as if it belonged to that one.
            insert_at = section_end if section else len(lines)
            while insert_at > 0 and not lines[insert_at - 1].strip():
                insert_at -= 1
            lines.insert(insert_at, new_line)

    backup = _backup(path)
    _atomic_write(path, "\n".join(lines).rstrip("\n") + "\n")
    log().info("wrote %s = %s to %s", dotted_key, literal, path)
    return WriteResult(path, backup, created, old_value, value)


def comment_out_toml_key(path: Path, dotted_key: str) -> WriteResult:
    """Comment a key out rather than deleting it, so the value is recoverable."""
    ensure_writable(path)
    if not path.is_file():
        raise WriteRefused(f"{path} does not exist")
    _, _, leaf = dotted_key.rpartition(".")
    lines = path.read_text(encoding="utf-8").splitlines()
    old = None
    for index, line in enumerate(lines):
        if re.match(rf"^\s*{re.escape(leaf)}\s*=", line):
            old = line.strip()
            lines[index] = "# " + line
            break
    if old is None:
        raise WriteRefused(f"{dotted_key} not found in {path}")
    backup = _backup(path)
    _atomic_write(path, "\n".join(lines) + "\n")
    return WriteResult(path, backup, False, old, None)


# ---------------------------------------------------------------------------
#  Front door
# ---------------------------------------------------------------------------
JSON_FILES = {"docker.daemon", "docker.cli", "podman.policy"}
TOML_FILES = {"podman.containers", "podman.storage", "podman.registries"}


def write_setting(setting, layer, raw_value: str) -> WriteResult:
    """Write one catalogue setting into one layer. Refuses root-owned files."""
    if layer is None:
        raise WriteRefused(
            "No user-writable layer exists for this setting. kontainy never "
            "elevates — use the command shown instead.")
    if not layer.writable:
        raise WriteRefused(
            f"{layer.path} is root-scoped. kontainy shows it read-only and "
            f"gives you the command instead.")

    value = coerce(raw_value, setting.vtype)
    if setting.file in JSON_FILES:
        return write_json_key(layer.path, setting.key, value)
    if setting.file in TOML_FILES:
        return write_toml_key(layer.path, setting.key, value)
    raise WriteRefused(
        f"{setting.file} is not a writable configuration file "
        f"(it is a runtime flag, not a stored setting).")


def restart_hint(setting) -> str:
    """What the user must do for the change to take effect."""
    if not setting.restart:
        return ("No restart needed \u2014 Podman reads its configuration on "
                "every command.")
    if setting.engine == "docker":
        return "Restart required: sudo systemctl restart docker"
    return "Restart required for this engine."
