"""
kontainy — Paylaşılan arayüz bileşenleri

VenvStudio'nun `src/gui/widgets.py` modülünden port edilmiştir; SidebarButton
ölçüleri (44px yükseklik, işaret imleci, checkable) birebir aynıdır.
"""

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLabel, QLayout, QPushButton, QStyledItemDelegate, QWidget


class PathElideMiddleDelegate(QStyledItemDelegate):
    """Uzun yolları ORTADAN kısaltır — soket yolları için.

    `/run/user/1000/podman/podman.sock` gibi yollarda anlamlı kısım hem
    başta hem sonda olduğundan Qt'nin varsayılan sağdan kısaltması yanlış
    tarafı yiyor.
    """

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        text = option.text
        if not text:
            return
        avail = max(0, option.rect.width() - 24)
        if avail <= 0:
            return
        option.text = option.fontMetrics.elidedText(text, Qt.ElideMiddle, avail)
        option.textElideMode = Qt.ElideMiddle


class SidebarButton(QPushButton):
    """Kenar çubuğu gezinme düğmesi."""

    def __init__(self, text, icon_text="", parent=None):
        display = f"  {icon_text}  {text}" if icon_text else f"  {text}"
        # Qt reads a single & as "underline the next letter", which turned
        # "History & Log" into "History _Log". Doubling it prints a real &.
        super().__init__(display.replace("&", "&&"), parent)
        self.setCheckable(True)
        self.setFixedHeight(44)
        self.setCursor(Qt.PointingHandCursor)


class LabelWrapPolicy(QObject):
    """Make every QLabel wrap by default, application-wide.

    A label that does not wrap is as wide as its text, and Qt's stacked
    widget gives the whole window the width of its widest page. One long
    label — a rule summary, a finding with a long socket path, a PowerShell
    command — was enough to push a page past the screen: the Diagnostics page
    reached 1582 pixels on Windows while fitting on Linux, because the text
    it shows depends on the machine. Fixing labels one at a time only finds
    the ones seen so far; this makes wrapping the default everywhere.

    A label that must stay on one line — the status bar's — sets the Qt
    property "noWrap" to True.
    """

    def eventFilter(self, obj, event):
        if (event.type() == QEvent.Polish and isinstance(obj, QLabel)
                and not obj.wordWrap() and not obj.property("noWrap")):
            obj.setWordWrap(True)
        return False


class FlowLayout(QLayout):
    """A row of widgets that continues on the next line when it runs out of
    room — for toolbars and button rows.

    Every page's width was set by its toolbar: a single QHBoxLayout row, as
    wide as all its buttons together. The Config Catalog already needed 1084
    pixels against 1048 available on Linux, and on Windows, where fonts and
    buttons are wider, the Containers and Docker pages overflowed too. With
    a flow layout a page is only as wide as its widest single item.

    Drop-in for the QHBoxLayout calls the pages make: addWidget(w, stretch)
    ignores the stretch, addStretch and addSpacing are no-ops, and
    addLayout wraps the nested layout in a widget so it moves as one piece.
    """

    def __init__(self, parent=None, hspacing: int = 8, vspacing: int = 6):
        super().__init__(parent)
        self._items = []
        self._hspacing = hspacing
        self._vspacing = vspacing
        self.setContentsMargins(0, 0, 0, 0)

    # --- the QHBoxLayout-compatible surface the pages use -----------------
    def addWidget(self, widget, stretch: int = 0, *args):          # noqa: N802
        super().addWidget(widget)

    def addLayout(self, layout, *args):                             # noqa: N802
        holder = QWidget()
        layout.setContentsMargins(0, 0, 0, 0)
        holder.setLayout(layout)
        super().addWidget(holder)

    def addStretch(self, *args):                                    # noqa: N802
        pass

    def addSpacing(self, *args):                                    # noqa: N802
        pass

    def setSpacing(self, spacing: int):                             # noqa: N802
        self._hspacing = spacing

    def spacing(self) -> int:
        return self._hspacing

    # --- QLayout ------------------------------------------------------------
    def addItem(self, item):                                        # noqa: N802
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):                                   # noqa: N802
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int):                                   # noqa: N802
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):                                  # noqa: N802
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:                            # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:                    # noqa: N802
        return self._arrange(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect):                                    # noqa: N802
        super().setGeometry(rect)
        self._arrange(rect, apply=True)

    def sizeHint(self):                                             # noqa: N802
        return self.minimumSize()

    def minimumSize(self):                                          # noqa: N802
        size = QSize()
        for item in self._items:
            if not item.isEmpty():
                size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QSize(margins.left() + margins.right(),
                            margins.top() + margins.bottom())

    def _arrange(self, rect, apply: bool) -> int:
        """Place items in lines; items on a line are centred vertically, so a
        label sits level with the taller buttons beside it."""
        margins = self.contentsMargins()
        area = rect.adjusted(margins.left(), margins.top(),
                             -margins.right(), -margins.bottom())
        lines, line, x = [], [], area.x()
        for item in self._items:
            if item.isEmpty():
                continue
            hint = item.sizeHint()
            if line and x + hint.width() > area.right() + 1:
                lines.append(line)
                line, x = [], area.x()
            line.append((item, hint, x))
            x += hint.width() + self._hspacing
        if line:
            lines.append(line)

        y = area.y()
        for index, line in enumerate(lines):
            height = max(hint.height() for _item, hint, _x in line)
            if apply:
                for item, hint, left in line:
                    top = y + (height - hint.height()) // 2
                    item.setGeometry(QRect(QPoint(left, top), hint))
            y += height + (self._vspacing if index < len(lines) - 1 else 0)
        return y - rect.y() + margins.bottom()
