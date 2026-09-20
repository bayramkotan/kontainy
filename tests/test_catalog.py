"""The settings catalogue is the heart of the project; guard its integrity."""

import pytest

from kontainy.core import catalog


def test_catalogue_is_not_empty():
    assert len(catalog.ALL_SETTINGS) > 100


def test_keys_are_unique():
    keys = [(s.key, s.engine) for s in catalog.ALL_SETTINGS]
    assert len(keys) == len(set(keys)), "duplicate key/engine pair"


@pytest.mark.parametrize("setting", catalog.ALL_SETTINGS,
                         ids=lambda s: f"{s.engine}:{s.key}")
def test_required_fields(setting):
    assert setting.key and setting.title and setting.desc
    assert setting.engine in ("docker", "podman", "both")
    assert setting.surface in catalog.SURFACE_TITLES
    assert setting.privilege in ("user", "root")
    assert setting.danger in (0, 1, 2)
    assert setting.vtype in ("bool", "int", "str", "choice", "list", "dict",
                             "size", "duration")


def test_choice_settings_declare_choices():
    for setting in catalog.ALL_SETTINGS:
        if setting.vtype == "choice":
            assert setting.choices, f"{setting.key} is a choice with no options"


def test_defaults_are_valid_choices():
    for setting in catalog.ALL_SETTINGS:
        if setting.choices and setting.default is not None:
            assert setting.default in setting.choices, \
                f"{setting.key} default {setting.default!r} is not an option"


def test_search_finds_known_keys():
    assert any(s.key == "log-driver" for s in catalog.search("log"))
    assert catalog.by_key("containers.cgroup_manager") is not None


def test_stats_are_consistent():
    stats = catalog.stats()
    assert stats["total"] == len(catalog.ALL_SETTINGS)
    assert stats["docker"] + stats["podman"] + stats["shared"] == stats["total"]
