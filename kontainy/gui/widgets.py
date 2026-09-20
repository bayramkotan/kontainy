"""
kontainy — Paylaşılan arayüz bileşenleri

VenvStudio'nun `src/gui/widgets.py` modülünden port edilmiştir; SidebarButton
ölçüleri (44px yükseklik, işaret imleci, checkable) birebir aynıdır.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QStyledItemDelegate


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
        super().__init__(display, parent)
        self.setCheckable(True)
        self.setFixedHeight(44)
        self.setCursor(Qt.PointingHandCursor)
