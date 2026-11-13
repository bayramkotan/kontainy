"""
kontainy — Containers page

Every container from every engine, in one table — and, for each one, WHERE
it lives: which engine, which context or connection, and what kind of socket
that is. Without those columns the page answered "here are your containers"
while quietly leaving out the ones on another context, which is the oldest
way to lose a container in this ecosystem.

It reads through the providers, the same as the Docker and Podman pages. It
used to open the engine sockets itself, which meant it saw nothing at all on
Windows, where Docker listens on a named pipe: the Docker page showed three
containers while this page showed none.
"""

from __future__ import annotations

import json

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QHeaderView, QLabel, QLineEdit, QSplitter,
    QTableWidget, QTableWidgetItem, QTabWidget, QTextBrowser, QVBoxLayout,
    QWidget,
)

from ...core import discovery, stats
from ...core.providers import by_id
from ...core.providers.base import socket_kind
from ...utils.config import log
from ...utils.workers import CallableJob, run_job
from .base import Page
from .tableactions import TableActions

STATE_COLORS = {
    "running": "#a6e3a1", "exited": "#9399b2", "created": "#89dceb",
    "paused": "#f9e2af", "dead": "#f38ba8", "stopped": "#9399b2",
}

#: Which technologies a unified page gathers. The page itself is the same;
#: only this list and a couple of labels differ, which is why "All machines"
#: is a subclass rather than a second page written twice.
ENGINES = ("docker", "podman", "incus", "lxd")
MACHINE_ENGINES = ("libvirt", "hyperv", "vmware")


class EngineChoice:
    """One place a container can be created: an engine on one of its targets.

    Carries what the create dialog needs, and the provider and target so the
    container is created with that engine's own CLI rather than by opening
    its socket.
    """

    reachable = True

    def __init__(self, provider, target, kind: str):
        self.provider = provider
        self.target = target
        self.family = provider.id
        self.address = target.address if target else ""
        self.kind = kind
        name = target.name if target else "(local)"
        self.title = f"{provider.name} \u00b7 {name}"
        if kind:
            self.title += f"  ({kind})"


def engine_choices(engines=("docker", "podman")) -> list:
    """Every engine and target that answered, for the create dialog.

    Creation still goes through Docker and Podman only; Incus and LXD are
    listed on the page but their create is not written yet.
    """
    out = []
    for engine_id in engines:
        provider = by_id(engine_id)
        if provider is None or not provider.shown_here() \
                or not provider.available():
            continue
        for target in provider.targets():
            listing = provider.objects(target)
            if listing.error:
                continue
            out.append(EngineChoice(provider, target,
                                    socket_kind(target.address)))
    return out


def _first(item: dict, *keys) -> str:
    """The first key that is actually there.

    Every technology spells its columns differently — Names, name, Name,
    State, state — and a page that assumes Docker's shows a row with an
    empty name for Hyper-V.
    """
    for key in keys:
        if key and item.get(key) not in (None, ""):
            return str(item[key])
    return ""


def _collect_all(engines=ENGINES) -> list:
    """Every container on every context and connection of both engines.

    One row per container, tagged with the target it came from, so the table
    can say where each one lives and the filter can narrow to one source.
    """
    rows = []
    for engine_id in engines:
        provider = by_id(engine_id)
        if provider is None or not provider.shown_here() \
                or not provider.available():
            continue
        for target in provider.targets():
            listing = provider.objects(target)
            if listing.error:
                log().warning("%s / %s: %s", provider.name, target.name,
                              listing.error.splitlines()[0])
                continue
            for item in listing.rows:
                # Every technology names its columns differently: Docker has
                # Names and Image, Incus has name and type, virsh has name
                # and state. The page reads them through the provider's own
                # key rather than assuming Docker's.
                rows.append({
                    "engine": provider.name, "engine_id": engine_id,
                    "target": target.name, "address": target.address,
                    "kind": socket_kind(target.address),
                    "active": target.active,
                    "name": _first(item, provider.object_key, "Names",
                                   "name", "Name"),
                    "image": _first(item, "Image", "image", "os", "type",
                                    "Guest OS", "guest"),
                    "state": _first(item, "State", "state", "Status").lower(),
                    "status": _first(item, "Status", "status", "uptime",
                                     "Uptime"),
                    "ports": _first(item, "Ports", "ports"),
                    "raw": item,
                })
    return rows


class ContainersPage(TableActions, Page):
    NAME = "containers"
    TITLE = "All containers"
    ICON = "📦"
    SUBTITLE = ("Containers from every engine, every context and every "
                "connection, in one table \u2014 with the source of each one "
                "named, so a container is never \"lost\".")

    #: What this page gathers, and what it calls the things it found.
    ENGINES = ENGINES
    NOUN = "containers"
    SECOND_COLUMN = "Image"
    CAN_CREATE = True
    SHOW_PORTS = True
    #: Hypervisors have no `stats`, so the machines page turns this off
    #: rather than showing two columns that can only ever hold dashes.
    SHOW_STATS = True

    def build(self) -> None:
        self.endpoints = []
        self.rows = []
        self.filtered = []
        self.snapshot = {}
        self._stats_busy = False
        self._timer = QTimer(self)
        # Five seconds, not one. A snapshot is a real command per context,
        # and a number that moves faster than you can read it is decoration.
        self._timer.setInterval(5000)
        self._timer.timeout.connect(self._tick)

        if self.CAN_CREATE:
            self.add_tool_button("\u2795  New", self._new_container,
                                 kind="primary")
            self.add_tool_button("\U0001f4e6  Template\u2026",
                                 self._from_template)
        self.refresh_btn = self.add_tool_button(
            "\U0001f504  Refresh", self.refresh)
        if self.SHOW_STATS:
            self.live_btn = self.add_tool_button("\u23f8  Live", None)
            self.live_btn.setCheckable(True)
            self.live_btn.setToolTip(
                "Read CPU and memory from every engine every five seconds. "
                "Each tick is one command per context, so it stops by "
                "itself whenever this page is not on screen.")
            self.live_btn.toggled.connect(self._toggle_live)
        self.add_tool_button("\u25b6  Start", lambda: self._act("start"))
        self.add_tool_button("\u25a0  Stop", lambda: self._act("stop"))
        self.add_tool_button("\u21bb  Restart", lambda: self._act("restart"))
        self.add_tool_button("\U0001f5d1  Remove", lambda: self._act("remove"),
                             kind="danger")

        self.source = QComboBox()
        self.source.setMinimumWidth(240)
        self.source.setToolTip(
            "Which engine and which context or connection to show. "
            "The active one of each engine is marked.")
        self.source.currentIndexChanged.connect(self._apply_filter)
        self.toolbar.addWidget(QLabel("Source:"))
        self.toolbar.addWidget(self.source)
        self.activate_btn = self.add_tool_button(
            "\u2714  Make active", self._activate_source)
        self.activate_btn.setToolTip(
            "Make the selected context or connection the active one for "
            "its engine \u2014 the command is shown first.")

        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter: name, image, engine, state\u2026")
        self.search.textChanged.connect(self._apply_filter)
        self.search.setMinimumWidth(240)
        self.toolbar.addWidget(self.search, 1)

        self.count_label = QLabel("—")
        self.toolbar.addWidget(self.count_label)

        split = QSplitter(Qt.Vertical)

        headers = ["Engine", "Context / Connection", "Name",
                   self.SECOND_COLUMN, "State", "Status"]
        if self.SHOW_STATS:
            headers += ["CPU", "Memory"]
        headers.append("Socket")
        self.table = QTableWidget(0, len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        # Several rows at once, as on a technology's own page: removing four
        # containers is one request, not four clicks.
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.currentCellChanged.connect(self._show_detail)
        self.wire_table()
        split.addWidget(self.table)

        self.detail = QTabWidget()
        self.tab_summary = QTextBrowser()
        self.tab_ports = QTextBrowser()
        self.tab_raw = QTextBrowser()
        self.detail.addTab(self.tab_summary, "Summary")
        if self.SHOW_PORTS:
            self.detail.addTab(self.tab_ports, "Ports")
        self.detail.addTab(self.tab_raw, "Raw JSON")
        split.addWidget(self.detail)
        split.setSizes([420, 260])

        self.body.addWidget(split, 1)

    def set_endpoints(self, endpoints) -> None:
        self.endpoints = endpoints
        self.refresh()

    def apply_theme(self) -> None:
        super().apply_theme()
        c = self.colors()
        self.table.setStyleSheet(
            f"QTableWidget {{ font-size: {c['fs_base'] + 2}px; }}"
            f"QTableWidget::item {{ padding: 7px 10px; }}"
            f"QHeaderView::section {{ font-size: {c['fs_base'] + 1}px;"
            f" font-weight: bold; padding: 9px; }}")

    def on_shown(self) -> None:
        if not self.rows:
            self.refresh()

    def refresh(self) -> None:
        self.refresh_btn.setEnabled(False)
        self.busy.emit(True)
        self.status.emit("Reading every context and connection\u2026")
        run_job(CallableJob(_collect_all, self.ENGINES), self._fill,
                self._failed)

    def _sources(self) -> list:
        """(engine_id, target name) pairs seen in the rows, active first."""
        seen = {}
        for row in self.rows:
            seen.setdefault((row["engine_id"], row["target"]),
                            (row["engine"], row["active"], row["kind"]))
        return [(key, value) for key, value in seen.items()]

    def _fill_sources(self) -> None:
        current = self.source.currentData()
        self.source.blockSignals(True)
        self.source.clear()
        self.source.addItem("All sources", None)
        for (engine_id, target), (engine, active, kind) in self._sources():
            mark = "\u25cf " if active else "   "
            label = f"{mark}{engine} \u00b7 {target}"
            if kind:
                label += f"  ({kind})"
            self.source.addItem(label, (engine_id, target))
        index = self.source.findData(current)
        self.source.setCurrentIndex(index if index >= 0 else 0)
        self.source.blockSignals(False)

    def _failed(self, message: str) -> None:
        self.refresh_btn.setEnabled(True)
        self.busy.emit(False)
        self.status.emit(f"Listing failed: {message}")

    def _fill(self, rows) -> None:
        self.rows = rows
        self.refresh_btn.setEnabled(True)
        self.busy.emit(False)
        self._fill_sources()
        self._apply_filter()
        log().info("%s: %d from %d source(s)", self.TITLE, len(rows),
                   len(self._sources()))

    def _apply_filter(self) -> None:
        text = self.search.text().strip().casefold()
        chosen = self.source.currentData()
        rows = self.rows
        if chosen:
            rows = [r for r in rows
                    if (r["engine_id"], r["target"]) == tuple(chosen)]
        if text:
            rows = [r for r in rows if text in " ".join(
                [r["name"], r["image"], r["engine"], r["state"],
                 r["target"], r["address"]]).casefold()]
        self.filtered = list(rows)
        self._update_activate_button()

        self.table.setRowCount(0)
        for row in self.filtered:
            r = self.table.rowCount()
            self.table.insertRow(r)
            target = row["target"] + (" \u25cf" if row["active"] else "")
            cells = [row["engine"], target, row["name"], row["image"],
                     row["state"], row["status"]]
            entry = {}
            if self.SHOW_STATS:
                entry = stats.for_row(self.snapshot, row)
                cells += [stats.cpu_text(entry), stats.memory_text(entry)]
            cells.append(row["kind"])
            for col, text_ in enumerate(cells):
                item = QTableWidgetItem(str(text_))
                if col == 4:
                    item.setForeground(QColor(STATE_COLORS.get(text_, "#9399b2")))
                self.table.setItem(r, col, item)
            if entry:
                self._colour_stats(r, entry)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)

        running = sum(1 for x in self.filtered if x["state"] == "running")
        sources = len(self._sources())
        self.count_label.setText(
            f"{len(self.filtered)}/{len(self.rows)} {self.NOUN} \u00b7 "
            f"{running} running \u00b7 {sources} "
            f"source{'s' if sources != 1 else ''}")
        if self.filtered:
            self.table.selectRow(0)

    # --- live figures ------------------------------------------------------
    def _colour_stats(self, row: int, entry: dict) -> None:
        """Amber on a busy container, red on one near its memory limit.

        The memory one is the only number in this table that predicts an
        outage rather than describing the past: a container at 90% of its
        own limit is about to be killed by the kernel, and the figure is
        worth nothing if it looks like all the others.
        """
        cpu = entry.get("cpu", float("nan"))
        if cpu == cpu and cpu >= stats.BUSY_CPU:
            item = self.table.item(row, 6)
            if item:
                item.setForeground(QColor("#f9e2af"))
        percent = entry.get("mem_percent", float("nan"))
        if percent == percent and percent >= stats.TIGHT_MEMORY:
            item = self.table.item(row, 7)
            if item:
                item.setForeground(QColor("#f38ba8"))

    def _stats_sources(self) -> list:
        """(provider, target, engine_id, has_running) for each source.

        ⚠️ A snapshot costs a real command, so a context whose containers
        are all stopped is skipped: there is nothing to measure there and
        waiting a second for a table of dashes is worse than no column.
        """
        seen = {}
        for row in self.rows:
            key = (row["engine_id"], row["target"])
            running = row["state"] == "running"
            if key in seen:
                seen[key] = seen[key] or running
            else:
                seen[key] = running
        found = []
        for (engine_id, target_name), has_running in seen.items():
            provider = by_id(engine_id)
            if provider is None:
                continue
            target = next((x for x in provider.targets()
                           if x.name == target_name), None)
            found.append((provider, target, engine_id, has_running))
        return found

    def _read_stats(self) -> dict:
        return stats.collect(self._stats_sources(), log_error=log().debug)

    def _tick(self) -> None:
        """One snapshot, off the UI thread, and never two at once.

        Without the in-flight guard a slow engine would have the timer
        stacking requests behind it until the machine gave up — which is
        exactly the failure people blame on the app rather than the socket.
        """
        if self._stats_busy or not self.live_btn.isChecked():
            return
        if not self.isVisible() or not self.rows:
            return
        self._stats_busy = True

        def done(snapshot) -> None:
            self._stats_busy = False
            self.snapshot = snapshot
            self._apply_filter()

        def failed(_message) -> None:
            self._stats_busy = False

        run_job(CallableJob(self._read_stats), done, failed)

    def _toggle_live(self, on: bool) -> None:
        self.live_btn.setText("⏺  Live" if on else "⏸  Live")
        if on:
            self._timer.start()
            self._tick()
        else:
            self._timer.stop()
            self.snapshot = {}
            self._apply_filter()

    def hideEvent(self, event) -> None:
        """Nothing runs while the page is not on screen.

        A timer that keeps shelling out to every engine behind a page
        nobody is looking at is how a desktop tool earns a reputation for
        making the fans spin.
        """
        self._timer.stop()
        super().hideEvent(event)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self.SHOW_STATS and self.live_btn.isChecked():
            self._timer.start()

    def _current(self):
        r = self.table.currentRow()
        if r < 0 or r >= len(self.filtered):
            return None
        return self.filtered[r]

    def _show_detail(self, row, *_) -> None:
        item = self._current()
        if item is None:
            for tab in (self.tab_summary, self.tab_ports, self.tab_raw):
                tab.clear()
            return

        provider = by_id(item["engine_id"])
        noun = provider.target_noun if provider else "Target"
        second = item["image"] or "\u2014"
        self.tab_summary.setHtml(
            f"<h2>{item['name']}</h2>"
            f"<table cellpadding='4'>"
            f"<tr><td><b>Engine</b></td><td>{item['engine']}</td></tr>"
            f"<tr><td><b>{noun}</b></td><td>{item['target']}"
            f"{' — active' if item['active'] else ''}</td></tr>"
            f"<tr><td><b>Socket</b></td><td><code>{item['address']}</code>"
            f"{'<br>' + item['kind'] if item['kind'] else ''}</td></tr>"
            f"<tr><td><b>{self.SECOND_COLUMN}</b></td>"
            f"<td>{second}</td></tr>"
            f"<tr><td><b>State</b></td><td>{item['state']} \u2014 "
            f"{item['status']}</td></tr>"
            f"</table>")

        ports = item["ports"]
        if ports:
            rows_html = "".join(f"<tr><td><code>{part.strip()}</code></td></tr>"
                                for part in ports.split(",") if part.strip())
            self.tab_ports.setHtml(
                f"<table cellpadding='4'>{rows_html}</table>"
                f"<p>Ports are fixed when a container is created. To change "
                f"them, open the {item['engine']} page and use "
                f"<b>Ports\u2026</b>, which recreates the container without "
                f"losing its volumes.</p>")
        else:
            self.tab_ports.setHtml("<p>No published ports.</p>")

        self.tab_raw.setHtml(
            f"<pre>{json.dumps(item['raw'], indent=2, ensure_ascii=False)}</pre>")

        # The command that describes THIS object, asked of its own provider:
        # "libvirt --connection system inspect win11" is not a command anyone
        # can run, and that is what assuming Docker's shape produced on the
        # machines page.
        self.show_command(self._detail_command(item),
                          engine=item["engine_id"], record=False)

    def _detail_command(self, item) -> str:
        """Asked of the provider, because only it knows its own words."""
        provider, target = self._target_of(item)
        if provider is None:
            return ""
        return provider.describe_command(target, item["raw"]) or ""

    # --- creation ----------------------------------------------------------
    def _new_container(self, preset: str = "") -> None:
        """Offer every context and connection of both engines.

        This used to ask `discovery` for reachable sockets and open them
        itself, so on Windows — where Docker listens on a named pipe — the
        New button found nothing and did nothing at all. The choices now
        come from the providers, the same as the table.
        """
        self.endpoints = engine_choices(("docker", "podman"))
        if not self.endpoints:
            self.status.emit(
                "No container engine answered. Start Docker or Podman from "
                "its own page, then try again.")
            return
        from ..dialogs.create_container import CreateContainerDialog
        dialog = CreateContainerDialog(self.endpoints, self, preset=preset)
        dialog.created.connect(self._on_created)
        dialog.exec()

    def _on_created(self, container_id: str) -> None:
        self.status.emit(f"Container created: {container_id[:12]}")
        self.refresh()

    def _from_template(self) -> None:
        from ...core import templates as tpl
        from PySide6.QtWidgets import QInputDialog
        labels = [f"{t.category} \u00b7 {t.name}  \u2014  {t.image}"
                  for t in tpl.TEMPLATES]
        choice, ok = QInputDialog.getItem(
            self, "Start from a template",
            "Ready-made definitions with ports, volumes, environment, "
            "healthcheck and a sane capability set already filled in:",
            labels, 0, False)
        if not ok:
            return
        self._new_container(tpl.TEMPLATES[labels.index(choice)].id)

    def _target_of(self, item):
        provider = by_id(item["engine_id"])
        if provider is None:
            return None, None
        target = next((x for x in provider.targets()
                       if x.name == item["target"]), None)
        return provider, target

    DEFAULT_VERB = "logs"
    REMOVE_VERB = "remove"

    def row_label(self, row: dict) -> str:
        return str(row.get("name") or row.get("id") or "")

    def actions_for_rows(self, rows: list) -> list:
        """The menu, built from the provider — never a second list.

        One row gets the engine's own actions for it. Several get the
        bulk builder, which returns nothing for a verb that does not fit
        every row, so the menu simply does not offer it: asking to remove
        four containers must not quietly remove three.
        """
        from ...core.providers.base import actions_for_selection
        provider, target = self._target_of(rows[0])
        if provider is None:
            return []
        if len(rows) == 1:
            return [provider.prepare(a) for a in
                    provider.object_actions(target, rows[0]["raw"])]

        # A selection can span engines and contexts; a single command
        # cannot. Offer the bulk verbs only while it is one source.
        sources = {(r["engine_id"], r["target"]) for r in rows}
        if len(sources) > 1:
            return []
        built = []
        for verb in ("start", "stop", "restart", "remove"):
            one = actions_for_selection(provider, target,
                                        [r["raw"] for r in rows], verb)
            if one is not None:
                built.append(provider.prepare(one))
        return built

    def run_action(self, action) -> None:
        self._run(action)

    def _selected_items(self) -> list:
        indexes = sorted({index.row() for index
                          in self.table.selectionModel().selectedRows()})
        return [self.filtered[i] for i in indexes if i < len(self.filtered)]

    def _act_on_selection(self, action: str, items: list) -> None:
        """The selection can span engines and contexts, so each group is
        asked of its own provider: one selection, the right command for
        every row."""
        from ...core.providers.base import actions_for_selection
        groups = {}
        for item in items:
            groups.setdefault((item["engine_id"], item["target"]),
                              []).append(item)
        wanted = {"start": "start", "stop": "stop", "restart": "restart",
                  "remove": "remove"}[action]
        for (engine_id, target_name), rows in groups.items():
            provider, target = self._target_of(rows[0])
            if provider is None:
                continue
            built = actions_for_selection(provider, target,
                                          [r["raw"] for r in rows], wanted)
            if built is None:
                self.status.emit(
                    f"{engine_id} / {target_name}: {action} does not apply to "
                    f"all the selected rows")
                continue
            self._run(provider.prepare(built))

    def _act(self, action: str) -> None:
        """Run the engine's own verb on the container, on ITS context.

        The page used to call the engine socket directly, which sent every
        action to whichever engine it had opened rather than the one the
        container actually lives on.
        """
        items = self._selected_items()
        if len(items) > 1:
            self._act_on_selection(action, items)
            return
        item = self._current()
        if item is None:
            return
        provider, target = self._target_of(item)
        if provider is None:
            return
        wanted = {"start": "start", "stop": "stop", "restart": "restart",
                  "remove": "remove", "recreate": "recreate",
                  "rename": "rename"}[action]
        actions = {self._verb(a.label): a
                   for a in provider.object_actions(target, item["raw"])}
        chosen = actions.get(wanted)
        if chosen is None:
            self.status.emit(
                f"{item['name']}: {action} does not apply now "
                f"(state: {item['state'] or 'unknown'})")
            return
        self._run(provider.prepare(chosen))

    @staticmethod
    def _verb(label: str) -> str:
        import re
        return "-".join(re.sub(r"[^A-Za-z0-9]+", " ", label).strip()
                        .lower().split())

    def _open_logs(self, action) -> None:
        """A follow goes to the log viewer, not to the run-once dialog,
        which would wait for a command that never ends."""
        from ..dialogs.logs_viewer import LogsDialog
        self.show_command(" ".join(action.follow), note=action.id,
                          record=False)
        LogsDialog(action, self).exec()

    def _run(self, action) -> None:
        from ..dialogs.run_command import RunCommandDialog
        if action.follow:
            self._open_logs(action)
            return
        self.show_command(action.display(), note=action.id, record=False)
        RunCommandDialog(action, self).exec()
        self.refresh()

    def _update_activate_button(self) -> None:
        chosen = self.source.currentData()
        if not chosen:
            self.activate_btn.setEnabled(False)
            return
        engine_id, target_name = tuple(chosen)
        active = any(r["active"] for r in self.rows
                     if r["engine_id"] == engine_id
                     and r["target"] == target_name)
        self.activate_btn.setEnabled(not active)

    def _activate_source(self) -> None:
        """Make the chosen context or connection the active one.

        This is the same switch as on the engine's own page — from here,
        because this is where someone notices they are looking at the wrong
        one.
        """
        chosen = self.source.currentData()
        if not chosen:
            return
        engine_id, target_name = tuple(chosen)
        provider = by_id(engine_id)
        target = next((x for x in provider.targets()
                       if x.name == target_name), None) if provider else None
        if provider is None or target is None:
            return
        self._run(provider.prepare(provider.activate(target)))


class MachinesPage(ContainersPage):
    """The same table, for the hypervisors.

    KVM, Hyper-V and VMware answer the same question — where is my machine,
    and which host is it on — and the page that answers it for containers
    already knows how to ask every provider in turn, mark the active target
    and act on a selection. Only the list of technologies and three labels
    differ.
    """

    NAME = "machines"
    TITLE = "All machines"
    ICON = "\U0001f5a5"
    SUBTITLE = ("Virtual machines from every hypervisor and every connection, "
                "in one table \u2014 KVM, Hyper-V and VMware side by side, "
                "with the host of each one named.")

    ENGINES = MACHINE_ENGINES
    SHOW_STATS = False
    NOUN = "machines"
    SECOND_COLUMN = "Guest OS"
    CAN_CREATE = False          # ky kvm create does this; the wizard is next
    SHOW_PORTS = False          # a machine publishes no ports
