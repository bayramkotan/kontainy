"""Ctrl+K — the one box that reaches all of it.

kontainy holds 19 pages, 152 settings and 204 Learn topics, and before this
every one of them was reachable only by clicking the sidebar and then
hunting inside the page. These tests are about the two things that decide
whether such a box gets used twice: it has to find what you half-remember,
and it has to open instantly.
"""

import pytest

from kontainy.core import palette


def entry(kind="page", label="Images", **kw):
    return palette.Entry(kind=kind, label=label, **kw)


# --- what makes a palette feel like it read your mind -----------------------------
def test_an_exact_name_always_wins():
    pool = [entry(label="Images"), entry(label="Image registries mirror")]
    assert palette.rank("Images", pool)[0].label == "Images"


def test_initials_find_a_hyphenated_key():
    """The catalogue is full of names like short-name-mode, and people type
    snm. A substring search answers nothing for that, which is how a search
    box teaches people it is useless."""
    pool = [palette.Entry(kind="setting", label="Short name mode"),
            palette.Entry(kind="setting", label="Storage driver")]
    assert palette.rank("snm", pool)[0].label == "Short name mode"


def test_letters_are_matched_in_order_not_as_a_block():
    pool = [entry(label="Default address pools")]
    assert palette.rank("dap", pool)
    assert not palette.rank("pad", pool)


def test_a_run_of_adjacent_letters_beats_scattered_ones():
    pool = [entry(label="Volume backup"), entry(label="Verify Open Logs")]
    assert palette.rank("vol", pool)[0].label == "Volume backup"


def test_matching_the_start_of_a_word_counts_for_more():
    pool = [entry(label="Rootless network program"),
            palette.Entry(kind="page", label="Troubleshooting",
                          keywords="r o o t")]
    assert palette.rank("root", pool)[0].label == "Rootless network program"


def test_keywords_are_searched_as_well_as_the_label():
    """Nobody searches for a page by its title alone. "Images" is
    findable; so should "unused" and "registry" be."""
    pool = [palette.Entry(kind="page", label="Images",
                          keywords="unused registry prune")]
    assert palette.rank("prune", pool)


def test_nothing_matches_returns_nothing_rather_than_everything():
    assert palette.rank("zzzqqq", [entry(label="Images")]) == []


def test_a_short_query_favours_pages_over_learn_topics():
    """Two letters almost always mean "take me to a page"."""
    pool = [palette.Entry(kind="topic", label="Volumes, and why they outlive"),
            palette.Entry(kind="page", label="Volumes")]
    assert palette.rank("vo", pool)[0].kind == "page"


def test_the_limit_is_honoured():
    pool = [entry(label=f"Page {i}") for i in range(200)]
    assert len(palette.rank("page", pool, limit=12)) == 12


# --- scopes ----------------------------------------------------------------------
def test_a_scope_character_narrows_before_anything_is_scored():
    """#storage must not drown in Learn topics about storage."""
    pool = [palette.Entry(kind="topic", label="Storage drivers explained"),
            palette.Entry(kind="setting", label="Storage driver")]
    hits = palette.rank("#storage", pool)
    assert hits and all(h.kind == "setting" for h in hits)


def test_every_scope_character_maps_to_a_real_kind():
    """A prefix that narrows to a kind nothing is indexed as returns an
    empty list for every query, which reads as a broken box."""
    assert set(palette.SCOPES.values()) <= set(palette.KINDS)


def test_an_empty_query_still_lists_things():
    """Opening the box and seeing nothing suggests it is broken."""
    pool = [entry(label="Images"), entry(label="Volumes")]
    assert len(palette.rank("", pool)) == 2


# --- the index -------------------------------------------------------------------
def test_the_whole_catalogue_is_indexed():
    from kontainy.core.catalog import ALL_SETTINGS
    assert len(palette.setting_entries()) == len(ALL_SETTINGS)


def test_every_learn_topic_is_indexed():
    from kontainy.learn.content import LEARN_CATEGORIES
    total = sum(len(c["topics"]) for c in LEARN_CATEGORIES)
    assert len(palette.topic_entries()) == total


def test_a_setting_carries_its_key_so_the_key_can_be_typed():
    entries = palette.setting_entries()
    hit = palette.rank("default-address-pools", entries)
    assert hit and hit[0].payload.get("setting") == "default-address-pools"


def test_a_topic_knows_exactly_which_of_the_204_it_is():
    """The search box finds the first match for a word; the palette
    already knows which topic it means and must say so."""
    entries = palette.topic_entries()
    for item in entries:
        index, position = item.payload["topic"]
        assert isinstance(index, int) and isinstance(position, int)


def test_a_dangerous_setting_is_marked_in_the_list():
    marked = [e for e in palette.setting_entries() if "⚠" in e.hint]
    assert marked


# --- cost ------------------------------------------------------------------------
class FakePage:
    TITLE = "All containers"
    SUBTITLE = "Containers from every engine"

    def __init__(self, rows=None):
        self.rows = rows or []


def test_building_the_object_index_never_runs_a_command(monkeypatch):
    """⚠️ Ctrl+K must not talk to an engine. A box that pauses for two
    seconds on a slow socket is a box nobody opens twice."""
    import subprocess

    def forbidden(*a, **k):
        raise AssertionError("the palette ran a command")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    pages = {"containers": FakePage([
        {"name": "web", "engine": "Docker", "target": "default",
         "state": "running"}])}
    assert palette.object_entries(pages)[0].label == "web"


def test_objects_come_only_from_what_the_pages_already_hold():
    pages = {"containers": FakePage(), "images": FakePage()}
    assert palette.object_entries(pages) == []


def test_an_object_knows_which_page_to_open_and_what_to_select():
    pages = {"volumes": FakePage([
        {"name": "pgdata", "engine": "Docker", "target": "default"}])}
    found = palette.object_entries(pages)[0]
    assert found.payload == {"page": "volumes", "select": "pgdata"}


def test_a_page_that_has_never_been_opened_contributes_nothing():
    """`rows` is absent until a page has loaded once, and that must read
    as "nothing to offer" rather than raise on a keystroke."""
    class NeverOpened:
        TITLE = "Images"
    assert palette.object_entries({"images": NeverOpened()}) == []


def test_ranking_the_real_index_is_fast():
    """It runs on every keystroke, so it is allowed to be linear and
    nothing more."""
    import time
    index = palette.setting_entries() + palette.topic_entries()
    start = time.perf_counter()
    for query in ("sto", "rootless", "seccomp", "dap", "k8s"):
        palette.rank(query, index)
    assert (time.perf_counter() - start) < 1.0


# --- actions ---------------------------------------------------------------------
def test_an_action_entry_carries_the_callable():
    called = []
    found = palette.action_entries([("New Container", "File",
                                     lambda: called.append(1))])[0]
    found.payload["call"]()
    assert called == [1]


def test_pages_are_indexed_by_title_and_by_name():
    pages = {"inventory-x": FakePage()}
    found = palette.page_entries(pages)[0]
    assert found.payload == {"page": "inventory-x"}
    assert palette.rank("inventory-x", [found])


# --- the two ranking faults found by driving the real index ----------------------
def test_a_whole_word_in_the_keywords_beats_letters_picked_out_of_one():
    """Typing "doctor" landed on the Docker page. "doctor" is a whole word
    in the Diagnostics page's keywords, but only the label was checked for
    a substring, so that exact hit was scored as a scattered fuzzy match
    and lost to letters picked out of the word "context"."""
    pool = [palette.Entry(kind="page", label="Docker",
                          keywords="docker dockerd daemon context compose"),
            palette.Entry(kind="page", label="Diagnostics",
                          keywords="doctor check problems")]
    assert palette.rank("doctor", pool)[0].label == "Diagnostics"


def test_a_match_buried_inside_a_word_is_not_treated_as_strong():
    """A Learn topic carries 400 characters of body in its keywords, so
    "dap" finds "adapter" — which must not outrank the setting whose
    initials it actually is."""
    pool = [palette.Entry(kind="topic", label="Networks and addressing",
                          keywords="the adapter is attached to a bridge"),
            palette.Entry(kind="setting", label="Drop capability")]
    assert palette.rank("dap", pool)[0].label == "Drop capability"


def test_the_kind_bonus_cannot_promote_a_weak_match_over_a_strong_one():
    """Added flat, it did: "snm" put the KVM page above "Short name mode",
    because a few of those letters are scattered through the page's
    subtitle and a page outweighs a setting by 20."""
    pool = [palette.Entry(kind="page", label="KVM / libvirt",
                          keywords="snapshots and migration"),
            palette.Entry(kind="setting", label="Short name mode")]
    assert palette.rank("snm", pool)[0].label == "Short name mode"


# --- aliases ---------------------------------------------------------------------
def test_k8s_finds_kubernetes():
    """There is no 8 in Kubernetes, so before the alias table this matched
    nothing at all — and a box that cannot find Kubernetes from "k8s" is
    one people stop trying."""
    pool = palette.page_entries(
        {"platform-kubernetes": type("P", (), {"TITLE": "Kubernetes",
                                               "SUBTITLE": ""})()})
    assert palette.rank("k8s", pool)


def test_the_words_people_actually_type_reach_their_page():
    pages = {"platform-libvirt": type("P", (), {"TITLE": "KVM / libvirt",
                                                "SUBTITLE": ""})(),
             "catalog": type("P", (), {"TITLE": "Config Catalog",
                                       "SUBTITLE": ""})()}
    pool = palette.page_entries(pages)
    assert palette.rank("qemu", pool)[0].label == "KVM / libvirt"
    assert palette.rank("daemon.json", pool)[0].label == "Config Catalog"


def test_every_alias_key_matches_a_real_page():
    """An alias for a page that does not exist is dead weight that can
    still steal a match from a page that does.

    Checked against every page kontainy can have, not the ones this OS
    shows: Hyper-V has no page on Linux and Incus none on Windows, and an
    alias is not wrong for being on the wrong machine today.
    """
    from kontainy.core.providers import PROVIDERS
    from kontainy.gui import main_window as mw

    names = {cls.NAME for _, cls in mw.SIDEBAR if cls is not None}
    names |= {f"platform-{p.id}" for p in PROVIDERS}
    blob = " ".join(names)
    assert [key for key in palette.ALIASES if key not in blob] == []
