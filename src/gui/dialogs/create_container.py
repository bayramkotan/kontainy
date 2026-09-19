"""
kontainy — Create Container dialog

What rival tools give you: image, name, ports, volumes.
What this gives you: all of it.

Seven tabs — Basics, Network, Storage, Resources, Security, Health, Advanced —
plus a **live command preview** that grows as you tick boxes. The preview is
the educational pillar at its most visible: the user sees exactly the command
they could have typed, and can copy it instead of clicking Create.

Templates fill every tab in one click, so nobody has to go hunting for example
code.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton,
    QSpinBox, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from ...core import templates as tpl
from ...core.api import EngineError
from ...utils.config import history, log
from ..syntax_highlighter import ShellHighlighter

CAPABILITIES = [
    "CHOWN", "DAC_OVERRIDE", "FOWNER", "FSETID", "KILL", "SETGID", "SETUID",
    "SETPCAP", "NET_BIND_SERVICE", "NET_RAW", "NET_ADMIN", "SYS_CHROOT",
    "SYS_PTRACE", "SYS_ADMIN", "SYS_NICE", "SYS_TIME", "MKNOD", "AUDIT_WRITE",
]


def _lines(widget: QPlainTextEdit) -> list:
    return [line.strip() for line in widget.toPlainText().splitlines()
            if line.strip()]


class CreateContainerDialog(QDialog):
    """Full-surface container creation."""

    created = Signal(str)

    def __init__(self, endpoints: list, parent=None, preset: str = ""):
        super().__init__(parent)
        self.endpoints = [e for e in endpoints if e.reachable]
        self.setWindowTitle("Create Container")
        self.resize(1080, 820)
        self._build()
        if preset:
            index = self.template_box.findData(preset)
            if index >= 0:
                self.template_box.setCurrentIndex(index)
        self._update_preview()

    # --- construction ------------------------------------------------------
    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        top = QHBoxLayout()
        top.addWidget(QLabel("Engine:"))
        self.engine_box = QComboBox()
        for endpoint in self.endpoints:
            self.engine_box.addItem(endpoint.title, endpoint)
        self.engine_box.currentIndexChanged.connect(self._update_preview)
        top.addWidget(self.engine_box, 2)

        top.addWidget(QLabel("Template:"))
        self.template_box = QComboBox()
        self.template_box.addItem("— none —", "")
        for category in tpl.CATEGORIES:
            for template in tpl.by_category(category):
                self.template_box.addItem(
                    f"{category} · {template.name}", template.id)
        self.template_box.currentIndexChanged.connect(self._apply_template)
        top.addWidget(self.template_box, 3)
        layout.addLayout(top)

        self.template_note = QLabel()
        self.template_note.setWordWrap(True)
        self.template_note.setVisible(False)
        layout.addWidget(self.template_note)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._tab_basics(), "Basics")
        self.tabs.addTab(self._tab_network(), "Network")
        self.tabs.addTab(self._tab_storage(), "Storage")
        self.tabs.addTab(self._tab_resources(), "Resources")
        self.tabs.addTab(self._tab_security(), "Security")
        self.tabs.addTab(self._tab_health(), "Health")
        self.tabs.addTab(self._tab_advanced(), "Advanced")
        layout.addWidget(self.tabs, 1)

        preview_box = QGroupBox("Command preview — this is exactly what runs")
        pl = QVBoxLayout(preview_box)
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setFixedHeight(160)
        self.preview.setStyleSheet(
            "QTextEdit { font-family: monospace; font-size: 13px; }")
        self._highlighter = ShellHighlighter(self.preview.document())
        pl.addWidget(self.preview)

        row = QHBoxLayout()
        copy_btn = QPushButton("Copy command")
        copy_btn.setObjectName("secondary")
        copy_btn.clicked.connect(self._copy)
        row.addWidget(copy_btn)
        quadlet_btn = QPushButton("Show as Quadlet unit")
        quadlet_btn.setObjectName("secondary")
        quadlet_btn.clicked.connect(self._show_quadlet)
        row.addWidget(quadlet_btn)
        compose_btn = QPushButton("Show as compose")
        compose_btn.setObjectName("secondary")
        compose_btn.clicked.connect(self._show_compose)
        row.addWidget(compose_btn)
        row.addStretch()
        pl.addLayout(row)
        layout.addWidget(preview_box)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Create and start")
        buttons.accepted.connect(self._create)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _wire(self, *widgets):
        for widget in widgets:
            if isinstance(widget, (QLineEdit,)):
                widget.textChanged.connect(self._update_preview)
            elif isinstance(widget, QPlainTextEdit):
                widget.textChanged.connect(self._update_preview)
            elif isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(self._update_preview)
            elif isinstance(widget, QCheckBox):
                widget.toggled.connect(self._update_preview)
            elif isinstance(widget, QSpinBox):
                widget.valueChanged.connect(self._update_preview)

    def _tab_basics(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.image = QLineEdit()
        self.image.setPlaceholderText("docker.io/library/nginx:alpine")
        self.name = QLineEdit()
        self.command = QLineEdit()
        self.command.setPlaceholderText("override the image CMD (optional)")
        self.entrypoint = QLineEdit()
        self.workdir = QLineEdit()
        self.user = QLineEdit()
        self.user.setPlaceholderText("uid[:gid] or name")
        self.restart = QComboBox()
        self.restart.addItems(["no", "on-failure", "always", "unless-stopped"])
        self.detach = QCheckBox("Run in background (-d)")
        self.detach.setChecked(True)
        self.autoremove = QCheckBox("Remove when it stops (--rm)")
        self.env = QPlainTextEdit()
        self.env.setPlaceholderText("KEY=value, one per line")
        self.env.setFixedHeight(90)
        self.labels = QPlainTextEdit()
        self.labels.setPlaceholderText("key=value, one per line")
        self.labels.setFixedHeight(60)

        form.addRow("Image *", self.image)
        form.addRow("Name", self.name)
        form.addRow("Command", self.command)
        form.addRow("Entrypoint", self.entrypoint)
        form.addRow("Working dir", self.workdir)
        form.addRow("User", self.user)
        form.addRow("Restart policy", self.restart)
        form.addRow("", self.detach)
        form.addRow("", self.autoremove)
        form.addRow("Environment", self.env)
        form.addRow("Labels", self.labels)
        self._wire(self.image, self.name, self.command, self.entrypoint,
                   self.workdir, self.user, self.restart, self.detach,
                   self.autoremove, self.env, self.labels)
        return page

    def _tab_network(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.network = QComboBox()
        self.network.setEditable(True)
        self.network.addItems(["bridge", "host", "none", "pasta",
                               "slirp4netns", "container:<name>"])
        self.ports = QPlainTextEdit()
        self.ports.setPlaceholderText(
            "8080:80\n127.0.0.1:5432:5432\n5353:53/udp")
        self.ports.setFixedHeight(90)
        self.hostname = QLineEdit()
        self.dns = QLineEdit()
        self.dns.setPlaceholderText("1.1.1.1, 9.9.9.9")
        self.add_hosts = QPlainTextEdit()
        self.add_hosts.setPlaceholderText("host:ip, one per line")
        self.add_hosts.setFixedHeight(60)
        self.publish_all = QCheckBox("Publish all exposed ports (-P)")

        form.addRow("Network", self.network)
        form.addRow("Published ports", self.ports)
        form.addRow("Hostname", self.hostname)
        form.addRow("DNS servers", self.dns)
        form.addRow("Extra hosts", self.add_hosts)
        form.addRow("", self.publish_all)
        hint = QLabel(
            "Rootless containers cannot bind host ports below 1024 unless "
            "net.ipv4.ip_unprivileged_port_start is lowered.")
        hint.setWordWrap(True)
        form.addRow("", hint)
        self._wire(self.network, self.ports, self.hostname, self.dns,
                   self.add_hosts, self.publish_all)
        return page

    def _tab_storage(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.volumes = QPlainTextEdit()
        self.volumes.setPlaceholderText(
            "pgdata:/var/lib/postgresql/data\n./src:/app:ro,Z")
        self.volumes.setFixedHeight(110)
        self.tmpfs = QPlainTextEdit()
        self.tmpfs.setPlaceholderText("/tmp\n/var/run")
        self.tmpfs.setFixedHeight(60)
        self.read_only = QCheckBox("Read-only root filesystem (--read-only)")
        self.shm_size = QLineEdit()
        self.shm_size.setPlaceholderText("64m — raise to 1g for ML workloads")

        form.addRow("Volumes / mounts", self.volumes)
        form.addRow("tmpfs mounts", self.tmpfs)
        form.addRow("", self.read_only)
        form.addRow("/dev/shm size", self.shm_size)
        hint = QLabel(
            "Suffixes: :ro read-only · :z shared SELinux label · :Z private "
            "label · :rslave mount propagation. Without :z or :Z a bind mount "
            "fails with Permission denied on SELinux systems.")
        hint.setWordWrap(True)
        form.addRow("", hint)
        self._wire(self.volumes, self.tmpfs, self.read_only, self.shm_size)
        return page

    def _tab_resources(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.memory = QLineEdit()
        self.memory.setPlaceholderText("512m, 2g …")
        self.memory_swap = QLineEdit()
        self.cpus = QLineEdit()
        self.cpus.setPlaceholderText("1.5")
        self.cpuset = QLineEdit()
        self.cpuset.setPlaceholderText("0-3,8")
        self.cpu_shares = QSpinBox()
        self.cpu_shares.setRange(0, 262144)
        self.pids_limit = QSpinBox()
        self.pids_limit.setRange(0, 100000)
        self.ulimits = QPlainTextEdit()
        self.ulimits.setPlaceholderText("nofile=65536:65536")
        self.ulimits.setFixedHeight(60)
        self.oom_score = QSpinBox()
        self.oom_score.setRange(-1000, 1000)

        form.addRow("Memory limit", self.memory)
        form.addRow("Memory + swap", self.memory_swap)
        form.addRow("CPUs", self.cpus)
        form.addRow("CPU set", self.cpuset)
        form.addRow("CPU shares", self.cpu_shares)
        form.addRow("PID limit", self.pids_limit)
        form.addRow("ulimits", self.ulimits)
        form.addRow("OOM score adj", self.oom_score)
        hint = QLabel(
            "On rootless cgroup v2 these limits are silently ignored unless "
            "the cgroup manager is systemd. Diagnostics rule RES01 checks it.")
        hint.setWordWrap(True)
        form.addRow("", hint)
        self._wire(self.memory, self.memory_swap, self.cpus, self.cpuset,
                   self.cpu_shares, self.pids_limit, self.ulimits,
                   self.oom_score)
        return page

    def _tab_security(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        form = QFormLayout()
        self.privileged = QCheckBox(
            "Privileged (removes nearly all isolation)")
        self.no_new_priv = QCheckBox("No new privileges")
        self.no_new_priv.setChecked(True)
        self.userns = QComboBox()
        self.userns.setEditable(True)
        self.userns.addItems(["", "keep-id", "nomap", "auto", "host"])
        self.seccomp = QLineEdit()
        self.seccomp.setPlaceholderText("path to profile, or 'unconfined'")
        self.apparmor = QLineEdit()
        self.selinux = QLineEdit()
        self.selinux.setPlaceholderText("type:container_t / disable")
        self.cap_drop_all = QCheckBox(
            "Drop ALL capabilities, then add only what is ticked")
        self.cap_drop_all.setChecked(True)
        form.addRow("", self.privileged)
        form.addRow("", self.no_new_priv)
        form.addRow("User namespace", self.userns)
        form.addRow("seccomp profile", self.seccomp)
        form.addRow("AppArmor profile", self.apparmor)
        form.addRow("SELinux label", self.selinux)
        form.addRow("", self.cap_drop_all)
        outer.addLayout(form)

        box = QGroupBox("Capabilities to add")
        grid = QVBoxLayout(box)
        self.cap_checks = {}
        row = None
        for index, capability in enumerate(CAPABILITIES):
            if index % 4 == 0:
                holder = QWidget()
                row = QHBoxLayout(holder)
                row.setContentsMargins(0, 0, 0, 0)
                grid.addWidget(holder)
            check = QCheckBox(capability)
            check.toggled.connect(self._update_preview)
            row.addWidget(check)
            self.cap_checks[capability] = check
        outer.addWidget(box)

        hint = QLabel(
            "SYS_ADMIN is close to privileged in practice. Docker and Podman "
            "ship different default capability sets, which is why an image "
            "that runs on one can fail with a permission error on the other.")
        hint.setWordWrap(True)
        outer.addWidget(hint)
        self._wire(self.privileged, self.no_new_priv, self.userns,
                   self.seccomp, self.apparmor, self.selinux,
                   self.cap_drop_all)
        return page

    def _tab_health(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.health_cmd = QLineEdit()
        self.health_interval = QLineEdit()
        self.health_interval.setPlaceholderText("30s")
        self.health_timeout = QLineEdit()
        self.health_retries = QSpinBox()
        self.health_retries.setRange(0, 50)
        self.health_start = QLineEdit()
        self.health_start.setPlaceholderText("30s — grace period at startup")
        form.addRow("Health command", self.health_cmd)
        form.addRow("Interval", self.health_interval)
        form.addRow("Timeout", self.health_timeout)
        form.addRow("Retries", self.health_retries)
        form.addRow("Start period", self.health_start)
        hint = QLabel(
            "Without a start period a slow database is marked unhealthy "
            "before it has finished starting, and anything depending on it "
            "never comes up.")
        hint.setWordWrap(True)
        form.addRow("", hint)
        self._wire(self.health_cmd, self.health_interval, self.health_timeout,
                   self.health_retries, self.health_start)
        return page

    def _tab_advanced(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.init = QCheckBox("Add an init process (--init)")
        self.tty = QCheckBox("Allocate a TTY (-t)")
        self.interactive = QCheckBox("Keep stdin open (-i)")
        self.log_driver = QComboBox()
        self.log_driver.addItems(["", "json-file", "journald", "k8s-file",
                                  "none", "passthrough"])
        self.log_opts = QPlainTextEdit()
        self.log_opts.setPlaceholderText("max-size=10m\nmax-file=3")
        self.log_opts.setFixedHeight(60)
        self.sysctls = QPlainTextEdit()
        self.sysctls.setPlaceholderText("net.core.somaxconn=1024")
        self.sysctls.setFixedHeight(60)
        self.devices = QPlainTextEdit()
        self.devices.setPlaceholderText("/dev/dri\nnvidia.com/gpu=all")
        self.devices.setFixedHeight(60)
        self.pod = QLineEdit()
        self.pod.setPlaceholderText("Podman only — join this pod")
        self.extra = QLineEdit()
        self.extra.setPlaceholderText("any further flags, passed through")

        form.addRow("", self.init)
        form.addRow("", self.tty)
        form.addRow("", self.interactive)
        form.addRow("Log driver", self.log_driver)
        form.addRow("Log options", self.log_opts)
        form.addRow("sysctls", self.sysctls)
        form.addRow("Devices", self.devices)
        form.addRow("Pod", self.pod)
        form.addRow("Extra flags", self.extra)
        self._wire(self.init, self.tty, self.interactive, self.log_driver,
                   self.log_opts, self.sysctls, self.devices, self.pod,
                   self.extra)
        return page

    # --- template ----------------------------------------------------------
    def _apply_template(self):
        template_id = self.template_box.currentData()
        if not template_id:
            self.template_note.setVisible(False)
            return
        template = tpl.by_id(template_id)
        if template is None:
            return

        self.image.setText(template.image)
        self.name.setText(template.id)
        self.restart.setCurrentText(template.restart)
        self.ports.setPlainText("\n".join(template.ports))
        self.volumes.setPlainText("\n".join(template.volumes))
        env = [f"{k}={v}" for k, v in template.env.items()]
        env += [f"{k}=CHANGE_ME" for k in template.env_required]
        self.env.setPlainText("\n".join(env))
        self.tmpfs.setPlainText("\n".join(template.tmpfs))
        self.read_only.setChecked(template.read_only)
        self.memory.setText(template.memory)
        self.health_cmd.setText(template.health_cmd)
        self.health_start.setText(template.health_start_period)
        self.cap_drop_all.setChecked("ALL" in template.cap_drop)
        for capability, check in self.cap_checks.items():
            check.setChecked(capability in template.cap_add)
        self.extra.setText(" ".join(template.extra_flags))

        note = template.description
        if template.note:
            note += f"\n\n⚠  {template.note}"
        if template.env_required:
            note += ("\n\nRequired before it will start: "
                     + ", ".join(template.env_required))
        self.template_note.setText(note)
        self.template_note.setVisible(True)
        self._update_preview()

    # --- command construction ---------------------------------------------
    def _engine_binary(self) -> str:
        endpoint = self.engine_box.currentData()
        family = getattr(endpoint, "family", "docker")
        return "podman" if family == "podman" else "docker"

    def _flags(self) -> list:
        flags = []
        add = flags.append

        if self.detach.isChecked():
            add("-d")
        if self.autoremove.isChecked():
            add("--rm")
        if self.interactive.isChecked():
            add("-i")
        if self.tty.isChecked():
            add("-t")
        if self.name.text().strip():
            add(f"--name {self.name.text().strip()}")
        if self.restart.currentText() != "no" and not self.autoremove.isChecked():
            add(f"--restart={self.restart.currentText()}")

        for entry in _lines(self.env):
            add(f"-e {entry}")
        for entry in _lines(self.labels):
            add(f"--label {entry}")
        if self.entrypoint.text().strip():
            add(f"--entrypoint {self.entrypoint.text().strip()}")
        if self.workdir.text().strip():
            add(f"-w {self.workdir.text().strip()}")
        if self.user.text().strip():
            add(f"-u {self.user.text().strip()}")

        network = self.network.currentText().strip()
        if network and network != "bridge":
            add(f"--network={network}")
        for entry in _lines(self.ports):
            add(f"-p {entry}")
        if self.publish_all.isChecked():
            add("-P")
        if self.hostname.text().strip():
            add(f"--hostname {self.hostname.text().strip()}")
        for server in self.dns.text().replace(",", " ").split():
            add(f"--dns {server}")
        for entry in _lines(self.add_hosts):
            add(f"--add-host {entry}")

        for entry in _lines(self.volumes):
            add(f"-v {entry}")
        for entry in _lines(self.tmpfs):
            add(f"--tmpfs {entry}")
        if self.read_only.isChecked():
            add("--read-only")
        if self.shm_size.text().strip():
            add(f"--shm-size={self.shm_size.text().strip()}")

        for widget, flag in ((self.memory, "--memory"),
                             (self.memory_swap, "--memory-swap"),
                             (self.cpus, "--cpus"),
                             (self.cpuset, "--cpuset-cpus")):
            if widget.text().strip():
                add(f"{flag}={widget.text().strip()}")
        if self.cpu_shares.value():
            add(f"--cpu-shares={self.cpu_shares.value()}")
        if self.pids_limit.value():
            add(f"--pids-limit={self.pids_limit.value()}")
        for entry in _lines(self.ulimits):
            add(f"--ulimit {entry}")
        if self.oom_score.value():
            add(f"--oom-score-adj={self.oom_score.value()}")

        if self.privileged.isChecked():
            add("--privileged")
        else:
            if self.cap_drop_all.isChecked():
                add("--cap-drop=ALL")
            for capability, check in self.cap_checks.items():
                if check.isChecked():
                    add(f"--cap-add={capability}")
        if self.no_new_priv.isChecked():
            add("--security-opt no-new-privileges")
        if self.seccomp.text().strip():
            add(f"--security-opt seccomp={self.seccomp.text().strip()}")
        if self.apparmor.text().strip():
            add(f"--security-opt apparmor={self.apparmor.text().strip()}")
        if self.selinux.text().strip():
            add(f"--security-opt label={self.selinux.text().strip()}")
        if self.userns.currentText().strip():
            add(f"--userns={self.userns.currentText().strip()}")

        if self.health_cmd.text().strip():
            add(f"--health-cmd='{self.health_cmd.text().strip()}'")
        for widget, flag in ((self.health_interval, "--health-interval"),
                             (self.health_timeout, "--health-timeout"),
                             (self.health_start, "--health-start-period")):
            if widget.text().strip():
                add(f"{flag}={widget.text().strip()}")
        if self.health_retries.value():
            add(f"--health-retries={self.health_retries.value()}")

        if self.init.isChecked():
            add("--init")
        if self.log_driver.currentText():
            add(f"--log-driver={self.log_driver.currentText()}")
        for entry in _lines(self.log_opts):
            add(f"--log-opt {entry}")
        for entry in _lines(self.sysctls):
            add(f"--sysctl {entry}")
        for entry in _lines(self.devices):
            add(f"--device {entry}")
        if self.pod.text().strip():
            add(f"--pod {self.pod.text().strip()}")
        if self.extra.text().strip():
            add(self.extra.text().strip())
        return flags

    def command_text(self) -> str:
        binary = self._engine_binary()
        image = self.image.text().strip() or "<image>"
        parts = [f"{binary} run"] + [f"  {f}" for f in self._flags()]
        parts.append(f"  {image}")
        if self.command.text().strip():
            parts.append(f"  {self.command.text().strip()}")
        return " \\\n".join(parts)

    def _update_preview(self):
        self.preview.setPlainText(self.command_text())

    def _copy(self):
        QGuiApplication.clipboard().setText(self.command_text())

    def _show_quadlet(self):
        template_id = self.template_box.currentData()
        template = tpl.by_id(template_id) if template_id else None
        name = self.name.text().strip() or "app"
        if template is not None:
            text = template.quadlet(name)
            install = template.install_hint(name)
        else:
            text = self._generic_quadlet(name)
            install = (f"mkdir -p ~/.config/containers/systemd\n"
                       f"systemctl --user daemon-reload\n"
                       f"systemctl --user start {name}\n"
                       f"loginctl enable-linger $USER")
        self._show_text(f"Quadlet unit — {name}.container",
                        text + "\n\n# Install:\n# "
                        + install.replace("\n", "\n# "))

    def _generic_quadlet(self, name: str) -> str:
        lines = ["[Unit]", f"Description={name}", "", "[Container]",
                 f"Image={self.image.text().strip()}",
                 f"ContainerName={name}"]
        for entry in _lines(self.ports):
            lines.append(f"PublishPort={entry}")
        for entry in _lines(self.volumes):
            lines.append(f"Volume={entry}")
        for entry in _lines(self.env):
            lines.append(f"Environment={entry}")
        if self.cap_drop_all.isChecked():
            lines.append("DropCapability=ALL")
        for capability, check in self.cap_checks.items():
            if check.isChecked():
                lines.append(f"AddCapability={capability}")
        lines += ["", "[Service]", "Restart=always",
                  "", "[Install]", "WantedBy=default.target"]
        return "\n".join(lines)

    def _show_compose(self):
        template_id = self.template_box.currentData()
        template = tpl.by_id(template_id) if template_id else None
        name = self.name.text().strip() or "app"
        if template is not None:
            text = template.compose(name)
        else:
            text = "\n".join(
                ["services:", f"  {name}:",
                 f"    image: {self.image.text().strip()}"]
                + (["    ports:"] + [f'      - "{p}"' for p in _lines(self.ports)]
                   if _lines(self.ports) else [])
                + (["    volumes:"] + [f"      - {v}" for v in _lines(self.volumes)]
                   if _lines(self.volumes) else []))
        self._show_text("compose.yaml", text)

    def _show_text(self, title: str, text: str):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(760, 620)
        layout = QVBoxLayout(dialog)
        view = QTextEdit()
        view.setPlainText(text)
        view.setReadOnly(True)
        view.setStyleSheet(
            "QTextEdit { font-family: monospace; font-size: 13px; }")
        ShellHighlighter(view.document())
        layout.addWidget(view)
        row = QHBoxLayout()
        copy_btn = QPushButton("Copy")
        copy_btn.clicked.connect(
            lambda: QGuiApplication.clipboard().setText(text))
        row.addWidget(copy_btn)
        row.addStretch()
        close = QPushButton("Close")
        close.setObjectName("secondary")
        close.clicked.connect(dialog.accept)
        row.addWidget(close)
        layout.addLayout(row)
        dialog.exec()

    # --- create ------------------------------------------------------------
    def _create(self):
        if not self.image.text().strip():
            QMessageBox.warning(self, "Image required",
                                "Pick an image or a template first.")
            return
        endpoint = self.engine_box.currentData()
        if endpoint is None:
            QMessageBox.warning(self, "No engine",
                                "No reachable engine to create this on.")
            return

        command = self.command_text()
        if "CHANGE_ME" in command:
            answer = QMessageBox.question(
                self, "Placeholder values left",
                "The command still contains CHANGE_ME. The container will "
                "very likely fail to start.\n\nCreate it anyway?")
            if answer != QMessageBox.Yes:
                return

        from ...core import discovery
        client = discovery.client_for(endpoint)
        try:
            container_id = self._create_via_api(client)
        except EngineError as exc:
            history().add(command, engine=endpoint.family,
                          note=f"failed: {exc}", ok=False)
            QMessageBox.critical(
                self, "Create failed",
                f"{exc}\n\nThe equivalent command is in the preview — try it "
                f"in a terminal to see the engine's own error.")
            return

        history().add(command, engine=endpoint.family, note="create container")
        log().info("created container %s on %s", container_id, endpoint.address)
        self.created.emit(container_id)
        self.accept()

    def _create_via_api(self, client) -> str:
        """Create through the engine API using the same values as the preview."""
        exposed = {}
        bindings = {}
        for entry in _lines(self.ports):
            spec = entry.split("/")
            proto = spec[1] if len(spec) > 1 else "tcp"
            bits = spec[0].split(":")
            host_ip, host_port, container_port = "", bits[0], bits[-1]
            if len(bits) == 3:
                host_ip, host_port, container_port = bits
            elif len(bits) == 2:
                host_port, container_port = bits
            key = f"{container_port}/{proto}"
            exposed[key] = {}
            bindings.setdefault(key, []).append(
                {"HostIp": host_ip, "HostPort": host_port})

        binds = [entry for entry in _lines(self.volumes)]
        host_config = {
            "Binds": binds,
            "PortBindings": bindings,
            "RestartPolicy": {"Name": self.restart.currentText()}
            if not self.autoremove.isChecked() else {"Name": "no"},
            "AutoRemove": self.autoremove.isChecked(),
            "Privileged": self.privileged.isChecked(),
            "ReadonlyRootfs": self.read_only.isChecked(),
        }
        if self.cap_drop_all.isChecked() and not self.privileged.isChecked():
            host_config["CapDrop"] = ["ALL"]
        adds = [c for c, w in self.cap_checks.items() if w.isChecked()]
        if adds:
            host_config["CapAdd"] = adds
        if self.memory.text().strip():
            host_config["Memory"] = _to_bytes(self.memory.text().strip())
        if self.pids_limit.value():
            host_config["PidsLimit"] = self.pids_limit.value()
        if self.cpuset.text().strip():
            host_config["CpusetCpus"] = self.cpuset.text().strip()

        payload = {
            "Image": self.image.text().strip(),
            "Env": _lines(self.env),
            "Labels": dict(
                entry.split("=", 1) for entry in _lines(self.labels)
                if "=" in entry),
            "ExposedPorts": exposed,
            "Tty": self.tty.isChecked(),
            "OpenStdin": self.interactive.isChecked(),
            "HostConfig": host_config,
        }
        if self.command.text().strip():
            payload["Cmd"] = self.command.text().strip().split()
        if self.entrypoint.text().strip():
            payload["Entrypoint"] = self.entrypoint.text().strip().split()
        if self.workdir.text().strip():
            payload["WorkingDir"] = self.workdir.text().strip()
        if self.user.text().strip():
            payload["User"] = self.user.text().strip()
        if self.hostname.text().strip():
            payload["Hostname"] = self.hostname.text().strip()

        name = self.name.text().strip()
        result = client._request(
            "POST", "/containers/create", params={"name": name or None},
            body=payload)
        container_id = (result or {}).get("Id", "")
        if self.detach.isChecked() and container_id:
            client.start(container_id)
        return container_id


def _to_bytes(text: str) -> int:
    units = {"b": 1, "k": 1024, "m": 1024 ** 2, "g": 1024 ** 3}
    text = text.strip().lower()
    if text and text[-1] in units:
        return int(float(text[:-1]) * units[text[-1]])
    return int(float(text))
