"""
kontainy — what the engines STORE: images and volumes, and who holds them

Containers, machines, networks and targets were all here; the two things
that actually fill a disk were nowhere. This module lists images and volumes
across every engine and every context, the same way the unified container
table does, and answers the one question Docker Desktop and Podman Desktop
leave you to guess:

    ⚠️ **Used by** — which containers are holding this image or this volume.

That column is the point of the page. The single most expensive mistake in
this ecosystem is deleting a volume that a database was using, and every
tool here lets you do it with one confirmation that names nothing. kontainy
names the containers before you decide, and when nothing holds a thing it
says that too, so "unused" is a fact rather than a hope.

Rules this module follows:

* **One `ps -a` per target, not one query per row.** Usage is cross-
  referenced in memory from a listing that was going to be read anyway.
* **Sizes come from `system df -v`, read once per target.** Asking per
  volume means starting a container per volume. When `system df` cannot be
  parsed the size is left empty rather than guessed — an invented number is
  worse than a dash.
* **Prune is never the engine's own `prune`.** `docker image prune` deletes
  a list it never shows. Here the unused rows are already known, so the
  removal is an explicit `rm` of named things, and the names are in the
  dialog before anything runs.
* Qt-free, so `ky images` and `ky volumes` work with no display.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .actions import Action, USER
from .providers import by_id
from .providers.base import Listing, action, cli_text, json_lines, \
    json_value, sequence, socket_kind

#: Engines that have images and volumes of their own.
ENGINES = ("docker", "podman", "incus", "lxd")

#: Engines whose CLI is Docker's, so one implementation serves both.
DOCKER_LIKE = ("docker", "podman")


@dataclass
class Source:
    """One engine on one of its targets — a place things are stored."""

    provider: object
    target: object
    engine_id: str = ""
    engine: str = ""
    name: str = ""
    address: str = ""
    kind: str = ""
    active: bool = False
    containers: list = field(default_factory=list)


def sources(engine_ids=ENGINES) -> list:
    """Every engine and target that is installed and shown here."""
    out = []
    for engine_id in engine_ids:
        provider = by_id(engine_id)
        if provider is None or not provider.shown_here() \
                or not provider.available():
            continue
        for target in provider.targets():
            out.append(Source(
                provider=provider, target=target, engine_id=engine_id,
                engine=provider.name, name=target.name,
                address=target.address, kind=socket_kind(target.address),
                active=target.active))
    return out


def _run(provider, argv, timeout=20.0):
    """Run a read-only query on the provider's own host."""
    return provider._cli(argv, timeout=timeout)


def conn(provider, target) -> list:
    """The flag that aims a command at one target, in that tool's words."""
    if provider.id == "docker":
        return ["--context", target.name] if target else []
    if provider.id == "podman":
        return ["--connection", target.name] if target else []
    return []


def _argv(source, rest: list) -> list:
    return [source.provider.binary] + conn(source.provider,
                                           source.target) + list(rest)


# --- who is holding what ---------------------------------------------------------
def containers_on(source) -> list:
    """Every container on this target, read once and reused.

    Both answers this module needs are in one listing: `Image` says which
    image a container runs, and `Mounts` names the volumes it has open. A
    page that asked per image, or per volume, would run hundreds of
    commands to learn what two already say.
    """
    if source.engine_id in DOCKER_LIKE:
        ok, text = _run(source.provider,
                        _argv(source, ["ps", "-a", "--format", "{{json .}}"]))
        return json_lines(text) if ok else []
    if source.engine_id in ("incus", "lxd"):
        ok, text = _run(source.provider,
                        _argv(source, ["list", "--format", "json"]))
        return json_value(text, []) or [] if ok else []
    return []


def _container_name(item: dict) -> str:
    for key in ("Names", "Name", "name", "names"):
        value = item.get(key)
        if isinstance(value, list) and value:
            return str(value[0]).lstrip("/")
        if value:
            return str(value).lstrip("/")
    return ""


def image_users(containers: list, repo_tag: str, image_id: str) -> list:
    """Containers running this image, by reference or by id.

    Both are needed. `docker ps` prints whatever reference the container was
    started with — a name:tag, a digest, or a bare id for an untagged image
    — so matching only one of them calls a held image unused.
    """
    short = (image_id or "").replace("sha256:", "")[:12]
    held = []
    for item in containers:
        used = str(item.get("Image") or item.get("image") or "")
        bare = used.replace("sha256:", "")
        if repo_tag and used == repo_tag:
            held.append(_container_name(item))
        elif short and bare.startswith(short):
            held.append(_container_name(item))
    return [name for name in held if name]


def volume_users(containers: list, volume: str) -> list:
    """Containers with this volume mounted.

    `docker ps --format` puts the mount sources in `Mounts`, comma
    separated — a named volume appears by name, a bind mount by path, so a
    bare substring match would call a volume "db" used by any container
    with /srv/dbdata bound in. Compared piece by piece instead.
    """
    held = []
    for item in containers:
        mounts = item.get("Mounts") or item.get("mounts") or ""
        if isinstance(mounts, list):
            parts = [str(m.get("Name") or m.get("Source") or m)
                     for m in mounts]
        else:
            parts = [p.strip() for p in str(mounts).split(",")]
        if volume and volume in parts:
            held.append(_container_name(item))
    return [name for name in held if name]


# --- sizes -----------------------------------------------------------------------
def disk_usage(source) -> dict:
    """`system df -v`, read ONCE, as {"volumes": {name: size}}.

    Volume size is the one figure no listing carries: `docker volume ls`
    does not compute it, and asking per volume starts a container per
    volume. `system df -v` walks the whole tree in one pass.

    Never fatal. An engine too old for `--format json` here simply leaves
    the Size column empty, which is honest; a made-up number is not.
    """
    if source.engine_id not in DOCKER_LIKE:
        return {"volumes": {}}
    ok, text = _run(source.provider,
                    _argv(source, ["system", "df", "-v", "--format",
                                   "{{json .}}"]), timeout=60.0)
    if not ok:
        return {"volumes": {}}
    data = json_value(text)
    if data is None:
        rows = json_lines(text)
        data = rows[0] if rows else None
    if not isinstance(data, dict):
        return {"volumes": {}}
    volumes = {}
    for item in data.get("Volumes") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("Name") or item.get("VolumeName") or "")
        size = str(item.get("Size") or "")
        if name:
            volumes[name] = size
    return {"volumes": volumes}


# --- images ----------------------------------------------------------------------
def images_on(source) -> tuple:
    """(rows, error) for one source. Rows are page-ready dicts."""
    provider = source.provider
    if source.engine_id in DOCKER_LIKE:
        argv = _argv(source, ["images", "--format", "{{json .}}"])
        ok, text = _run(provider, argv)
        if not ok:
            return [], text
        rows = []
        for item in json_lines(text):
            repo = str(item.get("Repository") or "")
            tag = str(item.get("Tag") or "")
            image_id = str(item.get("ID") or item.get("Id") or "")
            reference = f"{repo}:{tag}" if repo and tag else repo or image_id
            if tag == "<none>":
                reference = image_id
            rows.append({
                "repository": repo, "tag": tag, "id": image_id,
                "reference": reference,
                "created": str(item.get("CreatedSince")
                               or item.get("CreatedAt") or ""),
                "size": str(item.get("Size") or ""),
                "used_by": image_users(source.containers, f"{repo}:{tag}",
                                       image_id),
                "dangling": tag in ("", "<none>"),
                "raw": item,
            })
        return rows, ""
    if source.engine_id in ("incus", "lxd"):
        argv = _argv(source, ["image", "list", "--format", "json"])
        ok, text = _run(provider, argv)
        if not ok:
            return [], text
        rows = []
        for item in json_value(text, []) or []:
            aliases = [str(a.get("name", "")) for a in
                       (item.get("aliases") or []) if isinstance(a, dict)]
            fingerprint = str(item.get("fingerprint") or "")[:12]
            properties = item.get("properties") or {}
            rows.append({
                "repository": aliases[0] if aliases else
                              str(properties.get("description") or ""),
                "tag": ", ".join(aliases[1:]),
                "id": fingerprint, "reference": aliases[0] or fingerprint,
                "created": str(item.get("created_at") or "")[:10],
                "size": _human(item.get("size")),
                # Incus keeps this itself, and its answer is better than any
                # cross-reference: it knows profiles too, not just instances.
                "used_by": [str(u).rsplit("/", 1)[-1]
                            for u in (item.get("used_by") or [])],
                "dangling": not aliases,
                "raw": item,
            })
        return rows, ""
    return [], f"{source.engine}: no image listing yet"


def _human(size) -> str:
    try:
        value = float(size)
    except (TypeError, ValueError):
        return ""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f}{unit}" if unit != "B" else f"{value:.0f}B"
        value /= 1024
    return ""


# --- volumes ---------------------------------------------------------------------
def volumes_on(source) -> tuple:
    provider = source.provider
    if source.engine_id in DOCKER_LIKE:
        argv = _argv(source, ["volume", "ls", "--format", "{{json .}}"])
        ok, text = _run(provider, argv)
        if not ok:
            return [], text
        sizes = disk_usage(source)["volumes"]
        rows = []
        for item in json_lines(text):
            name = str(item.get("Name") or "")
            rows.append({
                "name": name,
                "driver": str(item.get("Driver") or ""),
                "mountpoint": str(item.get("Mountpoint") or ""),
                "size": sizes.get(name, ""),
                "used_by": volume_users(source.containers, name),
                "pool": "",
                "raw": item,
            })
        return rows, ""
    if source.engine_id in ("incus", "lxd"):
        return _incus_volumes(source)
    return [], f"{source.engine}: no volume listing yet"


def _incus_volumes(source) -> tuple:
    """Incus and LXD keep volumes inside storage pools, so pools come first.

    Their own `used_by` is authoritative — it covers profiles and snapshots
    as well as instances — so it is taken as given rather than recomputed.
    """
    provider = source.provider
    ok, text = _run(provider, _argv(source, ["storage", "list",
                                             "--format", "json"]))
    if not ok:
        return [], text
    rows, problems = [], []
    for pool in json_value(text, []) or []:
        pool_name = str((pool or {}).get("name") or "")
        if not pool_name:
            continue
        ok, body = _run(provider, _argv(source, ["storage", "volume", "list",
                                                 pool_name, "--format",
                                                 "json"]))
        if not ok:
            problems.append(f"{pool_name}: {body.splitlines()[0]}")
            continue
        for item in json_value(body, []) or []:
            rows.append({
                "name": str(item.get("name") or ""),
                "driver": str(item.get("type") or ""),
                "mountpoint": str((item.get("config") or {})
                                  .get("source") or ""),
                "size": str((item.get("config") or {})
                            .get("size") or ""),
                "used_by": [str(u).rsplit("/", 1)[-1]
                            for u in (item.get("used_by") or [])],
                "pool": pool_name,
                "raw": item,
            })
    return rows, "; ".join(problems)


# --- gathering across every source ------------------------------------------------
def _gather(reader, engine_ids, log_error=None) -> list:
    rows = []
    for source in sources(engine_ids):
        source.containers = containers_on(source)
        found, error = reader(source)
        if error and log_error:
            log_error(f"{source.engine} / {source.name}: "
                      f"{error.splitlines()[0]}")
        for row in found:
            row.update({
                "engine": source.engine, "engine_id": source.engine_id,
                "target": source.name, "address": source.address,
                "kind": source.kind, "active": source.active,
            })
            rows.append(row)
    return rows


def list_images(engine_ids=ENGINES, log_error=None) -> list:
    return _gather(images_on, engine_ids, log_error)


def list_volumes(engine_ids=ENGINES, log_error=None) -> list:
    return _gather(volumes_on, engine_ids, log_error)


# --- actions on one image ---------------------------------------------------------
def _held_note(users: list, noun: str) -> str:
    if not users:
        return (f"Nothing is holding this {noun}, so removing it frees the "
                f"space and breaks nothing.")
    return (f"⚠ Held by {len(users)} container"
            f"{'s' if len(users) != 1 else ''}: {', '.join(users)}.\n"
            f"The engine will refuse while they exist. Remove or recreate "
            f"them first — and if this is a data volume, that is exactly the "
            f"moment to check you meant it.")


def image_actions(provider, target, row: dict) -> list:
    """Everything that can be done to one image, each with its real command."""
    base = [provider.binary] + conn(provider, target)
    reference = row.get("reference") or row.get("id") or ""
    if provider.id in ("incus", "lxd"):
        return [
            action(f"image-info-{reference}", "\U0001f50e  Inspect",
                   base + ["image", "info", reference],
                   "Fingerprint, aliases, properties and what is using it."),
            action(f"image-rm-{reference}", "\U0001f5d1  Remove",
                   base + ["image", "delete", reference],
                   _held_note(row.get("used_by") or [], "image"),
                   destructive=True),
        ]
    return [
        action(f"image-inspect-{reference}", "\U0001f50e  Inspect",
               base + ["image", "inspect", reference],
               "The whole definition: layers, environment, entrypoint, "
               "exposed ports, labels and the digest it was pulled by."),
        action(f"image-history-{reference}", "\U0001f4dc  History",
               base + ["history", reference],
               "Every build step and what it cost. The line with the large "
               "size is the one worth changing — and a file deleted in a "
               "later step still weighs the same here, because a layer can "
               "only add."),
        action(f"image-pull-{reference}", "⬇  Pull again",
               base + ["pull", reference],
               "Fetches the current image for this tag. A tag is a moving "
               "name, so this can replace what you have — the old image "
               "stays behind untagged until it is removed."),
        action(f"image-push-{reference}", "⬆  Push",
               base + ["push", reference],
               "Uploads it to the registry its name points at. Without a "
               "registry prefix the name means Docker Hub, and without a "
               "login the push is refused — `docker login` first."),
        action(f"image-rm-{reference}", "\U0001f5d1  Remove",
               base + ["rmi", reference],
               _held_note(row.get("used_by") or [], "image"),
               destructive=True),
    ]


def tag_action(provider, target, row: dict, new_tag: str) -> Action:
    base = [provider.binary] + conn(provider, target)
    reference = row.get("reference") or row.get("id") or ""
    return action(
        f"image-tag-{reference}", "\U0001f3f7  Tag",
        base + ["tag", reference, new_tag],
        f"Gives the same image a second name. Nothing is copied and no "
        f"space is used: {new_tag} and {reference} become two names for one "
        f"image, and removing one leaves the other.")


def save_action(provider, target, row: dict, path: str) -> Action:
    base = [provider.binary] + conn(provider, target)
    reference = row.get("reference") or row.get("id") or ""
    return action(
        f"image-save-{reference}", "\U0001f4be  Save",
        base + ["save", "-o", path, reference],
        f"Writes the image and every layer to {path} as a tar archive. That "
        f"file can be carried to a machine with no registry and loaded "
        f"there with `{provider.binary} load -i`. It is the whole image, so "
        f"expect the size in the table on disk.")


def pull_action(provider, target, reference: str) -> Action:
    """Pulling streams, so it is given a `follow` and goes to the log view."""
    base = [provider.binary] + conn(provider, target)
    argv = base + ["pull", reference]
    return Action(
        id=f"image-pull-{reference}", label=f"⬇  Pull {reference}",
        command=argv, scope=USER, follow=argv,
        explanation=(
            f"Downloads {reference} layer by layer. Without a registry "
            f"prefix the name means Docker Hub; without a tag it means "
            f":latest, which is a moving target and the usual reason two "
            f"machines run different code from the same name."))


def prune_images_action(provider, target, rows: list) -> Action:
    """Remove the unused images BY NAME — never the engine's silent prune.

    `docker image prune -a` deletes a list it never shows, and the first
    time it takes something that was being kept on purpose is the last time
    anyone trusts it. Here the rows are already known, so this is an
    ordinary `rmi` of things the user can read first.
    """
    unused = [r for r in rows if not r.get("used_by")]
    if not unused:
        return None
    base = [provider.binary] + conn(provider, target)
    verb = "delete" if provider.id in ("incus", "lxd") else "rmi"
    head = ["image"] if provider.id in ("incus", "lxd") else []
    names = [r.get("reference") or r.get("id") for r in unused]
    total = ", ".join(str(n) for n in names)
    return sequence(
        "images-prune", f"\U0001f9f9  Remove {len(unused)} unused images",
        [base + head + [verb, str(n)] for n in names],
        f"These images have no container holding them:\n\n  {total}\n\n"
        f"One command each, so a refusal stops that one and not the rest. "
        f"Anything in the list that you want to keep — a base image you "
        f"build on, an image you will run next week — close this and remove "
        f"the others one at a time instead.",
        destructive=True)


# --- actions on one volume --------------------------------------------------------
def volume_actions(provider, target, row: dict) -> list:
    base = [provider.binary] + conn(provider, target)
    name = row.get("name") or ""
    if provider.id in ("incus", "lxd"):
        pool = row.get("pool") or ""
        return [
            action(f"volume-info-{name}", "\U0001f50e  Inspect",
                   base + ["storage", "volume", "show", pool, name],
                   "The volume's configuration and everything using it."),
            action(f"volume-rm-{name}", "\U0001f5d1  Remove",
                   base + ["storage", "volume", "delete", pool, name],
                   _held_note(row.get("used_by") or [], "volume"),
                   destructive=True),
        ]
    return [
        action(f"volume-inspect-{name}", "\U0001f50e  Inspect",
               base + ["volume", "inspect", name],
               "Driver, options and the path on the host where the data "
               "really is. For a local volume that path is readable as "
               "root, which is the quickest way to see what is inside."),
        action(f"volume-browse-{name}", "\U0001f4c2  Browse",
               base + ["run", "--rm", "-v", f"{name}:/v", "alpine",
                       "ls", "-la", "/v"],
               "Starts a throwaway container with the volume mounted and "
               "lists it. Nothing is written and the container is gone when "
               "the listing ends — this is how you look inside a volume "
               "without root and without guessing its path."),
        action(f"volume-rm-{name}", "\U0001f5d1  Remove",
               base + ["volume", "rm", name],
               _held_note(row.get("used_by") or [], "volume"),
               destructive=True),
    ]


def create_volume_action(provider, target, name: str, driver: str = "local",
                         options: dict = None) -> Action:
    base = [provider.binary] + conn(provider, target)
    argv = base + ["volume", "create"]
    if driver and driver != "local":
        argv += ["--driver", driver]
    for key, value in (options or {}).items():
        if key and value:
            argv += ["--opt", f"{key}={value}"]
    argv.append(name)
    return action(
        f"volume-create-{name}", "➕  Create volume", argv,
        f"Creates an empty volume called {name}. A volume outlives every "
        f"container that mounts it — that is the whole point of one — so "
        f"the name is what you will have to recognise in a year.")


def backup_action(provider, target, row: dict, path: str) -> Action:
    """Tar the volume out through a throwaway container.

    ⚠️ A running container may be mid-write, and tar will happily copy a
    half-written database file. The warning is in the explanation because
    this is the step where a backup silently becomes useless.
    """
    base = [provider.binary] + conn(provider, target)
    name = row.get("name") or ""
    users = row.get("used_by") or []
    warning = ""
    if users:
        warning = (f"\n\n⚠ {', '.join(users)} currently hold this "
                   f"volume. A copy taken while something is writing can "
                   f"contain a half-written file — for a database, stop the "
                   f"container first or use its own dump command.")
    import os
    folder, filename = os.path.split(path)
    return action(
        f"volume-backup-{name}", "\U0001f4be  Back up",
        base + ["run", "--rm", "-v", f"{name}:/v", "-v",
                f"{folder}:/backup", "alpine", "tar", "czf",
                f"/backup/{filename}", "-C", "/v", "."],
        f"Copies everything in {name} into {path} as a gzipped tar, through "
        f"a container that is deleted afterwards. Restore puts it back the "
        f"same way.{warning}")


def restore_action(provider, target, row: dict, path: str) -> Action:
    base = [provider.binary] + conn(provider, target)
    name = row.get("name") or ""
    import os
    folder, filename = os.path.split(path)
    return action(
        f"volume-restore-{name}", "♻  Restore",
        base + ["run", "--rm", "-v", f"{name}:/v", "-v",
                f"{folder}:/backup", "alpine", "tar", "xzf",
                f"/backup/{filename}", "-C", "/v"],
        f"Unpacks {path} into {name}. Files already there with the same "
        f"names are overwritten and anything else is left alone, so this "
        f"merges rather than replaces — restore into a volume you created "
        f"empty if you want exactly what was in the archive.",
        destructive=True)


def prune_volumes_action(provider, target, rows: list) -> Action:
    """The one that matters most. Named, every time."""
    unused = [r for r in rows if not r.get("used_by")]
    if not unused:
        return None
    base = [provider.binary] + conn(provider, target)
    names = [str(r.get("name")) for r in unused]
    commands = []
    for row in unused:
        if provider.id in ("incus", "lxd"):
            commands.append(base + ["storage", "volume", "delete",
                                    str(row.get("pool") or ""),
                                    str(row.get("name"))])
        else:
            commands.append(base + ["volume", "rm", str(row.get("name"))])
    return sequence(
        "volumes-prune", f"\U0001f9f9  Remove {len(unused)} unused volumes",
        commands,
        "No container is holding these volumes:\n\n  " + ", ".join(names) +
        "\n\n⚠ A volume with nothing attached is not the same as a "
        "volume with nothing in it. A stopped-and-removed database leaves "
        "its data here looking exactly this unused, and this is the "
        "deletion people regret most in this ecosystem. Read the names "
        "above; if one of them means something to you, close this.",
        destructive=True)


__all__ = ["ENGINES", "Source", "sources", "containers_on", "disk_usage",
           "images_on", "volumes_on", "list_images", "list_volumes",
           "image_users", "volume_users", "image_actions", "volume_actions",
           "tag_action", "save_action", "pull_action", "create_volume_action",
           "backup_action", "restore_action", "prune_images_action",
           "prune_volumes_action", "conn"]
