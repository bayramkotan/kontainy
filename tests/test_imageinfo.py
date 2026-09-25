"""The create dialog should suggest, not interrogate.

Bayram, 2026-09-25, looking at a form of empty boxes: "Ben yazacaksam her
şeyi, bunun ne önemi var ki? O zaman terminalden çalıştırayım."
"""

import json

import pytest

from kontainy.core import imageinfo as ii
from kontainy.core.providers import base
from kontainy.core.providers.containers import DockerProvider

TARGET = base.Target("default", "unix:///var/run/docker.sock", True)

INSPECT = json.dumps([{
    "Config": {"Entrypoint": ["/docker-entrypoint.sh"],
               "Cmd": ["nginx", "-g", "daemon off;"],
               "WorkingDir": "/usr/share/nginx", "User": "nginx",
               "ExposedPorts": {"80/tcp": {}, "443/tcp": {}},
               "Env": ["PATH=/usr/local/sbin", "NGINX_VERSION=1.27.2",
                       "TZ=UTC"],
               "Volumes": {"/var/cache/nginx": {}}, "Labels": {}},
    "Size": 187_000_000, "Created": "2026-08-01T10:00:00Z"}])

IMAGES = "\n".join(json.dumps(item) for item in [
    {"Repository": "nginx", "Tag": "1.27", "Size": "187MB",
     "CreatedSince": "3 weeks ago"},
    {"Repository": "<none>", "Tag": "<none>", "Size": "12MB",
     "CreatedSince": "1 day ago"},
    {"Repository": "redis", "Tag": "7-alpine", "Size": "41MB",
     "CreatedSince": "5 days ago"}])


@pytest.fixture
def engine(monkeypatch):
    monkeypatch.setattr(base, "cli_text", lambda argv, timeout=15.0: (
        (True, IMAGES) if "images" in argv else (True, INSPECT)))
    return DockerProvider()


def test_local_images_are_offered_without_the_dangling_ones(engine):
    images = ii.local_images(engine, TARGET)
    assert [i["reference"] for i in images] == ["nginx:1.27", "redis:7-alpine"]
    assert images[0]["size"] == "187MB", "say how big, it is why people choose"


def test_an_image_says_its_own_command_and_ports(engine):
    facts = ii.read_facts(engine, TARGET, "nginx:1.27")
    assert facts.local
    assert facts.command == ["nginx", "-g", "daemon off;"]
    assert facts.entrypoint == ["/docker-entrypoint.sh"]
    assert facts.ports == ["443/tcp", "80/tcp"]
    assert facts.working_dir == "/usr/share/nginx" and facts.user == "nginx"
    assert facts.size == "187 MB"


def test_an_image_that_is_not_here_is_not_an_error(monkeypatch):
    monkeypatch.setattr(base, "cli_text",
                        lambda argv, timeout=15.0: (False, "No such image"))
    facts = ii.read_facts(DockerProvider(), TARGET, "nope:1")
    assert not facts.local and facts.needs_pull
    assert "No such image" in facts.error


def test_the_name_is_suggested_from_the_image():
    assert ii.suggest_name("docker.io/library/nginx:1.27", []) == "nginx"
    assert ii.suggest_name("nginx:1.27", ["nginx"]) == "nginx-2"
    assert ii.suggest_name("nginx", ["nginx", "nginx-2"]) == "nginx-3"


def test_ports_are_suggested_from_what_the_image_exposes():
    facts = ii.ImageFacts(ports=["80/tcp", "443/tcp"])
    assert [(c, h) for c, h, _ in ii.suggest_ports(facts, [])] == [
        ("80/tcp", "80"), ("443/tcp", "443")]


def test_a_taken_port_moves_out_of_the_privileged_range():
    """Suggesting 81 because 80 was taken produced a port that needs root on
    Linux — a suggestion that argued with the dialog's own warning."""
    facts = ii.ImageFacts(ports=["80/tcp"])
    container, host, note = ii.suggest_ports(facts, ["80"])[0]
    assert int(host) >= 1024, host
    assert "already published" in note, "say why it is not 80"


def test_the_image_environment_is_shown_without_the_noise():
    facts = ii.read_facts.__wrapped__ if hasattr(ii.read_facts, "__wrapped__") \
        else None
    facts = ii.ImageFacts(env=["PATH=/x", "LANG=C", "TZ=UTC",
                               "NGINX_VERSION=1.27"])
    assert ii.env_defaults(facts) == ["TZ=UTC", "NGINX_VERSION=1.27"]


# --- what would go wrong ------------------------------------------------------
def test_no_image_is_an_error():
    found = ii.problems("web", "", [], [], [])
    assert any(s == "error" for s, _ in found)


def test_a_missing_tag_is_a_warning_not_a_refusal():
    found = ii.problems("web", "nginx", [], [], [])
    assert [s for s, _ in found] == ["warning"]
    assert "reproducible" in found[0][1]


def test_a_name_already_taken_is_refused_before_the_engine_refuses_it():
    found = ii.problems("web", "nginx:1", ["web"], [], [])
    assert ("error", ) == tuple({s for s, _ in found})
    assert "already a container called web" in found[0][1]


def test_an_invalid_name_is_explained_in_words():
    found = ii.problems("my container!", "nginx:1", [], [], [])
    assert any("letters, digits" in text for _s, text in found)


def test_a_published_port_that_is_taken_is_refused():
    found = ii.problems("web", "nginx:1", [], ["8080"], ["8080"])
    assert any(s == "error" and "8080" in t for s, t in found)


def test_a_privileged_port_is_a_warning():
    found = ii.problems("web", "nginx:1", [], ["80"], [])
    assert any(s == "warning" and "root" in t for s, t in found)


def test_a_clean_form_says_nothing():
    assert ii.problems("web", "nginx:1.27", ["other"], ["8080"], ["9000"]) == []
