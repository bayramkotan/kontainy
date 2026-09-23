"""
kontainy — Overview

Replaces the Engines page, which squeezed three unrelated things onto one
screen — Docker's context resolution chain, a raw socket list, and systemd
units — and was called "Engines" while knowing about only two of the seven
technologies kontainy covers. It did not fit on the page, and nothing on it
could be edited.

Each of those pieces moved to where it belongs: the resolution chain to the
Docker page, the systemd units to a Services tab on each technology's page.
What is left here is the one thing an overview should do: show every
technology at a glance — installed or not, which target is active, how many
objects it holds, whether its services run — and take you to it in a click.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QSizePolicy, QVBoxLayout, QWidget,
)

from ...core import actions as act
from ...core.providers import PROVIDERS
from ...core.providers.base import count_label as _count
from ...core.registry import OS_KIND, OS_LABEL
from ...utils.workers import CallableJob, run_job
from .base import Page


def _summarise(provider) -> dict:
    """One card's worth of facts, gathered off the GUI thread."""
    out = {"id": provider.id, "available": provider.available(),
           "version": "", "active": None, "targets": 0, "objects": None,
           "error": "", "services_up": 0, "services_total": 0}
    if out["available"]:
        out["version"] = provider.version()
        targets = provider.targets()
        out["targets"] = len(targets)
        active = next((t for t in targets if t.active), None)
        out["active"] = active
        listing = provider.objects(active)
        if listing.error:
            out["error"] = listing.error.strip()
        else:
            out["objects"] = len(listing.rows)
    for unit, user, _why in (provider.services if OS_KIND == "linux" else []):
        if act._unit_property(unit, user, "is-enabled") == "not-found":
            continue
        out["services_total"] += 1
        if act._unit_property(unit, user, "is-active") == "active":
            out["services_up"] += 1
    return out


def _probe_all(providers: list) -> list:
    """Probe every technology, saying what each one answered.

    Startup used to be silent in the terminal: kontainy was busy asking
    seven tools for their version and the user saw nothing at all.
    """
    import time
    from ...utils.config import log
    out = []
    for provider in providers:
        started = time.perf_counter()
        info = _summarise(provider)
        took = (time.perf_counter() - started) * 1000
        if info["available"]:
            log().info("%-14s %s \u00b7 %s \u00b7 %.0f ms", provider.name,
                       info["version"] or "installed",
                       (_count(info["objects"], provider.object_noun_plural)
                        if info["objects"] is not None else "unreachable"),
                       took)
        else:
            log().info("%-14s not installed \u00b7 %.0f ms", provider.name, took)
        out.append(info)
    return out


class OverviewPage(Page):
    NAME = "overview"
    TITLE = "Overview"
    ICON = "\U0001f9ed"
    SUBTITLE = ("Every container and virtualisation technology kontainy "
                "knows, at a glance. Click a card to manage it.")

    open_page = Signal(str)

    def build(self) -> None:
        self.providers = [p for p in PROVIDERS if p.shown_here()]
        self.cards = {}
        self.loaded = False

        self.refresh_btn = self.add_tool_button(
            "\U0001f501  Refresh", self.refresh, kind="primary")
        self.add_tool_stretch()
        self.summary_label = QLabel(f"\u2014 \u00b7 {OS_LABEL}")
        self.toolbar.addWidget(self.summary_label)

        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        self.grid = QGridLayout(inner)
        self.grid.setSpacing(14)
        self.grid.setContentsMargins(0, 4, 8, 8)
        columns = 3
        for index, provider in enumerate(self.providers):
            card = self._make_card(provider)
            self.cards[provider.id] = card
            self.grid.addWidget(card["frame"], index // columns,
                                index % columns)
        for column in range(columns):
            self.grid.setColumnStretch(column, 1)
        self.grid.setRowStretch(len(self.providers) // columns + 1, 1)
        area.setWidget(inner)
        self.body.addWidget(area, 1)

    def _make_card(self, provider) -> dict:
        frame = QFrame()
        frame.setObjectName("overviewCard")
        # Never shorter than its contents. With the default policy the grid
        # squeezed cards below their size hint and cut the last line and the
        # Open button in half.
        frame.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        frame.setCursor(Qt.PointingHandCursor)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)

        title = QLabel(f"{provider.icon}  {provider.name}")
        title.setObjectName("cardTitle")
        layout.addWidget(title)

        status = QLabel("checking\u2026")
        status.setWordWrap(True)
        status.setTextFormat(Qt.RichText)
        layout.addWidget(status)

        detail = QLabel("")
        detail.setWordWrap(True)
        detail.setTextFormat(Qt.RichText)
        layout.addWidget(detail, 1)

        # The tool's own words go behind an arrow: useful when something is
        # wrong, noise on a card for a technology the user may never install.
        more = QPushButton("\u25b8  Details")
        more.setObjectName("secondary")
        more.setCursor(Qt.PointingHandCursor)
        more.setCheckable(True)
        more.hide()
        more_row = QHBoxLayout()
        more_row.addWidget(more)
        more_row.addStretch()
        layout.addLayout(more_row)

        raw = QLabel("")
        raw.setWordWrap(True)
        raw.setObjectName("cardRaw")
        raw.setTextInteractionFlags(Qt.TextSelectableByMouse)
        raw.hide()
        layout.addWidget(raw)
        more.toggled.connect(
            lambda on, b=more, r=raw: (r.setVisible(on),
                                       b.setText(("\u25be  Details" if on
                                                  else "\u25b8  Details"))))

        row = QHBoxLayout()
        button = QPushButton("Open \u2192")
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(
            lambda _=False, pid=provider.id: self.open_page.emit(
                f"platform-{pid}"))
        row.addStretch()
        row.addWidget(button)
        layout.addLayout(row)

        frame.mousePressEvent = (
            lambda _e, pid=provider.id: self.open_page.emit(f"platform-{pid}"))
        return {"frame": frame, "title": title, "status": status,
                "detail": detail, "button": button, "more": more, "raw": raw}

    # --- data ----------------------------------------------------------------
    def on_shown(self) -> None:
        if not self.loaded:
            self.refresh()

    def refresh(self) -> None:
        self.refresh_btn.setEnabled(False)
        self.busy.emit(True)
        self.status.emit("Checking every technology\u2026")
        run_job(CallableJob(_probe_all, self.providers), self._fill,
                self._failed)

    def _failed(self, message: str) -> None:
        self.refresh_btn.setEnabled(True)
        self.busy.emit(False)
        self.status.emit(f"Overview failed: {message}")

    def _fill(self, summaries: list) -> None:
        self.loaded = True
        self.refresh_btn.setEnabled(True)
        self.busy.emit(False)
        c = self.colors()
        installed = 0
        for info in summaries:
            card = self.cards.get(info["id"])
            provider = next(p for p in self.providers if p.id == info["id"])
            if card is None:
                continue
            card["more"].setChecked(False)
            card["more"].setVisible(bool(info["error"]))
            card["raw"].setText(info["error"])
            card["raw"].hide()
            if not info["available"]:
                card["status"].setText(
                    f"<span style='color:{c['fg_muted']}'>\u25cb not "
                    f"installed</span>")
                card["detail"].setText(
                    f"<span style='color:{c['fg_muted']}'>Install it from "
                    f"its page.</span>")
                card["button"].setText("Install \u2192")
                continue
            installed += 1
            card["button"].setText("Open \u2192")
            colour = c["warning"] if info["error"] else c["success"]
            card["status"].setText(
                f"<span style='color:{colour}'>\u25cf "
                f"{info['version'] or 'installed'}</span>")
            lines = []
            active = info["active"]
            if active:
                lines.append(f"<b>{provider.target_noun}:</b> {active.name}")
            if info["targets"] > 1:
                lines.append(_count(info["targets"],
                                    provider.target_noun_plural)
                             + " configured")
            if info["objects"] is not None:
                lines.append("<b>" + _count(info["objects"],
                                            provider.object_noun_plural)
                             + "</b>")
            elif info["error"]:
                from ...core.providers.base import summarise_error
                lines.append(f"<span style='color:{c['warning']}'>"
                             f"\u26a0 {summarise_error(info['error'])}"
                             f"</span>")
            if info["services_total"]:
                up, total = info["services_up"], info["services_total"]
                colour = c["success"] if up else c["warning"]
                lines.append(f"<span style='color:{colour}'>{up}/{total} "
                             f"services running</span>")
            card["detail"].setText("<br>".join(lines))
        self.summary_label.setText(
            f"{installed} of {len(summaries)} installed \u00b7 {OS_LABEL}")
        self.status.emit(f"{installed} of {len(summaries)} technologies "
                         f"installed")

    def apply_theme(self) -> None:
        super().apply_theme()
        c = self.colors()
        for card in self.cards.values():
            card["frame"].setStyleSheet(
                f"QFrame#overviewCard {{ background: {c['card']};"
                f" border: 1px solid {c['border']}; border-radius: 10px; }}"
                f"QFrame#overviewCard:hover {{ border: 1px solid {c['accent']}; }}"
                f"QFrame#overviewCard QLabel {{ background: transparent;"
                f" border: none; }}")
            card["title"].setStyleSheet(
                f"color: {c['accent']}; font-size: {c['fs_base'] + 5}px;"
                f" font-weight: bold;")
            for key in ("status", "detail"):
                card[key].setStyleSheet(f"font-size: {c['fs_base'] + 1}px;")
            card["raw"].setStyleSheet(
                f"color: {c['fg_muted']}; font-size: {c['fs_base'] - 1}px;"
                f" font-family: \"Cascadia Code\", \"Fira Code\", "
                f"\"JetBrains Mono\", \"Consolas\", monospace;")
