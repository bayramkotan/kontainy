"""
kontainy — creating a container from named values

The dialog builds a `run` command from its fields; this builds the same
command from `key=value` pairs, so `ky create` and the window agree on what
they produce and on what they refuse.

    ky docker create web image=nginx:1.27 ports=8080:80 volume=site:/usr/share/nginx/html

Qt-free, and the checks are the dialog's own (imageinfo.problems), so a
name that is already taken is refused in both places with the same words.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The fields `create` accepts, in the order they are printed.
FIELDS = [
    ("image", "The image to run, with its tag \u2014 nginx:1.27", True),
    ("name", "What to call the container (suggested from the image)", False),
    ("ports", "host:container, comma separated \u2014 8080:80,8443:443", False),
    ("env", "KEY=VALUE, comma separated", False),
    ("volume", "name-or-path:/path/in/container, comma separated", False),
    ("network", "Which network to join \u2014 a user-defined one lets "
                "containers reach each other by name", False),
    ("restart", "no | on-failure | always | unless-stopped", False),
    ("command", "Override the image's own command", False),
    ("user", "uid[:gid] or a name", False),
    ("workdir", "Working directory inside the container", False),
    ("detach", "yes (default) or no \u2014 no keeps it in the foreground",
     False),
    ("rm", "yes to remove the container when it stops", False),
]

SPLIT = ","


@dataclass
class Plan:
    argv: list
    values: dict
    problems: list          # [(severity, text)]

    @property
    def refused(self) -> bool:
        return any(severity == "error" for severity, _ in self.problems)


def _many(values: dict, key: str) -> list:
    raw = values.get(key, "")
    return [part.strip() for part in str(raw).split(SPLIT) if part.strip()]


def build(provider, target, values: dict, existing_names: list = None,
          taken_ports: list = None, facts=None) -> Plan:
    """The command `create` would run, and everything wrong with it."""
    from . import imageinfo
    from .providers.containers import _conn_args

    values = dict(values)
    image = values.get("image", "").strip()
    name = values.get("name", "").strip()
    if not name and image:
        name = imageinfo.suggest_name(image, existing_names or [])
        values["name"] = name

    argv = [provider.binary] + _conn_args(provider, target) + ["run"]
    if str(values.get("detach", "yes")).lower() not in ("no", "false", "0"):
        argv.append("-d")
    if str(values.get("rm", "")).lower() in ("yes", "true", "1"):
        argv.append("--rm")
    if name:
        argv += ["--name", name]
    if values.get("network"):
        argv.append(f"--network={values['network'].strip()}")
    if values.get("restart"):
        argv += ["--restart", values["restart"].strip()]
    if values.get("user"):
        argv += ["--user", values["user"].strip()]
    if values.get("workdir"):
        argv += ["--workdir", values["workdir"].strip()]
    for entry in _many(values, "env"):
        argv += ["-e", entry]
    for entry in _many(values, "ports"):
        argv += ["-p", entry]
    for entry in _many(values, "volume"):
        argv += ["-v", entry]
    argv.append(image or "<image>")
    if values.get("command"):
        argv += values["command"].split()

    host_ports = []
    for entry in _many(values, "ports"):
        bits = entry.split("/")[0].split(":")
        if len(bits) >= 2:
            host_ports.append(bits[-2])
    problems = imageinfo.problems(name, image, existing_names or [],
                                  host_ports, taken_ports or [])
    unknown = [key for key in values
               if key not in {field for field, _help, _req in FIELDS}]
    for key in unknown:
        problems.append(("error", f"{key} is not a field of create; "
                                  f"run `ky {provider.id} create` to see them"))
    if facts is not None and facts.needs_pull and image:
        problems.append(("warning",
                         f"{image} is not on this target, so the run pulls "
                         f"it first."))
    return Plan(argv=argv, values=values, problems=problems)


def describe_fields(provider) -> str:
    lines = [f"usage: ky {provider.id} create [NAME] image=IMAGE [key=value ...]",
             "", "fields:"]
    for key, help_text, required in FIELDS:
        mark = " *" if required else "  "
        lines.append(f"  {key:9}{mark} {help_text}")
    lines += ["", "examples:",
              f"  ky {provider.id} create image=nginx:1.27 ports=8080:80",
              f"  ky {provider.id} create db image=postgres:16 "
              f"env=POSTGRES_PASSWORD=secret volume=pgdata:/var/lib/postgresql/data"]
    return "\n".join(lines)
