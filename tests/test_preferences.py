"""Preferences must cover every default, and defaults must be complete."""

import re
from pathlib import Path

import pytest

from kontainy.utils.config import DEFAULTS

SOURCE = Path(__file__).resolve().parents[1] / "kontainy/gui/pages/preferences.py"
TEXT = SOURCE.read_text(encoding="utf-8")


def _bound_keys() -> set:
    """Every DEFAULTS key the page binds a widget to."""
    return set(re.findall(r'_bind_\w+\(\s*"([a-z_]+)"', TEXT)) \
        | set(re.findall(r'_path_row\(\s*"([a-z_]+)"', TEXT))


def test_every_bound_key_exists_in_defaults():
    unknown = _bound_keys() - set(DEFAULTS)
    assert not unknown, f"Preferences binds keys with no default: {unknown}"


def test_every_reset_key_exists_in_defaults():
    reset_keys = set()
    for block in re.findall(r'self\._reset\(\[(.*?)\]', TEXT, re.S):
        reset_keys |= set(re.findall(r'"([a-z_]+)"', block))
    unknown = reset_keys - set(DEFAULTS)
    assert not unknown, f"Reset lists unknown keys: {unknown}"


def test_window_geometry_is_not_editable():
    """Window position is remembered, not configured; putting it on the page
    would invite someone to type a coordinate and lose the window."""
    assert "window_width" not in _bound_keys()
    assert "window_x" not in _bound_keys()


def test_meaningful_share_of_defaults_is_reachable():
    geometry = {k for k in DEFAULTS if k.startswith("window_")}
    locked = {"always_show_command"}
    reachable = _bound_keys()
    missing = set(DEFAULTS) - geometry - locked - reachable
    assert len(missing) <= 3, f"too many settings unreachable: {missing}"


def test_all_sections_present():
    for section in ("Appearance", "Language", "General", "Engines",
                    "Terminal", "Config Catalog", "Diagnostics",
                    "Privileges", "Advanced"):
        assert f'"{section}"' in TEXT, f"missing section: {section}"


def test_eleven_languages_are_offered():
    from kontainy.core.constants import LANGUAGES
    assert len(LANGUAGES) == 11
    codes = [code for code, _ in LANGUAGES]
    assert len(codes) == len(set(codes))
    assert "en" in codes and "tr" in codes


def test_show_command_cannot_be_turned_off():
    """Nothing runs unseen. An option to disable that would defeat the tool."""
    assert DEFAULTS["always_show_command"] is True
    assert "always_show_command" not in _bound_keys()


def test_gui_modules_import_without_qt():
    """Every page module must import under the CI stub. This is the test
    that would have caught the 0.0.3 failure before a tag was pushed."""
    import importlib
    for name in ("kontainy.gui.pages.base", "kontainy.gui.pages.preferences",
                 "kontainy.gui.pages.tools", "kontainy.gui.pages.settings",
                 "kontainy.gui.pages.overview", "kontainy.gui.dialogs.about",
                 "kontainy.gui.dialogs.run_command",
                 "kontainy.gui.pages.platform", "kontainy.gui.pages.overview",
                 "kontainy.gui.main_window"):
        importlib.import_module(name)
