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
from ...utils.workers import CallableJob, run_job
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
        self.existing_names = []
        self.taken_ports = []
        self.facts = None
        # What kontainy itself filled in. A suggestion may be replaced when
        # the image changes; something the user typed never is.
        self.suggested = {}
        self.template_image = ""
        self.trouble = ""
        self.setWindowTitle("Create Container")
        self.resize(1080, 820)
        self._build()
        if preset:
            index = self.template_box.findData(preset)
            if index >= 0:
                self.template_box.setCurrentIndex(index)
        self._update_preview()
        # Read the target once the dialog exists: which images are here,
        # which names and host ports are taken.
        self.image.currentTextChanged.connect(self._image_chosen)
        self._load_context()

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
        self.engine_box.currentIndexChanged.connect(self._load_context)
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

        # What kontainy can see is wrong, before anything runs.
        self.notes = QLabel("")
        self.notes.setWordWrap(True)
        self.notes.setTextFormat(Qt.RichText)
        self.notes.setVisible(False)
        layout.addWidget(self.notes)

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
        self.ok_button = buttons.button(QDialogButtonBox.Ok)
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
                if widget.isEditable():
                    # An editable combo changes by typing as well as by
                    # choosing; without this the preview lagged a keystroke
                    # behind the image being typed.
                    widget.currentTextChanged.connect(self._update_preview)
            elif isinstance(widget, QCheckBox):
                widget.toggled.connect(self._update_preview)
            elif isinstance(widget, QSpinBox):
                widget.valueChanged.connect(self._update_preview)

    def _tab_basics(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        # An editable dropdown, not a blank box: most of the time the image
        # is already on this machine, and kontainy knows which.
        self.image = QComboBox()
        self.image.setEditable(True)
        self.image.setInsertPolicy(QComboBox.NoInsert)
        self.image.lineEdit().setPlaceholderText(
            "Pick one that is here, or type any reference")
        self.image.lineEdit().setPlaceholderText(
            "Pick an image that is already here, or type any "
            "reference \u2014 docker.io/library/nginx:alpine")
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

        self.network_note = QLabel("")
        self.network_note.setWordWrap(True)
        self.network_note.setObjectName("hint")
        self.network.currentTextChanged.connect(self._network_note)

        form.addRow("Network", self.network)
        form.addRow("", self.network_note)
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

        self.volume_box = QComboBox()
        self.volume_box.setToolTip(
            "Volumes that already exist on this target. Choosing one adds a "
            "line; you still say where it goes inside the container.")
        self.volume_box.currentIndexChanged.connect(self._volume_chosen)
        self.volume_note = QLabel("")
        self.volume_note.setWordWrap(True)
        self.volume_note.setObjectName("hint")

        form.addRow("Volumes / mounts", self.volumes)
        form.addRow("Existing volumes", self.volume_box)
        form.addRow("", self.volume_note)
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

        self.image.setCurrentText(template.image)
        self.name.setText(template.id)
        self.restart.setCurrentText(template.restart)
        self.ports.setPlainText("\n".join(template.ports))
        self.volumes.setPlainText("\n".join(template.volumes))
        env = [f"{k}={v}" for k, v in template.env.items()]
        env += [f"{k}=CHANGE_ME" for k in template.env_required]
        self.env.setPlainText("\n".join(env))
        # A template fills the form the way kontainy would, so changing the
        # image afterwards may replace these — but anything typed by hand
        # after that is the user's and stays.
        self.template_image = template.image
        self.suggested.update({"name": template.id,
                               "ports": "\n".join(template.ports),
                               "volumes": "\n".join(template.volumes),
                               "env": "\n".join(env)})
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
    # --- what the image and the target already know -------------------------
    def _load_context(self) -> None:
        """Fill the image list and learn what names and ports are taken.

        Off the GUI thread: listing images and containers on a slow or
        remote target is not instant, and a dialog that freezes while it
        opens is worse than one that asks.
        """
        endpoint = self.engine_box.currentData()
        provider = getattr(endpoint, "provider", None)
        if provider is None:
            return
        target = endpoint.target

        def gather():
            """Each part on its own: a target with no networks command, or a
            volume listing that fails, must not take the image list down
            with it — which is exactly what happened when one exception was
            swallowed for the lot."""
            from ...core import imageinfo
            out = {"images": [], "names": [], "ports": [], "networks": [],
                   "volumes": [], "trouble": []}
            for key, work in (
                ("images", lambda: imageinfo.local_images(provider, target)),
                ("networks", lambda: imageinfo.networks(provider, target)),
                ("volumes", lambda: imageinfo.volumes(provider, target)),
            ):
                try:
                    out[key] = work()
                except Exception as exc:                     # noqa: BLE001
                    out["trouble"].append(f"{key}: {exc}")
                    log().warning("create dialog: %s failed: %r", key, exc)
            try:
                listing = provider.objects(target)
                rows = [] if listing.error else listing.rows
                out["names"] = [str(r.get("Names", "")) for r in rows]
                for row in rows:
                    for part in str(row.get("Ports", "")).split(","):
                        bit = part.strip().split("->")[0]
                        if ":" in bit:
                            out["ports"].append(bit.rsplit(":", 1)[-1])
            except Exception as exc:                         # noqa: BLE001
                out["trouble"].append(f"containers: {exc}")
                log().warning("create dialog: containers failed: %r", exc)
            return out

        run_job(CallableJob(gather), self._context_ready, self._context_failed)

    def _context_failed(self, message: str) -> None:
        """Say it, and keep saying it.

        A dialog that quietly shows an empty image list teaches the user
        that kontainy is broken rather than that something failed. Held in
        `trouble` so the next preview does not wipe it off the screen.
        """
        log().warning("create dialog could not read the target: %s", message)
        self.trouble = message
        self._show_notes()

    def _context_ready(self, data) -> None:
        self.existing_names = data["names"]
        self.taken_ports = data["ports"]
        current = self.image.currentText()
        self.image.blockSignals(True)
        self.image.clear()
        for item in data["images"]:
            label = item["reference"]
            if item.get("size"):
                label += f"   ({item['size']}, {item.get('created', '')})"
            self.image.addItem(label, item["reference"])
        self.image.setCurrentText(current)
        self.image.blockSignals(False)
        if not data["images"]:
            self.image.lineEdit().setPlaceholderText(
                "No images on this target yet \u2014 type a reference, "
                "e.g. docker.io/library/nginx:alpine")
        elif not current.strip():
            # Start on something real rather than an empty box: the dialog
            # is here to suggest, and the first image is a suggestion the
            # user can change in one click.
            self.image.setCurrentIndex(0)
            self._image_chosen()
        if data.get("trouble"):
            self._context_failed("; ".join(data["trouble"]))

        # Real networks, not a fixed list: a container on the default bridge
        # cannot reach another by name, and the note says so.
        self.network_info = {n["name"]: n["note"] for n in data["networks"]}
        chosen = self.network.currentText()
        self.network.blockSignals(True)
        self.network.clear()
        for item in data["networks"]:
            self.network.addItem(item["name"])
        for extra in ("pasta", "slirp4netns", "container:<name>"):
            if self.network.findText(extra) < 0:
                self.network.addItem(extra)
        self.network.setCurrentText(chosen or "bridge")
        self.network.blockSignals(False)
        self._network_note()

        self.volume_box.blockSignals(True)
        self.volume_box.clear()
        self.volume_box.addItem("\u2014 add an existing volume \u2014", "")
        for item in data["volumes"]:
            self.volume_box.addItem(item["name"], item["name"])
        self.volume_box.blockSignals(False)
        self.volume_note.setText(
            f"{len(data['volumes'])} named volumes on this target."
            if data["volumes"] else
            "No named volumes here yet. A path on the left of the colon that "
            "is not a path becomes a NAMED volume, which survives the "
            "container.")
        self._update_preview()

    def _network_note(self, *_):
        name = self.network.currentText().strip()
        note = getattr(self, "network_info", {}).get(name, "")
        if not note and name.startswith("container:"):
            note = ("shares another container's network namespace \u2014 they "
                    "see each other on localhost")
        self.network_note.setText(note)

    def _volume_chosen(self, *_):
        name = self.volume_box.currentData()
        if not name:
            return
        text = self.volumes.toPlainText().rstrip()
        line = f"{name}:/path/in/container"
        self.volumes.setPlainText((text + "\n" + line).strip())
        self.volume_box.setCurrentIndex(0)

    def _image_reference(self) -> str:
        data = self.image.currentData()
        text = self.image.currentText().strip()
        if data and text.startswith(str(data)):
            return str(data)
        return text.split("   (")[0].strip()

    def _image_chosen(self, *_):
        """Read the image and offer what it already says about itself."""
        reference = self._image_reference()
        if not reference:
            return
        endpoint = self.engine_box.currentData()
        provider = getattr(endpoint, "provider", None)
        if provider is None:
            return
        target = endpoint.target
        from ...core import imageinfo
        run_job(CallableJob(imageinfo.read_facts, provider, target,
                            reference),
                self._facts_ready, lambda _m: None)

    def _mine(self, field: str, widget) -> bool:
        """True when the box is empty or still holds kontainy's own guess.

        Picking a template and then another image left the template's name
        in place — "postgres" on top of a redis image — because the field
        was simply "not empty".
        """
        current = (widget.toPlainText() if hasattr(widget, "toPlainText")
                   else widget.text()).strip()
        return not current or current == self.suggested.get(field, "")

    def _facts_ready(self, facts) -> None:
        from ...core import imageinfo
        self.facts = facts
        if self._mine("name", self.name):
            suggestion = imageinfo.suggest_name(facts.reference,
                                                self.existing_names)
            self.name.setText(suggestion)
            self.suggested["name"] = suggestion
        # The image's own values become the placeholders: an empty box now
        # means "what the image does", which is what the engine will use.
        self.command.setPlaceholderText(
            " ".join(facts.command) or "override the image CMD (optional)")
        self.entrypoint.setPlaceholderText(
            " ".join(facts.entrypoint) or "override the image ENTRYPOINT")
        self.workdir.setPlaceholderText(facts.working_dir or "the image's own")
        self.user.setPlaceholderText(facts.user or "the image's own (often root)")
        if facts.ports and self._mine("ports", self.ports):
            lines = [f"{host}:{container.split('/')[0]}"
                     + ("" if container.endswith("tcp") else "/udp")
                     for container, host, _note in
                     imageinfo.suggest_ports(facts, self.taken_ports)]
            text = "\n".join(lines)
            self.ports.setPlainText(text)
            self.suggested["ports"] = text
        if facts.volumes and self._mine("volumes", self.volumes):
            # An image that declares VOLUME gets an anonymous one on every
            # run; that is how a database loses its data on the next
            # recreate. Naming them is the fix, offered before the mistake.
            text = "\n".join(
                imageinfo.suggest_volumes(facts, self.name.text().strip()))
            self.volumes.setPlainText(text)
            self.suggested["volumes"] = text
            self.volume_note.setText(
                f"{facts.reference} declares "
                f"{', '.join(facts.volumes)} as a volume. kontainy named "
                f"them, so the data survives a recreate; leave them out and "
                f"the engine makes an anonymous volume you will not find "
                f"again.")
        if facts.env and not self.env.toPlainText().strip():
            self.env.setPlaceholderText(
                "The image already sets: "
                + ", ".join(imageinfo.env_defaults(facts)[:6]))
        self._update_preview()

    def _show_notes(self) -> None:
        from ...core import imageinfo
        host_ports = []
        for line in self.ports.toPlainText().splitlines():
            bits = line.strip().split("/")[0].split(":")
            if len(bits) >= 2:
                host_ports.append(bits[-2])
        found = imageinfo.problems(
            self.name.text().strip(), self._image_reference(),
            self.existing_names, host_ports, self.taken_ports)
        if self.trouble:
            found.append(("warning",
                          f"Could not read this target: {self.trouble}. You "
                          f"can still type an image reference by hand; "
                          f"kontainy simply has nothing to suggest from."))
        image = self._image_reference()
        template_id = self.template_box.currentData()
        if template_id and self.template_image and image and \
                image.split(":")[0].split("/")[-1] != \
                self.template_image.split(":")[0].split("/")[-1]:
            found.append((
                "warning",
                f"The template is for {self.template_image}, but the image "
                f"is {image}. The environment, ports and volumes below came "
                f"from the template and probably do not fit this image \u2014 "
                f"set Template to \u2014 none \u2014 to clear them."))
        facts = getattr(self, "facts", None)
        if facts is not None and facts.reference == self._image_reference() \
                and facts.needs_pull and self._image_reference():
            found.append(("warning",
                          f"{facts.reference} is not on this target yet, so "
                          f"the run command pulls it first. That can take a "
                          f"while and needs network."))
        if not found:
            self.notes.setVisible(False)
            # The button is re-enabled here too: hiding the warnings without
            # this left it disabled after the problem had been fixed.
            self.ok_button.setEnabled(True)
            return
        colours = {"error": "#f38ba8", "warning": "#f9e2af"}
        marks = {"error": "\u26d4", "warning": "\u26a0"}
        rows = [f"<div style='color:{colours[severity]}'>"
                f"{marks[severity]} {text}</div>"
                for severity, text in found]
        self.notes.setText("".join(rows))
        self.notes.setVisible(True)
        self.ok_button.setEnabled(
            not any(severity == "error" for severity, _ in found))

    def _engine_binary(self) -> str:
        """The binary AND the target it goes to.

        Without the context, the preview showed `docker run ...` while the
        container would land on whichever context happened to be active —
        not necessarily the one chosen in this dialog.
        """
        endpoint = self.engine_box.currentData()
        provider = getattr(endpoint, "provider", None)
        if provider is not None:
            from ...core.providers.containers import _conn_args
            return " ".join([provider.binary]
                            + _conn_args(provider, endpoint.target))
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
        image = self._image_reference() or "<image>"
        parts = [f"{binary} run"] + [f"  {f}" for f in self._flags()]
        parts.append(f"  {image}")
        if self.command.text().strip():
            parts.append(f"  {self.command.text().strip()}")
        return " \\\n".join(parts)

    def _update_preview(self):
        self.preview.setPlainText(self.command_text())
        self._show_notes()

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
                 f"Image={self._image_reference()}",
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
                 f"    image: {self._image_reference()}"]
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
        if not self._image_reference():
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

        # A choice that knows its provider is created with that engine's own
        # command — the one in the preview. Opening the socket ourselves
        # cannot work on Windows named pipes, and it hid the command that
        # this whole dialog exists to teach.
        if getattr(endpoint, "provider", None) is not None:
            self._create_via_cli(endpoint, command)
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

    def _create_via_cli(self, endpoint, command: str) -> None:
        """Run the previewed command through the run dialog."""
        import shlex

        from ...core.actions import Action, USER
        from .run_command import RunCommandDialog
        argv = shlex.split(command.replace("\\\n", " "))
        argv = endpoint.provider.prepare(Action(
            id="create-container", label="Create the container",
            command=argv, scope=USER,
            explanation=(
                "This is the command in the preview, run as it stands. "
                "Nothing else is created: if it fails, the engine's own "
                "error is shown and no container is left behind."))).command
        action = Action(
            id="create-container", label="Create the container",
            command=argv, scope=USER,
            explanation=("The command from the preview, run as it stands. "
                         "If it fails you see the engine's own error and "
                         "nothing is left behind."))
        dialog = RunCommandDialog(action, self)
        dialog.exec()
        result = getattr(dialog, "result_obj", None)
        if result is None or not result.ok:
            return
        container_id = (result.output or "").strip().splitlines()[-1] \
            if result.output.strip() else ""
        history().add(command, engine=endpoint.family, note="create container")
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
            "Image": self._image_reference(),
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
