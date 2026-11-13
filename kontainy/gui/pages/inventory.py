"""
kontainy — Images and Volumes

The two pages Docker Desktop and Podman Desktop have, built on the same
unified skeleton as All containers: every engine, every context, one table,
with the source of each row named.

What makes these two different from a listing is the **Used by** column. An
image or a volume with no name attached to it looks identical whether it is
genuinely rubbish or the data directory of a database somebody stopped last
week, and every tool in this ecosystem offers to delete both with the same
one-line confirmation. Here the holders are counted in the table, named in
the detail pane, and spelled out in the dialog before anything runs.

Prune is the same idea taken to its conclusion: `docker image prune -a`
deletes a list it never shows, so this page does not call it. The unused
rows are already on screen, so removal is an ordinary `rm` of things the
user has just read.
"""

from __future__ import annotations

import json

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QHeaderView, QInputDialog,
    QLabel, QLineEdit, QMessageBox, QSplitter, QTableWidget, QTableWidgetItem,
    QTabWidget, QTextBrowser,
)

from ...core import inventory
from ...core.providers import by_id
from ...utils.config import log
from ...utils.workers import CallableJob, run_job
from .base import Page
from .tableactions import TableActions

HELD = "#f9e2af"          # something is using it — think before removing
FREE = "#9399b2"          # nothing holds it


class StockPage(TableActions, Page):
    """Shared skeleton for the two pages: table, source filter, detail tabs.

    Only the columns, the reader and the actions differ, so they live in the
    subclasses and everything else is written once. The alternative — a
    second page copied and edited — is how All containers and All machines
    would have drifted apart.
    """

    NOUN = "items"
    COLUMNS: list = []            # (title, row key)
    STRETCH = 2

    def build(self) -> None:
        self.rows = []
        self.filtered = []
        self.visited = []
        self.problems = []
        self.build_tools()

        self.refresh_btn = self.add_tool_button("\U0001f504  Refresh",
                                                self.refresh)
        self.source = QComboBox()
        self.source.setMinimumWidth(240)
        self.source.setToolTip("Which engine and which context or connection "
                               "to show. The active one of each is marked.")
        self.source.currentIndexChanged.connect(self._apply_filter)
        self.toolbar.addWidget(QLabel("Source:"))
        self.toolbar.addWidget(self.source)

        self.search = QLineEdit()
        self.search.setPlaceholderText(self.FILTER_HINT)
        self.search.textChanged.connect(self._apply_filter)
        self.search.setMinimumWidth(220)
        self.toolbar.addWidget(self.search, 1)

        self.count_label = QLabel("—")
        self.toolbar.addWidget(self.count_label)

        split = QSplitter(Qt.Vertical)
        titles = ["Engine", "Context / Connection"] + \
                 [title for title, _ in self.COLUMNS] + ["Used by"]
        self.table = QTableWidget(0, len(titles))
        self.table.setHorizontalHeaderLabels(titles)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.currentCellChanged.connect(self._show_detail)
        self.wire_table()
        split.addWidget(self.table)

        self.detail = QTabWidget()
        self.tab_summary = QTextBrowser()
        self.tab_users = QTextBrowser()
        self.tab_raw = QTextBrowser()
        self.detail.addTab(self.tab_summary, "Summary")
        self.detail.addTab(self.tab_users, "Used by")
        self.detail.addTab(self.tab_raw, "Raw JSON")
        split.addWidget(self.detail)
        split.setSizes([420, 260])
        self.body.addWidget(split, 1)

    def build_tools(self) -> None:
        """Buttons before Refresh. Subclasses fill this in."""

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

    # --- reading -----------------------------------------------------------
    def read(self) -> list:
        raise NotImplementedError

    def refresh(self) -> None:
        self.refresh_btn.setEnabled(False)
        self.busy.emit(True)
        self.status.emit(f"Reading {self.NOUN} from every context…")
        run_job(CallableJob(self.read), self._fill, self._failed)

    def _failed(self, message: str) -> None:
        self.refresh_btn.setEnabled(True)
        self.busy.emit(False)
        self.status.emit(f"Listing failed: {message}")

    def _fill(self, stock) -> None:
        self.rows = list(stock.rows)
        self.visited = list(stock.sources)
        self.problems = list(stock.problems)
        self.refresh_btn.setEnabled(True)
        self.busy.emit(False)
        self._fill_sources()
        self._apply_filter()
        log().info("%s: %d from %d source(s), %d unreachable", self.TITLE,
                   len(self.rows), len(self.visited), len(self.problems))
        if self.problems and not self.rows:
            where, why = self.problems[0]
            self.status.emit(f"{where}: {why}")

    def _sources(self) -> list:
        """Every source that was ASKED, not every source that answered.

        Counting them from the rows makes an engine that answered and holds
        nothing vanish from the dropdown, and the page then reports "0 from
        0 sources" — which reads as "nothing answered" when the truth is
        "nothing stored". An empty Docker is not an absent Docker.
        """
        return [((engine_id, target), (engine, active, kind))
                for engine_id, engine, target, kind, active
                in getattr(self, "visited", [])]

    def _fill_sources(self) -> None:
        current = self.source.currentData()
        self.source.blockSignals(True)
        self.source.clear()
        self.source.addItem("All sources", None)
        for (engine_id, target), (engine, active, kind) in self._sources():
            mark = "● " if active else "   "
            label = f"{mark}{engine} · {target}"
            if kind:
                label += f"  ({kind})"
            self.source.addItem(label, (engine_id, target))
        index = self.source.findData(current)
        self.source.setCurrentIndex(index if index >= 0 else 0)
        self.source.blockSignals(False)

    def searchable(self, row: dict) -> str:
        return " ".join(str(row.get(key, "")) for _, key in self.COLUMNS)

    def _apply_filter(self) -> None:
        text = self.search.text().strip().casefold()
        chosen = self.source.currentData()
        rows = self.rows
        if chosen:
            rows = [r for r in rows
                    if (r["engine_id"], r["target"]) == tuple(chosen)]
        if text:
            rows = [r for r in rows
                    if text in (self.searchable(r) + " " + r["engine"] + " "
                                + r["target"]).casefold()]
        self.filtered = list(rows)

        self.table.setRowCount(0)
        for row in self.filtered:
            r = self.table.rowCount()
            self.table.insertRow(r)
            users = row.get("used_by") or []
            known = row.get("usage_known", True)
            if users:
                held = f"{len(users)} · {', '.join(users[:2])}"
                if len(users) > 2:
                    held += f" +{len(users) - 2}"
            elif not known:
                # ⚠️ Not "nothing holds it" — "we could not find out". The
                # two look identical and only one of them is safe to act
                # on, so they must never print the same character.
                held = "?"
            else:
                held = "—"
            cells = ([row["engine"],
                      row["target"] + (" ●" if row["active"] else "")]
                     + [str(row.get(key, "")) for _, key in self.COLUMNS]
                     + [held])
            for col, value in enumerate(cells):
                item = QTableWidgetItem(value)
                if col == len(cells) - 1:
                    item.setForeground(QColor(FREE if (not users and known)
                                              else HELD))
                self.table.setItem(r, col, item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(
            self.STRETCH, QHeaderView.Stretch)

        # Only rows whose holders were actually read can be called unused.
        free = sum(1 for r in self.filtered
                   if not r.get("used_by") and r.get("usage_known", True))
        blind = sum(1 for r in self.filtered
                    if not r.get("usage_known", True))
        sources = len(self._sources())
        text_ = (f"{len(self.filtered)}/{len(self.rows)} {self.NOUN} · "
                 f"{free} unused · {sources} "
                 f"source{'s' if sources != 1 else ''}")
        if blind:
            text_ += f" · ⚠ {blind} unknown"
        trouble = len(getattr(self, "problems", []))
        if trouble:
            text_ += f" · ⚠ {trouble} unreachable"
        self.count_label.setText(text_)
        if self.filtered:
            self.table.selectRow(0)

    # --- the selected row --------------------------------------------------
    def _current(self):
        r = self.table.currentRow()
        if r < 0 or r >= len(self.filtered):
            return None
        return self.filtered[r]

    def _target_of(self, item):
        provider = by_id(item["engine_id"])
        if provider is None:
            return None, None
        target = next((x for x in provider.targets()
                       if x.name == item["target"]), None)
        return provider, target

    def _show_detail(self, *_) -> None:
        item = self._current()
        if item is None:
            for tab in (self.tab_summary, self.tab_users, self.tab_raw):
                tab.clear()
            return
        self.tab_summary.setHtml(self.summary_html(item))

        users = item.get("used_by") or []
        if users:
            rows_html = "".join(f"<tr><td><code>{name}</code></td></tr>"
                                for name in users)
            self.tab_users.setHtml(
                f"<p><b>{len(users)}</b> container"
                f"{'s' if len(users) != 1 else ''} hold this "
                f"{self.SINGULAR}:</p>"
                f"<table cellpadding='4'>{rows_html}</table>"
                f"<p>The engine refuses to remove it while they exist. That "
                f"refusal is a safety net, not an obstacle — it is the "
                f"only thing standing between a typo and a lost "
                f"{self.SINGULAR}.</p>")
        elif not item.get("usage_known", True):
            self.tab_users.setHtml(
                f"<p>\u26a0 <b>Unknown.</b> The container list on this "
                f"source could not be read, so kontainy does not know "
                f"whether anything is using this {self.SINGULAR}.</p>"
                f"<p>An empty Used by column here means "
                f"<i>not found out</i>, never <i>free</i>. Prune is "
                f"switched off for this source for the same reason.</p>")
        else:
            self.tab_users.setHtml(
                f"<p>Nothing is holding this {self.SINGULAR} right now.</p>"
                f"<p>{self.UNUSED_NOTE}</p>")

        self.tab_raw.setHtml(
            f"<pre>{json.dumps(item.get('raw', {}), indent=2, ensure_ascii=False)}</pre>")

        provider, target = self._target_of(item)
        if provider is not None:
            actions = self.actions_for(provider, target, item)
            if actions:
                self.show_command(provider.prepare(actions[0]).display(),
                                  engine=item["engine_id"], record=False)

    def summary_html(self, item: dict) -> str:
        raise NotImplementedError

    def actions_for(self, provider, target, item) -> list:
        raise NotImplementedError

    # --- what the right-click menu and the keys use ------------------------
    def row_label(self, row: dict) -> str:
        return str(row.get("name") or row.get("reference")
                   or row.get("id") or "")

    def actions_for_rows(self, rows: list) -> list:
        """The same actions the toolbar runs, for the row under the cursor.

        Only for a single row: an image or a volume is removed by name and
        the prune path already exists for "everything unused", which is a
        far better answer than a menu quietly looping over a selection.
        """
        if len(rows) != 1:
            return []
        provider, target = self._target_of(rows[0])
        if provider is None:
            return []
        return [provider.prepare(a)
                for a in self.actions_for(provider, target, rows[0])]

    def run_action(self, action) -> None:
        self._run(action)

    # --- running -----------------------------------------------------------
    def _run(self, action) -> None:
        if action is None:
            return
        from ..dialogs.run_command import RunCommandDialog
        from ..dialogs.logs_viewer import LogsDialog
        if action.follow:
            self.show_command(" ".join(action.follow), note=action.id,
                              record=False)
            LogsDialog(action, self).exec()
            self.refresh()
            return
        self.show_command(action.display(), note=action.id, record=False)
        RunCommandDialog(action, self).exec()
        self.refresh()

    def _act(self, verb: str) -> None:
        item = self._current()
        if item is None:
            self.status.emit(f"Select a {self.SINGULAR} first.")
            return
        provider, target = self._target_of(item)
        if provider is None:
            return
        for candidate in self.actions_for(provider, target, item):
            if verb in candidate.label.lower():
                self._run(provider.prepare(candidate))
                return
        self.status.emit(f"{verb} does not apply to this {self.SINGULAR}.")

    def _selected_source(self):
        """The provider and target the prune should run against.

        Prune is per engine and per target: "remove everything unused" over
        a mixed table would send one engine's names to another.
        """
        chosen = self.source.currentData()
        if not chosen:
            item = self._current()
            if item is None:
                return None, None, []
            chosen = (item["engine_id"], item["target"])
        engine_id, target_name = tuple(chosen)
        provider = by_id(engine_id)
        target = next((x for x in provider.targets()
                       if x.name == target_name), None) if provider else None
        rows = [r for r in self.rows if r["engine_id"] == engine_id
                and r["target"] == target_name]
        return provider, target, rows


class ImagesPage(StockPage):
    NAME = "images"
    TITLE = "Images"
    ICON = "\U0001f5bc"
    SUBTITLE = ("Every image on every engine and context, with the "
                "containers holding each one — so you know what is "
                "safe to remove before you remove it.")
    NOUN = "images"
    SINGULAR = "image"
    DEFAULT_VERB = "inspect"
    FILTER_HINT = "Filter: repository, tag, id…"
    COLUMNS = [("Repository", "repository"), ("Tag", "tag"),
               ("Image ID", "id"), ("Created", "created"), ("Size", "size")]
    STRETCH = 2
    UNUSED_NOTE = ("Removing it frees its layers — though layers shared "
                   "with another image stay, which is why the space "
                   "recovered is often less than the size shown.")

    def build_tools(self) -> None:
        self.add_tool_button("⬇  Pull…", self._pull, kind="primary")
        self.add_tool_button("▶  Run…", self._run_image)
        self.add_tool_button("\U0001f3f7  Tag…", self._tag)
        self.add_tool_button("\U0001f50e  Inspect",
                             lambda: self._act("inspect"))
        self.add_tool_button("\U0001f4dc  History",
                             lambda: self._act("history"))
        self.add_tool_button("\U0001f4be  Save…", self._save)
        self.add_tool_button("\U0001f5d1  Remove", lambda: self._act("remove"),
                             kind="danger")
        self.add_tool_button("\U0001f9f9  Prune…", self._prune,
                             kind="danger")

    def read(self) -> list:
        return inventory.list_images(log_error=log().warning)

    def actions_for(self, provider, target, item) -> list:
        return inventory.image_actions(provider, target, item)

    def summary_html(self, item: dict) -> str:
        users = item.get("used_by") or []
        return (
            f"<h2>{item.get('reference') or item.get('id')}</h2>"
            f"<table cellpadding='4'>"
            f"<tr><td><b>Engine</b></td><td>{item['engine']} · "
            f"{item['target']}</td></tr>"
            f"<tr><td><b>Socket</b></td><td><code>{item['address']}</code>"
            f"{'<br>' + item['kind'] if item['kind'] else ''}</td></tr>"
            f"<tr><td><b>Image ID</b></td><td><code>{item.get('id')}</code>"
            f"</td></tr>"
            f"<tr><td><b>Created</b></td><td>{item.get('created') or '—'}"
            f"</td></tr>"
            f"<tr><td><b>Size</b></td><td>{item.get('size') or '—'}</td></tr>"
            f"<tr><td><b>Used by</b></td>"
            f"<td>{', '.join(users) if users else 'nothing'}</td></tr>"
            f"</table>"
            + ("<p>This image has no tag. An untagged image is usually the "
               "previous build of something you rebuilt — it keeps its "
               "layers and its space until it is removed.</p>"
               if item.get("dangling") else ""))

    # --- actions that need a value first -----------------------------------
    def _pull(self) -> None:
        provider, target, _ = self._selected_source()
        if provider is None:
            self.status.emit("No engine answered. Start Docker or Podman "
                             "from its own page first.")
            return
        name, ok = QInputDialog.getText(
            self, "Pull an image",
            "Image to pull — name:tag, or a full registry path.\n"
            "Without a tag this means :latest, which moves: the same name "
            "can be a different image tomorrow.",
            text="docker.io/library/alpine:3.20")
        if not ok or not name.strip():
            return
        self._run(provider.prepare(
            inventory.pull_action(provider, target, name.strip())))

    def _run_image(self) -> None:
        """Open the create dialog with this image already filled in."""
        item = self._current()
        if item is None:
            self.status.emit("Select an image first.")
            return
        from .containers import engine_choices
        from ..dialogs.create_container import CreateContainerDialog
        choices = engine_choices(("docker", "podman"))
        if not choices:
            self.status.emit("No container engine answered.")
            return
        dialog = CreateContainerDialog(choices, self)
        reference = item.get("reference") or item.get("id") or ""
        # The dialog's own image box, filled from the row that was selected:
        # going back to type a name that is already on screen is the kind of
        # small friction that makes people use the terminal instead.
        for attr in ("image", "image_box", "image_combo"):
            widget = getattr(dialog, attr, None)
            if widget is not None and hasattr(widget, "setCurrentText"):
                widget.setCurrentText(reference)
                break
            if widget is not None and hasattr(widget, "setText"):
                widget.setText(reference)
                break
        dialog.exec()
        self.refresh()

    def _tag(self) -> None:
        item = self._current()
        if item is None:
            self.status.emit("Select an image first.")
            return
        provider, target = self._target_of(item)
        if provider is None:
            return
        new_tag, ok = QInputDialog.getText(
            self, "Tag this image",
            "New name:tag for the same image. Nothing is copied — the "
            "two names point at one image.",
            text=item.get("reference") or "")
        if not ok or not new_tag.strip():
            return
        self._run(provider.prepare(
            inventory.tag_action(provider, target, item, new_tag.strip())))

    def _save(self) -> None:
        item = self._current()
        if item is None:
            self.status.emit("Select an image first.")
            return
        provider, target = self._target_of(item)
        if provider is None:
            return
        suggested = (item.get("repository") or "image").replace("/", "_")
        path, _ = QFileDialog.getSaveFileName(
            self, "Save the image as a tar archive", f"{suggested}.tar",
            "Tar archives (*.tar)")
        if not path:
            return
        self._run(provider.prepare(
            inventory.save_action(provider, target, item, path)))

    def _prune(self) -> None:
        provider, target, rows = self._selected_source()
        if provider is None:
            return
        built = inventory.prune_images_action(provider, target, rows)
        if built is None:
            unknown = any(not r.get("usage_known", True) for r in rows)
            QMessageBox.information(
                self, "Nothing to remove",
                "The container list on this source could not be read, so "
                "kontainy cannot tell which images are unused. Removing "
                "them by guess is not something it will offer."
                if unknown else
                "Every image on this source is held by a container.")
            return
        self._run(provider.prepare(built))


class VolumesPage(StockPage):
    NAME = "volumes"
    TITLE = "Volumes"
    ICON = "\U0001f4be"
    SUBTITLE = ("Every volume on every engine and context, with the "
                "containers holding each one — the column that stops a "
                "database being deleted by mistake.")
    NOUN = "volumes"
    SINGULAR = "volume"
    DEFAULT_VERB = "inspect"
    FILTER_HINT = "Filter: name, driver, mountpoint…"
    COLUMNS = [("Name", "name"), ("Driver", "driver"),
               ("Mountpoint", "mountpoint"), ("Size", "size")]
    STRETCH = 4
    UNUSED_NOTE = ("⚠ Unused is not the same as empty. A database whose "
                   "container was removed leaves its data here looking "
                   "exactly this idle — check the name means nothing to "
                   "you before removing it.")

    def build_tools(self) -> None:
        self.add_tool_button("➕  Create…", self._create,
                             kind="primary")
        self.add_tool_button("\U0001f50e  Inspect",
                             lambda: self._act("inspect"))
        self.add_tool_button("\U0001f4c2  Browse",
                             lambda: self._act("browse"))
        self.add_tool_button("\U0001f4be  Back up…", self._backup)
        self.add_tool_button("♻  Restore…", self._restore)
        self.add_tool_button("\U0001f5d1  Remove", lambda: self._act("remove"),
                             kind="danger")
        self.add_tool_button("\U0001f9f9  Prune…", self._prune,
                             kind="danger")

    def read(self) -> list:
        return inventory.list_volumes(log_error=log().warning)

    def actions_for(self, provider, target, item) -> list:
        return inventory.volume_actions(provider, target, item)

    def summary_html(self, item: dict) -> str:
        users = item.get("used_by") or []
        return (
            f"<h2>{item.get('name')}</h2>"
            f"<table cellpadding='4'>"
            f"<tr><td><b>Engine</b></td><td>{item['engine']} · "
            f"{item['target']}</td></tr>"
            f"<tr><td><b>Driver</b></td><td>{item.get('driver') or '—'}"
            f"</td></tr>"
            f"<tr><td><b>Mountpoint</b></td>"
            f"<td><code>{item.get('mountpoint') or '—'}</code></td></tr>"
            f"<tr><td><b>Size</b></td><td>{item.get('size') or '—'}</td></tr>"
            f"<tr><td><b>Used by</b></td>"
            f"<td>{', '.join(users) if users else 'nothing'}</td></tr>"
            f"</table>"
            f"<p>A volume outlives every container that mounts it. That is "
            f"what it is for, and it is also why removing one is the only "
            f"action on this page that cannot be undone.</p>")

    def _create(self) -> None:
        provider, target, _ = self._selected_source()
        if provider is None:
            self.status.emit("No engine answered. Start Docker or Podman "
                             "from its own page first.")
            return
        name, ok = QInputDialog.getText(
            self, "Create a volume",
            "Name for the new volume. It outlives the containers that "
            "mount it, so pick something you will still recognise later.")
        if not ok or not name.strip():
            return
        self._run(provider.prepare(
            inventory.create_volume_action(provider, target, name.strip())))

    def _backup(self) -> None:
        item = self._current()
        if item is None:
            self.status.emit("Select a volume first.")
            return
        provider, target = self._target_of(item)
        if provider is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Back the volume up to", f"{item.get('name')}.tar.gz",
            "Gzipped tar (*.tar.gz)")
        if not path:
            return
        self._run(provider.prepare(
            inventory.backup_action(provider, target, item, path)))

    def _restore(self) -> None:
        item = self._current()
        if item is None:
            self.status.emit("Select a volume first.")
            return
        provider, target = self._target_of(item)
        if provider is None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Restore into this volume from", "",
            "Gzipped tar (*.tar.gz *.tgz);;All files (*)")
        if not path:
            return
        self._run(provider.prepare(
            inventory.restore_action(provider, target, item, path)))

    def _prune(self) -> None:
        provider, target, rows = self._selected_source()
        if provider is None:
            return
        built = inventory.prune_volumes_action(provider, target, rows)
        if built is None:
            unknown = any(not r.get("usage_known", True) for r in rows)
            QMessageBox.information(
                self, "Nothing to remove",
                "The container list on this source could not be read, so "
                "kontainy cannot tell which volumes are unused \u2014 and "
                "guessing here is how a database is deleted."
                if unknown else
                "Every volume on this source is held by a container.")
            return
        self._run(provider.prepare(built))
