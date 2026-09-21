"""
kontainy — shell profile

The persistent alternative to choosing a target in the dropdown. Picking a
Docker context changes ~/.docker/config.json for everyone; an environment
variable in your shell profile changes only the shells you open, and is how
people pin a terminal to a particular socket or cluster.

Variables that matter, per technology:

    Docker      DOCKER_CONTEXT   pick a context for this shell only
                DOCKER_HOST      bypass contexts entirely — use with care
    Podman      CONTAINER_CONNECTION, CONTAINER_HOST
    Kubernetes  KUBECONFIG
    libvirt     LIBVIRT_DEFAULT_URI

kontainy writes ONLY inside its own marked block:

    # >>> kontainy >>>
    export DOCKER_CONTEXT=desktop-linux
    # <<< kontainy <<<

so it can add and remove its lines precisely and never rewrites a line you
wrote. Lines of yours that set the same variable are listed, and can be
commented out — with a backup — but never edited or deleted.

A change takes effect in NEW shells. The shell you already have open keeps
its environment; `source ~/.bashrc` reloads it. That is not a limitation of
kontainy: no program can change the environment of a shell that started it.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from ..utils import fs
from .actions import Action, USER

BEGIN = "# >>> kontainy >>>"
END = "# <<< kontainy <<<"

VARIABLES = {
    "docker": [
        ("DOCKER_CONTEXT",
         "Selects a context for shells that read this profile, without "
         "changing the global choice in ~/.docker/config.json. The safe way "
         "to pin a terminal to one engine."),
        ("DOCKER_HOST",
         "Points docker straight at a socket and makes every context "
         "IGNORED. `docker context use` then reports success and changes "
         "nothing \u2014 the most common reason containers seem to vanish. "
         "Prefer DOCKER_CONTEXT."),
    ],
    "podman": [
        ("CONTAINER_CONNECTION",
         "Selects a podman system connection for shells that read this "
         "profile."),
        ("CONTAINER_HOST",
         "Points podman straight at a socket, e.g. "
         "unix:///run/user/1000/podman/podman.sock."),
    ],
    "kubernetes": [
        ("KUBECONFIG",
         "Which kubeconfig file or files kubectl reads, separated by ':'. "
         "Several files are merged, which is how one shell sees clusters "
         "from different sources."),
    ],
    "libvirt": [
        ("LIBVIRT_DEFAULT_URI",
         "The connection virsh uses when no -c is given. Overrides "
         "uri_default in libvirt.conf."),
    ],
}


def shell_kind() -> str:
    if platform.system() == "Windows":
        return "powershell"
    name = Path(os.environ.get("SHELL", "")).name
    return name if name in ("bash", "zsh", "fish") else "bash"


def profile_path(kind: str = "") -> Path:
    kind = kind or shell_kind()
    home = Path.home()
    if kind == "zsh":
        return home / ".zshrc"
    if kind == "fish":
        return home / ".config" / "fish" / "config.fish"
    if kind == "powershell":
        docs = home / "Documents"
        return docs / "PowerShell" / "Microsoft.PowerShell_profile.ps1"
    return home / ".bashrc"


def line_for(kind: str, name: str, value: str) -> str:
    if kind == "fish":
        return f"set -gx {name} '{value}'"
    if kind == "powershell":
        return f"$env:{name} = '{value}'"
    return f"export {name}='{value}'"


def _matches(kind: str, name: str):
    if kind == "fish":
        return re.compile(rf"^\s*set\s+(-\w+\s+)*{re.escape(name)}\s")
    if kind == "powershell":
        return re.compile(rf"^\s*\$env:{re.escape(name)}\s*=", re.I)
    return re.compile(rf"^\s*(export\s+)?{re.escape(name)}=")


@dataclass
class Entry:
    name: str
    managed_value: str        # value inside kontainy's block, "" if none
    foreign: list             # [(line_number, text)] set outside the block
    current: str              # value in this process's environment


def _split(lines: list) -> tuple:
    """(before, block, after) — block excludes the marker lines."""
    try:
        start = lines.index(BEGIN)
        end = lines.index(END, start)
    except ValueError:
        return lines, [], []
    return lines[:start], lines[start + 1:end], lines[end + 1:]


def read(provider_id: str, kind: str = "") -> list:
    kind = kind or shell_kind()
    path = profile_path(kind)
    lines = fs.read_text(path).splitlines()
    _before, block, _after = _split(lines)
    entries = []
    for name, _why in VARIABLES.get(provider_id, []):
        pattern = _matches(kind, name)
        managed = ""
        for line in block:
            if pattern.match(line):
                managed = line.split("=", 1)[-1].strip().strip("'\"") \
                    if kind != "fish" else line.split(None, 3)[-1].strip("'\"")
        in_block = False
        foreign = []
        for number, line in enumerate(lines, 1):
            if line == BEGIN:
                in_block = True
            elif line == END:
                in_block = False
            elif not in_block and pattern.match(line) \
                    and not line.lstrip().startswith("#"):
                foreign.append((number, line.strip()))
        entries.append(Entry(name, managed, foreign, os.environ.get(name, "")))
    return entries


def _write(path: Path, lines: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_name(path.name + ".kontainy.bak")
        shutil.copy2(path, backup)
    tmp = path.with_name(path.name + ".kontainy.tmp")
    tmp.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")
    os.replace(tmp, path)


def set_value(name: str, value: str, kind: str = "") -> str:
    kind = kind or shell_kind()
    path = profile_path(kind)
    lines = fs.read_text(path).splitlines()
    before, block, after = _split(lines)
    pattern = _matches(kind, name)
    block = [l for l in block if not pattern.match(l)]
    block.append(line_for(kind, name, value))
    if not before and not after and BEGIN not in lines:
        before = lines
    new = before + ([""] if before and before[-1].strip() else []) + \
        [BEGIN] + block + [END] + after
    _write(path, new)
    return f"{path}: {line_for(kind, name, value)}"


def unset_value(name: str, kind: str = "") -> str:
    kind = kind or shell_kind()
    path = profile_path(kind)
    lines = fs.read_text(path).splitlines()
    before, block, after = _split(lines)
    pattern = _matches(kind, name)
    block = [l for l in block if not pattern.match(l)]
    new = before + ([BEGIN] + block + [END] if block else []) + after
    _write(path, new)
    return f"{name} removed from kontainy's block in {path}"


def comment_out(number: int, kind: str = "") -> str:
    kind = kind or shell_kind()
    path = profile_path(kind)
    lines = fs.read_text(path).splitlines()
    if not 1 <= number <= len(lines):
        raise RuntimeError(f"{path} has no line {number}")
    lines[number - 1] = "# disabled by kontainy: " + lines[number - 1]
    _write(path, lines)
    return f"line {number} of {path} commented out; backup kept"


# --- Actions ---------------------------------------------------------------
_RELOAD = ("It takes effect in NEW shells. To apply it to a shell that is "
           "already open, run:  {reload}")


def _reload_hint(kind: str) -> str:
    path = profile_path(kind)
    if kind == "powershell":
        return f". $PROFILE"
    return f"source {path}"


def set_action(name: str, value: str) -> Action:
    kind = shell_kind()
    path = profile_path(kind)
    line = line_for(kind, name, value)
    return Action(
        id=f"profile-set-{name}", label=f"Set {name} in {path.name}",
        command=[], scope=USER,
        shell_text=f"# inside kontainy's block in {path}\n{line}",
        explanation=(f"Writes {line!r} into kontainy's marked block in "
                     f"{path}, replacing any earlier value there. Lines you "
                     f"wrote yourself are not touched. A backup is kept as "
                     f"{path.name}.kontainy.bak.\n\n"
                     + _RELOAD.format(reload=_reload_hint(kind))),
        func=lambda: set_value(name, value, kind))


def unset_action(name: str) -> Action:
    kind = shell_kind()
    path = profile_path(kind)
    return Action(
        id=f"profile-unset-{name}", label=f"Remove {name} from {path.name}",
        command=[], scope=USER,
        shell_text=f"# delete the {name} line from kontainy's block in {path}",
        explanation=(f"Removes {name} from kontainy's block in {path}. "
                     f"Lines you wrote yourself are not touched.\n\n"
                     + _RELOAD.format(reload=_reload_hint(kind))
                     + ("" if kind == "powershell" else
                        f"\n\nIn an open shell, `unset {name}` clears it at "
                        f"once.")),
        destructive=True,
        func=lambda: unset_value(name, kind))


def comment_action(name: str, number: int, text: str) -> Action:
    kind = shell_kind()
    path = profile_path(kind)
    return Action(
        id=f"profile-comment-{name}-{number}",
        label=f"Comment out line {number}",
        command=[], scope=USER,
        shell_text=f"sed -i '{number}s/^/# disabled by kontainy: /' {path}",
        explanation=(f"This line sets {name} outside kontainy's block:\n\n"
                     f"    {text}\n\nIt is turned into a comment, not deleted, "
                     f"so you can restore it by removing the prefix. A backup "
                     f"is kept as {path.name}.kontainy.bak."),
        destructive=True,
        func=lambda: comment_out(number, kind))
