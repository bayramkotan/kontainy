"""
kontainy — the Ctrl+K box

Nineteen pages, 152 settings, 204 Learn topics, and every one of them
previously reachable only by clicking the sidebar and then hunting inside
the page. This is the way in: type three letters, press Enter, be there.

Design decisions worth keeping:

* **It opens instantly or it is useless.** The index is built once and
  handed in; the only work on a keystroke is ranking a few hundred strings.
  Nothing here talks to an engine.
* **Every row says what it is.** Pages, settings, containers and Learn
  topics in one list with no labels is a guessing game, so each row carries
  its kind on the right and its home underneath.
* **The scopes are visible, not folklore.** A palette with secret prefixes
  is a palette only its author can drive, so the empty state lists them.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QVBoxLayout, QWidget,
)

from ...core.palette import KINDS, SCOPES, rank
from ...utils.config import config
from ..styles import get_colors

ROW_HEIGHT = 46


class _Row(QWidget):
    """One result: label, detail underneath, kind on the right."""

    def __init__(self, entry, colors: dict):
        super().__init__()
        c = colors
        box = QHBoxLayout(self)
        box.setContentsMargins(12, 5, 12, 5)
        box.setSpacing(10)

        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(1)

        label = QLabel(entry.label)
        label.setStyleSheet(f"font-size: {c['fs_base'] + 1}px;"
                            f" font-weight: 600; color: {c['fg']};"
                            f" background: transparent;")
        text.addWidget(label)

        if entry.detail:
            detail = QLabel(entry.detail)
            detail.setStyleSheet(f"font-size: {c['fs_small']}px;"
                                 f" color: {c['fg_muted']};"
                                 f" background: transparent;")
            text.addWidget(detail)
        box.addLayout(text, 1)

        if entry.hint:
            hint = QLabel(entry.hint)
            hint.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            hint.setStyleSheet(f"font-size: {c['fs_tiny']}px;"
                               f" color: {c['fg_muted']};"
                               f" background: transparent;")
            box.addWidget(hint)


class CommandPalette(QDialog):
    """Ctrl+K. Emits `chosen` with the entry's payload."""

    chosen = Signal(object)

    def __init__(self, entries: list, parent=None):
        super().__init__(parent)
        self.entries = entries
        self.results = []
        self.setWindowTitle("Go to…")
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setModal(True)

        c = get_colors(config().get("theme", "dark"),
                       config().get("font_size", 13),
                       config().get("font_primary_size", 22),
                       config().get("font_tertiary_size", 11))
        self.colors = c

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        frame = QFrame()
        frame.setObjectName("PaletteFrame")
        frame.setStyleSheet(
            f"QFrame#PaletteFrame {{ background-color: {c['card']};"
            f" border: 1px solid {c['border']}; border-radius: 12px; }}")
        outer.addWidget(frame)

        inner = QVBoxLayout(frame)
        inner.setContentsMargins(10, 10, 10, 10)
        inner.setSpacing(8)

        self.box = QLineEdit()
        self.box.setPlaceholderText(
            "Go to a page, setting, container or topic…")
        self.box.setStyleSheet(
            f"QLineEdit {{ background-color: {c['input_bg']};"
            f" color: {c['fg']}; border: 1px solid {c['border']};"
            f" border-radius: 8px; padding: 10px 12px;"
            f" font-size: {c['fs_base'] + 3}px; }}")
        self.box.textChanged.connect(self._filter)
        self.box.returnPressed.connect(self._accept_current)
        self.box.installEventFilter(self)
        inner.addWidget(self.box)

        self.list = QListWidget()
        self.list.setFrameShape(QFrame.NoFrame)
        self.list.setStyleSheet(
            f"QListWidget {{ background: transparent; border: none; }}"
            f"QListWidget::item {{ border-radius: 8px; margin: 1px 0; }}"
            f"QListWidget::item:selected {{"
            f" background-color: {c['accent']}; }}")
        self.list.itemActivated.connect(lambda _i: self._accept_current())
        self.list.itemClicked.connect(lambda _i: self._accept_current())
        inner.addWidget(self.list, 1)

        self.footer = QLabel()
        self.footer.setStyleSheet(f"font-size: {c['fs_tiny']}px;"
                                  f" color: {c['fg_muted']};"
                                  f" padding: 0 4px;")
        inner.addWidget(self.footer)

        self._resize_to(parent)
        self._filter("")

    def _resize_to(self, parent) -> None:
        """A wide, short box near the top — where the eyes already are."""
        if parent is not None:
            width = max(560, min(820, int(parent.width() * 0.62)))
            height = min(520, max(320, int(parent.height() * 0.62)))
            self.resize(width, height)
            centre = parent.frameGeometry().center()
            self.move(centre.x() - width // 2,
                      parent.frameGeometry().top()
                      + max(40, int(parent.height() * 0.12)))
        else:
            self.resize(640, 420)

    # --- searching ---------------------------------------------------------
    def _filter(self, text: str) -> None:
        self.results = rank(text, self.entries, limit=50)
        self.list.clear()
        for entry in self.results:
            item = QListWidgetItem()
            item.setSizeHint(_Row(entry, self.colors).sizeHint())
            self.list.addItem(item)
            self.list.setItemWidget(item, _Row(entry, self.colors))
        if self.results:
            self.list.setCurrentRow(0)

        if not text.strip():
            # The scopes have to be visible somewhere, or they are folklore.
            self.footer.setText(
                "  ".join(f"<b>{ch}</b> {name}"
                          for ch, name in SCOPES.items())
                + f"   ·   {len(self.entries)} things indexed")
        elif self.results:
            kinds = {}
            for entry in self.results:
                kinds[entry.kind] = kinds.get(entry.kind, 0) + 1
            self.footer.setText(
                "  ·  ".join(
                    f"{count} {KINDS.get(kind, (kind, 0))[0] or kind}"
                    for kind, count in kinds.items())
                + "    ↑↓ move   ↵ go   Esc close")
        else:
            self.footer.setText(
                f"Nothing matches “{text}”. Letters are matched in "
                f"order, not as a block — “snm” finds "
                f"“Short name mode”.")

    # --- keys --------------------------------------------------------------
    def eventFilter(self, obj, event) -> bool:
        """Arrows drive the list while the cursor stays in the box.

        Without this, moving down the results means leaving the text field,
        and then typing another letter does nothing — which feels broken
        even though every widget is behaving.
        """
        if obj is self.box and event.type() == QEvent.KeyPress:
            key = event.key()
            if key in (Qt.Key_Down, Qt.Key_Up):
                row = self.list.currentRow()
                count = self.list.count()
                if count:
                    step = 1 if key == Qt.Key_Down else -1
                    self.list.setCurrentRow((row + step) % count)
                return True
            if key in (Qt.Key_PageDown, Qt.Key_PageUp):
                row = self.list.currentRow()
                step = 8 if key == Qt.Key_PageDown else -8
                self.list.setCurrentRow(
                    max(0, min(self.list.count() - 1, row + step)))
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    def _accept_current(self) -> None:
        row = self.list.currentRow()
        if 0 <= row < len(self.results):
            self.chosen.emit(self.results[row])
        self.accept()
