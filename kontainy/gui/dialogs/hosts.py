"""
kontainy — servers

Most servers have no display, which is exactly why managing them from a
window is worth something: the engine runs there, the screen is here.

A server is a name, an ssh target and, when they are not the defaults, a
port, a key and a jump host. No password is stored or asked for: kontainy
connects with BatchMode, so a key or an agent is the way in and a prompt
can never block a probe running in the background.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QFormLayout, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from ...core import hosts
from ...utils.config import config
from ...utils.workers import CallableJob, run_job


def _probe(host):
    ok, why = host.reach()
    if not ok:
        return {"ok": False, "why": why, "tools": []}
    found = [name for name in ("docker", "podman", "virsh", "incus", "lxc")
             if host.which(name)]
    return {"ok": True, "why": "", "tools": found}


class HostsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Servers")
        self.resize(820, 560)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        intro = QLabel(
            "kontainy can manage a server over SSH: the engine runs there, "
            "the window is here. Nothing is stored but the address \u2014 "
            "the way in is your key or your agent.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["Name", "Server", "Options", "State"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch)
        self.table.currentCellChanged.connect(self._selected)
        layout.addWidget(self.table, 1)

        row = QHBoxLayout()
        self.use_btn = QPushButton("\u2714  Work on this server")
        self.use_btn.clicked.connect(self._use)
        row.addWidget(self.use_btn)
        self.test_btn = QPushButton("\U0001f50c  Test")
        self.test_btn.setObjectName("secondary")
        self.test_btn.clicked.connect(self._test)
        row.addWidget(self.test_btn)
        self.remove_btn = QPushButton("\U0001f5d1  Remove")
        self.remove_btn.setObjectName("danger")
        self.remove_btn.clicked.connect(self._remove)
        row.addWidget(self.remove_btn)
        row.addStretch()
        self.local_btn = QPushButton("\U0001f4bb  Work on this machine")
        self.local_btn.clicked.connect(self._use_local)
        row.addWidget(self.local_btn)
        layout.addLayout(row)

        form_box = QWidget()
        form = QFormLayout(form_box)
        self.name = QLineEdit()
        self.name.setPlaceholderText("prod")
        self.target = QLineEdit()
        self.target.setPlaceholderText("deploy@server.example")
        self.port = QSpinBox()
        self.port.setRange(0, 65535)
        self.port.setSpecialValueText("22 (default)")
        self.identity = QLineEdit()
        self.identity.setPlaceholderText("~/.ssh/id_ed25519 \u2014 optional")
        self.jump = QLineEdit()
        self.jump.setPlaceholderText("bastion \u2014 optional, ProxyJump")
        form.addRow("Name", self.name)
        form.addRow("Server", self.target)
        form.addRow("Port", self.port)
        form.addRow("Key file", self.identity)
        form.addRow("Jump host", self.jump)
        layout.addWidget(form_box)

        self.hint = QLabel("")
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)

        buttons = QHBoxLayout()
        self.add_btn = QPushButton("\u2795  Add server")
        self.add_btn.clicked.connect(self._add)
        buttons.addWidget(self.add_btn)
        buttons.addStretch()
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        layout.addLayout(buttons)

        self._fill()

    # --- the list -----------------------------------------------------------
    def _entries(self) -> list:
        known = {entry.get("name") for entry in hosts.remote_hosts()}
        extra = [{"name": alias, "target": alias, "from_ssh_config": True}
                 for alias in hosts.ssh_config_hosts() if alias not in known]
        return hosts.remote_hosts() + extra

    def _fill(self) -> None:
        active = (config().get("active_host") or "").strip()
        self.rows = self._entries()
        self.table.setRowCount(len(self.rows))
        for index, entry in enumerate(self.rows):
            options = []
            if entry.get("port"):
                options.append(f"port {entry['port']}")
            if entry.get("jump"):
                options.append(f"via {entry['jump']}")
            if entry.get("identity"):
                options.append("key")
            state = "active" if entry.get("name") == active else ""
            if entry.get("from_ssh_config"):
                state = state or "from ~/.ssh/config"
            for column, text in enumerate([entry.get("name", ""),
                                           entry.get("target", ""),
                                           ", ".join(options), state]):
                item = QTableWidgetItem(str(text))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(index, column, item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch)
        self.hint.setText(
            f"Working on {active}." if active
            else "Working on this machine.")
        self._selected()

    def _current(self):
        index = self.table.currentRow()
        return self.rows[index] if 0 <= index < len(self.rows) else None

    def _selected(self, *_):
        entry = self._current()
        has = entry is not None
        for button in (self.use_btn, self.test_btn):
            button.setEnabled(has)
        # An alias from ~/.ssh/config is not ours to delete.
        self.remove_btn.setEnabled(has and not entry.get("from_ssh_config"))

    # --- actions -------------------------------------------------------------
    def _host_of(self, entry):
        return hosts.host_from_entry(entry)

    def _add(self) -> None:
        name = self.name.text().strip()
        target = self.target.text().strip()
        if not target:
            self.hint.setText("Give the server as user@host.")
            return
        entry = {"name": name or target, "target": target,
                 "port": self.port.value(),
                 "identity": self.identity.text().strip(),
                 "jump": self.jump.text().strip()}
        cfg = config()
        entries = [e for e in (cfg.get("ssh_hosts") or [])
                   if e.get("name") != entry["name"]] + [entry]
        cfg.set("ssh_hosts", entries)
        self.name.clear()
        self.target.clear()
        self.identity.clear()
        self.jump.clear()
        self.port.setValue(0)
        self._fill()
        self._run_probe(entry, added=True)

    def _remove(self) -> None:
        entry = self._current()
        if entry is None or entry.get("from_ssh_config"):
            return
        cfg = config()
        cfg.set("ssh_hosts", [e for e in (cfg.get("ssh_hosts") or [])
                              if e.get("name") != entry.get("name")])
        if (cfg.get("active_host") or "") == entry.get("name"):
            cfg.set("active_host", "")
        self._fill()

    def _test(self) -> None:
        entry = self._current()
        if entry is not None:
            self._run_probe(entry)

    def _run_probe(self, entry, added: bool = False) -> None:
        self.hint.setText(f"Connecting to {entry.get('target')}\u2026")
        host = self._host_of(entry)

        def done(result):
            if not result["ok"]:
                self.hint.setText(
                    f"<b>{entry.get('name')}</b>: {result['why']}")
                return
            tools = ", ".join(result["tools"]) or "no container tools found"
            self.hint.setText(
                f"<b>{entry.get('name')}</b>: reachable \u00b7 {tools}"
                + ("  \u2014 choose it above to work there." if added else ""))

        run_job(CallableJob(_probe, host), done,
                lambda message: self.hint.setText(f"Failed: {message}"))

    def _use(self) -> None:
        entry = self._current()
        if entry is None:
            return
        host = self._host_of(entry)
        ok, why = host.reach()
        if not ok:
            self.hint.setText(f"Not reachable: {why}")
            return
        config().set("active_host", entry.get("name"))
        self._fill()
        self.accept()

    def _use_local(self) -> None:
        config().set("active_host", "")
        self._fill()
        self.accept()
