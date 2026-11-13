"""
kontainy — what a container is actually doing right now

The container table said what exists and what state it is in, and nothing
about what any of it is costing. That is the difference between a list and
a tool: "nginx is running" is a fact you could have guessed, "nginx is
running and eating 190% of a core" is the one that makes you open it.

Qt-free, so the parsing is tested without a display and `ky` can use the
same reader.

Three things this module refuses to do, each of them a way the figure
would be worse than no figure at all:

* **It never invents a zero.** Rootless Podman without cgroup v2 delegation
  reports nothing for memory, and a 0 B in that column reads as "this
  container uses no memory" rather than "this machine cannot tell you".
  Missing stays missing, and the page shows a dash.
* **It never streams.** `docker stats` without `--no-stream` runs forever,
  which is right for a terminal and wrong for a table that redraws: one
  snapshot per tick, taken off the UI thread, and nothing left running when
  the page is closed.
* **It never asks about a container that is not running.** Stopped
  containers have no statistics, and including them turns a cheap call into
  a slow one that answers with blanks.
"""

from __future__ import annotations

import json
import re

#: Engines whose CLI reports statistics in a shape this understands.
ENGINES = ("docker", "podman")

#: Below this a container is doing nothing worth noticing; above it, the
#: number is worth the eye it catches.
BUSY_CPU = 50.0
#: A container at or above this much of its memory limit is about to be
#: killed by the kernel, and that is the one number in the table that
#: predicts an outage rather than describing one.
TIGHT_MEMORY = 90.0


def _number(text: str) -> float:
    """The leading number of "12.34%" or "1.5GiB", or NaN if there isn't one."""
    match = re.match(r"\s*([0-9]*\.?[0-9]+)", str(text or ""))
    return float(match.group(1)) if match else float("nan")


def to_bytes(text: str) -> float:
    """"1.5GiB" as bytes. NaN when it cannot be read.

    Both engines print human units here and neither prints raw bytes, so
    this is the only way to compare two containers or sort a column.
    """
    raw = str(text or "").strip()
    value = _number(raw)
    if value != value:                       # NaN
        return value
    unit = raw[len(re.match(r"\s*[0-9]*\.?[0-9]+", raw).group(0)):].strip()
    scale = {"b": 1, "kb": 10 ** 3, "mb": 10 ** 6, "gb": 10 ** 9,
             "tb": 10 ** 12, "kib": 1024, "mib": 1024 ** 2,
             "gib": 1024 ** 3, "tib": 1024 ** 4, "": 1}
    return value * scale.get(unit.casefold(), float("nan"))


def human(size: float) -> str:
    """Bytes as something readable, or an em dash for a number we do not have."""
    if size != size:
        return "—"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024
    return "—"


def _first(item: dict, *names):
    for name in names:
        if name in item and item[name] not in (None, ""):
            return item[name]
    return ""


def parse(text: str, engine: str = "docker") -> dict:
    """One snapshot, keyed by container name AND by short id.

    Keyed by both on purpose: the table knows a container by whatever the
    listing called it, and the two engines disagree — Docker's stats print
    the name, Podman's print the name without a leading slash and an id
    beside it. Looking a row up by one key and failing silently would
    leave the column empty on a machine where everything works.
    """
    found = {}
    items = []
    if engine == "podman":
        # Podman answers with a JSON array; Docker with one object per line.
        try:
            loaded = json.loads(text) if text.strip() else []
            items = loaded if isinstance(loaded, list) else [loaded]
        except (json.JSONDecodeError, TypeError):
            items = []
    else:
        for line in (text or "").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(_first(item, "Name", "name", "Names")).lstrip("/")
        ident = str(_first(item, "ID", "Id", "id", "ContainerID"))
        cpu = _number(_first(item, "CPUPerc", "CPU", "cpu_percent", "CPUPercent"))
        used, limit = _memory(item)
        entry = {
            "cpu": cpu,
            "mem": used,
            "mem_limit": limit,
            "mem_percent": (used / limit * 100.0)
                           if (used == used and limit == limit and limit)
                           else _number(_first(item, "MemPerc", "MemPercent")),
            "net": str(_first(item, "NetIO", "net_io", "NetInput")),
            "block": str(_first(item, "BlockIO", "block_io")),
            "pids": str(_first(item, "PIDs", "PIDS", "pids")),
            "name": name,
            "id": ident[:12],
        }
        if name:
            found[name] = entry
        if ident:
            found[ident[:12]] = entry
    return found


def _memory(item: dict) -> tuple:
    """(used, limit) in bytes, each NaN when the engine did not say.

    Docker prints "MemUsage": "12.5MiB / 1.94GiB". Podman splits it into
    MemUsage and MemLimit, and on a rootless machine with no cgroup v2
    delegation it prints neither — which must stay NaN rather than become
    a zero that reads as "uses no memory".
    """
    usage = str(_first(item, "MemUsage", "mem_usage", "MemoryUsage"))
    if "/" in usage:
        left, _, right = usage.partition("/")
        return to_bytes(left), to_bytes(right)
    used = to_bytes(usage) if usage else float("nan")
    limit = to_bytes(str(_first(item, "MemLimit", "mem_limit", "MemoryLimit")))
    return used, limit


def argv(provider, target, engine: str) -> list:
    """The command for one snapshot, aimed at this target.

    `--no-stream` is not optional. Without it the command never returns,
    and a table that refreshes would leave one of these running per tick
    until the machine gave up.
    """
    from .providers.containers import connection_args
    base = [provider.binary] + connection_args(provider, target)
    if engine == "podman":
        return base + ["stats", "--no-stream", "--format", "json"]
    return base + ["stats", "--no-stream", "--format", "{{json .}}"]


def read(provider, target, engine: str, timeout: float = 20.0) -> tuple:
    """(stats, error). Never raises; an engine that cannot measure is normal.

    Plenty of working setups cannot produce these numbers — rootless
    Podman without cgroup v2 delegation is the common one — and that is a
    reason to leave the column empty, not to show an error over a table
    that is otherwise correct.
    """
    ok, text = provider._cli(argv(provider, target, engine), timeout=timeout)
    if not ok:
        return {}, (text or "").splitlines()[0] if text else "no answer"
    return parse(text, engine), ""


def collect(sources, log_error=None) -> dict:
    """Snapshots from every source, keyed by (engine_id, target, name).

    ⚠️ Only for sources that have a running container. A snapshot costs a
    real command, and taking one for a context whose containers are all
    stopped is a second of waiting for a table full of dashes.
    """
    found = {}
    for provider, target, engine_id, has_running in sources:
        if engine_id not in ENGINES or not has_running:
            continue
        stats, error = read(provider, target, engine_id)
        if error and log_error:
            log_error(f"{engine_id} / {getattr(target, 'name', '')}: {error}")
        for key, entry in stats.items():
            found[(engine_id, getattr(target, "name", ""), key)] = entry
    return found


def for_row(snapshot: dict, row: dict) -> dict:
    """This row's numbers, looked up by name and then by id."""
    where = (row.get("engine_id"), row.get("target"))
    for key in (row.get("name"), str(row.get("id") or "")[:12]):
        if key:
            entry = snapshot.get((where[0], where[1], key))
            if entry:
                return entry
    return {}


def cpu_text(entry: dict) -> str:
    value = entry.get("cpu", float("nan"))
    return "—" if value != value else f"{value:.1f}%"


def memory_text(entry: dict) -> str:
    """Used, and the limit when there is one — "190MB / 2.0GB".

    The limit matters more than the figure beside it: a container at 90% of
    its own limit is about to be killed, and without the denominator there
    is no way to see that coming.
    """
    used = entry.get("mem", float("nan"))
    limit = entry.get("mem_limit", float("nan"))
    if used != used:
        return "—"
    if limit != limit or not limit:
        return human(used)
    return f"{human(used)} / {human(limit)}"


__all__ = ["ENGINES", "BUSY_CPU", "TIGHT_MEMORY", "to_bytes", "human",
           "parse", "argv", "read", "collect", "for_row", "cpu_text",
           "memory_text"]
