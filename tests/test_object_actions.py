"""Actions on containers, VMs and instances, and the port-change recreate."""

import pytest

from kontainy.core.providers import base, containers, platforms
from kontainy.core.providers.base import socket_kind

INSPECT = {
    "Name": "/web",
    "Config": {"Image": "nginx:1.27", "Env": ["A=1", "B=two words"],
               "Cmd": ["nginx", "-g", "daemon off;"], "Entrypoint": None,
               "User": "", "WorkingDir": "/srv"},
    "HostConfig": {"PortBindings": {"80/tcp": [{"HostIp": "", "HostPort": "8080"}],
                                    "53/udp": [{"HostIp": "127.0.0.1", "HostPort": "5353"}]},
                   "RestartPolicy": {"Name": "unless-stopped"},
                   "NetworkMode": "appnet"},
}


def test_port_bindings_are_read():
    got = sorted(containers.port_bindings(INSPECT))
    assert ("", "8080", "80", "tcp") in got
    assert ("127.0.0.1", "5353", "53", "udp") in got


def test_recreate_command_carries_the_configuration():
    argv = containers.run_argv_from_inspect(
        "docker", ["--context", "x"], INSPECT, "web", "web-old",
        [("", "9090", "80", "tcp")])
    joined = " ".join(argv)
    assert argv[:3] == ["docker", "--context", "x"]
    assert "--volumes-from web-old" in joined, "volumes must come across"
    assert "--restart unless-stopped" in joined
    assert "--network appnet" in joined
    assert "--workdir /srv" in joined
    assert ["-e", "B=two words"] == argv[argv.index("B=two words") - 1:argv.index("B=two words") + 1]
    assert "-p 9090:80" in joined and "8080" not in joined
    assert argv[-4:] == ["nginx:1.27", "nginx", "-g", "daemon off;"]


def test_entrypoint_is_split_correctly():
    info = {"Config": {"Image": "i", "Entrypoint": ["/bin/sh", "-c"],
                       "Cmd": ["echo hi"]}, "HostConfig": {}}
    argv = containers.run_argv_from_inspect("podman", [], info, "n", "o", [])
    assert argv[argv.index("--entrypoint") + 1] == "/bin/sh"
    assert argv[-3:] == ["i", "-c", "echo hi"]


def test_default_bridge_network_is_not_forced():
    info = {"Config": {"Image": "i"}, "HostConfig": {"NetworkMode": "default"}}
    assert "--network" not in containers.run_argv_from_inspect(
        "docker", [], info, "n", "o", [])


def test_port_change_keeps_the_old_container(monkeypatch):
    import json
    monkeypatch.setattr(containers, "cli_text",
                        lambda argv, timeout=15.0: (True, json.dumps([INSPECT])))
    act = containers.recreate_with_ports(
        containers.DockerProvider(), base.Target("default", ""), "web",
        [("", "9090", "80", "tcp")])
    shown = act.display()
    assert "rm" not in shown.split(), "the old container must not be removed"
    assert "rename web web-before-ports-" in shown
    assert "--volumes-from web-before-ports-" in shown


def test_port_change_rolls_back_when_the_new_container_fails(monkeypatch):
    import json
    monkeypatch.setattr(containers, "cli_text",
                        lambda argv, timeout=15.0: (True, json.dumps([INSPECT])))
    calls = []

    class Result:
        def __init__(self, ok):
            self.ok, self.output = ok, "" if ok else "port already allocated"

    def fake_run(argv, note=""):
        calls.append(argv)
        return Result("run" not in argv)
    monkeypatch.setattr(containers, "_run", fake_run)
    act = containers.recreate_with_ports(
        containers.DockerProvider(), base.Target("default", ""), "web",
        [("", "9090", "80", "tcp")])
    result = act.execute()
    assert not result.ok
    assert "restored" in result.stderr
    renamed_back = [c for c in calls if c[-3:-1] == ["rename", c[-2]] or
                    (len(c) >= 2 and c[-1] == "web" and "rename" in c)]
    assert renamed_back, "the original must be renamed back"
    assert calls[-1][-2:] == ["start", "web"], "and started again"


def test_bulk_start_and_stop_are_split_by_state():
    rows = [{"Names": "a", "State": "running"}, {"Names": "b", "State": "exited"},
            {"Names": "c", "State": "running"}]
    acts = {a.id: a for a in containers.container_bulk(
        containers.DockerProvider(), base.Target("default", ""), rows)}
    assert acts["start-all"].command[-1:] == ["b"]
    assert acts["stop-all"].command[-2:] == ["a", "c"]
    assert acts["stop-all"].destructive


def test_single_container_actions_follow_state():
    running = [a.id for a in containers.container_actions(
        containers.DockerProvider(), None, {"Names": "a", "State": "running"})]
    stopped = [a.id for a in containers.container_actions(
        containers.DockerProvider(), None, {"Names": "a", "State": "exited"})]
    assert "stop-a" in running and "start-a" not in running
    assert "start-a" in stopped and "stop-a" not in stopped


def test_libvirt_bulk_runs_one_domain_per_command():
    rows = [{"name": "w", "state": "running"}, {"name": "f", "state": "shut off"}]
    acts = {a.id: a for a in platforms.LibvirtProvider().bulk_actions(
        base.Target("system", "qemu:///system"), rows)}
    assert "virsh -c qemu:///system start f" in acts["virsh-start-all"].display()
    assert "shutdown w" in acts["virsh-shutdown-all"].display()


def test_destroy_is_explained_as_not_deleting():
    acts = platforms.LibvirtProvider().object_actions(
        base.Target("system", "qemu:///system"), {"name": "w", "state": "running"})
    destroy = [a for a in acts if "destroy" in a.display()][0]
    assert destroy.destructive and "nothing is deleted" in destroy.explanation


@pytest.mark.parametrize("address,expected", [
    ("unix:///var/run/docker.sock", "root"),
    ("unix:///run/user/1000/podman/podman.sock", "your user"),
    ("unix:///home/u/.docker/desktop/docker.sock", "Docker Desktop"),
    ("ssh://core@127.0.0.1:52341/run/user/501/podman/podman.sock", "podman machine"),
    ("ssh://me@10.0.0.5", "remote"),
    ("qemu:///system", "root"),
    ("qemu:///session", "your user"),
])
def test_socket_kind_answers_root_or_user(address, expected):
    assert expected in socket_kind(address)


NET_LIST = (" Name      State      Autostart   Persistent\n"
            "--------------------------------------------\n"
            " default   active     yes         yes\n"
            " labnet    inactive   no          yes\n")


def test_net_list_is_parsed():
    rows = platforms.parse_net_list(NET_LIST)
    assert [r["name"] for r in rows] == ["default", "labnet"]
    assert rows[0]["autostart"] == "yes" and rows[1]["state"] == "inactive"


def test_network_xml_for_nat_and_isolated():
    nat = platforms.network_xml("lab", "virbr10", "192.168.110.1", 24,
                                "192.168.110.100", "192.168.110.200")
    assert "<forward mode='nat'/>" in nat
    assert "netmask='255.255.255.0'" in nat
    assert "<range start='192.168.110.100' end='192.168.110.200'/>" in nat
    iso = platforms.network_xml("iso", "virbr11", "10.9.0.1", 16, "", "",
                                "isolated")
    assert "<forward" not in iso and "<dhcp>" not in iso
    assert "netmask='255.255.0.0'" in iso


def test_libvirt_offers_a_networks_section():
    # On Windows the same provider also carries a Backend tab for the WSL
    # distribution it runs in, so the list is not the same everywhere. The
    # first version of this test asserted the Linux list exactly and failed
    # the Windows CI job for a correct result.
    sections = {s.id: s for s in platforms.LibvirtProvider().sections()}
    assert "networks" in sections
    net = sections["networks"]
    acts = net.row_actions(base.Target("system", "qemu:///system"),
                           {"name": "default", "state": "inactive",
                            "autostart": "no"})
    shown = [a.display() for a in acts]
    assert any("net-start default" in s for s in shown)
    assert any("net-autostart default" in s for s in shown)
    assert any("net-dhcp-leases default" in s for s in shown)
    create = net.create(base.Target("system", "qemu:///system"),
                        {"name": "lab", "bridge": "virbr10",
                         "address": "192.168.110.1", "prefix": "24",
                         "dhcp_start": "", "dhcp_end": "", "mode": "nat"})
    assert "net-define" in create.display() and "net-autostart lab" in create.display()
