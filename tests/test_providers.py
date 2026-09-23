"""Providers parse each tool's own CLI output. These tests feed them real
output shapes, so they run anywhere — no docker, kubectl or virsh needed,
and they behave the same on Linux, Windows and macOS CI."""

import pytest

from kontainy.core import providers
from kontainy.core.providers import base, containers, platforms

DOCKER_CONTEXTS = (
    '{"Current":true,"Description":"Current DOCKER_HOST based configuration",'
    '"DockerEndpoint":"unix:///var/run/docker.sock","Error":"","Name":"default"}\n'
    '{"Current":false,"Description":"Docker Desktop","DockerEndpoint":'
    '"unix:///home/u/.docker/desktop/docker.sock","Error":"","Name":"desktop-linux"}\n')

PODMAN_CONNECTIONS = (
    '[{"Name":"podman-machine-default","URI":"ssh://core@127.0.0.1:52341/run/'
    'user/501/podman/podman.sock","Identity":"/home/u/.ssh/pm","IsMachine":true,'
    '"Default":true,"ReadWrite":true}]')

KUBE_CONFIG = (
    '{"contexts":[{"name":"kind-dev","context":{"cluster":"kind-dev",'
    '"user":"kind-dev"}},{"name":"prod","context":{"cluster":"prod",'
    '"user":"admin","namespace":"web"}}],"current-context":"kind-dev"}')

INCUS_REMOTES = (
    '{"local":{"Addr":"unix://","Protocol":"incus","Public":false,"Static":true},'
    '"images":{"Addr":"https://images.linuxcontainers.org","Protocol":'
    '"simplestreams","Public":true,"Static":false}}')

VIRSH_LIST = (" Id   Name     State\n"
              "--------------------------\n"
              " 1    win11    running\n"
              " -    fedora   shut off\n")

WSL_LIST = ("  NAME              STATE           VERSION\n"
            "* Ubuntu-24.04      Running         2\n"
            "  docker-desktop    Running         2\n"
            "  podman-machine-default Stopped    2\n")


@pytest.fixture(autouse=True)
def local_tools(monkeypatch):
    """These tests are about parsing a Linux tool's own output, so the tools
    run here, on this machine.

    Without this they fail on Windows, and only there: a Windows machine with
    WSL runs the Linux tools inside it, so every command arrives wrapped in
    `wsl -d Ubuntu -- ...` and the faked CLI below no longer recognises it —
    and libvirt's default connection is kept in kontainy's settings instead
    of the distribution's libvirt.conf. Both are correct behaviour; the
    tests simply have to say where they stand.
    """
    from kontainy.core import hosts, registry
    monkeypatch.setattr(registry, "OS_KIND", "linux")
    monkeypatch.setattr(hosts, "on_windows", lambda: False)


def fake_cli(responses: dict):
    """cli_text replacement keyed by the joined argv prefix."""
    def run(argv, timeout=15.0):
        joined = " ".join(argv)
        for key, value in responses.items():
            if joined.startswith(key):
                return True, value
        return False, f"unexpected: {joined}"
    return run


def test_docker_contexts(monkeypatch):
    monkeypatch.setattr(containers, "cli_text", fake_cli(
        {"docker context ls": DOCKER_CONTEXTS}))
    targets = containers.DockerProvider().targets()
    assert [t.name for t in targets] == ["default", "desktop-linux"]
    assert targets[0].active and not targets[1].active
    assert not targets[0].removable, "the default context cannot be removed"


def test_docker_warns_when_docker_host_is_set(monkeypatch):
    monkeypatch.setenv("DOCKER_HOST", "unix:///tmp/x.sock")
    assert "DOCKER_HOST" in containers.DockerProvider().warning()
    monkeypatch.delenv("DOCKER_HOST")
    assert containers.DockerProvider().warning() == ""


def test_podman_connections(monkeypatch):
    monkeypatch.setattr(containers, "cli_text", fake_cli(
        {"podman system connection list": PODMAN_CONNECTIONS}))
    targets = containers.PodmanProvider().targets()
    assert targets[0].name == "podman-machine-default"
    assert targets[0].active


def test_podman_without_connections_shows_local(monkeypatch):
    """An empty dropdown would lie: with no connection podman runs locally."""
    monkeypatch.setattr(containers, "cli_text", fake_cli(
        {"podman system connection list": "[]"}))
    targets = containers.PodmanProvider().targets()
    assert targets[0].name == "(local)" and targets[0].active
    assert not targets[0].removable


def test_kubernetes_contexts(monkeypatch):
    monkeypatch.setattr(platforms, "cli_text", fake_cli(
        {"kubectl config view": KUBE_CONFIG}))
    targets = platforms.KubernetesProvider().targets()
    assert [t.name for t in targets] == ["kind-dev", "prod"]
    assert targets[0].active
    assert "namespace web" in targets[1].detail


def test_incus_remotes(monkeypatch):
    monkeypatch.setattr(platforms, "cli_text", fake_cli({
        "incus remote list": INCUS_REMOTES,
        "incus remote get-default": "local"}))
    targets = platforms.IncusProvider().targets()
    names = {t.name: t for t in targets}
    assert names["local"].active
    assert not names["local"].removable


def test_virsh_list_keeps_shut_off_domains(monkeypatch):
    """A shut-off domain has "-" as its id. The first parser skipped every
    line starting with a dash and silently dropped them."""
    monkeypatch.setattr(platforms, "cli_text", fake_cli(
        {"virsh -c": VIRSH_LIST}))
    provider = platforms.LibvirtProvider()
    listing = provider.objects(base.Target("system", "qemu:///system"))
    names = [row["name"] for row in listing.rows]
    assert names == ["win11", "fedora"]
    assert listing.rows[1]["state"] == "shut off"


def test_wsl_list_marks_default_and_docker_desktop():
    targets = providers.parse_wsl_list(WSL_LIST)
    by_name = {t.name: t for t in targets}
    assert by_name["Ubuntu-24.04"].active
    assert "Docker Desktop" in by_name["docker-desktop"].detail
    assert not by_name["docker-desktop"].removable
    assert "Podman machine" in by_name["podman-machine-default"].detail


def test_wsl_output_in_utf16_is_decoded(monkeypatch):
    """wsl.exe writes UTF-16LE to a pipe; undecoded, every character is
    followed by a NUL byte and nothing parses."""
    raw = WSL_LIST.encode("utf-16-le")

    class Proc:
        returncode = 0
        stdout = raw
        stderr = b""
    monkeypatch.setattr(base.subprocess, "run", lambda *a, **k: Proc())
    ok, text = base.cli_text(["wsl", "--list", "--verbose"])
    assert ok and "Ubuntu-24.04" in text and "\x00" not in text


def test_libvirt_activate_rewrites_uri_default(tmp_path, monkeypatch):
    conf = tmp_path / "libvirt.conf"
    conf.write_text('# comment\nuri_default = "qemu:///session"\nx = 1\n',
                    encoding="utf-8")
    monkeypatch.setattr(platforms, "LIBVIRT_CONF", conf)
    target = base.Target("system", "qemu:///system")
    result = platforms.LibvirtProvider().activate(target).execute()
    assert result.ok
    text = conf.read_text(encoding="utf-8")
    assert 'uri_default = "qemu:///system"' in text
    assert text.count("uri_default") == 1, "must replace, not append"
    assert "# comment" in text and "x = 1" in text


@pytest.mark.parametrize("provider", providers.PROVIDERS, ids=lambda p: p.id)
def test_every_provider_is_complete(provider):
    assert provider.id and provider.name and provider.binary
    assert provider.target_noun and provider.object_noun_plural
    assert provider.summary
    target = base.Target("sample", "sample://address")
    for make in (provider.activate, provider.test):
        act = make(target)
        assert act.display().strip(), f"{provider.id}: action shows nothing"
        assert act.explanation.strip()


@pytest.mark.parametrize("provider", providers.PROVIDERS, ids=lambda p: p.id)
def test_removal_is_marked_destructive(provider):
    act = provider.remove(base.Target("sample", "sample://address"))
    assert act.destructive, f"{provider.id}: removal must ask twice"


@pytest.mark.parametrize("provider", providers.PROVIDERS, ids=lambda p: p.id)
def test_add_requires_fields(provider):
    fields = provider.add_fields()
    assert fields, f"{provider.id} offers no way to add a target"
    values = {f.key: f"v-{f.key}" for f in fields}
    act = provider.add(values)
    assert act.display().strip()


def test_install_tab_tools_exist():
    from kontainy.core import registry
    known = {t.id for t in registry.ALL_TOOLS}
    for provider in providers.PROVIDERS:
        missing = [t for t in provider.tool_ids if t not in known]
        assert not missing, f"{provider.id} lists unknown tools {missing}"
