"""kontainy edits shell profiles, so it must never damage one.

It writes only inside its own marked block, and a line the user wrote is
never rewritten — only commented out on request, with a backup.
"""

import pytest

from kontainy.core import shellprofile as sp

USER_BASHRC = """# my aliases
alias ll='ls -l'
export DOCKER_HOST=unix:///tmp/mine.sock
export PATH=$PATH:~/bin
"""


@pytest.fixture
def bashrc(tmp_path, monkeypatch):
    path = tmp_path / ".bashrc"
    path.write_text(USER_BASHRC, encoding="utf-8")
    monkeypatch.setattr(sp, "profile_path", lambda kind="": path)
    monkeypatch.setattr(sp, "shell_kind", lambda: "bash")
    return path


def test_set_writes_only_inside_the_block(bashrc):
    sp.set_value("DOCKER_CONTEXT", "desktop-linux", "bash")
    text = bashrc.read_text(encoding="utf-8")
    assert USER_BASHRC.strip() in text, "the user's lines must survive intact"
    block = text[text.index(sp.BEGIN):text.index(sp.END)]
    assert "export DOCKER_CONTEXT='desktop-linux'" in block


def test_setting_twice_replaces_not_duplicates(bashrc):
    sp.set_value("DOCKER_CONTEXT", "a", "bash")
    sp.set_value("DOCKER_CONTEXT", "b", "bash")
    text = bashrc.read_text(encoding="utf-8")
    assert text.count("DOCKER_CONTEXT") == 1
    assert text.count(sp.BEGIN) == 1
    assert "'b'" in text


def test_unset_removes_the_line_and_an_empty_block(bashrc):
    sp.set_value("DOCKER_CONTEXT", "a", "bash")
    sp.unset_value("DOCKER_CONTEXT", "bash")
    text = bashrc.read_text(encoding="utf-8")
    assert "DOCKER_CONTEXT" not in text
    assert sp.BEGIN not in text, "an empty block is removed entirely"
    assert USER_BASHRC.strip() in text


def test_foreign_lines_are_reported_not_touched(bashrc):
    entries = {e.name: e for e in sp.read("docker", "bash")}
    host = entries["DOCKER_HOST"]
    assert host.foreign and host.foreign[0][0] == 3
    assert host.managed_value == ""


def test_comment_out_keeps_the_line_and_a_backup(bashrc):
    sp.comment_out(3, "bash")
    text = bashrc.read_text(encoding="utf-8")
    assert "# disabled by kontainy: export DOCKER_HOST=" in text
    backup = bashrc.with_name(".bashrc.kontainy.bak")
    assert backup.is_file()
    assert "export DOCKER_HOST=unix:///tmp/mine.sock" in backup.read_text()
    assert sp.read("docker", "bash")[1].foreign == [], \
        "a commented-out line no longer counts"


def test_a_value_written_is_read_back(bashrc):
    sp.set_value("DOCKER_CONTEXT", "prod", "bash")
    entries = {e.name: e for e in sp.read("docker", "bash")}
    assert entries["DOCKER_CONTEXT"].managed_value == "prod"


@pytest.mark.parametrize("kind,expected", [
    ("bash", "export X='v'"), ("zsh", "export X='v'"),
    ("fish", "set -gx X 'v'"), ("powershell", "$env:X = 'v'")])
def test_syntax_per_shell(kind, expected):
    assert sp.line_for(kind, "X", "v") == expected


def test_every_provider_variable_is_explained():
    for provider, variables in sp.VARIABLES.items():
        for name, why in variables:
            assert why.strip(), f"{provider}:{name} has no explanation"


def test_docker_host_warns_that_it_overrides_contexts():
    why = dict(sp.VARIABLES["docker"])["DOCKER_HOST"]
    assert "IGNORED" in why
