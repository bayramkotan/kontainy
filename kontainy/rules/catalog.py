"""
kontainy — rule set

Every rule matches a symptom that actually occurs. No invented checks: each
corresponds to a failure this ecosystem really produces, and most of those
failures emit no error message at all, which is exactly why detecting them
is worth the effort.

Rule id prefixes:
    CTX   context and terminal target
    PERM  permissions
    POD   Podman and rootless
    NET   networking
    DSK   disk
    RES   resource limits
    SVC   services and systemd
    DKR   Docker Desktop and virtualisation
"""

from __future__ import annotations

import shutil
from pathlib import Path

from ..utils import fs
from .engine import ERROR, INFO, WARN, Rule

# ---------------------------------------------------------------------------
#  CTX — context and terminal target
# ---------------------------------------------------------------------------


def _ctx01(env):
    if env.docker_host and env.current_context:
        return {"host": env.docker_host, "context": env.current_context}
    return None


def _ctx02(env):
    docker_eps = [e for e in env.endpoints if e.reachable and e.family == "docker"]
    if len(docker_eps) < 2:
        return None
    versions = {e.info.version for e in docker_eps if e.info}
    if len(versions) < 2:
        return None
    return {"count": len(docker_eps), "versions": ", ".join(sorted(versions))}


def _ctx03(env):
    store = env.docker_cli_config.get("credsStore", "")
    if not store:
        return None
    if shutil.which(f"docker-credential-{store}"):
        return None
    return {"store": store}


def _ctx04(env):
    user = set(env.cli_plugin_dirs.get("user", []))
    system = set(env.cli_plugin_dirs.get("system", [])) | \
        set(env.cli_plugin_dirs.get("libexec", []))
    shadowed = sorted(user & system)
    if not shadowed:
        return None
    return {"plugins": ", ".join(shadowed)}


def _ctx05(env):
    if env.docker_real_path and "podman" in env.docker_real_path:
        return {"link": env.docker_binary, "target": env.docker_real_path}
    return None


def _ctx06(env):
    """Is the target the terminal resolves to actually reachable?"""
    target = getattr(env.cli_target, "winner", "")
    if not target:
        return None
    wanted = target.replace("unix://", "")
    for ep in env.endpoints:
        if ep.address.replace("unix://", "") == wanted:
            return None if ep.reachable else {"target": target, "error": ep.error}
    return {"target": target, "error": "not found at all"}


# ---------------------------------------------------------------------------
#  PERM — permissions
# ---------------------------------------------------------------------------
def _perm01(env):
    unreachable = [e for e in env.endpoints
                   if not e.reachable and "denied" in (e.error or "").lower()]
    if not unreachable:
        return None
    if "docker" in env.user_groups:
        return {"sockets": ", ".join(e.address for e in unreachable),
                "note": "The user appears to be in the `docker` group, so the "
                        "membership may not have reached this session yet."}
    return {"sockets": ", ".join(e.address for e in unreachable),
            "note": "The user is not in the `docker` group."}


# ---------------------------------------------------------------------------
#  POD — Podman and rootless
# ---------------------------------------------------------------------------
def _pod01(env):
    if not env.podman_binary:
        return None
    has_socket = any("podman" in e.address for e in env.endpoints if e.reachable)
    if has_socket:
        return None
    state = env.units.get(("podman.socket", "user"), "bilinmiyor")
    return {"state": state}


def _pod02(env):
    if not env.podman_binary or not env.username:
        return None
    if env.linger:
        return None
    return {"user": env.username}


def _pod03(env):
    if not env.podman_binary or not env.username:
        return None
    if env.subuid_ok and env.subgid_ok:
        return None
    missing = []
    if not env.subuid_ok:
        missing.append("/etc/subuid")
    if not env.subgid_ok:
        missing.append("/etc/subgid")
    return {"user": env.username, "files": " ve ".join(missing)}


def _pod04(env):
    """Rootless Podman is present but the auto-update timer is off."""
    if not env.podman_binary:
        return None
    state = env.units.get(("podman-auto-update.timer", "user"), "")
    if state == "active":
        return None
    return {"state": state or "not found"}


# ---------------------------------------------------------------------------
#  NET — networking
# ---------------------------------------------------------------------------
def _docker_pools(env) -> list:
    pools = []
    for entry in env.daemon_json.get("default-address-pools") or []:
        base = entry.get("base") if isinstance(entry, dict) else None
        if base:
            pools.append(base)
    if not pools:
        pools = ["172.17.0.0/16", "172.18.0.0/16"]
    bip = env.daemon_json.get("bip")
    if bip:
        pools.append(bip)
    return pools


def _prefix16(cidr: str) -> str:
    return ".".join(cidr.split("/")[0].split(".")[:2])


def _net01(env):
    if not env.host_routes:
        return None
    docker_prefixes = {_prefix16(p) for p in _docker_pools(env)}
    clashes = []
    for route in env.host_routes:
        if "docker" in route or "podman" in route or "cni" in route:
            continue
        dest = route.split()[0]
        if "/" not in dest:
            continue
        if _prefix16(dest) in docker_prefixes:
            clashes.append(route)
    if not clashes:
        return None
    return {"routes": "; ".join(clashes[:3])}


def _net02(env):
    if env.unprivileged_port_start <= 80:
        return None
    if not env.podman_binary:
        return None
    return {"value": env.unprivileged_port_start}


def _net03(env):
    """nftables without the iptables-nft bridge, common on Arch."""
    if not shutil.which("nft"):
        return None
    if shutil.which("iptables"):
        return None
    if not any(e.reachable for e in env.endpoints):
        return None
    return {}


# ---------------------------------------------------------------------------
#  DSK — disk
# ---------------------------------------------------------------------------
def _dsk01(env):
    driver = env.daemon_json.get("log-driver", "json-file")
    opts = env.daemon_json.get("log-opts") or {}
    if driver != "json-file":
        return None
    if opts.get("max-size"):
        return None
    if not any(e.reachable and e.family == "docker" for e in env.endpoints):
        return None
    return {"path": env.daemon_json_path}


def _dsk02(env):
    gc = (env.daemon_json.get("builder") or {}).get("gc") or {}
    if not any(e.reachable and e.family == "docker" for e in env.endpoints):
        return None
    if gc.get("defaultKeepStorage") or gc.get("enabled") is False:
        return None
    return {}


# ---------------------------------------------------------------------------
#  RES — resource limits
# ---------------------------------------------------------------------------
def _res01(env):
    """cgroup v2 plus rootless plus cgroupfs: limits are silently ignored."""
    if not fs.exists("/sys/fs/cgroup/cgroup.controllers"):
        return None
    rootless = [e for e in env.endpoints
                if e.reachable and e.info and e.info.rootless]
    if not rootless:
        return None
    user_conf = Path.home() / ".config/containers/containers.conf"
    text = fs.read_text(user_conf)
    if "cgroupfs" not in text:
        return None
    return {"path": str(user_conf)}


# ---------------------------------------------------------------------------
#  SVC — services and systemd
# ---------------------------------------------------------------------------
def _svc01(env):
    sock = env.units.get(("docker.socket", "system"), "")
    svc = env.units.get(("docker.service", "system"), "")
    if sock == "active" and svc == "active":
        return {}
    return None


# ---------------------------------------------------------------------------
#  DKR — Docker Desktop and virtualisation
# ---------------------------------------------------------------------------
def _dkr01(env):
    desktop = [e for e in env.endpoints if "desktop" in e.address]
    if not desktop:
        return None
    if env.kvm_present and env.kvm_readable:
        return None
    if not env.kvm_present:
        return {"reason": "/dev/kvm is missing \u2014 virtualisation may be "
                          "disabled in the BIOS"}
    return {"reason": "/dev/kvm exists but is not readable \u2014 the user "
                      "is not in the `kvm` group"}


# ---------------------------------------------------------------------------
#  Rule table
# ---------------------------------------------------------------------------
RULES = [
    Rule(
        id="CTX01", severity=ERROR,
        title="DOCKER_HOST is overriding your context",
        detect=_ctx01,
        explain=(
            "The `DOCKER_HOST` environment variable is set to `{host}`. "
            "While it is set, the context in `~/.docker/config.json` "
            "(`{context}`) is ignored COMPLETELY.\n\n"
            "The consequence: `docker context use` reports success and "
            "changes nothing. This is the number one cause of the "
            "complaint that containers have disappeared.\n\n"
            "To find where the variable comes from, check your shell "
            "startup files: ~/.bashrc, ~/.zshrc, ~/.profile, "
            "~/.config/environment.d/*.conf"),
        fix_command="unset DOCKER_HOST",
        fix_scope="user",
        setting_key="currentContext",
        learn_topic="troubleshooting/context-chain",
        tags=["context", "critical"],
    ),
    Rule(
        id="CTX02", severity=INFO,
        title="More than one Docker engine is running",
        detect=_ctx02,
        explain=(
            "{count} separate Docker engines are reachable and their "
            "versions differ: {versions}.\n\n"
            "This is not an error, but the CLI only ever looks at one of "
            "them. If a container is missing from your terminal it is "
            "probably on the other engine. kontainy shows them all on the "
            "Containers page, with an Engine column."),
        fix_scope="none",
        learn_topic="troubleshooting/multiple-engines",
        tags=["context"],
    ),
    Rule(
        id="CTX03", severity=ERROR,
        title="Credential helper missing: docker-credential-{store}",
        detect=_ctx03,
        explain=(
            "`~/.docker/config.json` declares `credsStore: {store}`, but "
            "`docker-credential-{store}` is not on PATH.\n\n"
            "This usually happens after Docker Desktop is removed: the "
            "setting is left behind and every `docker` command fails with "
            "`docker-credential-{store} not found in $PATH`.\n\n"
            "The fix is to remove the key. Stored registry passwords then "
            "fall back to plain text in `~/.docker/config.json`, so you may "
            "need to run `docker login` again."),
        fix_command=(
            "python -c \"import json,pathlib;"
            "p=pathlib.Path.home()/'.docker/config.json';"
            "d=json.loads(p.read_text());d.pop('credsStore',None);"
            "p.write_text(json.dumps(d,indent=2))\""),
        fix_scope="user",
        setting_key="credsStore",
        learn_topic="migration/desktop-leftovers",
        tags=["desktop", "critical"],
    ),
    Rule(
        id="CTX04", severity=WARN,
        title="CLI plugins are being shadowed",
        detect=_ctx04,
        explain=(
            "These plugins exist in both `~/.docker/cli-plugins` and a "
            "system directory: {plugins}.\n\n"
            "The user directory takes precedence, so the distribution's "
            "version is shadowed. `docker compose version` and "
            "`docker-compose version` can report different versions, and "
            "which one actually runs becomes unclear.\n\n"
            "A Docker Desktop install fills this directory with its own "
            "plugins."),
        fix_command="ls -l ~/.docker/cli-plugins /usr/lib/docker/cli-plugins",
        fix_scope="user",
        setting_key="cliPluginsExtraDirs",
        learn_topic="migration/desktop-leftovers",
        tags=["desktop", "compose"],
    ),
    Rule(
        id="CTX05", severity=INFO,
        title="The `docker` command actually goes to Podman",
        detect=_ctx05,
        explain=(
            "`{link}` points to `{target}`. The `podman-docker` package is "
            "installed and `docker` is Podman's compatibility wrapper.\n\n"
            "This is not an error, but it burns hours when you do not know "
            "about it: `docker run` works, `docker ps` comes back empty "
            "because it looks at Podman's own store, and a few "
            "Docker-specific flags behave differently without saying so."),
        fix_scope="none",
        learn_topic="migration/podman-docker-shim",
        tags=["podman", "compatibility"],
    ),
    Rule(
        id="CTX06", severity=ERROR,
        title="The target your terminal points at is unreachable",
        detect=_ctx06,
        explain=(
            "The `docker` command goes to `{target}`, but that address "
            "cannot be reached: {error}\n\n"
            "Every `docker` command you run in a terminal will fail with "
            "this. kontainy carries on showing the other engines."),
        fix_command="docker context ls",
        fix_scope="user",
        learn_topic="troubleshooting/context-chain",
        tags=["context", "critical"],
    ),

    Rule(
        id="PERM01", severity=ERROR,
        title="Permission denied on a socket",
        detect=_perm01,
        explain=(
            "Could not connect to these sockets because of a permission "
            "error: {sockets}\n\n{note}\n\n"
            "After being added to the group you must log out and back in. "
            "`newgrp docker` affects only that one shell and does not reach "
            "GUI applications."),
        fix_command="sudo usermod -aG docker $USER   # then log out and back in",
        fix_scope="root",
        learn_topic="troubleshooting/permissions",
        tags=["permissions", "critical"],
    ),

    Rule(
        id="POD01", severity=WARN,
        title="Podman is installed but its socket is not running",
        detect=_pod01,
        explain=(
            "`podman` is installed but no API socket was found "
            "(`podman.socket` --user state: {state}).\n\n"
            "Without the socket kontainy cannot list Podman containers over "
            "the API. systemd starts the socket on demand; enabling it "
            "makes that persist across reboots."),
        fix_command="systemctl --user enable --now podman.socket",
        fix_scope="user",
        learn_topic="systemd/socket-activation",
        tags=["podman", "systemd"],
    ),
    Rule(
        id="POD02", severity=WARN,
        title="Linger is off, so rootless containers die at logout",
        detect=_pod02,
        explain=(
            "Linger is disabled for `{user}`. User systemd units run only "
            "while a session is open, so when you log out or an SSH "
            "connection drops, rootless containers stop \u2014 and they do "
            "not come back after a reboot.\n\n"
            "This is required for Quadlet units and for `--restart=always` "
            "to mean anything. It is the most commonly skipped step in a "
            "rootless setup."),
        fix_command="loginctl enable-linger $USER",
        fix_scope="user",
        setting_key="Install.WantedBy",
        learn_topic="systemd/linger",
        tags=["podman", "rootless", "systemd", "critical"],
    ),
    Rule(
        id="POD03", severity=ERROR,
        title="No subuid/subgid range, so rootless Podman cannot work",
        detect=_pod03,
        explain=(
            "No entry for `{user}` was found in {files}.\n\n"
            "Rootless Podman maps users inside the container onto a range "
            "of UIDs on the host. Without that range no image can be pulled "
            "and no container can start. The typical symptom is "
            "`potentially insufficient UIDs or GIDs available in user "
            "namespace`.\n\n"
            "After adding the entry you must run `podman system migrate`, "
            "or existing containers keep the old mapping."),
        fix_command=(
            "sudo usermod --add-subuids 100000-165535 "
            "--add-subgids 100000-165535 $USER && podman system migrate"),
        fix_scope="root",
        learn_topic="podman/rootless-subuid",
        tags=["podman", "rootless", "critical"],
    ),
    Rule(
        id="POD04", severity=INFO,
        title="Auto-update timer is inactive",
        detect=_pod04,
        explain=(
            "`podman-auto-update.timer` state: {state}.\n\n"
            "Labelling a container `AutoUpdate=registry` is not enough on "
            "its own; this timer is what performs the update. While it is "
            "off the label silently does nothing."),
        fix_command="systemctl --user enable --now podman-auto-update.timer",
        fix_scope="user",
        setting_key="Container.AutoUpdate",
        learn_topic="systemd/auto-update",
        tags=["podman", "systemd"],
    ),

    Rule(
        id="NET01", severity=ERROR,
        title="Docker's address pool clashes with your local network",
        detect=_net01,
        explain=(
            "A local route shares the same /16 prefix as the IP block "
            "Docker uses: {routes}\n\n"
            "This is the classic reason a corporate network or VPN becomes "
            "unreachable the moment Docker is installed. The fix is to move "
            "Docker to an unused block, for example 10.200.0.0/16.\n\n"
            "Note that `default-address-pools` only affects NEW networks; "
            "the `docker0` bridge itself needs the `bip` key."),
        fix_command="sudo $EDITOR /etc/docker/daemon.json   # default-address-pools",
        fix_scope="root",
        setting_key="default-address-pools",
        learn_topic="network/subnet-clash",
        tags=["network", "vpn", "critical"],
    ),
    Rule(
        id="NET02", severity=INFO,
        title="Rootless containers cannot bind ports below 1024",
        detect=_net02,
        explain=(
            "`net.ipv4.ip_unprivileged_port_start` is {value}. Rootless "
            "containers cannot bind host ports below that value, which "
            "includes 80 and 443.\n\n"
            "To run a web server rootless, either publish on a high port "
            "such as 8080 or lower this sysctl. Making it permanent needs a "
            "file under /etc/sysctl.d/."),
        fix_command="sudo sysctl net.ipv4.ip_unprivileged_port_start=80",
        fix_scope="root",
        setting_key="Container.PublishPort",
        learn_topic="network/rootless-ports",
        tags=["podman", "rootless", "network"],
    ),
    Rule(
        id="NET03", severity=WARN,
        title="nftables is present with no iptables compatibility layer",
        detect=_net03,
        explain=(
            "`nft` exists on this system but the `iptables` command was not "
            "found. Docker and netavark write port-publishing rules through "
            "the iptables interface; without that layer, publishing a port "
            "silently does nothing \u2014 the container starts and the port "
            "is unreachable.\n\n"
            "On Arch and CachyOS the `iptables-nft` package provides the "
            "bridge."),
        fix_command="sudo pacman -S iptables-nft",
        fix_scope="root",
        setting_key="network.firewall_driver",
        learn_topic="network/firewall-backends",
        tags=["network", "arch", "firewall"],
    ),

    Rule(
        id="DSK01", severity=WARN,
        title="Docker logs are growing without limit",
        detect=_dsk01,
        explain=(
            "No log rotation is configured in `{path}`. The `json-file` "
            "driver is UNLIMITED by default: a long-running container's log "
            "file grows into gigabytes and fills the root disk.\n\n"
            "This is the number one cause of Docker-related disk "
            "exhaustion. A reasonable starting point is `max-size: 10m` "
            "with `max-file: 3`."),
        fix_command="sudo $EDITOR /etc/docker/daemon.json   # log-opts.max-size",
        fix_scope="root",
        setting_key="log-opts.max-size",
        learn_topic="storage/log-rotation",
        tags=["disk", "logging", "critical"],
    ),
    Rule(
        id="DSK02", severity=INFO,
        title="BuildKit cache is unbounded",
        detect=_dsk02,
        explain=(
            "`builder.gc` is not configured. On machines that build often, "
            "the build cache can take more space than the images "
            "themselves.\n\n"
            "`docker image prune` does NOT remove it \u2014 it is a "
            "separate line in `docker system df` and needs "
            "`docker builder prune`."),
        fix_command="docker system df && docker builder prune",
        fix_scope="user",
        setting_key="builder.gc.defaultKeepStorage",
        learn_topic="performance/build-cache",
        tags=["disk", "buildkit"],
    ),

    Rule(
        id="RES01", severity=WARN,
        title="cgroupfs is selected, so resource limits may be ignored",
        detect=_res01,
        explain=(
            "`cgroupfs` appears in `{path}` and this system uses cgroup "
            "v2.\n\n"
            "On rootless cgroup v2, limits such as `--memory`, `--cpus` and "
            "`--pids-limit` require `cgroup_manager = systemd`. With "
            "cgroupfs they are ignored without an error \u2014 you believe "
            "a limit is in place while the container uses the whole "
            "machine."),
        fix_command="podman info --format '{{.Host.CgroupManager}}'",
        fix_scope="user",
        setting_key="containers.cgroup_manager",
        learn_topic="troubleshooting/silent-limits",
        tags=["cgroup", "rootless", "critical"],
    ),

    Rule(
        id="SVC01", severity=INFO,
        title="docker.socket is active, so stopping the service is not enough",
        detect=_svc01,
        explain=(
            "Both `docker.service` and `docker.socket` are enabled. With "
            "socket activation on, the first `docker` command after "
            "`systemctl stop docker.service` starts the daemon again.\n\n"
            "To actually stop the daemon, both have to be stopped."),
        fix_command="sudo systemctl stop docker.socket docker.service",
        fix_scope="root",
        learn_topic="systemd/socket-activation",
        tags=["systemd", "docker"],
    ),

    Rule(
        id="DKR01", severity=ERROR,
        title="Virtualisation is not ready for Docker Desktop",
        detect=_dkr01,
        explain=(
            "A Docker Desktop socket was found, but {reason}.\n\n"
            "Docker Desktop for Linux runs inside a virtual machine and "
            "will not start at all if it cannot reach KVM."),
        fix_command="sudo usermod -aG kvm $USER   # then log out and back in",
        fix_scope="root",
        learn_topic="kvm/basics",
        tags=["desktop", "kvm"],
    ),
]


def rule_by_id(rule_id: str):
    for rule in RULES:
        if rule.id == rule_id:
            return rule
    return None


def rule_stats() -> dict:
    from .engine import ERROR as E, INFO as I, WARN as W
    return {
        "total": len(RULES),
        "error": len([r for r in RULES if r.severity == E]),
        "warning": len([r for r in RULES if r.severity == W]),
        "info": len([r for r in RULES if r.severity == I]),
    }
