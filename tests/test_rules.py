"""Diagnostic rules must never crash and never need root to detect."""

import pytest

from kontainy.rules import RULES, Environment, run_rules


def test_rule_ids_are_unique():
    ids = [rule.id for rule in RULES]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("rule", RULES, ids=lambda r: r.id)
def test_rule_shape(rule):
    assert rule.severity in ("error", "warn", "info")
    assert rule.title and rule.explain
    assert rule.fix_scope in ("user", "root", "none")
    assert callable(rule.detect)


def test_rules_survive_an_empty_environment():
    """An empty Environment must not raise — a rule that crashes on a missing
    field would take the whole diagnostics page down on someone's machine."""
    findings = run_rules(Environment(), RULES)
    assert isinstance(findings, list)


def test_findings_are_sorted_by_severity():
    findings = run_rules(Environment(), RULES)
    order = {"error": 0, "warn": 1, "info": 2}
    severities = [order[f.severity] for f in findings]
    assert severities == sorted(severities)
