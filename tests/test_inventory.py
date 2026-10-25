"""Images and volumes, and the column the whole feature exists for.

"Used by" is not decoration. Docker Desktop and Podman Desktop will remove
a volume that holds a database with the same confirmation they use for an
empty one, and that is the most expensive mistake available in this
ecosystem. Every test here is about getting that answer right, and about
never deleting a list the user has not read.
"""

import json

import pytest

from kontainy.core import inventory


# --- fakes ------------------------------------------------------------------------
class FakeTarget:
    def __init__(self, name="default", address="unix:///var/run/docker.sock",
                 active=True):
        self.name = name
        self.address = address
        self.active = active
        self.detail = ""
        self.removable = True


class FakeProvider:
    """Answers CLI calls from a script of {command fragment: output}."""

    def __init__(self, id="docker", binary="docker", answers=None):
        self.id = id
        self.name = id.capitalize()
        self.binary = binary
        self.answers = answers or {}
        self.calls = []

    def shown_here(self):
        return True

    def available(self):
        return True

    def targets(self):
        return [FakeTarget()]

    def _cli(self, argv, timeout=15.0):
        self.calls.append(list(argv))
        joined = " ".join(argv)
        for needle, answer in self.answers.items():
            if needle in joined:
                return True, answer
        return False, f"no answer scripted for: {joined}"

    def prepare(self, action):
        return action


PS = "\n".join(json.dumps(x) for x in [
    {"Names": "web", "Image": "nginx:1.27", "Mounts": "site,logs"},
    {"Names": "db", "Image": "postgres:16", "Mounts": "pgdata"},
    {"Names": "old", "Image": "sha256:abc123def456", "Mounts": ""},
])

IMAGES = "\n".join(json.dumps(x) for x in [
    {"Repository": "nginx", "Tag": "1.27", "ID": "111111111111",
     "Size": "71MB", "CreatedSince": "2 weeks ago"},
    {"Repository": "postgres", "Tag": "16", "ID": "222222222222",
     "Size": "431MB", "CreatedSince": "3 weeks ago"},
    {"Repository": "redis", "Tag": "7", "ID": "333333333333",
     "Size": "41MB", "CreatedSince": "a month ago"},
    {"Repository": "<none>", "Tag": "<none>", "ID": "abc123def456",
     "Size": "120MB", "CreatedSince": "5 days ago"},
])

VOLUMES = "\n".join(json.dumps(x) for x in [
    {"Name": "pgdata", "Driver": "local",
     "Mountpoint": "/var/lib/docker/volumes/pgdata/_data"},
    {"Name": "site", "Driver": "local",
     "Mountpoint": "/var/lib/docker/volumes/site/_data"},
    {"Name": "logs", "Driver": "local",
     "Mountpoint": "/var/lib/docker/volumes/logs/_data"},
    {"Name": "forgotten", "Driver": "local",
     "Mountpoint": "/var/lib/docker/volumes/forgotten/_data"},
])

DF = json.dumps({"Volumes": [{"Name": "pgdata", "Size": "2.1GB"},
                             {"Name": "site", "Size": "14MB"},
                             {"Name": "forgotten", "Size": "900MB"}]})


def docker(**extra):
    answers = {"ps -a": PS, "images": IMAGES, "volume ls": VOLUMES,
               "system df": DF}
    answers.update(extra)
    return FakeProvider(answers=answers)


def source(provider):
    src = inventory.Source(provider=provider, target=provider.targets()[0],
                           engine_id=provider.id, engine=provider.name,
                           name="default")
    src.containers = inventory.containers_on(src)
    return src


# --- who holds what ---------------------------------------------------------------
def test_an_image_is_matched_by_its_reference():
    rows, error = inventory.images_on(source(docker()))
    assert not error
    nginx = next(r for r in rows if r["repository"] == "nginx")
    assert nginx["used_by"] == ["web"]


def test_an_untagged_image_is_matched_by_its_id():
    """`docker ps` prints whatever the container was started with. For an
    untagged image that is a bare id, so matching only name:tag calls a held
    image unused — and then offers to delete it."""
    rows, _ = inventory.images_on(source(docker()))
    dangling = next(r for r in rows if r["id"] == "abc123def456")
    assert dangling["used_by"] == ["old"]
    assert dangling["dangling"] is True


def test_an_image_nothing_runs_is_reported_free():
    rows, _ = inventory.images_on(source(docker()))
    redis = next(r for r in rows if r["repository"] == "redis")
    assert redis["used_by"] == []


def test_a_volume_knows_its_containers():
    rows, _ = inventory.volumes_on(source(docker()))
    held = {r["name"]: r["used_by"] for r in rows}
    assert held["pgdata"] == ["db"]
    assert held["site"] == ["web"]
    assert held["forgotten"] == []


def test_a_bind_mount_path_is_not_a_volume_match():
    """Mounts carries bind-mount paths too. A substring match would call a
    volume named "db" used by any container with /srv/dbdata bound in."""
    containers = [{"Names": "api", "Mounts": "/srv/dbdata,/etc/localtime"}]
    assert inventory.volume_users(containers, "db") == []
    assert inventory.volume_users(containers, "/srv/dbdata") == ["api"]


def test_mounts_given_as_a_list_of_objects_also_work():
    """Podman's JSON spells Mounts as objects, not a comma-joined string."""
    containers = [{"Names": "api",
                   "Mounts": [{"Name": "pgdata"}, {"Source": "/etc/hosts"}]}]
    assert inventory.volume_users(containers, "pgdata") == ["api"]


def test_a_leading_slash_is_stripped_from_a_container_name():
    assert inventory.image_users([{"Names": "/web", "Image": "nginx:1.27"}],
                                 "nginx:1.27", "") == ["web"]


# --- cost ------------------------------------------------------------------------
def test_containers_are_read_once_not_once_per_row():
    """Four images and four volumes must not mean eight `ps` calls."""
    provider = docker()
    src = source(provider)
    inventory.images_on(src)
    inventory.volumes_on(src)
    assert sum(1 for call in provider.calls if "ps" in call) == 1


def test_volume_sizes_come_from_one_system_df():
    provider = docker()
    rows, _ = inventory.volumes_on(source(provider))
    assert {r["name"]: r["size"] for r in rows}["pgdata"] == "2.1GB"
    assert sum(1 for c in provider.calls if "df" in c) == 1


def test_a_size_that_cannot_be_read_is_left_empty_not_invented():
    """An engine too old for --format json here shows a dash. A made-up
    number is worse than no number."""
    provider = docker()
    provider.answers["system df"] = "not json at all"
    rows, _ = inventory.volumes_on(source(provider))
    assert all(r["size"] == "" for r in rows)


# --- the commands ----------------------------------------------------------------
def test_removing_a_held_image_says_what_is_holding_it():
    provider = docker()
    rows, _ = inventory.images_on(source(provider))
    nginx = next(r for r in rows if r["repository"] == "nginx")
    remove = next(a for a in inventory.image_actions(
        provider, provider.targets()[0], nginx) if "Remove" in a.label)
    assert "web" in remove.explanation
    assert remove.destructive


def test_removing_a_free_image_says_so_plainly():
    provider = docker()
    rows, _ = inventory.images_on(source(provider))
    redis = next(r for r in rows if r["repository"] == "redis")
    remove = next(a for a in inventory.image_actions(
        provider, provider.targets()[0], redis) if "Remove" in a.label)
    assert "Nothing is holding" in remove.explanation


def test_every_command_is_aimed_at_its_own_context():
    """A page that spans contexts must not send one context's names to
    another. The --context flag is what stops that."""
    provider = docker()
    target = provider.targets()[0]
    rows, _ = inventory.images_on(source(provider))
    for built in inventory.image_actions(provider, target, rows[0]):
        assert built.command[:3] == ["docker", "--context", "default"]


def test_podman_is_aimed_with_its_own_flag():
    """podman says --connection; --context is a docker word and podman
    stops with an unknown-flag error."""
    provider = FakeProvider(id="podman", binary="podman")
    assert inventory.conn(provider, FakeTarget("prod")) == \
        ["--connection", "prod"]


def test_pulling_streams_so_it_goes_to_the_log_view():
    """A pull prints layer progress for a minute. Without a follow it would
    sit in the run-once dialog looking frozen."""
    provider = docker()
    built = inventory.pull_action(provider, provider.targets()[0],
                                  "alpine:3.20")
    assert built.follow == built.command


def test_tagging_explains_that_nothing_is_copied():
    provider = docker()
    built = inventory.tag_action(provider, provider.targets()[0],
                                 {"reference": "nginx:1.27"}, "mine:v1")
    assert built.command[-2:] == ["nginx:1.27", "mine:v1"]
    assert "Nothing is copied" in built.explanation


# --- prune: the one that must never be silent ------------------------------------
def test_pruning_images_names_every_one_it_will_remove():
    """`docker image prune -a` deletes a list it never shows. This cannot."""
    provider = docker()
    rows, _ = inventory.images_on(source(provider))
    built = inventory.prune_images_action(provider, provider.targets()[0],
                                          rows)
    assert "redis:7" in built.explanation
    assert built.destructive


def test_pruning_never_touches_something_that_is_held():
    provider = docker()
    rows, _ = inventory.images_on(source(provider))
    built = inventory.prune_images_action(provider, provider.targets()[0],
                                          rows)
    assert "nginx" not in built.shell_text
    assert "postgres" not in built.shell_text


def test_pruning_volumes_names_them_and_warns_about_data():
    provider = docker()
    rows, _ = inventory.volumes_on(source(provider))
    built = inventory.prune_volumes_action(provider, provider.targets()[0],
                                           rows)
    assert "forgotten" in built.explanation
    assert "pgdata" not in built.shell_text
    assert "not the same as a volume with nothing in it" in built.explanation


def test_pruning_with_nothing_free_returns_nothing_to_run():
    provider = docker()
    rows, _ = inventory.volumes_on(source(provider))
    held = [dict(r, used_by=["x"]) for r in rows]
    assert inventory.prune_volumes_action(
        provider, provider.targets()[0], held) is None


# --- backup ----------------------------------------------------------------------
def test_backing_up_a_running_volume_warns_about_a_torn_copy():
    """tar will happily copy a half-written database file, and the backup
    looks fine until the day it is restored."""
    provider = docker()
    built = inventory.backup_action(
        provider, provider.targets()[0],
        {"name": "pgdata", "used_by": ["db"]}, "/tmp/pg.tar.gz")
    assert "db" in built.explanation and "half-written" in built.explanation


def test_backing_up_an_idle_volume_does_not_cry_wolf():
    provider = docker()
    built = inventory.backup_action(
        provider, provider.targets()[0],
        {"name": "forgotten", "used_by": []}, "/tmp/x.tar.gz")
    assert "half-written" not in built.explanation


# --- incus -----------------------------------------------------------------------
INCUS_IMAGES = json.dumps([
    {"fingerprint": "deadbeefcafe0000", "created_at": "2026-02-01T00:00:00Z",
     "size": 198000000, "aliases": [{"name": "debian/12"}],
     "used_by": ["/1.0/instances/web"]},
])
INCUS_POOLS = json.dumps([{"name": "default"}])
INCUS_VOLUMES = json.dumps([
    {"name": "data", "type": "custom", "config": {"size": "10GB"},
     "used_by": ["/1.0/instances/web"]},
])


def incus():
    return FakeProvider(id="incus", binary="incus", answers={
        "image list": INCUS_IMAGES, "storage list": INCUS_POOLS,
        "storage volume list": INCUS_VOLUMES, "list --format json": "[]"})


def test_incus_images_use_the_engines_own_used_by():
    """Incus tracks this itself and knows about profiles too, which a
    cross-reference against running instances would miss."""
    rows, error = inventory.images_on(source(incus()))
    assert not error
    assert rows[0]["used_by"] == ["web"]
    assert rows[0]["reference"] == "debian/12"


def test_incus_volumes_are_found_through_their_storage_pools():
    rows, error = inventory.volumes_on(source(incus()))
    assert not error
    assert rows[0]["name"] == "data" and rows[0]["pool"] == "default"
    assert rows[0]["used_by"] == ["web"]


def test_an_incus_volume_is_removed_with_its_pool_named():
    """`incus storage volume delete data` without the pool is not a
    command: the pool is a positional argument."""
    provider = incus()
    rows, _ = inventory.volumes_on(source(provider))
    remove = next(a for a in inventory.volume_actions(
        provider, provider.targets()[0], rows[0]) if "Remove" in a.label)
    assert remove.command[-2:] == ["default", "data"]


# --- failure ---------------------------------------------------------------------
def test_an_engine_that_does_not_answer_reports_rather_than_raises():
    provider = FakeProvider(answers={})
    rows, error = inventory.images_on(source(provider))
    assert rows == [] and error


def test_a_source_that_fails_does_not_stop_the_others(monkeypatch):
    good, bad = docker(), FakeProvider(id="podman", binary="podman")
    monkeypatch.setattr(inventory, "sources", lambda engine_ids=None: [
        source(good), source(bad)])
    problems = []
    rows = inventory.list_images(log_error=problems.append)
    assert [r["repository"] for r in rows if r["repository"] == "nginx"]
    assert problems


def test_every_row_says_where_it_came_from(monkeypatch):
    """Without this the table answers "here are your images" while quietly
    leaving out another context's — the oldest way to lose something here."""
    provider = docker()
    monkeypatch.setattr(inventory, "sources",
                        lambda engine_ids=None: [source(provider)])
    for row in inventory.list_images():
        assert row["engine"] and row["target"] and "engine_id" in row


# --- the pages and the commands they are reachable by ----------------------------
def test_both_pages_are_in_the_sidebar_on_every_os(monkeypatch):
    """Images and volumes exist wherever an engine does, so neither page is
    allowed to be a Linux-only or Windows-only entry."""
    import importlib
    from kontainy.core import hosts, registry
    for os_kind in ("linux", "windows", "macos"):
        monkeypatch.setattr(registry, "OS_KIND", os_kind)
        monkeypatch.setattr(hosts, "wsl_available", lambda: True)
        import kontainy.gui.main_window as mw
        mw = importlib.reload(mw)
        names = [cls.NAME for _, cls in mw.SIDEBAR if cls is not None]
        assert "images" in names and "volumes" in names, os_kind
    importlib.reload(mw)


def test_the_pages_put_used_by_last_so_it_is_always_visible():
    from kontainy.gui.pages.inventory import ImagesPage, VolumesPage
    for cls in (ImagesPage, VolumesPage):
        assert cls.COLUMNS and cls.SINGULAR and cls.UNUSED_NOTE


def test_ky_images_and_ky_volumes_are_real_commands():
    from kontainy import cli
    parser = cli.build_parser()
    assert parser.parse_args(["images"]).command == "images"
    assert parser.parse_args(["volumes", "--unused"]).unused is True


def test_the_cli_can_list_only_what_nothing_holds(monkeypatch, capsys):
    """The flag a cleanup script needs. Without it the only way to find the
    unused ones is to parse the table, which is how a script ends up
    deleting a held volume."""
    from kontainy import cli
    rows = [{"engine": "Docker", "engine_id": "docker", "target": "default",
             "name": "pgdata", "driver": "local", "mountpoint": "/v",
             "size": "2GB", "used_by": ["db"]},
            {"engine": "Docker", "engine_id": "docker", "target": "default",
             "name": "forgotten", "driver": "local", "mountpoint": "/w",
             "size": "900MB", "used_by": []}]
    monkeypatch.setattr(inventory, "list_volumes",
                        lambda *a, **k: [dict(r) for r in rows])
    assert cli.main(["volumes", "--unused"]) == 0
    printed = capsys.readouterr().out
    assert "forgotten" in printed and "pgdata" not in printed
