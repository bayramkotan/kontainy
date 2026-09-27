"""`ky create` — the window's create dialog, on the command line.

Both build the run command from the same builder and refuse on the same
checks, so the two cannot drift apart.
"""

import json
import os
import pathlib
import stat
import subprocess
import sys

import pytest

from kontainy.core import containercreate as cc
from kontainy.core import imageinfo
from kontainy.core.providers import base
from kontainy.core.providers.containers import DockerProvider, PodmanProvider

TARGET = base.Target("default", "unix:///var/run/docker.sock", True)
ROOT = pathlib.Path(__file__).resolve().parents[1]
posix_only = pytest.mark.skipif(os.name == "nt", reason="shell script engine")


def _plan(values, existing=(), ports=(), facts=None):
    return cc.build(DockerProvider(), TARGET, values, list(existing),
                    list(ports), facts)


def test_the_command_carries_every_field():
    plan = _plan({"image": "nginx:1.27", "name": "web", "ports": "8080:80",
                  "env": "TZ=Europe/Istanbul,DEBUG=1",
                  "volume": "site:/usr/share/nginx/html",
                  "network": "lab", "restart": "unless-stopped"})
    argv = " ".join(plan.argv)
    assert argv.startswith("docker --context default run -d --name web")
    assert "--network=lab" in argv and "--restart unless-stopped" in argv
    assert "-e TZ=Europe/Istanbul" in argv and "-e DEBUG=1" in argv
    assert "-p 8080:80" in argv
    assert "-v site:/usr/share/nginx/html" in argv
    assert plan.argv[-1] == "nginx:1.27", "the image comes last"


def test_the_name_is_suggested_when_none_is_given():
    plan = _plan({"image": "docker.io/library/redis:7"}, existing=["redis"])
    assert plan.values["name"] == "redis-2"
    assert "--name redis-2" in " ".join(plan.argv)


def test_detach_can_be_turned_off():
    plan = _plan({"image": "alpine", "detach": "no", "command": "sh -c 'ls'"})
    assert "-d" not in plan.argv
    assert plan.argv[-3:] == ["sh", "-c", "'ls'"]


def test_rm_is_opt_in():
    assert "--rm" not in _plan({"image": "alpine"}).argv
    assert "--rm" in _plan({"image": "alpine", "rm": "yes"}).argv


# --- what it refuses ----------------------------------------------------------
def test_a_name_already_taken_is_refused():
    plan = _plan({"image": "nginx:1", "name": "web"}, existing=["web"])
    assert plan.refused
    assert any("already a container called web" in text
               for _s, text in plan.problems)


def test_a_published_port_that_is_taken_is_refused():
    plan = _plan({"image": "nginx:1", "name": "a", "ports": "80:80"},
                 ports=["80"])
    assert plan.refused


def test_no_image_is_refused():
    assert _plan({"name": "web"}).refused


def test_an_unknown_field_is_refused_by_name():
    plan = _plan({"image": "nginx:1", "porst": "8080:80"})
    assert plan.refused
    assert any("porst is not a field" in text for _s, text in plan.problems)


def test_a_missing_tag_is_only_a_warning():
    plan = _plan({"image": "nginx", "name": "web"})
    assert not plan.refused
    assert any(severity == "warning" for severity, _t in plan.problems)


def test_an_image_that_is_not_here_warns_about_the_pull():
    facts = imageinfo.ImageFacts(reference="nginx:1.27", local=False)
    plan = _plan({"image": "nginx:1.27", "name": "web"}, facts=facts)
    assert not plan.refused
    assert any("pulls it first" in text for _s, text in plan.problems)


def test_podman_gets_podman_commands():
    plan = cc.build(PodmanProvider(), base.Target("(local)", "", True),
                    {"image": "alpine"}, [], [])
    assert plan.argv[0] == "podman"


def test_the_field_list_names_the_required_one():
    text = cc.describe_fields(DockerProvider())
    assert "image" in text and "*" in text
    assert "ky docker create" in text


# --- end to end ----------------------------------------------------------------
FAKE = r"""#!/bin/sh
echo "$*" >> "$KY_CALLS"
case "$*" in
  "--version") echo "Docker version 29.8.1" ;;
  "context ls --format {{json .}}")
    echo '{"Current":true,"Name":"default","DockerEndpoint":"unix:///var/run/docker.sock"}' ;;
  *"ps -a --format {{json .}}")
    echo '{"Names":"web","Image":"nginx","State":"running","Ports":"0.0.0.0:80->80/tcp"}' ;;
  *"image inspect nginx:1.27")
    echo '[{"Config":{"Cmd":["nginx"],"ExposedPorts":{"80/tcp":{}},"Env":[],"Volumes":{},"Labels":{}},"Size":1,"Created":"x"}]' ;;
  *) echo "created-abc123" ;;
esac
"""


@pytest.fixture
def fake_docker(tmp_path, monkeypatch):
    binary = tmp_path / "docker"
    binary.write_text(FAKE, encoding="utf-8")
    binary.chmod(binary.stat().st_mode | stat.S_IEXEC)
    calls = tmp_path / "calls.log"
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("KY_CALLS", str(calls))
    return lambda: (calls.read_text().splitlines() if calls.exists() else [])


def ky(*args, **kwargs):
    proc = subprocess.run([sys.executable, "-m", "kontainy", *args],
                          capture_output=True, text=True, cwd=str(ROOT),
                          stdin=subprocess.DEVNULL, timeout=120, **kwargs)
    return proc.returncode, proc.stdout, proc.stderr


@posix_only
def test_cli_creates_the_container(fake_docker):
    code, _out, _err = ky("-q", "docker", "create", "api",
                          "image=nginx:1.27", "ports=9090:80", "-y")
    assert code == 0
    ran = [line for line in fake_docker() if " run " in f" {line} "]
    assert ran, fake_docker()
    assert "--name api" in ran[0] and "-p 9090:80" in ran[0]


@posix_only
def test_cli_takes_the_port_from_the_image(fake_docker):
    code, out, _err = ky("docker", "create", "site", "image=nginx:1.27",
                         "--dry-run")
    assert code == 0
    assert "ports taken from the image" in out
    assert "-p 8080:80" in out, "80 is taken by web, so it moves"


@posix_only
def test_cli_refuses_a_taken_name_without_running_anything(fake_docker):
    code, _out, err = ky("docker", "create", "web", "image=nginx:1.27", "-y")
    assert code == 2
    assert "already a container called web" in err
    assert not [line for line in fake_docker() if " run " in f" {line} "]


@posix_only
def test_cli_lists_the_fields_when_asked_for_nothing(fake_docker):
    code, out, _err = ky("docker", "create")
    assert code == 2
    assert "image" in out and "volume" in out
