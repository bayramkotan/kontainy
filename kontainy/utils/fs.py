"""
kontainy — filesystem probing that cannot raise

``Path.exists()`` does not answer "is there a file here"; it answers "can I
stat this path", and it RAISES when a parent directory is not traversable.
``/run/podman/`` is root-owned and mode 0700 on most distributions, so a
plain ``Path("/run/podman/podman.sock").exists()`` throws PermissionError for
any ordinary user whenever rootful Podman is installed.

kontainy probes system paths constantly — every discovery sweep, every
configuration read, every diagnostic rule — and it must never crash because
one of them is out of reach. "I cannot see it" and "it is not there" lead to
the same answer here: do not offer it.

Found by CI on 2026-09-20, where the runner has exactly that directory
layout. The test that caught it is
``tests/test_discovery.py::test_discovery_returns_endpoints_without_probing``.
"""

from __future__ import annotations

from pathlib import Path


def exists(path) -> bool:
    """True when the path is there AND reachable. Never raises."""
    try:
        return Path(path).exists()
    except (OSError, ValueError):
        return False


def is_file(path) -> bool:
    try:
        return Path(path).is_file()
    except (OSError, ValueError):
        return False


def is_dir(path) -> bool:
    try:
        return Path(path).is_dir()
    except (OSError, ValueError):
        return False


def read_text(path, limit: int = 4_000_000) -> str:
    """File contents, or an empty string for anything unreadable."""
    try:
        target = Path(path)
        if not target.is_file() or target.stat().st_size > limit:
            return ""
        return target.read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        return ""


def iterdir(path) -> list:
    """Directory entries, or an empty list when it cannot be listed."""
    try:
        return sorted(Path(path).iterdir())
    except (OSError, ValueError):
        return []


def glob(path, pattern: str) -> list:
    try:
        return sorted(Path(path).glob(pattern))
    except (OSError, ValueError):
        return []
