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


#: What each desktop considers its own terminal. Asked before the list,
#: because "the first one installed" is not the same as "the one this
#: desktop opens", and a KDE user with kitty installed still expects
#: Konsole.
DESKTOP_TERMINALS = {
    "kde": "konsole", "plasma": "konsole",
    "gnome": "gnome-terminal", "cinnamon": "gnome-terminal",
    "xfce": "xfce4-terminal", "mate": "mate-terminal",
    "lxqt": "qterminal", "deepin": "deepin-terminal",
    "budgie": "gnome-terminal", "pantheon": "io.elementary.terminal",
}


def desktop_terminal() -> str:
    """The terminal this desktop session would open, if it can be told."""
    session = " ".join(filter(None, [
        os.environ.get("XDG_CURRENT_DESKTOP", ""),
        os.environ.get("XDG_SESSION_DESKTOP", ""),
        os.environ.get("DESKTOP_SESSION", "")])).lower()
    for key, binary in DESKTOP_TERMINALS.items():
        if key in session and shutil.which(binary):
            return binary
    return ""


def _prefix_for(binary: str) -> list:
    for known, prefix in LINUX_TERMINALS:
        if known == binary:
            return prefix
    flag = (config().get("terminal_arg") or "-e").strip()
    return [binary, flag]


def _chosen() -> tuple:
    """(binary, argv prefix), in the order a user would expect.

    1. what they chose in Preferences,
    2. $TERMINAL, which is how people say it on Arch and CachyOS,
    3. xdg-terminal-exec, the freedesktop way to ask for "the" terminal,
    4. what this desktop environment uses,
    5. the first one installed, which is where this started and is the
       worst of the five.
    """
    name = (config().get("terminal_emulator") or "").strip()
    if name and shutil.which(name):
        return name, _prefix_for(name)

    from_env = (os.environ.get("TERMINAL") or "").strip()
    if from_env and shutil.which(from_env):
        return from_env, _prefix_for(from_env)

    if shutil.which("xdg-terminal-exec"):
        return "xdg-terminal-exec", ["xdg-terminal-exec"]

    preferred = desktop_terminal()
    if preferred:
        return preferred, _prefix_for(preferred)

    for binary, prefix in LINUX_TERMINALS:
        if shutil.which(binary):
            return binary, prefix
    return "", []


def login_shell() -> str:
    """The shell to start, or "" for the terminal's own.

    Empty is the default and the right one: a terminal already knows which
    shell to run — the one configured in its profile. kontainy used to
    append $SHELL, which overrode that profile and opened fish for someone
    whose Konsole runs bash. Forcing a shell is now something you ask for.
    """
    chosen = (config().get("terminal_shell") or "").strip()
    if chosen and (shutil.which(chosen) or os.path.isabs(chosen)):
        return chosen
    return ""


def describe(env: dict) -> str:
    """The shell-equivalent line shown in the command strip."""
    exports = " ".join(f"{k}={v}" for k, v in env.items())
    if platform.system() == "Windows":
        sets = "; ".join(f"$env:{k}='{v}'" for k, v in env.items())
        return f"wt.exe powershell -NoExit -Command \"{sets}\"" if env else "wt.exe"
    shell = login_shell()
    if shell:
        return f"env {exports} {shell}" if env else shell
    binary = _chosen()[0] or "your terminal"
    return f"env {exports} {binary}" if env else binary


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
        shell = login_shell()
        # No shell named: start the terminal itself, so it opens whatever
        # its own profile says. The environment still carries the target.
        argv = (prefix + [shell]) if shell else [binary]

    log().info("opening terminal: %s  env=%s", argv, env)
    subprocess.Popen(argv, env=merged, start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return " ".join(argv)
