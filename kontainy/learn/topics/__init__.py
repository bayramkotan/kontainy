"""
kontainy — Learn content, one module per category

The Learn page is the educational pillar: it explains the ecosystem, not
kontainy. Every topic is written in ENGLISH, like the rest of the product,
and every command shown is one the reader can actually type — flags are
checked against `--help` rather than remembered.

One module per category, because 204 topics in one file is a file nobody
opens twice, and because the categories are written in batches.

A topic is a dict:

    title    (required)  the question a person would actually ask
    body     (required)  plain text, paragraphs separated by a blank line
    snippet              a runnable example
    language             bash | toml | ini | json | yaml | python
    tip                  green card — the practice worth keeping
    note                 blue card — the context that is missing elsewhere
    warning              orange card — the thing that bites
    table                {"headers": [...], "rows": [[...]]}
    diagram              monospace drawing
    links                [(text, url), ...]
    setting_key          opens that setting in the catalogue
    rule_id              the diagnostic rule that finds this in practice

RULE: topics are added, never removed. A body may grow richer later.
"""

from . import (compose, docker, fundamentals, images,  # noqa: F401
               kubernetes, kvm, lxc, migration, network, performance,
               podman, quickstart, security, storage, systemd,
               troubleshooting)

__all__ = ["quickstart", "fundamentals", "docker", "podman", "systemd",
           "kubernetes", "kvm", "lxc", "network", "storage", "security",
           "images", "compose", "troubleshooting", "performance",
           "migration"]
