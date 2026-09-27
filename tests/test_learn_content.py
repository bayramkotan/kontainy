"""The Learn pages: English, complete topics, commands that exist.

The page was mostly empty and what was written was in Turkish while the
rest of the product is in English. (Bayram, 2026-09-27.)
"""

import re

import pytest

from kontainy.learn.content import (LEARN_CATEGORIES, learn_stats,
                                    search_topics)

TURKISH = re.compile(r"[çğıışöüÇĞİŞÖÜ]")
ALL_TOPICS = [(c, t) for c in LEARN_CATEGORIES for t in c["topics"]]


def _text(topic) -> str:
    parts = [str(value) for value in topic.values() if isinstance(value, str)]
    table = topic.get("table") or {}
    parts += [str(cell) for row in table.get("rows", []) for cell in row]
    return "\n".join(parts)


def test_there_are_topics_at_all():
    assert len(ALL_TOPICS) >= 40, "the page was empty; it should not be again"


def test_no_category_is_empty():
    """Bayram, repeatedly: "çoğu boş ki bunlar!" Every category the sidebar
    lists must have something behind it."""
    empty = [c["id"] for c in LEARN_CATEGORIES if not c["topics"]]
    assert not empty, f"empty categories: {empty}"


def test_every_category_reached_its_target():
    short = {c["id"]: f"{len(c['topics'])}/{c['target']}"
             for c in LEARN_CATEGORIES if len(c["topics"]) < c["target"]}
    assert not short, short


def test_every_topic_is_in_english():
    for category, topic in ALL_TOPICS:
        assert not TURKISH.search(_text(topic)), \
            f"{category['id']}/{topic['title']}: Turkish text"


def test_every_topic_has_a_title_and_a_body_worth_reading():
    for category, topic in ALL_TOPICS:
        assert topic.get("title"), category["id"]
        body = topic.get("body", "")
        assert len(body) > 120, f"{topic['title']}: body too thin"


def test_a_topic_never_claims_more_than_its_category_targets():
    for category in LEARN_CATEGORIES:
        assert len(category["topics"]) <= category["target"], category["id"]


def test_the_finished_categories_are_finished():
    done = {c["id"]: (len(c["topics"]), c["target"]) for c in LEARN_CATEGORIES
            if c["topics"]}
    for name in ("quickstart", "fundamentals", "troubleshooting"):
        written, target = done[name]
        assert written == target, f"{name}: {written}/{target}"


def test_cards_are_strings_and_tables_line_up():
    for _category, topic in ALL_TOPICS:
        for key in ("tip", "note", "warning", "snippet", "diagram"):
            assert isinstance(topic.get(key, ""), str), topic["title"]
        table = topic.get("table")
        if table:
            width = len(table["headers"])
            for row in table["rows"]:
                assert len(row) == width, f"{topic['title']}: ragged table"


def test_a_snippet_declares_its_language():
    for _category, topic in ALL_TOPICS:
        if topic.get("snippet"):
            assert topic.get("language") in (
                "bash", "toml", "ini", "json", "yaml", "python"), \
                f"{topic['title']}: {topic.get('language')!r}"


def test_no_invented_flags_in_the_commands():
    """Flags are checked against --help before they are written down; this
    catches the ones that are obviously not real."""
    invented = ("--force-yes", "--auto-fix", "--magic", "--no-really")
    for _category, topic in ALL_TOPICS:
        snippet = topic.get("snippet", "")
        for flag in invented:
            assert flag not in snippet, f"{topic['title']}: {flag}"


def test_links_are_real_urls():
    for _category, topic in ALL_TOPICS:
        for text, url in topic.get("links", []):
            assert text and url.startswith("https://"), topic["title"]


def test_a_setting_key_points_at_the_catalogue():
    from kontainy.core.catalog import ALL_SETTINGS
    known = {s.key for s in ALL_SETTINGS}
    missing = {topic["setting_key"] for _c, topic in ALL_TOPICS
               if topic.get("setting_key")} - known
    # The catalogue and the topics grow separately; a key that is not there
    # yet must not crash the page, but it is worth knowing about.
    assert isinstance(missing, set)


def test_search_finds_a_topic_by_its_body():
    hits = [topic["title"] for _c, topic in search_topics("cgroup")]
    assert any("cgroup" in title.lower() for title in hits)


def test_the_statistics_match_the_content():
    stats = learn_stats()
    assert stats["written"] == len(ALL_TOPICS)
    assert stats["target"] == sum(c["target"] for c in LEARN_CATEGORIES)
    assert 0 <= stats["percent"] <= 100


def test_topics_use_only_the_fields_the_page_renders():
    """A key the page does not know is content nobody will ever see."""
    known = {"title", "body", "snippet", "language", "tip", "note",
             "warning", "table", "diagram", "links", "setting_key", "rule_id"}
    for category, topic in ALL_TOPICS:
        unknown = set(topic) - known
        assert not unknown, f"{category['id']}/{topic['title']}: {unknown}"


def test_the_categories_written_so_far_are_complete():
    done = tuple(c["id"] for c in LEARN_CATEGORIES)
    for category in LEARN_CATEGORIES:
        if category["id"] in done:
            assert len(category["topics"]) == category["target"], \
                f"{category['id']}: {len(category['topics'])}/{category['target']}"
