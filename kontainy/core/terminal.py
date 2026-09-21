"""
kontainy — opening a terminal pointed at the selected target

"Open Terminal" on every platform page starts a real terminal whose
environment already points at what you selected: DOCKER_CONTEXT for Docker,
CONTAINER_CONNECTION for Podman, LIBVIRT_DEFAULT_URI for libvirt. The shell
you get behaves exactly as the page does, without changing anything global.

This is the honest answer to "make this target active for my shell" — a
child process cannot change the environment of a shell that is already open,
but it can start a new one with the right environment.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess

from ..utils.config import config, log

# (binary, argv prefix that runs a command) — the first one found wins.
LINUX_TERMINALS = [
    ("konsole", ["konsole", "-e"]),
    ("gnome-terminal", ["gnome-terminal", "--"]),
    ("kitty", ["kitty"]),
    ("alacritty", ["alacritty", "-e"]),
    ("wezterm", ["wezterm", "start", "--"]),
    ("foot", ["foot"]),
    ("xfce4-terminal", ["xfce4-terminal", "-x"]),
    ("x-terminal-emulator", ["x-terminal-emulator", "-e"]),
    ("xterm", ["xterm", "-e"]),
]


def _chosen() -> tuple:
    """(binary, argv prefix) honouring the Preferences choice."""
    name = (config().get("terminal_emulator") or "").strip()
    flag = (config().get("terminal_arg") or "-e").strip()
    if name and shutil.which(name):
        for binary, prefix in LINUX_TERMINALS:
            if binary == name:
                return binary, prefix
        return name, [name, flag]
    for binary, prefix in LINUX_TERMINALS:
        if shutil.which(binary):
            return binary, prefix
    return "", []


def describe(env: dict) -> str:
    """The shell-equivalent line shown in the command strip."""
    exports = " ".join(f"{k}={v}" for k, v in env.items())
    if platform.system() == "Windows":
        sets = "; ".join(f"$env:{k}='{v}'" for k, v in env.items())
        return f"wt.exe powershell -NoExit -Command \"{sets}\"" if env else "wt.exe"
    return f"env {exports} $SHELL" if env else "$SHELL"


def open_terminal(env: dict) -> str:
    """Start a terminal with `env` applied. Returns what was started, or
    raises RuntimeError with the reason."""
    merged = dict(os.environ)
    merged.update(env)
    system = platform.system()

    if system == "Windows":
        sets = "; ".join(f"$env:{k}='{v}'" for k, v in env.items())
        inner = ["powershell", "-NoExit", "-Command", sets or "Write-Host kontainy"]
        argv = (["wt.exe"] + inner) if shutil.which("wt.exe") else \
               ["cmd.exe", "/c", "start"] + inner
    elif system == "Darwin":
        exports = "; ".join(f"export {k}='{v}'" for k, v in env.items())
        script = f'tell application "Terminal" to do script "{exports}"'
        argv = ["osascript", "-e", script]
    else:
        binary, prefix = _chosen()
        if not binary:
            raise RuntimeError(
                "No terminal emulator was found. Choose one in "
                "Preferences \u2192 Terminal.")
        shell = os.environ.get("SHELL") or "/bin/sh"
        argv = prefix + [shell]

    log().info("opening terminal: %s  env=%s", argv, env)
    subprocess.Popen(argv, env=merged, start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return " ".join(argv)
