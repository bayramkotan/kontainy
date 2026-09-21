"""kontainy — Docker contexts and Podman system connections."""

from __future__ import annotations

import os

from .base import (Field, Listing, Column, Provider, Target, action, cli_text,
                   json_lines, json_value)


class DockerProvider(Provider):
    id = "docker"
    name = "Docker"
    icon = "\U0001f433"
    binary = "docker"
    target_noun = "Context"
    target_noun_plural = "Contexts"
    object_noun_plural = "Containers"
    tool_ids = ["docker", "docker-desktop", "containerd"]
    catalog_engine = "docker"
    learn_category = "docker"
    summary = ("A context names one Docker endpoint — the local daemon, "
               "Docker Desktop's VM, a remote host over SSH. The active one "
               "is where every docker command goes.")
    services = [
        ("docker.service", False, "The Docker daemon itself."),
        ("docker.socket", False,
         "Socket activation. While active, stopping docker.service is not "
         "enough \u2014 the next docker command starts it again."),
        ("containerd.service", False, "The runtime Docker sits on."),
    ]

    def resolution(self):
        from ..discovery import resolve_cli_target
        return resolve_cli_target().as_rows()

    def targets(self) -> list:
        ok, text = cli_text(["docker", "context", "ls", "--format", "{{json .}}"])
        if not ok:
            return []
        out = []
        for row in json_lines(text):
            name = row.get("Name", "")
            out.append(Target(
                name=name,
                address=row.get("DockerEndpoint", ""),
                active=bool(row.get("Current")),
                detail=row.get("Description", ""),
                removable=name != "default"))
        return out

    def warning(self) -> str:
        host = os.environ.get("DOCKER_HOST", "")
        if host:
            return (f"DOCKER_HOST is set ({host}). While it is, the selected "
                    f"context is ignored by every docker command — switching "
                    f"here reports success and changes nothing.")
        return ""

    def activate(self, target):
        return action(
            f"docker-context-use-{target.name}",
            f"Make '{target.name}' the active context",
            ["docker", "context", "use", target.name],
            f"Writes currentContext: {target.name} into ~/.docker/config.json. "
            f"New shells send docker commands to {target.address or 'it'}."
            + (f"\n\n\u26a0 {self.warning()}" if self.warning() else ""))

    def add_fields(self):
        return [
            Field("name", "Name", "remote-build"),
            Field("host", "Docker host", "ssh://user@server  or  unix:///path/docker.sock",
                  "ssh://, tcp://, unix:// or npipe:// (Windows)."),
            Field("description", "Description", "", required=False),
        ]

    def add(self, values):
        argv = ["docker", "context", "create", values["name"],
                "--docker", f"host={values['host']}"]
        if values.get("description"):
            argv += ["--description", values["description"]]
        return action(
            f"docker-context-create-{values['name']}",
            f"Create context '{values['name']}'", argv,
            "Adds a context. It does not become active until you select it.")

    def remove(self, target):
        return action(
            f"docker-context-rm-{target.name}",
            f"Remove context '{target.name}'",
            ["docker", "context", "rm", target.name],
            "Deletes only the context entry. The engine it pointed at, and "
            "everything on it, is untouched.",
            destructive=True)

    def test(self, target):
        return action(
            f"docker-context-test-{target.name}",
            f"Test '{target.name}'",
            ["docker", "--context", target.name, "version"],
            "Asks the engine behind this context for its version. An answer "
            "means the endpoint is reachable and speaking the Docker API.")

    def objects(self, target):
        argv = ["docker"]
        if target:
            argv += ["--context", target.name]
        argv += ["ps", "-a", "--format", "{{json .}}"]
        ok, text = cli_text(argv)
        listing = Listing(
            columns=[Column("Names", "Name"), Column("Image", "Image"),
                     Column("State", "State"), Column("Status", "Status"),
                     Column("Ports", "Ports")],
            command=" ".join(argv))
        if not ok:
            listing.error = text
            return listing
        listing.rows = json_lines(text)
        return listing

    def terminal_env(self, target):
        return {"DOCKER_CONTEXT": target.name} if target else {}


class PodmanProvider(Provider):
    id = "podman"
    name = "Podman"
    icon = "\U0001f9ad"
    binary = "podman"
    target_noun = "Connection"
    target_noun_plural = "Connections"
    object_noun_plural = "Containers"
    tool_ids = ["podman", "podman-desktop", "buildah", "skopeo"]
    catalog_engine = "podman"
    learn_category = "podman"
    summary = ("A system connection names one Podman service — rootless on "
               "this machine, rootful, a podman machine VM, or a remote host "
               "over SSH. With none defined, podman runs locally.")
    needs_linger = True
    services = [
        ("podman.socket", True,
         "The rootless API socket. kontainy and podman-remote talk to it."),
        ("podman.socket", False, "The rootful API socket."),
        ("podman-auto-update.timer", True,
         "Performs updates for containers labelled AutoUpdate=registry."),
        ("podman-restart.service", True,
         "Restarts --restart=always containers after a reboot; rootless "
         "Podman has no daemon to do it."),
    ]

    def targets(self) -> list:
        ok, text = cli_text(["podman", "system", "connection", "list",
                             "--format", "json"])
        rows = json_value(text, []) if ok else []
        out = []
        for row in rows or []:
            out.append(Target(
                name=row.get("Name", ""),
                address=row.get("URI", ""),
                active=bool(row.get("Default")),
                detail=row.get("Identity", "")))
        if not any(t.active for t in out):
            # No default connection means podman talks to the local engine
            # directly. Show that honestly rather than an empty dropdown.
            out.insert(0, Target(name="(local)", address="this machine",
                                 active=True, removable=False,
                                 detail="no connection selected — podman "
                                        "runs against the local engine"))
        return out

    def activate(self, target):
        if target.name == "(local)":
            return action("podman-local", "Use the local engine", [],
                          "There is nothing to switch to: with no default "
                          "connection podman already runs locally.",
                          scope="none")
        return action(
            f"podman-connection-default-{target.name}",
            f"Make '{target.name}' the default connection",
            ["podman", "system", "connection", "default", target.name],
            f"Every podman command now goes to {target.address}.")

    def add_fields(self):
        return [
            Field("name", "Name", "build-server"),
            Field("uri", "URI",
                  "ssh://user@host/run/user/1000/podman/podman.sock",
                  "ssh://… for a remote host, unix://… for a local socket."),
            Field("identity", "SSH key", "~/.ssh/id_ed25519", required=False),
        ]

    def add(self, values):
        argv = ["podman", "system", "connection", "add"]
        if values.get("identity"):
            argv += ["--identity", os.path.expanduser(values["identity"])]
        argv += [values["name"], values["uri"]]
        return action(f"podman-connection-add-{values['name']}",
                      f"Add connection '{values['name']}'", argv,
                      "Adds a connection. It does not become the default "
                      "until you select it.")

    def remove(self, target):
        return action(
            f"podman-connection-remove-{target.name}",
            f"Remove connection '{target.name}'",
            ["podman", "system", "connection", "remove", target.name],
            "Deletes only the connection entry, not the engine behind it.",
            destructive=True)

    def test(self, target):
        argv = ["podman"]
        if target and target.name != "(local)":
            argv += ["--connection", target.name]
        argv += ["info", "--format", "{{.Host.Hostname}} {{.Version.Version}}"]
        return action(f"podman-test-{target.name}", f"Test '{target.name}'",
                      argv, "Asks the service for its hostname and version.")

    def objects(self, target):
        argv = ["podman"]
        if target and target.name != "(local)":
            argv += ["--connection", target.name]
        argv += ["ps", "-a", "--format", "json"]
        ok, text = cli_text(argv)
        listing = Listing(
            columns=[Column("Names", "Name"), Column("Image", "Image"),
                     Column("State", "State"), Column("Status", "Status"),
                     Column("Pod", "Pod")],
            command=" ".join(argv))
        if not ok:
            listing.error = text
            return listing
        rows = []
        for row in json_value(text, []) or []:
            names = row.get("Names") or []
            rows.append({
                "Names": ", ".join(names) if isinstance(names, list) else names,
                "Image": row.get("Image", ""),
                "State": row.get("State", ""),
                "Status": row.get("Status", ""),
                "Pod": row.get("PodName", ""),
            })
        listing.rows = rows
        return listing

    def terminal_env(self, target):
        if target and target.name != "(local)":
            return {"CONTAINER_CONNECTION": target.name}
        return {}


# ===========================================================================
#  Object actions, bulk actions and port editing — shared by Docker and Podman
# ===========================================================================
import time as _time

from ..actions import Action, USER
from ..elevate import run as _run


def _conn_args(provider, target) -> list:
    if provider.id == "docker" and target:
        return ["--context", target.name]
    if provider.id == "podman" and target and target.name != "(local)":
        return ["--connection", target.name]
    return []


def _is_running(row: dict) -> bool:
    return str(row.get("State", "")).lower() in ("running", "restarting")


def container_actions(provider, target, row: dict) -> list:
    base = [provider.binary] + _conn_args(provider, target)
    name = row.get("Names", "")
    out = []
    if _is_running(row):
        out.append(Action(f"stop-{name}", "\u25a0  Stop", base + ["stop", name],
                          USER, f"Sends SIGTERM to {name}, then SIGKILL after "
                          f"the stop timeout if it has not exited."))
        out.append(Action(f"restart-{name}", "\u21bb  Restart",
                          base + ["restart", name], USER,
                          f"Stops and starts {name} again."))
    else:
        out.append(Action(f"start-{name}", "\u25b6  Start",
                          base + ["start", name], USER,
                          f"Starts the stopped container {name}."))
    out.append(Action(f"logs-{name}", "\U0001f4dc  Logs",
                      base + ["logs", "--tail", "200", name], USER,
                      "The last 200 lines of the container's output."))
    out.append(Action(f"rm-{name}", "\U0001f5d1  Remove",
                      base + ["rm", "-f", name], USER,
                      f"Removes {name}. Named volumes survive; anything "
                      f"written only inside the container is lost.",
                      destructive=True))
    return out


def container_bulk(provider, target, rows: list) -> list:
    base = [provider.binary] + _conn_args(provider, target)
    stopped = [r["Names"] for r in rows if not _is_running(r) and r.get("Names")]
    running = [r["Names"] for r in rows if _is_running(r) and r.get("Names")]
    out = []
    if stopped:
        out.append(Action("start-all", f"\u25b6  Start all ({len(stopped)})",
                          base + ["start"] + stopped, USER,
                          "Starts every stopped container on this target, "
                          "in one command."))
    if running:
        out.append(Action("stop-all", f"\u25a0  Stop all ({len(running)})",
                          base + ["stop"] + running, USER,
                          "Stops every running container on this target, "
                          "in one command.", destructive=True))
    return out


def port_bindings(inspect: dict) -> list:
    """[(host_ip, host_port, container_port, protocol)] from inspect output."""
    out = []
    bindings = ((inspect.get("HostConfig") or {}).get("PortBindings") or {})
    for key, hosts in bindings.items():
        port, _, proto = key.partition("/")
        for host in hosts or [{}]:
            out.append((host.get("HostIp", "") or "", host.get("HostPort", "") or "",
                        port, proto or "tcp"))
    return out


def run_argv_from_inspect(binary: str, conn: list, inspect: dict, name: str,
                          old_name: str, bindings: list) -> list:
    """Rebuild a run command for a container, with new port bindings.

    Carries the image, command, entrypoint, environment, user, working
    directory, restart policy and network. Every mount — named volumes,
    anonymous volumes and bind mounts — comes across with --volumes-from,
    which is why the old container is kept rather than removed: it is the
    source of those mounts.

    Not carried: labels, healthcheck, capabilities, resource limits and
    devices. The explanation in the dialog says so.
    """
    config = inspect.get("Config") or {}
    host = inspect.get("HostConfig") or {}
    argv = [binary] + conn + ["run", "-d", "--name", name,
                              "--volumes-from", old_name]

    restart = (host.get("RestartPolicy") or {}).get("Name") or ""
    if restart and restart != "no":
        argv += ["--restart", restart]
    network = host.get("NetworkMode") or ""
    if network and network not in ("default", "bridge"):
        argv += ["--network", network]
    if config.get("User"):
        argv += ["--user", config["User"]]
    if config.get("WorkingDir"):
        argv += ["--workdir", config["WorkingDir"]]
    for env in config.get("Env") or []:
        argv += ["-e", env]
    for host_ip, host_port, container_port, proto in bindings:
        spec = f"{container_port}/{proto}" if proto and proto != "tcp" else container_port
        if host_port:
            spec = f"{host_port}:{spec}"
            if host_ip:
                spec = f"{host_ip}:{spec}"
        argv += ["-p", spec]

    entrypoint = config.get("Entrypoint") or []
    cmd = list(config.get("Cmd") or [])
    if entrypoint:
        argv += ["--entrypoint", entrypoint[0]]
        cmd = list(entrypoint[1:]) + cmd
    argv.append(config.get("Image") or inspect.get("Image", ""))
    argv += cmd
    return argv


def recreate_with_ports(provider, target, name: str, bindings: list) -> Action:
    conn = _conn_args(provider, target)
    base = [provider.binary] + conn
    old_name = f"{name}-before-ports-{_time.strftime('%Y%m%d%H%M%S')}"

    ok, text = cli_text(base + ["inspect", name])
    info = (json_value(text, []) or [{}])[0] if ok else {}
    network = (info.get("HostConfig") or {}).get("NetworkMode", "")
    run_argv = run_argv_from_inspect(provider.binary, conn, info, name,
                                     old_name, bindings)
    steps = [base + ["stop", name], base + ["rename", name, old_name], run_argv]

    def execute():
        if not ok:
            raise RuntimeError(f"could not inspect {name}: {text}")
        if network == "host":
            raise RuntimeError(f"{name} uses host networking, where port "
                               f"mappings do not apply.")
        for step in steps[:2]:
            result = _run(step, note=f"ports-{name}")
            if not result.ok:
                raise RuntimeError(result.output)
        result = _run(steps[2], note=f"ports-{name}")
        if not result.ok:
            # Roll back: put the original container back exactly as it was.
            _run(base + ["rename", old_name, name], note="ports-rollback")
            _run(base + ["start", name], note="ports-rollback")
            raise RuntimeError("the new container did not start, so the "
                               "original was restored:\n" + result.output)
        return (f"{name} now runs with the new ports.\nThe previous container "
                f"is kept, stopped, as {old_name} — remove it once you are "
                f"satisfied:  {provider.binary} rm {old_name}")

    return Action(
        id=f"ports-{name}", label=f"Change the ports of {name}",
        command=[], scope=USER,
        shell_text="\n".join(" ".join(s) for s in steps),
        explanation=(
            "Neither Docker nor Podman can change the ports of an existing "
            "container; port mappings are fixed when it is created. The only "
            "honest way is to recreate it, and this does so without losing "
            f"anything:\n\n"
            f"1. {name} is stopped.\n"
            f"2. It is renamed to {old_name} and kept.\n"
            f"3. A new {name} is started from the same image with the same "
            f"command, environment, user, working directory, restart policy "
            f"and network, taking every volume and bind mount from the old "
            f"one with --volumes-from.\n\n"
            "If the new container does not start, the original is renamed "
            "back and restarted automatically.\n\n"
            "Not carried across: labels, healthcheck, capabilities, resource "
            "limits and devices. Compose-managed containers should have "
            "their ports changed in the compose file instead."),
        func=execute)


def _attach(cls):
    cls.object_key = "Names"
    cls.object_actions = lambda self, target, row: container_actions(self, target, row)
    cls.bulk_actions = lambda self, target, rows: container_bulk(self, target, rows)
    cls.can_edit_ports = lambda self: True

    def inspect_ports(self, target, name):
        ok, text = cli_text([self.binary] + _conn_args(self, target) + ["inspect", name])
        info = (json_value(text, []) or [{}])[0] if ok else {}
        return port_bindings(info), info

    cls.inspect_ports = inspect_ports
    cls.recreate_with_ports = (lambda self, target, name, bindings:
                               recreate_with_ports(self, target, name, bindings))


_attach(DockerProvider)
_attach(PodmanProvider)
