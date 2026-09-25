"""
kontainy — command-line interface

Everything the window can do, without a window — for servers, SSH sessions
and scripts. The CLI adds no logic of its own: it drives the same providers
and the same actions as the GUI, so a button and its command always agree,
and every action prints the exact command it will run before running it.

    ky                              open the window
    ky overview                     every technology on this machine
    ky docker targets               the contexts, the active one marked
    ky docker use desktop-linux     switch (asks first; -y to skip)
    ky podman ls                    containers on the active connection
    ky docker stop web db           act on objects by name
    ky libvirt start-all            act on every object at once
    ky libvirt networks             an extra tab of a technology
    ky libvirt networks start labnet
    ky docker ports web 8080:80     change a container's ports safely
    ky docker shell set DOCKER_CONTEXT desktop-linux
    ky install qemu                 install a tool for this system
    ky doctor                       diagnostics

Flags for every action: -y/--yes (no prompt), --dry-run (show only),
--json (machine-readable lists), --target NAME (not the active target).
Without a terminal, an action that would ask refuses unless -y is given.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

TECH_ALIASES = {
    "docker": "docker", "podman": "podman",
    "kubernetes": "kubernetes", "k8s": "kubernetes", "kube": "kubernetes",
    "kubectl": "kubernetes",
    "libvirt": "libvirt", "kvm": "libvirt", "qemu": "libvirt",
    "virsh": "libvirt",
    "hyperv": "hyperv", "hyper-v": "hyperv",
    "vmware": "vmware", "vmrun": "vmware", "fusion": "vmware",
    "incus": "incus", "lxd": "lxd",
}

TARGET_VERBS = ("targets", "use", "add", "rm-target", "test")
TECH_VERBS = TARGET_VERBS + ("ls", "start-all", "stop-all", "services",
                             "service", "shell", "ports", "verbs")


# --- output helpers -----------------------------------------------------------------
class Out:
    json = False
    quiet = False


def _print_table(rows: list, columns: list) -> None:
    """columns: [(key, title)]"""
    if Out.json:
        print(json.dumps(rows, indent=2, default=str))
        return
    if not rows:
        print("(none)")
        return
    widths = [max(len(title), *(len(str(r.get(k, "") or "")) for r in rows))
              for k, title in columns]
    print("  ".join(t.ljust(w) for (_, t), w in zip(columns, widths)).rstrip())
    print("  ".join("-" * w for w in widths))
    for row in rows:
        print("  ".join(str(row.get(k, "") or "").ljust(w)
                        for (k, _), w in zip(columns, widths)).rstrip())


def _fail(message: str, code: int = 2) -> int:
    print(f"ky: {message}", file=sys.stderr)
    return code


def _verb(label: str) -> str:
    """'■  Shut down' -> 'shut-down'; the name an action has on the CLI."""
    words = re.sub(r"[^A-Za-z0-9]+", " ", label).strip().lower()
    return "-".join(words.split())


# Words that mean the same thing across technologies: Docker "removes",
# libvirt and Incus "delete", Hyper-V "turns off" what libvirt "forces off".
SYNONYMS = [
    {"rm", "remove", "delete"},
    {"shutdown", "shut-down"},
    {"poweroff", "power-off", "turn-off", "force-off", "kill", "destroy"},
    {"autostart", "start-at-boot"},
    {"leases", "dhcp-leases"},
    {"xml", "show-definition", "definition"},
]


def _find(actions: dict, verb: str):
    """The action a CLI verb means, allowing for each tool's own words."""
    if verb in actions:
        return actions[verb]
    for group in SYNONYMS:
        if verb in group:
            for word in group:
                if word in actions:
                    return actions[word]
    # A leading word is enough when it names exactly one action:
    # `delete` for Kubernetes' "Delete (recreate)". Never for the basic
    # verbs: on a running VM `start` must fail, not quietly turn into
    # "start-at-boot" and change the autostart setting instead.
    if verb in PRIMARY_VERBS:
        return None
    matches = [name for name in actions if name.startswith(verb + "-")]
    if len(matches) == 1:
        return actions[matches[0]]
    return None


VERB_ALIASES = {}

PRIMARY_VERBS = {"start", "stop", "restart", "reboot", "run", "show", "set"}


# --- running an action ----------------------------------------------------------------
def run_action(action, args, provider=None) -> int:
    """Show the command, ask, run it — the CLI's version of the dialog."""
    from .core.actions import NONE, ROOT, SHELL
    from .utils.config import history

    if provider is not None:
        action = provider.prepare(action)
    from .utils import logs
    shown = action.display() or "(nothing to run)"
    # The label carries its own symbol for the buttons ("■  Stop"); the
    # banner adds one of its own, so the label goes in bare.
    title = re.sub(r"^[^\w]+\s*", "", action.label).strip() or action.label
    details = []
    if action.explanation and not Out.quiet:
        import textwrap
        for paragraph in action.explanation.splitlines():
            details += textwrap.wrap(paragraph, 66) or [""]
    logs.banner(title, "warning" if action.destructive else "start",
                details, record=False)
    for line in shown.splitlines():
        logs.banner_command(line, action.id)
    if action.scope == NONE:
        return 0
    if action.scope == SHELL:
        print("\nThis must run in your own shell; kontainy cannot change the "
              "environment of the shell that started it.")
        return 0
    if args.dry_run:
        return 0
    if not args.yes:
        if not sys.stdin.isatty():
            return _fail("not running without confirmation; add -y to run "
                         "non-interactively")
        answer = input("\nRun this? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("Cancelled.")
            return 1

    if action.func is not None:
        result = action.execute()
        text = (result.stdout or result.stderr or "").strip()
        if text:
            print(text)
        (logs.banner_success if result.ok else logs.banner_error)(
            title + (" \u2014 done" if result.ok else " \u2014 failed"))
        return 0 if result.ok else 1

    argv = list(action.command)
    if action.scope == ROOT and os.name != "nt":
        geteuid = getattr(os, "geteuid", None)
        if geteuid is None or geteuid() != 0:
            argv = ["sudo"] + argv
    elif action.scope == ROOT and os.name == "nt":
        from .core.elevate import run_elevated
        result = run_elevated(action.command, note=action.id)
        print(result.output)
        return 0 if result.ok else 1
    # Stream straight to the terminal: logs, prompts and progress bars
    # behave exactly as they would if the user had typed the command.
    try:
        code = subprocess.call(argv)
    except FileNotFoundError:
        return _fail(f"{argv[0]}: not found", 127)
    history().add(" ".join(argv), note=action.id, ok=code == 0)
    if code == 0:
        logs.banner_success(f"{title} \u2014 done")
    else:
        logs.banner_error(f"{title} \u2014 exit {code}")
    return code


def _add_run_flags(parser) -> None:
    parser.add_argument("-y", "--yes", action="store_true",
                        help="run without asking")
    parser.add_argument("--dry-run", action="store_true",
                        help="show the command, run nothing")


# --- providers -------------------------------------------------------------------------
def _providers_here() -> list:
    from .core.providers import PROVIDERS
    return [p for p in PROVIDERS if p.shown_here()]


def _provider(tech: str):
    from .core.providers import by_id
    provider = by_id(TECH_ALIASES.get(tech, tech))
    if provider is None or not provider.shown_here():
        return None
    return provider


def _pick_target(provider, name: str):
    targets = provider.targets()
    if not name:
        return next((t for t in targets if t.active), None), targets
    for target in targets:
        if target.name == name:
            return target, targets
    return None, targets


def _values(pairs: list) -> dict:
    values = {}
    for pair in pairs:
        if "=" not in pair:
            raise ValueError(f"expected key=value, got {pair!r}")
        key, _, value = pair.partition("=")
        values[key.strip()] = value.strip()
    return values


def cmd_tech(args) -> int:
    provider = _provider(args.tech)
    if provider is None:
        return _fail(f"{args.tech} is not available on this system. "
                     f"See: ky tech")
    verb = args.verb or "targets"
    rest = list(args.rest)

    if verb == "verbs":
        return _show_verbs(provider)

    # Asked to start the engine, "not answering" is the reason for asking,
    # not a reason to refuse.
    if verb == "start-engine":
        built = provider.start_engine()
        if built is None:
            return _fail(f"{provider.name} has nothing to start here \u2014 "
                         f"it is a client, not a daemon")
        return run_action(built, args, provider)

    if not provider.available() and verb not in ("shell", "verbs"):
        reason = provider.unavailable_reason().replace(
            "Install it from the Install tab.", "").strip()
        hint = (f"\nInstall it with:  ky install {provider.tool_ids[0]}"
                if provider.tool_ids else "")
        return _fail(reason + hint, 3)

    host = provider.host()
    if host is not None and host.is_wsl and not Out.quiet and not Out.json:
        print(f"[{provider.name} {host.label}]", file=sys.stderr)

    # --- targets ---
    if verb == "targets":
        from .core.providers.base import socket_kind
        rows = [{"active": "*" if t.active else "", "name": t.name,
                 "address": t.address, "kind": socket_kind(t.address),
                 "detail": t.detail} for t in provider.targets()]
        _print_table(rows, [("active", ""), ("name", provider.target_noun),
                            ("address", "Address"), ("kind", "Kind"),
                            ("detail", "Detail")])
        return 0
    if verb in ("use", "rm-target", "test"):
        if not rest and verb != "test":
            return _fail(f"usage: ky {args.tech} {verb} NAME")
        target, targets = _pick_target(provider, rest[0] if rest else "")
        if target is None:
            names = ", ".join(t.name for t in targets) or "none"
            return _fail(f"no {provider.target_noun.lower()} named "
                         f"{rest[0] if rest else '(active)'}; have: {names}")
        if verb == "use":
            if target.active:
                print(f"{target.name} is already active.")
                return 0
            return run_action(provider.activate(target), args, provider)
        if verb == "rm-target":
            if not target.removable:
                return _fail(f"{target.name} is built in and cannot be removed")
            return run_action(provider.remove(target), args, provider)
        return run_action(provider.test(target), args, provider)
    if verb == "add":
        fields = provider.add_fields()
        if not rest:
            print(f"usage: ky {args.tech} add NAME key=value ...\nfields:")
            for f in fields:
                print(f"  {f.key:12} {f.label}"
                      + ("" if f.required else " (optional)")
                      + (f" — e.g. {f.placeholder}" if f.placeholder else ""))
            return 2
        try:
            values = _values(rest[1:])
        except ValueError as exc:
            return _fail(str(exc))
        values[fields[0].key] = rest[0]
        missing = [f.key for f in fields if f.required and not values.get(f.key)]
        if missing:
            return _fail(f"missing: {', '.join(missing)}")
        return run_action(provider.add(values), args, provider)

    # --- objects ---
    target, _targets = _pick_target(provider, args.target or "")
    if args.target and target is None:
        return _fail(f"no {provider.target_noun.lower()} named {args.target}")
    if verb == "ls":
        listing = provider.objects(target)
        if listing.error:
            return _fail(listing.error, 1)
        _print_table(listing.rows, [(c.key, c.title) for c in listing.columns])
        return 0
    if verb in ("start-all", "stop-all"):
        listing = provider.objects(target)
        wanted = {"start-all": ("start", "boot"), "stop-all": ("stop", "shut")}
        for action in provider.bulk_actions(target, listing.rows):
            v = _verb(action.label)
            if any(v.startswith(w) for w in wanted[verb]):
                return run_action(action, args, provider)
        print(f"Nothing to do: no {provider.object_noun_plural.lower()} "
              f"to {verb.split('-')[0]}.")
        return 0

    # --- services ---
    if verb == "services":
        return _services(provider)
    if verb == "service":
        return _service_action(provider, rest, args)

    # --- shell profile ---
    if verb == "shell":
        return _shell(provider, rest, args, target)

    # --- ports ---
    if verb == "ports":
        return _ports(provider, rest, args, target)

    # --- sections: networks, switches, backend ---
    for section in provider.sections():
        if verb in (section.id, _verb(section.title)):
            return _section(provider, section, rest, args, target)

    # --- per-object actions ---
    names = rest
    if not names:
        return _fail(f"usage: ky {args.tech} {verb} NAME...  "
                     f"(see: ky {args.tech} verbs)")
    listing = provider.objects(target)
    if listing.error:
        return _fail(listing.error, 1)
    wanted = VERB_ALIASES.get(verb, verb)
    status = 0
    for name in names:
        row = next((r for r in listing.rows
                    if str(r.get(provider.object_key, "")) == name), None)
        if row is None:
            status = _fail(f"no {provider.object_noun_plural.lower()[:-1]} "
                           f"named {name}", 1)
            continue
        actions = {_verb(a.label): a for a in provider.object_actions(target, row)}
        action = _find(actions, wanted)
        if action is None:
            status = _fail(f"{verb} is not available for {name} now; "
                           f"available: {', '.join(sorted(actions))}", 1)
            continue
        status = run_action(action, args, provider) or status
    return status


def _show_verbs(provider) -> int:
    print(f"ky {provider.id} — {provider.name}\n")
    print(f"  targets                 list {provider.target_noun_plural.lower()}")
    print(f"  use NAME                make one active")
    print(f"  add NAME key=value ...  add one (run without values for fields)")
    print(f"  rm-target NAME          remove one")
    print(f"  test [NAME]             check one answers")
    print(f"  ls [--target NAME]      list {provider.object_noun_plural.lower()}")
    print(f"  start-all | stop-all    act on all of them")
    if provider.start_engine() is not None:
        print(f"  start-engine            start it when it is installed but "
              f"not answering")
    print(f"  VERB NAME...            act on one or more; verbs depend on state,")
    print(f"                          e.g. start, stop, restart, logs, rm")
    if provider.services:
        print("  services                the system services it depends on")
        print("  service ACTION UNIT     start | stop | restart | enable | "
              "disable | status")
    print("  shell [set VAR [VALUE] | unset VAR]   your shell profile")
    if provider.can_edit_ports():
        print("  ports NAME [HOST:CONTAINER ...]       show or change ports")
    for section in provider.sections():
        print(f"  {section.id:22}  {section.title.lower()}: ls, ACTION NAME"
              + (", create key=value ..." if section.create else ""))
    return 0


def _services(provider) -> int:
    from .core import actions as act
    from .core.registry import OS_KIND
    if OS_KIND != "linux" or not provider.services:
        print("No system services to manage here.")
        return 0
    rows = []
    for unit, user, why in provider.services:
        rows.append({"unit": unit, "scope": "user" if user else "system",
                     "state": act._unit_property(unit, user, "is-active"),
                     "boot": act._unit_property(unit, user, "is-enabled"),
                     "why": why})
    _print_table(rows, [("unit", "Unit"), ("scope", "Scope"),
                        ("state", "State"), ("boot", "At boot"),
                        ("why", "What it does")])
    return 0


def _service_action(provider, rest, args) -> int:
    from .core import actions as act
    if len(rest) < 2:
        return _fail("usage: ky TECH service start|stop|restart|enable|"
                     "disable|status UNIT")
    verb, unit = rest[0], rest[1]
    for name, user, why in provider.services:
        if name == unit:
            state = act._unit_property(name, user, "is-active")
            enabled = act._unit_property(name, user, "is-enabled")
            candidates = act.actions_for_unit(act.Unit(
                name=name, user=user, state=state, enabled=enabled,
                description=why))
            for action in candidates:
                if _verb(action.label).startswith(verb) or \
                        verb in _verb(action.label).split("-"):
                    return run_action(action, args, provider)
            return _fail(f"{verb} does not apply to {unit} now "
                         f"(state {state}, at boot {enabled})")
    return _fail(f"{provider.name} has no unit {unit}; see: ky "
                 f"{provider.id} services")


def _shell(provider, rest, args, target) -> int:
    from .core import shellprofile as sp
    if not sp.VARIABLES.get(provider.id):
        return _fail(f"{provider.name} has no shell variables")
    if not rest:
        print(f"profile: {sp.profile_path()}\n")
        rows = [{"var": e.name, "block": e.managed_value,
                 "elsewhere": "; ".join(f"line {n}: {x}" for n, x in e.foreign),
                 "now": e.current} for e in sp.read(provider.id)]
        _print_table(rows, [("var", "Variable"), ("block", "kontainy's block"),
                            ("elsewhere", "Set elsewhere"),
                            ("now", "In this environment")])
        return 0
    known = [n for n, _ in sp.VARIABLES[provider.id]]
    if rest[0] == "set" and len(rest) >= 2:
        name = rest[1]
        if name not in known:
            return _fail(f"{name} is not one of: {', '.join(known)}")
        value = rest[2] if len(rest) > 2 else (
            target.name if target and name.endswith(("CONTEXT", "CONNECTION"))
            else target.address if target else "")
        if not value:
            return _fail(f"give a value: ky {provider.id} shell set {name} VALUE")
        return run_action(sp.set_action(name, value), args)
    if rest[0] == "unset" and len(rest) == 2:
        return run_action(sp.unset_action(rest[1]), args)
    return _fail("usage: ky TECH shell [set VAR [VALUE] | unset VAR]")


def _ports(provider, rest, args, target) -> int:
    if not provider.can_edit_ports():
        return _fail(f"{provider.name} has no port editing")
    if not rest:
        return _fail(f"usage: ky {provider.id} ports NAME [HOST:CONTAINER[/proto] ...]")
    name = rest[0]
    bindings, info = provider.inspect_ports(target, name)
    if not info:
        return _fail(f"no container named {name}", 1)
    if len(rest) == 1:
        _print_table([{"ip": b[0], "host": b[1], "container": b[2],
                       "proto": b[3]} for b in bindings],
                     [("ip", "Host IP"), ("host", "Host port"),
                      ("container", "Container port"), ("proto", "Protocol")])
        return 0
    new = []
    for spec in rest[1:]:
        m = re.fullmatch(r"(?:(\d+\.\d+\.\d+\.\d+):)?(\d*):?(\d+)(?:/(tcp|udp))?",
                         spec)
        if not m:
            return _fail(f"cannot read {spec!r}; use HOST:CONTAINER, "
                         f"IP:HOST:CONTAINER or CONTAINER, optionally /udp")
        new.append((m.group(1) or "", m.group(2) or "", m.group(3),
                    m.group(4) or "tcp"))
    return run_action(provider.recreate_with_ports(target, name, new), args,
                      provider)


def _section(provider, section, rest, args, target) -> int:
    if not rest or rest[0] == "ls":
        listing = section.listing(target)
        if listing.error:
            return _fail(listing.error, 1)
        _print_table(listing.rows, [(c.key, c.title) for c in listing.columns])
        return 0
    if rest[0] == "create":
        if section.create is None:
            return _fail(f"{section.title} cannot be created from kontainy")
        if len(rest) == 1:
            print(f"usage: ky {provider.id} {section.id} create key=value ...")
            for f in section.create_fields:
                print(f"  {f.key:12} {f.label}"
                      + ("" if f.required else " (optional)")
                      + (f" — e.g. {f.placeholder}" if f.placeholder else ""))
            return 2
        try:
            values = _values(rest[1:])
        except ValueError as exc:
            return _fail(str(exc))
        missing = [f.key for f in section.create_fields
                   if f.required and not values.get(f.key)]
        if missing:
            return _fail(f"missing: {', '.join(missing)}")
        return run_action(section.create(target, values), args, provider)
    if len(rest) < 2:
        return _fail(f"usage: ky {provider.id} {section.id} ACTION NAME")
    verb, name = VERB_ALIASES.get(rest[0], rest[0]), rest[1]
    listing = section.listing(target)
    row = next((r for r in listing.rows if str(r.get(section.key)) == name), None)
    if row is None:
        return _fail(f"no {section.noun.lower()} named {name}", 1)
    actions = {_verb(a.label): a for a in section.row_actions(target, row)}
    action = _find(actions, verb)
    if action is None:
        return _fail(f"{rest[0]} is not available for {name}; available: "
                     f"{', '.join(sorted(actions))}", 1)
    return run_action(action, args, provider)


# --- machine-wide commands ------------------------------------------------------------------
def cmd_overview(args) -> int:
    rows = []
    for p in _providers_here():
        row = {"id": p.id, "name": p.name, "installed": p.available(),
               "version": "", "active": "", "objects": ""}
        host = p.host()
        row["runs"] = host.label if host is not None and host.is_wsl else "here"
        if row["installed"]:
            row["version"] = p.version()
            active = p.active()
            row["active"] = active.name if active else ""
            listing = p.objects(active)
            from .core.providers.base import count_label
            row["objects"] = (count_label(len(listing.rows),
                                          p.object_noun_plural)
                              if not listing.error else "unreachable")
        rows.append(row)
    if Out.json:
        print(json.dumps(rows, indent=2))
        return 0
    for row in rows:
        row["installed"] = "yes" if row["installed"] else "no"
    _print_table(rows, [("id", "ky"), ("name", "Technology"),
                        ("installed", "Installed"), ("version", "Version"),
                        ("active", "Active target"), ("objects", "Objects"),
                        ("runs", "Runs")])
    return 0


def cmd_techs(args) -> int:
    rows = []
    for p in _providers_here():
        host = p.host()
        rows.append({"id": p.id, "name": p.name,
                     "targets": p.target_noun_plural.lower(),
                     "objects": p.object_noun_plural.lower(),
                     "runs": host.label if host is not None and host.is_wsl
                     else "here"})
    _print_table(rows, [("id", "ky"), ("name", "Technology"),
                        ("targets", "Targets"), ("objects", "Objects"),
                        ("runs", "Runs")])
    return 0


def cmd_tools(args) -> int:
    from .core import registry as reg
    rows = []
    for group in reg.GROUPS:
        if args.group and args.group.lower() not in group.lower():
            continue
        for tool in reg.by_group(group):
            rows.append({"id": tool.id, "name": tool.name, "group": group,
                         "installed": "yes" if tool.installed() else "no",
                         "install": tool.install_command()})
    _print_table(rows, [("id", "Id"), ("name", "Tool"), ("group", "Group"),
                        ("installed", "Installed"),
                        ("install", "Install command")])
    return 0


def cmd_install(args, remove: bool = False) -> int:
    from .core import actions as act
    from .core import registry as reg
    tool = reg.by_id(args.tool)
    if tool is None:
        return _fail(f"unknown tool {args.tool}; see: ky tools")
    line = tool.remove_command() if remove else tool.install_command()
    if not line:
        others = "\n".join(f"  {label}: {cmd}"
                           for label, cmd in tool.all_install_commands())
        return _fail(f"no {'remove' if remove else 'install'} command for "
                     f"{tool.name} on {reg.OS_LABEL}"
                     + (f". Other platforms:\n{others}" if others else ""))
    root = line.startswith("sudo ")
    action = act.Action(
        id=f"{'remove' if remove else 'install'}-{tool.id}",
        label=f"{'Remove' if remove else 'Install'} {tool.name}",
        command=line.replace("sudo ", "", 1).split(),
        scope=act.ROOT if root else act.USER, destructive=remove,
        explanation=tool.summary + (f"\n\n\u26a0 {tool.note}" if tool.note else ""))
    return run_action(action, args)


def cmd_catalog(args) -> int:
    from .core.catalog import ALL_SETTINGS
    if args.key:
        for s in ALL_SETTINGS:
            if s.key == args.key:
                data = {k: getattr(s, k) for k in (
                    "key", "title", "engine", "file", "vtype", "default",
                    "choices", "cli", "restart", "privilege", "danger",
                    "desc", "gotcha", "docs")}
                if Out.json:
                    print(json.dumps(data, indent=2, default=str))
                else:
                    for k, v in data.items():
                        if v not in ("", None):
                            print(f"{k:12} {v}")
                return 0
        if args.key and not args.search:
            args.search = args.key
    text = (args.search or "").lower()
    rows = [{"key": s.key, "engine": s.engine, "title": s.title,
             "file": s.file}
            for s in ALL_SETTINGS
            if (not args.engine or s.engine in (args.engine, "both"))
            and (not text or text in s.key.lower() or text in s.title.lower())]
    _print_table(rows, [("key", "Key"), ("engine", "Engine"),
                        ("title", "Title"), ("file", "File")])
    return 0


def cmd_wsl(args) -> int:
    from . import core as _core  # noqa: F401
    from .core import hosts
    from .utils.config import config
    if not hosts.on_windows():
        return _fail("WSL exists only on Windows")
    if args.action in (None, "list"):
        current = hosts.linux_tools_distro()
        rows = [{"mark": "*" if name == current else "", "name": name,
                 "state": state, "version": version,
                 "default": "yes" if default else "",
                 "usable": "" if hosts.usable_for_tools(name) else "belongs to "
                 + ("Docker Desktop" if name.startswith("docker")
                    else "podman machine")}
                for name, state, version, default in hosts.wsl_distributions()]
        _print_table(rows, [("mark", ""), ("name", "Distribution"),
                            ("state", "State"), ("version", "WSL"),
                            ("default", "Default"), ("usable", "Note")])
        print("\n* carries kontainy's Linux tools (ky wsl use NAME to change)")
        return 0
    if args.action == "use":
        if not args.name:
            return _fail("usage: ky wsl use NAME")
        config().set("wsl_distro", args.name)
        print(f"kontainy's Linux tools now run in {args.name}. "
              f"Your default distribution is unchanged.")
        return 0
    return _fail("usage: ky wsl [list | use NAME]")


# --- parser ---------------------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ky",
        description=("kontainy — containers and virtualisation, in a window "
                     "or from the command line. Run  ky  with no arguments to "
                     "open the window."),
        epilog=("Technologies: " + ", ".join(sorted(set(TECH_ALIASES.values())))
                + ". Per technology:  ky TECH verbs"),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-V", "--version", action="store_true",
                        help="show the version")
    parser.add_argument("--json", action="store_true",
                        help="print lists as JSON")
    parser.add_argument("-q", "--quiet", action="store_true",
                        help="do not print explanations")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    sub.add_parser("version", help="show the version")
    sub.add_parser("gui", help="open the window")
    sub.add_parser("overview", help="every technology on this machine")
    sub.add_parser("tech", help="the technologies kontainy offers here")
    sub.add_parser("doctor", help="run the diagnostic rules")
    p = sub.add_parser("report", help="a system report to paste into an issue")
    p.add_argument("--short", action="store_true",
                   help="skip the list of installed tools")
    sub.add_parser("scan", help="find every engine and socket")
    sub.add_parser("stats", help="catalogue and rule counts")

    p = sub.add_parser("tools", help="installable tools and their state")
    p.add_argument("--group", default="")
    for name, help_text in (("install", "install a tool for this system"),
                            ("uninstall", "remove a tool")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("tool")
        _add_run_flags(p)

    p = sub.add_parser("catalog", help="configuration keys, explained")
    p.add_argument("key", nargs="?", default="")
    p.add_argument("--search", default="")
    p.add_argument("--engine", choices=("docker", "podman"))

    p = sub.add_parser("wsl", help="(Windows) which WSL distribution carries "
                                   "the Linux tools")
    p.add_argument("action", nargs="?", choices=("list", "use"))
    p.add_argument("name", nargs="?")

    for tech in sorted(TECH_ALIASES):
        p = sub.add_parser(tech, help=(f"{TECH_ALIASES[tech]}: see  ky "
                                       f"{tech} verbs")
                           if tech == TECH_ALIASES[tech] else argparse.SUPPRESS)
        p.set_defaults(tech=tech)
        p.add_argument("verb", nargs="?", default="")
        p.add_argument("rest", nargs=argparse.REMAINDER)
        p.add_argument("--target", default="",
                       help="act on this target instead of the active one")
        _add_run_flags(p)
    return parser


def _hoist_flags(argv: list) -> list:
    """Allow -y, --dry-run, --json and --target anywhere on the line.

    argparse.REMAINDER swallows everything after the verb, so
    `ky docker stop web -y` would treat -y as a container name.
    """
    flags, rest, i = [], [], 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("-y", "--yes", "--dry-run", "-q", "--quiet"):
            flags.append(arg)
        elif arg == "--json":
            flags.append(arg)
        elif arg == "--target" and i + 1 < len(argv):
            flags += [arg, argv[i + 1]]
            i += 1
        elif arg.startswith("--target="):
            flags.append(arg)
        else:
            rest.append(arg)
        i += 1
    return rest, flags


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    rest, flags = _hoist_flags(argv)
    globals_ = [f for f in flags if f in ("--json", "-q", "--quiet")]
    local = [f for f in flags if f not in globals_]
    # Global flags go before the command, per-command flags after it.
    if rest and rest[0] in TECH_ALIASES:
        argv = globals_ + rest[:1] + local + rest[1:]
        # verb and its arguments come after the command's own flags
    elif rest and rest[0] in ("install", "uninstall"):
        argv = globals_ + rest[:1] + local + rest[1:]
    else:
        argv = globals_ + rest
    parser = build_parser()
    args = parser.parse_args(argv)
    Out.json = args.json
    Out.quiet = args.quiet

    if args.version or args.command == "version":
        from .core.constants import APP_NAME, APP_VERSION
        print(f"{APP_NAME} {APP_VERSION}")
        return 0
    command = args.command
    if command in (None, "gui"):
        return -1                        # the caller opens the window
    if command == "overview":
        return cmd_overview(args)
    if command == "tech":
        return cmd_techs(args)
    if command in ("doctor", "scan", "stats"):
        from . import __main__ as entry
        return {"doctor": entry.cli_doctor, "scan": entry.cli_scan,
                "stats": entry.cli_stats}[command]()
    if command == "report":
        from .core import report as _report
        print(_report.build(full=not args.short))
        return 0
    if command == "tools":
        return cmd_tools(args)
    if command == "install":
        return cmd_install(args)
    if command == "uninstall":
        return cmd_install(args, remove=True)
    if command == "catalog":
        return cmd_catalog(args)
    if command == "wsl":
        return cmd_wsl(args)
    if command in TECH_ALIASES:
        return cmd_tech(args)
    parser.print_help()
    return 2
