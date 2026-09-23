"""
kontainy — Sayfa tabanı

VenvStudio'nun sayfa düzenine uyar: QLabel#header başlık, QLabel#subheader
alt başlık, altta komut şeridi.

Düğme renkleri VenvStudio kuralına göre: varsayılan QPushButton VURGU
renklidir (dolu, kalın). Araç çubuğundaki sıradan düğmeler `#secondary`,
yıkıcı olanlar `#danger` objectName'i alır — yoksa her sayfa mavi düğme
tarlasına döner.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from ...utils.config import config, history, log
from ..widgets import FlowLayout
from ..styles import _strip_bg, get_colors


class CommandStrip(QFrame):
    """Son çalıştırılan komutu gösterir ve kopyalatır.

    Arka planı `_strip_bg` ile panelin bir ton uzağına alınır — VenvStudio'nun
    B120'de çözdüğü şey: sabit bir koyu renk açık temalarda şeridi şerit
    olmaktan çıkarıyordu.
    """

    def __init__(self):
        super().__init__()
        self.setObjectName("CommandStrip")
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 8, 0)

        self.label = QLabel("$ \u2014")
        self.label.setObjectName("CommandText")
        self.label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        # Long commands wrap instead of widening the page. A single-line
        # label took the width of the whole command, and one PowerShell
        # pipeline on the Hyper-V page pushed its page to 2172 pixels. The
        # Copy button always copies the full command, wrapped or not.
        self.label.setWordWrap(True)
        self.label.setMinimumWidth(120)
        row.addWidget(self.label, 1)

        self.copy_btn = QPushButton("Copy")
        self.copy_btn.setObjectName("secondary")
        self.copy_btn.setFixedWidth(96)
        self.copy_btn.clicked.connect(self._copy)
        row.addWidget(self.copy_btn)

        self._command = ""
        self.setVisible(bool(config().get("show_command_strip", True)))
        self.apply_theme()

    def apply_theme(self) -> None:
        c = get_colors(config().get("theme", "dark"),
                       config().get("font_size", 13),
                       config().get("font_primary_size", 22),
                       config().get("font_tertiary_size", 11))
        self.setStyleSheet(
            f"QFrame#CommandStrip {{ background-color: {_strip_bg(c['card'])};"
            f" border: 1px solid {c['border']}; border-radius: 8px; }}"
            f"QLabel#CommandText {{ font-family: monospace;"
            f" font-size: {c['fs_base'] + 1}px; color: {c['success']};"
            f" padding: 9px 12px; background: transparent; }}")

    def show_command(self, command: str, *, engine: str = "", note: str = "",
                     record: bool = True) -> None:
        self._command = command
        self.label.setText(f"$ {command}")
        if record:
            history().add(command, engine=engine, note=note)
        log().debug("CLI equivalent: %s", command)

    def _copy(self) -> None:
        if self._command:
            QGuiApplication.clipboard().setText(self._command)


class Page(QWidget):
    """Tüm sayfaların tabanı."""

    NAME = "page"
    TITLE = "Sayfa"
    ICON = "•"
    SUBTITLE = ""

    busy = Signal(bool)
    status = Signal(str)

    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 18, 24, 16)
        outer.setSpacing(10)

        self.header = QLabel(self.TITLE)
        self.header.setObjectName("header")
        outer.addWidget(self.header)

        if self.SUBTITLE:
            self.subheader = QLabel(self.SUBTITLE)
            self.subheader.setObjectName("subheader")
            self.subheader.setWordWrap(True)
            outer.addWidget(self.subheader)

        # Wraps onto a second line instead of widening the page.
        self.toolbar = FlowLayout()
        self.toolbar.setSpacing(8)
        outer.addLayout(self.toolbar)

        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        outer.addLayout(self.body, 1)

        self.command_strip = CommandStrip()
        outer.addWidget(self.command_strip)

        self.build()

    # --- alt sınıfların yazacakları ---------------------------------------
    def build(self) -> None:
        """Gövdeyi kur. `self.body` düzenine widget eklenir."""

    def refresh(self) -> None:
        """Yenile'ye basıldığında çağrılır."""

    def on_shown(self) -> None:
        """Sayfaya ilk geçildiğinde bir kez çağrılır."""

    def apply_theme(self) -> None:
        """Tema değiştiğinde çağrılır; satır içi stiller burada tazelenir."""
        self.command_strip.apply_theme()

    # --- kolaylıklar -------------------------------------------------------
    def add_tool_button(self, text: str, slot, *, kind: str = "secondary",
                        width: int = None) -> QPushButton:
        """Araç çubuğu düğmesi. kind: secondary | primary | danger."""
        btn = QPushButton(text)
        if kind != "primary":
            btn.setObjectName(kind)
        btn.setCursor(Qt.PointingHandCursor)
        if width:
            btn.setFixedWidth(width)
        btn.clicked.connect(slot)
        self.toolbar.addWidget(btn)
        return btn

    def add_tool_stretch(self) -> None:
        self.toolbar.addStretch()

    def show_command(self, command: str, **kw) -> None:
        self.command_strip.show_command(command, **kw)

    def colors(self) -> dict:
        return get_colors(config().get("theme", "dark"),
                          config().get("font_size", 13),
                          config().get("font_primary_size", 22),
                          config().get("font_tertiary_size", 11))
