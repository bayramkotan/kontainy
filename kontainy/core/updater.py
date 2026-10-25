"""
kontainy — is there a newer release, and can it install itself?

Asks PyPI, because that is where `pip install -U kontainy` will look: the
answer and the upgrade command then agree. The GitHub releases page carries
the same version, but a user who installed from PyPI can be told something
true only by PyPI.

No third-party HTTP library: urllib, one request, a short timeout. Qt-free,
so the command line can use it too.

⚠️ The upgrade must go to the installation that is RUNNING. `pip` on PATH
belongs to whichever environment was activated last, so `ky update` can
install a new kontainy somewhere the running one will never see, report
success, and change nothing. Everything here goes through
``sys.executable -m pip``, which can only ever mean this one.

The install kinds differ in what they will accept, and guessing wrong wastes
the user's time with an error they then have to decode:

* **checkout** — running from git. pip would overwrite nothing useful; the
  answer is `git pull`, and saying so is better than a no-op.
* **pipx** — `pip install -U` inside a pipx venv works but leaves pipx's own
  metadata behind; `pipx upgrade kontainy` is the supported route.
* **system** — site-packages owned by root, and on a PEP 668 distribution
  (Arch, Debian, Fedora) pip refuses outright without
  ``--break-system-packages``. That flag is added only here, where the
  install already IS system-wide, never for a venv.
* **user** / **venv** — a plain upgrade, no elevation.
"""

from __future__ import annotations

import json
import os
import site
import subprocess
import sys
import sysconfig
import urllib.error
import urllib.request
from pathlib import Path

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


# --- how this copy was installed -----------------------------------------------
def install_kind() -> str:
    """"checkout" | "pipx" | "venv" | "user" | "system"."""
    package = Path(__file__).resolve().parents[2]
    if (package / "main.py").is_file() and (package / "pyproject.toml").is_file():
        return "checkout"
    prefix = Path(sys.prefix).resolve()
    if "pipx" in prefix.parts:
        return "pipx"
    if sys.prefix != sys.base_prefix:
        return "venv"
    try:
        user_site = Path(site.getusersitepackages()).resolve()
    except (AttributeError, OSError):
        user_site = None
    if user_site is not None and str(package).startswith(str(user_site)):
        return "user"
    return "system"


def externally_managed() -> bool:
    """PEP 668: the distribution forbids pip from touching site-packages.

    Arch, Debian and Fedora all ship this marker. Without the flag pip
    stops with "externally-managed-environment" and installs nothing.
    """
    try:
        stdlib = sysconfig.get_path("stdlib")
    except (KeyError, ValueError):
        return False
    return (Path(stdlib) / "EXTERNALLY-MANAGED").is_file()


def upgrade_argv() -> list:
    """The exact command for THIS installation, ready to run.

    Always `sys.executable -m pip`: a bare `pip` is whichever environment
    was activated last, and upgrading that one would leave the running
    kontainy untouched while reporting success.
    """
    kind = install_kind()
    if kind == "pipx":
        return ["pipx", "upgrade", "kontainy"]
    argv = [sys.executable, "-m", "pip", "install", "-U", "kontainy",
            "--no-cache-dir"]
    if kind == "user":
        argv.append("--user")
    if kind == "system" and externally_managed():
        argv.append("--break-system-packages")
    # getattr, not os.geteuid(): the name does not exist on Windows at all,
    # so a direct call is an AttributeError there rather than a False.
    if kind == "system" and getattr(os, "geteuid", lambda: 0)() != 0:
        argv.insert(0, "sudo")
    return argv


def upgrade_command() -> str:
    """What to type, for a message that shows it rather than running it."""
    if install_kind() == "checkout":
        return "git pull"
    return " ".join(upgrade_argv())


def perform_upgrade(timeout: float = 600.0) -> tuple:
    """Run the upgrade. Returns (ok, output).

    Never raises: a failed upgrade is something to read, not a traceback.
    """
    if install_kind() == "checkout":
        return False, ("This kontainy runs from a git checkout, so pip has "
                       "nothing to upgrade. Use: git pull")
    argv = upgrade_argv()
    try:
        done = subprocess.run(argv, capture_output=True, text=True,
                              timeout=timeout)
    except FileNotFoundError:
        return False, f"{argv[0]} is not installed, so kontainy cannot " \
                      f"upgrade itself. Run this yourself:\n    " \
                      f"{' '.join(argv)}"
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"{exc}\n\nRun this yourself:\n    {' '.join(argv)}"
    output = (done.stdout or "") + (done.stderr or "")
    return done.returncode == 0, output.strip()
