"""kontainy ships a Windows exe and two macOS builds, so POSIX-only calls
must not crash them.

Found on 2026-09-20 by running the suite on Windows: os.getuid() does not
exist there, discovery called it unguarded, and discovery runs when the
Engines page opens — so the Windows build crashed at startup. CI never saw
it because the test job only ran on Ubuntu. It runs on all three now.
"""

import os
import pathlib

import pytest

from kontainy.core import discovery


@pytest.fixture
def no_posix_ids(monkeypatch):
    """Pretend to be Windows: no uid, no euid, no XDG runtime directory."""
    for name in ("getuid", "geteuid", "getgid"):
        monkeypatch.delattr(os, name, raising=False)
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)


def test_runtime_dir_is_empty_without_getuid(no_posix_ids):
    assert discovery._xdg_runtime() == ""


def test_podman_candidates_survive_without_getuid(no_posix_ids):
    candidates = discovery.podman_socket_candidates()
    assert candidates, "the rootful socket should still be offered"
    assert all("/run/user/" not in path for path, _ in candidates)


def test_discovery_survives_without_getuid(no_posix_ids):
    assert isinstance(discovery.discover(probe=False), list)


def test_environment_does_not_claim_root_without_getuid(no_posix_ids):
    """The old fallback set uid = 0, telling every rule the user was root.
    In a tool that decides when to ask for elevation that is exactly the
    wrong way to be wrong."""
    from kontainy.rules.engine import collect
    env = collect(probe=False)
    assert env.uid != 0


def test_is_root_is_false_without_geteuid(no_posix_ids):
    from kontainy.core.elevate import is_root
    assert is_root() is False


def test_no_unguarded_posix_calls_in_the_package():
    """A direct os.getuid() / os.geteuid() call outside a guard is how the
    Windows crash happened. Allow them only on lines that also handle the
    AttributeError or use getattr."""
    root = pathlib.Path(__file__).resolve().parents[1] / "kontainy"
    offenders = []
    for path in root.rglob("*.py"):
        lines = path.read_text(encoding="utf-8").splitlines()
        in_docstring = False
        for number, line in enumerate(lines, 1):
            # Track triple-quoted blocks so prose that MENTIONS the call —
            # like the note explaining this very bug — is not flagged.
            quotes = line.count('"""') + line.count("\'\'\'")
            was_in_docstring = in_docstring
            if quotes % 2 == 1:
                in_docstring = not in_docstring
            if was_in_docstring or quotes:
                continue
            code = line.split("#", 1)[0]
            if not any(call in code for call in
                       ("os.getuid()", "os.geteuid()", "os.getgid()")):
                continue
            window = "\n".join(lines[max(0, number - 4):number + 3])
            if "AttributeError" in window or "getattr(os" in window:
                continue
            offenders.append(f"{path.relative_to(root)}:{number}")
    assert not offenders, f"unguarded POSIX calls: {offenders}"
