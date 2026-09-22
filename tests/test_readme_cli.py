"""Every command the README's CLI table shows must actually exist.

A documented command that does not work is worse than none. This reads the
table and checks each `ky` line against the real parser, the real
technologies, their sections and the verbs their actions produce.
"""

import pathlib
import re

import pytest

from kontainy import cli
from kontainy.core.providers import PROVIDERS, base

ROOT = pathlib.Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")


def _cli_rows() -> list:
    section = README[README.index("### CLI"):]
    section = section[:section.index("\n---")]
    commands = []
    for line in section.splitlines():
        if not line.startswith("| `ky"):
            continue
        cell = line.split("|")[1]
        for chunk in re.findall(r"`(ky[^`]*)`", cell):
            commands.append(chunk)
    return commands


def _object_verbs(provider) -> set:
    rows = [{provider.object_key: "x", "State": s, "state": s, "status": s,
             "Status": s} for s in ("running", "exited", "shut off", "Off",
                                    "Running", "Stopped")]
    verbs = set()
    for row in rows:
        for action in provider.object_actions(base.Target("t", "a"), row):
            verbs.add(cli._verb(action.label))
    return verbs


def _section_verbs(section) -> set:
    verbs = {"ls", "create"}
    for state in ("active", "inactive"):
        for auto in ("yes", "no"):
            row = {section.key: "x", "state": state, "autostart": auto}
            for action in section.row_actions(base.Target("t", "a"), row):
                verbs.add(cli._verb(action.label))
    return verbs


def test_the_readme_has_a_cli_table():
    assert len(_cli_rows()) > 20


@pytest.mark.parametrize("command", _cli_rows())
def test_every_documented_command_exists(command):
    words = command.split()[1:]
    words = [w for w in words if not w.startswith("-")]
    if not words:
        return
    head = words[0]
    top = {"overview", "tech", "tools", "install", "uninstall", "catalog",
           "doctor", "scan", "stats", "wsl", "version", "gui"}
    if head in top or head.upper() == head:      # TECH placeholder
        return
    assert head in cli.TECH_ALIASES, f"unknown command {head!r} in README"
    provider = next(p for p in PROVIDERS if p.id == cli.TECH_ALIASES[head])
    if len(words) == 1:
        return
    verb = words[1]
    if verb in cli.TECH_VERBS:
        return
    sections = {s.id: s for s in provider.sections()}
    if verb in sections:
        if len(words) > 2:
            sub = words[2]
            known = _section_verbs(sections[verb])
            assert sub in known or cli._find(dict.fromkeys(known, 1), sub), \
                f"{command}: {sub!r} not among {sorted(known)}"
        return
    known = _object_verbs(provider)
    assert verb in known or cli._find(dict.fromkeys(known, 1), verb), \
        f"{command}: {verb!r} not among {sorted(known)}"


def test_every_verb_named_in_prose_resolves():
    """The table also names verbs in its description column."""
    checks = {"libvirt": ["start", "shutdown", "reboot", "force-off",
                          "autostart"],
              "hyperv": ["start", "shutdown", "save-state", "turn-off",
                         "checkpoint"],
              "kubernetes": ["logs", "describe", "delete"],
              "incus": ["start", "stop", "restart", "delete"],
              "docker": ["start", "stop", "restart", "logs", "rm"]}
    for pid, verbs in checks.items():
        provider = next(p for p in PROVIDERS if p.id == pid)
        known = dict.fromkeys(_object_verbs(provider), 1)
        for verb in verbs:
            assert cli._find(known, verb), f"ky {pid} {verb}: not a verb"
