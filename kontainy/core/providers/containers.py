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
