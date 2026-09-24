"""
kontainy — the system report

What someone needs to paste into a bug report, gathered once: the versions,
the platform, which technologies answered and which did not, which tools are
installed, and whether any crash reports are waiting.

It used to be a tab of the About dialog, where nobody writing a bug report
would think to look. It lives on the Diagnostics page now — beside the
findings — and `ky report` prints the same text.

Qt-free: the report must work on a server with no window.
"""

from __future__ import annotations

import platform
import shutil
import sys

WIDTH = 72


def _line(key: str, value) -> str:
    return f"{key:<22} {value}"


def _section(title: str) -> str:
    return f"\n{title}\n{'-' * min(len(title), WIDTH)}"


def versions() -> dict:
    from ..utils import logs
    return logs.session_context()


def technologies() -> list:
    """(name, state) for every technology kontainy offers on this system."""
    from .providers import PROVIDERS
    out = []
    for provider in PROVIDERS:
        if not provider.shown_here():
            continue
        host = provider.host()
        where = f" [{host.label}]" if host is not None and host.is_wsl else ""
        if not provider.available():
            out.append((provider.name, f"not installed{where}"))
            continue
        version = provider.version() or "installed"
        active = provider.active()
        listing = provider.objects(active)
        if listing.error:
            count = f"unreachable — {listing.error.splitlines()[0][:60]}"
        else:
            from .providers.base import count_label
            count = count_label(len(listing.rows), provider.object_noun_plural)
        target = f"{active.name}" if active else "no active target"
        out.append((provider.name, f"{version}{where} · {target} · {count}"))
    return out


def tools() -> list:
    """(name, where) for the tools that ARE installed; the rest is noise."""
    from . import registry as reg
    out = []
    for group in reg.GROUPS:
        for tool in reg.by_group(group):
            if tool.installed():
                out.append((tool.name,
                            tool.version() or tool.binary_path() or "installed"))
    return out


def environment() -> list:
    """The variables that quietly override everything else."""
    import os
    names = ("DOCKER_HOST", "DOCKER_CONTEXT", "CONTAINER_HOST",
             "LIBVIRT_DEFAULT_URI", "KUBECONFIG", "XDG_RUNTIME_DIR",
             "WSL_DISTRO_NAME", "NO_COLOR", "KY_LOG_LEVEL")
    return [(name, os.environ[name]) for name in names if os.environ.get(name)]


def crash_reports() -> list:
    from ..utils import logs
    return [(path.name, path.stat().st_size) for path in logs.crash_reports()]


def build(full: bool = True) -> str:
    """The whole report as plain text, ready to paste."""
    from ..utils import logs
    from .catalog import ALL_SETTINGS
    from ..rules.catalog import RULES

    lines = ["kontainy system report", "=" * 22]
    for key, value in versions().items():
        lines.append(_line(key, value))
    lines.append(_line("shell", shutil.which(
        "pwsh" if platform.system() == "Windows" else "bash") or "?"))

    lines.append(_section("Technologies"))
    for name, state in technologies():
        lines.append(_line(name, state))

    if full:
        lines.append(_section("Tools installed"))
        found = tools()
        for name, where in found:
            lines.append(_line(name, where))
        if not found:
            lines.append("none found")

    variables = environment()
    if variables:
        lines.append(_section("Environment"))
        for name, value in variables:
            lines.append(_line(name, value))

    lines.append(_section("kontainy"))
    lines.append(_line("catalogue", f"{len(ALL_SETTINGS)} settings"))
    lines.append(_line("rules", f"{len(RULES)} diagnostic rules"))
    lines.append(_line("log", str(logs.log_path())))
    reports = crash_reports()
    lines.append(_line("crash reports", len(reports) or "none"))
    for name, size in reports[:5]:
        lines.append(_line("", f"{name} ({size} bytes)"))

    return "\n".join(lines) + "\n"
