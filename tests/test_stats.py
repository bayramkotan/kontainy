"""What a container is actually doing — and what we refuse to claim.

The table said what exists and what state it is in, and nothing about what
any of it costs. These tests are mostly about the three ways a figure here
would be worse than no figure: inventing a zero where the machine cannot
measure, streaming a command that never returns, and paying for a snapshot
of containers that are not running.
"""

import json

import pytest

from kontainy.core import stats


DOCKER = "\n".join(json.dumps(x) for x in [
    {"Name": "web", "ID": "a1b2c3d4e5f6", "CPUPerc": "190.42%",
     "MemUsage": "190MiB / 1.94GiB", "MemPerc": "9.57%",
     "NetIO": "1.2kB / 0B", "BlockIO": "0B / 0B", "PIDs": "9"},
    {"Name": "db", "ID": "ffeeddccbbaa", "CPUPerc": "0.03%",
     "MemUsage": "1.80GiB / 1.94GiB", "MemPerc": "92.8%"},
])

PODMAN = json.dumps([
    {"name": "api", "id": "112233445566", "cpu_percent": "12.5%",
     "mem_usage": "", "mem_limit": ""},
    {"name": "cache", "id": "998877665544", "cpu_percent": "0.00%",
     "mem_usage": "8MiB", "mem_limit": "512MiB"},
])


# --- reading two engines that disagree --------------------------------------------
def test_docker_prints_one_object_per_line():
    found = stats.parse(DOCKER, "docker")
    assert stats.cpu_text(found["web"]) == "190.4%"


def test_podman_prints_an_array():
    """Read as Docker's line-per-object output it yields nothing, and
    nothing looks exactly like an engine with no containers."""
    found = stats.parse(PODMAN, "podman")
    assert stats.cpu_text(found["cache"]) == "0.0%"


def test_a_row_is_found_by_name_and_by_id():
    """The table knows a container by whatever the listing called it, and
    looking it up by one key and failing silently would leave the column
    empty on a machine where everything works."""
    found = stats.parse(DOCKER, "docker")
    assert found["web"] is found["a1b2c3d4e5f6"]


def test_a_leading_slash_is_stripped_from_the_name():
    found = stats.parse(json.dumps({"Name": "/web", "CPUPerc": "1%"}),
                        "podman")
    assert "web" in found


# --- the zero we refuse to invent -------------------------------------------------
def test_an_engine_that_cannot_measure_memory_reports_nothing():
    """⚠️ Rootless Podman without cgroup v2 delegation reports no memory at
    all. A 0 B there reads as "this container uses no memory" rather than
    "this machine cannot tell you", which is the opposite of the truth."""
    found = stats.parse(PODMAN, "podman")
    assert stats.memory_text(found["api"]) == "—"
    assert found["api"]["mem"] != found["api"]["mem"]       # NaN


def test_a_cpu_figure_that_is_absent_is_a_dash_not_a_zero():
    found = stats.parse(json.dumps({"Name": "x"}), "podman")
    assert stats.cpu_text(found["x"]) == "—"


def test_garbage_is_no_rows_rather_than_a_crash():
    assert stats.parse("not json at all", "docker") == {}
    assert stats.parse("", "podman") == {}
    assert stats.parse("[1, 2, 3]", "podman") == {}


# --- units ------------------------------------------------------------------------
@pytest.mark.parametrize("text,expected", [
    ("1KiB", 1024), ("1kB", 1000), ("1MiB", 1024 ** 2),
    ("1.5GiB", int(1.5 * 1024 ** 3)), ("512B", 512), ("0B", 0),
])
def test_both_engines_human_units_are_understood(text, expected):
    assert round(stats.to_bytes(text)) == expected


def test_a_unit_nobody_prints_is_not_guessed_at():
    assert stats.to_bytes("12 parsecs") != stats.to_bytes("12 parsecs")


def test_the_limit_is_kept_beside_the_figure():
    """A container at 90% of its own limit is about to be killed, and
    without the denominator there is no way to see that coming."""
    found = stats.parse(DOCKER, "docker")
    assert stats.memory_text(found["db"]) == "1.8GB / 1.9GB"
    assert found["db"]["mem_percent"] > stats.TIGHT_MEMORY


def test_a_percentage_is_computed_from_the_two_figures_not_trusted():
    """Docker prints MemPerc too, but it is the percentage of the HOST on
    a container with no limit, which is a different question."""
    found = stats.parse(
        json.dumps({"Name": "x", "MemUsage": "1GiB / 2GiB",
                    "MemPerc": "3.1%"}), "docker")
    assert round(found["x"]["mem_percent"]) == 50


# --- the command ------------------------------------------------------------------
class FakeTarget:
    def __init__(self, name="default"):
        self.name = name
        self.address = "unix:///x"
        self.active = True


class FakeProvider:
    def __init__(self, id="docker", answer=DOCKER, ok=True):
        self.id = id
        self.binary = id
        self.answer = answer
        self.ok = ok
        self.calls = []

    def _cli(self, argv, timeout=20.0):
        self.calls.append(list(argv))
        return self.ok, self.answer


def test_the_snapshot_never_streams():
    """⚠️ `docker stats` without --no-stream never returns. On a table that
    refreshes, that leaves one running per tick until the machine gives
    up — and people blame the app, not the flag."""
    for engine in ("docker", "podman"):
        argv = stats.argv(FakeProvider(engine), FakeTarget(), engine)
        assert "--no-stream" in argv


def test_each_engine_is_asked_in_its_own_format():
    assert stats.argv(FakeProvider(), FakeTarget(), "docker")[-1] == "{{json .}}"
    assert stats.argv(FakeProvider("podman"), FakeTarget(),
                      "podman")[-1] == "json"


def test_the_command_is_aimed_at_its_own_target():
    argv = stats.argv(FakeProvider(), FakeTarget("prod"), "docker")
    assert argv[:3] == ["docker", "--context", "prod"]


def test_podman_without_a_connection_is_not_given_one():
    """The same (local) trap the Images page fell into — avoided by using
    the one implementation rather than writing a second."""
    from kontainy.core.providers.containers import PodmanProvider
    argv = stats.argv(PodmanProvider(), FakeTarget("(local)"), "podman")
    assert "--connection" not in argv


def test_an_engine_that_refuses_is_not_an_error_on_screen():
    """Plenty of working setups cannot produce these numbers, and that is
    a reason to leave a column empty, not to shout over a correct table."""
    found, error = stats.read(FakeProvider(ok=False, answer="nope"),
                              FakeTarget(), "docker")
    assert found == {} and error


# --- cost -------------------------------------------------------------------------
def test_a_source_with_nothing_running_is_never_asked():
    """⚠️ A snapshot is a real command. Taking one for a context whose
    containers are all stopped is a second of waiting for a table of
    dashes."""
    idle, busy = FakeProvider(), FakeProvider()
    stats.collect([(idle, FakeTarget(), "docker", False),
                   (busy, FakeTarget(), "docker", True)])
    assert idle.calls == [] and busy.calls


def test_an_engine_with_no_stats_command_is_skipped():
    hypervisor = FakeProvider("libvirt")
    stats.collect([(hypervisor, FakeTarget(), "libvirt", True)])
    assert hypervisor.calls == []


def test_one_source_failing_does_not_stop_the_others():
    good, bad = FakeProvider(), FakeProvider(ok=False, answer="boom")
    said = []
    found = stats.collect([(bad, FakeTarget("a"), "docker", True),
                           (good, FakeTarget("b"), "docker", True)],
                          log_error=said.append)
    assert found and said


def test_a_row_finds_its_own_numbers_and_not_another_contexts():
    """Two contexts can hold a container with the same name, and showing
    one's CPU against the other's row is worse than showing none."""
    snapshot = {("docker", "default", "web"): {"cpu": 1.0},
                ("docker", "prod", "web"): {"cpu": 99.0}}
    row = {"engine_id": "docker", "target": "prod", "name": "web", "id": ""}
    assert stats.for_row(snapshot, row)["cpu"] == 99.0


def test_a_row_with_no_snapshot_gets_an_empty_one():
    assert stats.for_row({}, {"engine_id": "docker", "target": "x",
                              "name": "web"}) == {}


# --- the page ---------------------------------------------------------------------
@pytest.fixture
def qt():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def row(name, state="running"):
    return {"engine": "Docker", "engine_id": "docker", "target": "default",
            "name": name, "image": "nginx:1.27", "state": state,
            "status": "Up 2h", "id": name * 2, "address": "unix:///x",
            "kind": "local", "active": True, "ports": "",
            "raw": {"Names": name, "State": state}}


def test_the_table_gains_cpu_and_memory(qt):
    from kontainy.gui.pages.containers import ContainersPage
    page = ContainersPage()
    headers = [page.table.horizontalHeaderItem(c).text()
               for c in range(page.table.columnCount())]
    assert "CPU" in headers and "Memory" in headers


def test_the_machines_page_has_neither(qt):
    """Hypervisors have no `stats`, and two columns that can only ever
    hold dashes are worse than no columns."""
    from kontainy.gui.pages.containers import MachinesPage
    page = MachinesPage()
    headers = [page.table.horizontalHeaderItem(c).text()
               for c in range(page.table.columnCount())]
    assert "CPU" not in headers and "Memory" not in headers


def test_a_busy_container_is_marked_and_a_quiet_one_is_not(qt):
    from kontainy.gui.pages.containers import ContainersPage
    page = ContainersPage()
    page.rows = [row("web"), row("db")]
    page.snapshot = {
        ("docker", "default", "web"): {"cpu": 190.0, "mem": float("nan"),
                                       "mem_limit": float("nan"),
                                       "mem_percent": float("nan")},
        ("docker", "default", "db"): {"cpu": 0.5, "mem": float("nan"),
                                      "mem_limit": float("nan"),
                                      "mem_percent": float("nan")},
    }
    page._apply_filter()
    busy = page.table.item(0, 6).foreground().color().name()
    quiet = page.table.item(1, 6).foreground().color().name()
    assert busy != quiet


def test_a_container_near_its_memory_limit_is_marked_in_red(qt):
    from kontainy.gui.pages.containers import ContainersPage
    page = ContainersPage()
    page.rows = [row("db")]
    page.snapshot = {("docker", "default", "db"): {
        "cpu": 0.5, "mem": 1.9e9, "mem_limit": 2.0e9, "mem_percent": 95.0}}
    page._apply_filter()
    assert page.table.item(0, 7).foreground().color().name() == "#f38ba8"


def test_a_stopped_container_shows_dashes_not_zeros(qt):
    from kontainy.gui.pages.containers import ContainersPage
    page = ContainersPage()
    page.rows = [row("old", "exited")]
    page.snapshot = {}
    page._apply_filter()
    assert page.table.item(0, 6).text() == "—"
    assert page.table.item(0, 7).text() == "—"


def test_live_is_off_until_it_is_switched_on(qt):
    """It costs a command per context per tick, so it is a choice rather
    than something that starts happening to you."""
    from kontainy.gui.pages.containers import ContainersPage
    page = ContainersPage()
    assert page.live_btn.isCheckable()
    assert not page.live_btn.isChecked()
    assert not page._timer.isActive()


def test_the_timer_stops_when_the_page_is_hidden(qt):
    """A timer shelling out to every engine behind a page nobody is
    looking at is how a desktop tool earns a reputation for making the
    fans spin."""
    from PySide6.QtGui import QHideEvent
    from kontainy.gui.pages.containers import ContainersPage
    page = ContainersPage()
    page._timer.start()
    page.hideEvent(QHideEvent())
    assert not page._timer.isActive()


def test_two_snapshots_never_run_at_once(qt):
    """Without the guard a slow engine has the timer stacking requests
    behind it until the machine gives up."""
    from kontainy.gui.pages.containers import ContainersPage
    page = ContainersPage()
    page.rows = [row("web")]
    page.live_btn.setChecked(True)
    page._stats_busy = True
    started = []
    page._read_stats = lambda: started.append(1) or {}
    page._tick()
    assert started == []


def test_the_sources_say_which_ones_have_something_running(qt):
    from kontainy.gui.pages.containers import ContainersPage
    page = ContainersPage()
    page.rows = [row("old", "exited")]
    found = page._stats_sources()
    assert found and found[0][3] is False
    page.rows.append(row("web"))
    assert page._stats_sources()[0][3] is True
