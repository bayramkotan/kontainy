"""Help → Check for Updates asks PyPI, because that is where pip looks."""

import json
import io

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


def test_the_upgrade_command_matches_the_published_name():
    assert "kontainy" in updater.upgrade_command()
    assert updater.upgrade_command().startswith("pip install -U")
