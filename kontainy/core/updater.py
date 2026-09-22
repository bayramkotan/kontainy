"""
kontainy — is there a newer release?

Asks PyPI, because that is where `pip install -U kontainy` will look: the
answer and the upgrade command then agree. The GitHub releases page carries
the same version, but a user who installed from PyPI can be told something
true only by PyPI.

No third-party HTTP library: urllib, one request, a short timeout. Qt-free,
so the command line can use it too.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

PYPI_JSON = "https://pypi.org/pypi/kontainy/json"
PROJECT_PAGE = "https://pypi.org/project/kontainy/"
RELEASES_PAGE = "https://github.com/bayramkotan/kontainy/releases"


def parse_version(text: str) -> tuple:
    """(1, 2, 3) from '1.2.3'. Unknown parts sort lowest, never crash."""
    parts = []
    for chunk in str(text).strip().split("."):
        # Leading digits only: "3rc1" is release 3, not 31. Collecting every
        # digit made a release candidate look newer than the release.
        digits = ""
        for character in chunk:
            if not character.isdigit():
                break
            digits += character
        parts.append(int(digits) if digits else 0)
    return tuple(parts + [0] * (3 - len(parts))) if len(parts) < 3 \
        else tuple(parts)


def is_newer(latest: str, current: str) -> bool:
    return parse_version(latest) > parse_version(current)


def check_for_update(timeout: float = 8.0) -> dict:
    """Ask PyPI. Never raises: a machine with no network is not an error."""
    from .constants import APP_VERSION
    result = {"current": APP_VERSION, "latest": "", "update_available": False,
              "url": PROJECT_PAGE, "error": ""}
    request = urllib.request.Request(
        PYPI_JSON, headers={"Accept": "application/json",
                            "User-Agent": f"kontainy/{APP_VERSION}"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, TimeoutError) as exc:
        result["error"] = str(exc)
        return result
    latest = str(((data or {}).get("info") or {}).get("version", "")).strip()
    if not latest:
        result["error"] = "PyPI did not report a version"
        return result
    result["latest"] = latest
    result["update_available"] = is_newer(latest, APP_VERSION)
    return result


def upgrade_command() -> str:
    """What to type. The PEP 668 flag is the one Linux users hit first."""
    return "pip install -U kontainy --no-cache-dir"
