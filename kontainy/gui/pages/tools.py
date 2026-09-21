"""
kontainy — tool pages, one per group

Docker, Podman, KVM, QEMU, libvirt, LXC, Incus, Kubernetes and the desktop
applications each get a row here, and each row can be acted on. This is the
page that answers "where is KVM" and "why can I only read things".

Every tool shows four things:

* whether it is installed, which version, and whether its services are running
* the install command **for the system you are actually on**, plus the
  command for every other platform, because seeing that `pacman -S docker`
  and `apt install docker.io` are different packages is itself the lesson
* the catalogue settings and diagnostic rules that belong to it
* its Learn category

Nothing runs before the command is shown. Install and removal are root-scoped
and go through the same confirmation dialog as everything else.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QPushButton,
    QSplitter, QTableWidget, QTableWidgetItem, QTextBrowser, QVBoxLayout,
    QWidget,
)

from ...core import actions as act
from ...core import registry as reg
from ...core.catalog import ALL_SETTINGS
from ...rules import RULES
from ...utils.workers import CallableJob, run_job
from ..styles import cmd_html
from .base import Page


def _probe(group: str, ids=None) -> list:
    """Status for a group of tools, or for an explicit list of tool ids."""
    rows = []
    tools = ([reg.by_id(i) for i in ids
              if reg.by_id(i) and reg.available_here(reg.by_id(i))] if ids
             else reg.by_group(group))
    for tool in tools:
        services = []
        for unit, user in tool.services:
            state = act._unit_property(unit, user, "is-active")
            enabled = act._unit_property(unit, user, "is-enabled")
            services.append((unit, "user" if user else "system", state,
                             enabled))
        rows.append({
            "tool": tool,
            "installed": tool.installed(),
            "path": tool.binary_path(),
            "version": tool.version() if tool.installed() else "",
            "services": services,
        })
    return rows


class ToolsPage(Page):
    """Base for every group page. Subclasses only set GROUP and the labels."""

    GROUP = "Containers"
    TOOL_IDS = None           # set to restrict the page to these tools
    open_setting = Signal(str)

    def build(self) -> None:
        self.rows = []
        self.refresh_btn = self.add_tool_button(
            "\U0001f501  Re-check", self.refresh, kind="primary")
        self.add_tool_stretch()
        self.count_label = QLabel("\u2014")
        self.toolbar.addWidget(self.count_label)

        split = QSplitter(Qt.Horizontal)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["", "Tool", "Version", "Services"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.currentCellChanged.connect(self._selected)
        split.addWidget(self.table)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        self.detail = QTextBrowser()
        self.detail.setOpenExternalLinks(True)
        rl.addWidget(self.detail, 1)
        self.action_row = QVBoxLayout()
        rl.addLayout(self.action_row)
        split.addWidget(right)
        split.setSizes([560, 700])
        self.body.addWidget(split, 1)

    def on_shown(self) -> None:
        if not self.rows:
            self.refresh()

    def refresh(self) -> None:
        self.refresh_btn.setEnabled(False)
        self.busy.emit(True)
        self.status.emit(f"Checking {self.GROUP.lower()}\u2026")
        run_job(CallableJob(_probe, self.GROUP, self.TOOL_IDS),
                self._fill, self._failed)

    def _failed(self, message: str) -> None:
        self.refresh_btn.setEnabled(True)
        self.busy.emit(False)
        self.status.emit(f"Check failed: {message}")

    def _fill(self, rows) -> None:
        c = self.colors()
        self.rows = rows
        self.table.setRowCount(0)
        for row in rows:
            r = self.table.rowCount()
            self.table.insertRow(r)
            running = sum(1 for _, _, state, _ in row["services"]
                          if state == "active")
            if row["services"]:
                services = f"{running}/{len(row['services'])} running"
            else:
                services = "\u2014"
            cells = ["\u2705" if row["installed"] else "\u25cb",
                     row["tool"].name,
                     row["version"] or ("not installed"
                                        if not row["installed"] else ""),
                     services]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(str(text))
                if col == 2 and not row["installed"]:
                    item.setForeground(QColor(c["fg_muted"]))
                elif col == 3 and row["services"] and running:
                    item.setForeground(QColor(c["success"]))
                self.table.setItem(r, col, item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)

        installed = sum(1 for r in rows if r["installed"])
        self.count_label.setText(
            f"{installed} of {len(rows)} installed \u00b7 {reg.OS_LABEL}")
        self.refresh_btn.setEnabled(True)
        self.busy.emit(False)
        self.status.emit(f"{installed} of {len(rows)} installed")
        if rows:
            self.table.selectRow(0)

    def _current(self):
        r = self.table.currentRow()
        if r < 0 or r >= len(self.rows):
            return None
        return self.rows[r]

    # --- detail ------------------------------------------------------------
    def _selected(self, row, *_):
        entry = self._current()
        if entry is None:
            return
        tool = entry["tool"]
        c = self.colors()
        h = cmd_html(c, size=c["fs_base"] + 3)

        p = [f"<h2 style='color:{c['accent']}'>{tool.name}</h2>",
             f"<p style='font-size:{c['fs_base'] + 2}px'>{tool.summary}</p>"]

        # --- status ---
        p.append("<table cellpadding='4'>")
        if entry["installed"]:
            p.append(f"<tr><td><b>Status</b></td><td style='color:"
                     f"{c['success']}'>installed</td></tr>")
            p.append(f"<tr><td><b>Path</b></td>"
                     f"<td><code>{entry['path']}</code></td></tr>")
            if entry["version"]:
                p.append(f"<tr><td><b>Version</b></td>"
                         f"<td>{entry['version']}</td></tr>")
        else:
            p.append(f"<tr><td><b>Status</b></td><td style='color:"
                     f"{c['fg_muted']}'>not installed</td></tr>")
        p.append(f"<tr><td><b>This system</b></td>"
                 f"<td>{reg.OS_LABEL}</td></tr>")
        p.append("</table>")

        # --- services ---
        if entry["services"]:
            p.append("<h3>Services</h3><table cellpadding='4'>")
            for unit, scope, state, enabled in entry["services"]:
                colour = c["success"] if state == "active" else c["fg_muted"]
                p.append(f"<tr><td><code>{unit}</code></td><td>{scope}</td>"
                         f"<td style='color:{colour}'>{state}</td>"
                         f"<td>{enabled}</td></tr>")
            p.append("</table>")

        # --- config files ---
        if tool.config_files:
            p.append("<h3>Configuration files</h3><ul>")
            for path in tool.config_files:
                p.append(f"<li><code>{path}</code></li>")
            p.append("</ul>")

        # --- the educational part: every platform's command ---
        commands = tool.all_install_commands()
        if commands:
            p.append(h["title"]("\U0001f4e6", "Install commands, per platform"))
            here = tool.install_command()
            for label, command in commands:
                mark = " \u2190 this system" if command == here and here else ""
                p.append(f"<p style='margin:6px 0 0 0;color:{c['fg_muted']};"
                         f"font-size:{c['fs_small'] + 1}px'>{label}{mark}</p>")
                p.append(h["line"](_colourise(command, h)))
            if not here:
                p.append(h["note"](
                    "No package is listed for this system. The tool may ship "
                    "under a different name here, or only upstream."))

        if tool.note:
            p.append(f"<div style='background:{c['warning']}1a;border-left:"
                     f"4px solid {c['warning']};padding:11px;margin-top:12px;"
                     f"border-radius:6px'><b>\u26a0 Worth knowing</b><br>"
                     f"{tool.note}</div>")

        # --- what else in kontainy relates to this tool ---
        settings = self._related_settings(tool)
        rules = self._related_rules(tool)
        if settings or rules:
            p.append("<h3>Elsewhere in kontainy</h3><ul>")
            if settings:
                p.append(f"<li><b>{len(settings)} settings</b> in the "
                         f"catalogue \u2014 open Settings and filter by "
                         f"engine <code>{tool.catalog_engine}</code></li>")
            if rules:
                p.append(f"<li><b>{len(rules)} diagnostic rules</b>: "
                         + ", ".join(r.id for r in rules[:8]) + "</li>")
            if tool.learn_category:
                p.append(f"<li>Learn category: "
                         f"<code>{tool.learn_category}</code></li>")
            p.append("</ul>")

        if tool.docs:
            p.append(f"<p><a href='{tool.docs}'>Official documentation "
                     f"\u2192</a></p>")
        self.detail.setHtml("".join(p))
        self._build_actions(entry)

    def _related_settings(self, tool) -> list:
        if not tool.catalog_engine:
            return []
        return [s for s in ALL_SETTINGS
                if s.engine in (tool.catalog_engine, "both")]

    def _related_rules(self, tool) -> list:
        if not tool.rule_prefixes:
            return []
        return [r for r in RULES
                if any(r.id.startswith(p) for p in tool.rule_prefixes)]

    # --- actions -----------------------------------------------------------
    def _build_actions(self, entry) -> None:
        while self.action_row.count():
            item = self.action_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for action in self._actions_for(entry):
            button = QPushButton(action.label)
            button.setCursor(Qt.PointingHandCursor)
            if action.destructive:
                button.setObjectName("danger")
            elif action.scope != act.USER:
                button.setObjectName("secondary")
            button.clicked.connect(
                lambda _=False, a=action: self._open_action(a))
            self.action_row.addWidget(button)

    def _actions_for(self, entry) -> list:
        tool = entry["tool"]
        actions = []

        if not entry["installed"]:
            command = tool.install_command()
            if command:
                actions.append(act.Action(
                    id=f"install-{tool.id}",
                    label=f"\U0001f4e5  Install {tool.name}",
                    command=command.replace("sudo ", "").split(),
                    scope=act.ROOT,
                    explanation=(
                        f"Installs {tool.name} using this system's package "
                        f"manager ({reg.OS_LABEL}).\n\n{tool.summary}"
                        + (f"\n\n\u26a0 {tool.note}" if tool.note else ""))))
            else:
                actions.append(act.Action(
                    id=f"noinstall-{tool.id}",
                    label="No package for this system",
                    command=[], scope=act.NONE,
                    explanation=(
                        "kontainy has no package name for this tool on "
                        f"{reg.OS_LABEL}. The panel lists the command for "
                        "every platform that does have one; upstream "
                        "instructions are behind the documentation link.")))
        else:
            remove = tool.remove_command()
            if remove:
                actions.append(act.Action(
                    id=f"remove-{tool.id}",
                    label=f"\U0001f5d1  Remove {tool.name}",
                    command=remove.replace("sudo ", "").split(),
                    scope=act.ROOT, destructive=True,
                    explanation=(
                        f"Removes the {tool.name} package.\n\n"
                        "Configuration files and data directories are "
                        "usually left behind by the package manager \u2014 "
                        "images, volumes and containers are not deleted by "
                        "this.")))

        for unit, scope, state, enabled in entry["services"]:
            unit_obj = act.Unit(name=unit, user=(scope == "user"),
                                state=state, enabled=enabled)
            actions.extend(act.actions_for_unit(unit_obj)[:2])

        return actions

    def _open_action(self, action) -> None:
        from ..dialogs.run_command import RunCommandDialog
        self.show_command(action.display(), note=action.id, record=False)
        dialog = RunCommandDialog(action, self)
        dialog.finished_ok.connect(self._after_action)
        dialog.exec()

    def _after_action(self, ok: bool) -> None:
        if ok:
            self.status.emit("Done \u2014 re-checking")
            self.refresh()

    def apply_theme(self) -> None:
        super().apply_theme()
        c = self.colors()
        self.table.setStyleSheet(
            f"QTableWidget {{ font-size: {c['fs_base'] + 2}px; }}"
            f"QTableWidget::item {{ padding: 8px 10px; }}"
            f"QHeaderView::section {{ font-size: {c['fs_base'] + 1}px;"
            f" font-weight: bold; padding: 9px; }}")


def _colourise(command: str, h: dict) -> str:
    out = []
    for index, token in enumerate(command.split()):
        if index == 0 or token in ("sudo", "pacman", "apt", "dnf", "zypper",
                                   "apk", "emerge", "xbps-install", "brew",
                                   "winget", "pkg", "nix-env", "install"):
            out.append(h["cmd"](token))
        elif token.startswith("-"):
            out.append(h["arg"](token))
        else:
            out.append(h["ph"](token))
    return " ".join(out)


# ---------------------------------------------------------------------------
#  One page per group
# ---------------------------------------------------------------------------
class ContainerToolsPage(ToolsPage):
    NAME = "tools-containers"
    TITLE = "Container engines"
    ICON = "\U0001f433"
    GROUP = "Containers"
    SUBTITLE = ("Docker, Podman, containerd and the image tools. Install, "
                "remove, start and enable them here \u2014 every command is "
                "shown before it runs.")


class KubernetesToolsPage(ToolsPage):
    NAME = "tools-kubernetes"
    TITLE = "Kubernetes"
    ICON = "\u2638"
    GROUP = "Kubernetes"
    SUBTITLE = ("kubectl and the local cluster distributions: k3s, kind, "
                "minikube, Helm.")


class VMToolsPage(ToolsPage):
    NAME = "tools-vm"
    TITLE = "Virtual machines"
    ICON = "\U0001f5a5"
    GROUP = "Virtual machines"
    SUBTITLE = ("KVM, QEMU, libvirt and Virtual Machine Manager, plus "
                "VirtualBox, Multipass and Vagrant.")


class SystemContainerToolsPage(ToolsPage):
    NAME = "tools-system"
    TITLE = "System containers"
    ICON = "\U0001f9f1"
    GROUP = "System containers"
    SUBTITLE = ("LXC, LXD, Incus, systemd-nspawn and Distrobox \u2014 full "
                "operating systems in a container rather than one process.")


class DesktopToolsPage(ToolsPage):
    NAME = "tools-desktop"
    TITLE = "Desktop apps"
    ICON = "\U0001f5b1"
    GROUP = "Desktop applications"
    SUBTITLE = ("Docker Desktop, Podman Desktop, Lens, k9s and Cockpit. "
                "Install them, and see whether their services are running.")


def embedded_tools(tool_ids: list, label: str) -> ToolsPage:
    """A tools list for a platform page's Install tab.

    Same install, remove and service logic as the standalone pages, without
    the page chrome — one implementation, two places.
    """
    cls = type(f"EmbeddedTools_{label}", (ToolsPage,), {
        "NAME": f"embedded-{label}", "TITLE": "", "SUBTITLE": "",
        "GROUP": label, "TOOL_IDS": list(tool_ids)})
    page = cls()
    page.header.hide()
    page.command_strip.hide()
    page.layout().setContentsMargins(0, 6, 0, 0)
    return page


class InstallPage(Page):
    """Every installable tool, one tab per group — VenvStudio's tab layout.

    Replaces five separate sidebar pages. The platform pages each carry an
    Install tab for their own tools; this page is the whole catalogue.
    """

    NAME = "install"
    TITLE = "Install"
    ICON = "\U0001f4e5"
    SUBTITLE = ("Every engine and tool kontainy knows, with the install "
                "command for this system and for every other platform. "
                "Nothing runs before the command is shown.")
    open_setting = Signal(str)

    def build(self) -> None:
        from PySide6.QtWidgets import QTabWidget
        self.tabs = QTabWidget()
        self.panels = {}
        icons = {"Containers": "\U0001f433", "Kubernetes": "\u2638",
                 "Virtual machines": "\U0001f5a5",
                 "System containers": "\U0001f9f1",
                 "Desktop applications": "\U0001f5b1"}
        for group in reg.GROUPS:
            ids = [t.id for t in reg.by_group(group)]
            if not ids:
                # Nothing in this group exists on this operating system —
                # System containers on Windows, for one. No empty tab.
                continue
            panel = embedded_tools(ids, group.replace(" ", "_"))
            panel.status.connect(self.status.emit)
            panel.busy.connect(self.busy.emit)
            self.panels[group] = panel
            self.tabs.addTab(panel, f"{icons.get(group, '')}  {group}")
        self.tabs.currentChanged.connect(self._tab_changed)
        self.body.addWidget(self.tabs, 1)

    def _tab_changed(self, index: int) -> None:
        panel = self.tabs.widget(index)
        if panel is not None and not panel.rows:
            panel.refresh()

    def on_shown(self) -> None:
        self._tab_changed(self.tabs.currentIndex())

    def show_group(self, group: str) -> None:
        panel = self.panels.get(group)
        if panel is not None:
            self.tabs.setCurrentWidget(panel)

    def apply_theme(self) -> None:
        super().apply_theme()
        for panel in self.panels.values():
            panel.apply_theme()
