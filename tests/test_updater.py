"""Help → Check for Updates asks PyPI, because that is where pip looks."""

import io
import json
import sys

import pytest

from kontainy.core import updater


@pytest.mark.parametrize("latest,current,newer", [
    ("0.0.8", "0.0.7", True),
    ("0.0.7", "0.0.7", False),
    ("0.0.6", "0.0.7", False),
    # The trap of comparing versions as text: "0.0.10" < "0.0.7" as strings.
    ("0.0.10", "0.0.7", True),
    ("0.1.0", "0.0.99", True),
    ("1.0", "0.9.9", True),
])
def test_version_comparison(latest, current, newer):
    assert updater.is_newer(latest, current) is newer


def test_a_release_candidate_is_not_newer_than_the_release():
    """Collecting every digit turned 1.2.3rc1 into (1, 2, 31), which would
    have announced an update to a release candidate."""
    assert updater.parse_version("1.2.3rc1") == (1, 2, 3)
    assert not updater.is_newer("1.2.3rc1", "1.2.3")
    assert updater.parse_version("") == (0, 0, 0)
    assert updater.parse_version("2026.1") == (2026, 1, 0)


def _answer(monkeypatch, payload: dict):
    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False
    monkeypatch.setattr(updater.urllib.request, "urlopen",
                        lambda *a, **k: Response(json.dumps(payload).encode()))


def test_a_newer_release_is_reported(monkeypatch):
    from kontainy.core.constants import APP_VERSION
    _answer(monkeypatch, {"info": {"version": "99.0.0"}})
    result = updater.check_for_update()
    assert result["update_available"] and result["latest"] == "99.0.0"
    assert result["current"] == APP_VERSION and not result["error"]


def test_the_current_release_is_not_an_update(monkeypatch):
    from kontainy.core.constants import APP_VERSION
    _answer(monkeypatch, {"info": {"version": APP_VERSION}})
    assert updater.check_for_update()["update_available"] is False


def test_no_network_is_not_an_error_to_the_user(monkeypatch):
    def boom(*args, **kwargs):
        raise updater.urllib.error.URLError("no route to host")
    monkeypatch.setattr(updater.urllib.request, "urlopen", boom)
    result = updater.check_for_update()
    assert result["error"] and not result["update_available"]


def test_nonsense_from_pypi_is_handled(monkeypatch):
    _answer(monkeypatch, {"info": {}})
    assert updater.check_for_update()["error"]


def test_the_upgrade_command_matches_the_published_name(monkeypatch):
    """It used to be the fixed string "pip install -U kontainy". That names
    a different installation from the running one whenever another
    environment is active, so it is built per install now."""
    monkeypatch.setattr(updater, "install_kind", lambda: "venv")
    command = updater.upgrade_command()
    assert "kontainy" in command
    assert "-m pip install -U" in command


# --- ky update: the upgrade must reach the copy that is running -------------------
def test_the_upgrade_uses_this_interpreter_not_pip_on_path(monkeypatch):
    """A bare `pip` is whichever environment was activated last. Upgrading
    that one leaves the running kontainy untouched and still reports
    success — the worst possible outcome for an update command."""
    monkeypatch.setattr(updater, "install_kind", lambda: "venv")
    argv = updater.upgrade_argv()
    assert argv[:3] == [sys.executable, "-m", "pip"]
    assert "kontainy" in argv and "-U" in argv


def test_a_system_install_on_arch_gets_the_pep_668_flag(monkeypatch):
    """Without it pip stops with externally-managed-environment and
    installs nothing at all."""
    monkeypatch.setattr(updater, "install_kind", lambda: "system")
    monkeypatch.setattr(updater, "externally_managed", lambda: True)
    monkeypatch.setattr(updater.os, "geteuid", lambda: 0, raising=False)
    assert "--break-system-packages" in updater.upgrade_argv()


def test_a_venv_never_gets_that_flag(monkeypatch):
    """It is meaningless inside a venv and hides real mistakes."""
    monkeypatch.setattr(updater, "install_kind", lambda: "venv")
    monkeypatch.setattr(updater, "externally_managed", lambda: True)
    assert "--break-system-packages" not in updater.upgrade_argv()


def test_a_user_install_stays_a_user_install(monkeypatch):
    monkeypatch.setattr(updater, "install_kind", lambda: "user")
    monkeypatch.setattr(updater, "externally_managed", lambda: False)
    assert "--user" in updater.upgrade_argv()


def test_pipx_is_upgraded_the_pipx_way(monkeypatch):
    """pip -U inside a pipx venv works and leaves pipx's metadata stale."""
    monkeypatch.setattr(updater, "install_kind", lambda: "pipx")
    assert updater.upgrade_argv() == ["pipx", "upgrade", "kontainy"]


def test_a_checkout_is_told_to_pull_rather_than_pip(monkeypatch):
    monkeypatch.setattr(updater, "install_kind", lambda: "checkout")
    assert updater.upgrade_command() == "git pull"
    ok, message = updater.perform_upgrade()
    assert ok is False and "git pull" in message


def test_this_checkout_identifies_itself_as_one():
    assert updater.install_kind() == "checkout"


def test_a_missing_installer_is_explained_not_raised(monkeypatch):
    """pipx not installed must produce something to read, not a traceback
    out of a GUI thread."""
    monkeypatch.setattr(updater, "install_kind", lambda: "pipx")

    def missing(*a, **k):
        raise FileNotFoundError("pipx")

    monkeypatch.setattr(updater.subprocess, "run", missing)
    ok, message = updater.perform_upgrade()
    assert ok is False and "pipx upgrade kontainy" in message
