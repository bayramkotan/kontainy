"""Managing a server over SSH.

The architecture already answered "where does this command run" for the
local machine and for WSL; a remote host is the third answer, and nothing
above it had to change.
"""

import shutil

import pytest

from kontainy.core import hosts
from kontainy.core.hosts import Host


def test_a_remote_command_is_wrapped_in_ssh():
    host = Host("ssh", "deploy@server")
    argv = host.wrap(["docker", "ps"])
    assert argv[0] == "ssh"
    assert argv[-3:] == ["deploy@server", "--", "ps"][-3:] or \
        argv[-2:] == ["docker", "ps"]
    assert "docker ps" in " ".join(argv)


def test_it_never_waits_for_a_password():
    """A prompt nobody can see would hang a background probe forever."""
    argv = Host("ssh", "me@host").wrap(["true"])
    joined = " ".join(argv)
    assert "BatchMode=yes" in joined
    assert "ConnectTimeout=" in joined


def test_the_connection_is_reused():
    """A page makes dozens of calls; a handshake each time is the
    difference between usable and unbearable."""
    joined = " ".join(Host("ssh", "me@host").wrap(["true"]))
    assert "ControlMaster=auto" in joined and "ControlPersist" in joined


def test_port_key_and_jump_host_are_carried():
    host = Host("ssh", "me@host", port=2222, identity="~/.ssh/id_ed25519",
                jump="bastion")
    joined = " ".join(host.wrap(["true"]))
    assert "-p 2222" in joined
    assert "-i ~/.ssh/id_ed25519" in joined
    assert "-J bastion" in joined


def test_root_becomes_sudo_without_a_prompt():
    joined = " ".join(Host("ssh", "me@host").wrap(["systemctl", "start",
                                                   "docker"], root=True))
    assert "sudo -n systemctl start docker" in joined, joined


def test_an_already_wrapped_command_is_not_wrapped_twice():
    host = Host("ssh", "me@host")
    once = host.wrap(["docker", "ps"])
    assert host.wrap(once) == once


def test_a_local_host_is_left_alone():
    assert hosts.LOCAL.wrap(["docker", "ps"]) == ["docker", "ps"]


def test_the_label_says_where_it_runs():
    assert Host("ssh", "me@host").label == "via SSH · me@host"
    assert Host("wsl", "Ubuntu-24.04").label == "via WSL · Ubuntu-24.04"
    assert hosts.LOCAL.label == ""


# --- failures, in words a person can act on ------------------------------------
@pytest.mark.parametrize("output,expected", [
    ("Permission denied (publickey).", "authorized_keys"),
    ("Host key verification failed.", "known_hosts"),
    ("ssh: Could not resolve hostname x", "does not resolve"),
    ("ssh: connect to host x port 22: Connection refused", "Nothing is listening"),
    ("ssh: connect to host x port 22: Connection timed out", "timeout"),
    ("ssh: connect to host x: No route to host", "No route"),
])
def test_ssh_failures_are_explained(output, expected):
    assert expected in hosts.ssh_reason(output)


def test_an_unknown_failure_still_says_something():
    assert hosts.ssh_reason("kex_exchange_identification: banana")


def test_no_ssh_client_is_its_own_message(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name, *a, **k: None)
    ok, why = Host("ssh", "me@host").reach()
    assert not ok and "no ssh command" in why.lower()


# --- the host list --------------------------------------------------------------
def test_hosts_come_from_the_settings(monkeypatch):
    monkeypatch.setattr(hosts, "config", lambda: {"ssh_hosts": [
        {"name": "prod", "target": "deploy@server", "port": 2222}]})
    entries = hosts.remote_hosts()
    assert entries[0]["name"] == "prod"
    host = hosts.host_from_entry(entries[0])
    assert host.is_remote and host.port == 2222


def test_a_name_resolves_to_its_host(monkeypatch):
    monkeypatch.setattr(hosts, "config", lambda: {"ssh_hosts": [
        {"name": "prod", "target": "deploy@server"}]})
    monkeypatch.setattr(hosts, "ssh_config_hosts", lambda: [])
    assert hosts.named_host("prod").distro == "deploy@server"
    assert hosts.named_host("local") is hosts.LOCAL
    assert hosts.named_host("nope") is None


def test_ssh_config_aliases_are_usable_without_adding_them(monkeypatch,
                                                            tmp_path):
    config_file = tmp_path / "config"
    config_file.write_text("Host bastion prod-eu\n  User deploy\n"
                           "Host *.internal\n  User x\n", encoding="utf-8")
    monkeypatch.setattr("os.path.expanduser", lambda p: str(config_file))
    found = hosts.ssh_config_hosts()
    assert "bastion" in found and "prod-eu" in found
    assert not any("*" in name for name in found), "a pattern is not a host"


def test_the_active_host_defaults_to_this_machine(monkeypatch):
    monkeypatch.setattr(hosts, "config", lambda: {})
    assert hosts.active_host() is hosts.LOCAL


def test_choosing_a_server_moves_every_provider_there(monkeypatch):
    """The point of the whole feature: one setting, and the pages follow."""
    monkeypatch.setattr(hosts, "config", lambda: {
        "active_host": "prod",
        "ssh_hosts": [{"name": "prod", "target": "deploy@server"}]})
    from kontainy.core.providers import by_id
    docker = by_id("docker")
    host = docker.host()
    assert host is not None and host.is_remote
    assert " ".join(host.wrap(["docker", "ps"])).startswith("ssh ")


def test_a_windows_only_technology_is_not_offered_on_a_linux_server(
        monkeypatch):
    monkeypatch.setattr(hosts, "config", lambda: {
        "active_host": "prod",
        "ssh_hosts": [{"name": "prod", "target": "deploy@server"}]})
    from kontainy.core.providers import by_id
    assert by_id("hyperv").host() is None
