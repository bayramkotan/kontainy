"""
kontainy — Ana pencere

Yerleşim VenvStudio'nun `main_window.py::_setup_ui` düzenine uyar:
220px sabit kenar çubuğu (#sidebar), üstte emoji + uygulama adı, altında
sürüm etiketi, sonra SidebarButton'lar, en altta altbilgi.

Sayfalar QStackedWidget içinde durur ve `_switch_page(index)` ile
değiştirilir; nav_buttons listesi sayfa numarasıyla AYNI SIRADADIR —
VenvStudio'da Projects düğmesinin ekrandaki yeri ile listedeki yeri
ayrıştığı için oraya uzun bir not düşülmüş; burada ikisi bilerek aynı
tutulur.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QScrollArea,
    QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow, QProgressBar,
    QStackedWidget, QStatusBar, QVBoxLayout, QWidget,
)

from ..core.catalog import stats as catalog_stats
from ..core.constants import APP_NAME, APP_TAGLINE, APP_VERSION
from ..learn.content import learn_stats
from ..core.registry import stats as registry_stats
from ..rules import rule_stats
from ..utils.config import config, log
from ..utils.workers import stop_all_jobs
from .pages.containers import ContainersPage
from .pages.diagnostics import DiagnosticsPage
from .pages.overview import OverviewPage
from .pages.learn import LearnPage
from .pages.logs import LogPage
from .pages.preferences import PreferencesPage
from .pages.settings import CatalogPage
from ..core.providers import PROVIDERS
from ..core.registry import OS_KIND
from .pages.platform import make_platform_page
from .pages.tools import InstallPage
from .styles import get_colors, get_theme
from .window_menu import WindowMenuMixin
from .widgets import SidebarButton

# The sidebar is grouped. A flat list of pages stopped being readable once
# KVM, LXC and Kubernetes arrived, and "where is KVM" was the first thing
# anyone asked. None means a section header rather than a page.
def _platform(provider_id: str):
    """The page class for one provider, or None where it cannot exist.

    WSL is Windows-only and libvirt does not run on Windows; showing either
    where it can never work would only be clutter.
    """
    for provider in PROVIDERS:
        if provider.id == provider_id:
            if OS_KIND not in provider.platforms:
                return None
            return make_platform_page(provider)
    return None


# Grouped by technology, the way the user asked for it: every container and
# virtualisation technology gets its own entry, each with the same layout —
# an active-target dropdown on top and tabs underneath, like VenvStudio's
# Packages page. None marks a section header; entries that resolve to None
# for this operating system are dropped.
SIDEBAR = [
    ("OVERVIEW", None),
    (None, OverviewPage),
    (None, DiagnosticsPage),

    ("CONTAINERS", None),
    (None, _platform("docker")),
    (None, _platform("podman")),
    (None, ContainersPage),

    ("ORCHESTRATION", None),
    (None, _platform("kubernetes")),

    ("VIRTUALISATION", None),
    (None, _platform("libvirt")),
    (None, _platform("wsl")),

    ("SYSTEM CONTAINERS", None),
    (None, _platform("incus")),
    (None, _platform("lxd")),

    ("SET UP", None),
    (None, InstallPage),
    (None, CatalogPage),
    (None, PreferencesPage),

    ("LEARN", None),
    (None, LearnPage),
    (None, LogPage),
]


def _drop_empty_sections(entries: list) -> list:
    """Remove unavailable pages, then any header left with nothing under it."""
    kept = [(h, cls) for h, cls in entries if h is not None or cls is not None]
    out = []
    for index, (header, cls) in enumerate(kept):
        if header is not None:
            following = kept[index + 1] if index + 1 < len(kept) else None
            if following is None or following[0] is not None:
                continue
        out.append((header, cls))
    return out


SIDEBAR = _drop_empty_sections(SIDEBAR)

PAGE_CLASSES = tuple(cls for _, cls in SIDEBAR if cls is not None)


class MainWindow(WindowMenuMixin, QMainWindow):
    def __init__(self, version: str = APP_VERSION):
        super().__init__()
        self.config = config()
        self._applying_theme = False
        self._shown = set()

        self._setup_window(version)
        self._setup_ui()
        self._setup_menubar()
        self._connect_pages()
        self._apply_theme()

        start = self.config.get("start_page", "overview")
        index = next((i for i, p in enumerate(PAGE_CLASSES)
                      if p.NAME == start), 0)
        self._switch_page(index)

    # --- palet kısayolu (VenvStudio'daki self._c ile aynı) -----------------
    def _c(self) -> dict:
        return get_colors(
            self.config.get("theme", "dark"),
            self.config.get("font_size", 13),
            self.config.get("font_primary_size", 22),
            self.config.get("font_tertiary_size", 11),
        )

    # --- pencere -----------------------------------------------------------
    def _setup_window(self, version: str) -> None:
        self.setWindowTitle(f"{APP_NAME} v{version}")
        self.setMinimumSize(980, 640)

        width = self.config.get("window_width", 1280)
        height = self.config.get("window_height", 820)
        saved_x = self.config.get("window_x", None)
        saved_y = self.config.get("window_y", None)

        target = None
        if saved_x is not None and saved_y is not None:
            for screen in QApplication.screens():
                if screen.geometry().contains(saved_x + width // 2,
                                              saved_y + height // 2):
                    target = screen
                    break
        if target is None:
            target = QApplication.primaryScreen()
        avail = target.availableGeometry()

        width = min(width, avail.width() - 40)
        height = min(height, avail.height() - 40)
        self.resize(width, height)

        if saved_x is not None and saved_y is not None:
            x = max(avail.x(), min(saved_x, avail.x() + avail.width() - width))
            y = max(avail.y(), min(saved_y, avail.y() + avail.height() - height))
        else:
            x = avail.x() + (avail.width() - width) // 2
            y = avail.y() + (avail.height() - height) // 2
        self.move(x, y)

    # --- yerleşim ----------------------------------------------------------
    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(232)
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(8, 16, 8, 16)
        sl.setSpacing(4)

        self.logo_label = QLabel(f"  \U0001f4e6 {APP_NAME}")
        self.logo_label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        self.logo_label.setFixedHeight(48)
        sl.addWidget(self.logo_label)

        self.version_label = QLabel(f"      v{APP_VERSION}")
        sl.addWidget(self.version_label)

        self.tagline_label = QLabel(f"      {APP_TAGLINE}")
        self.tagline_label.setWordWrap(True)
        sl.addWidget(self.tagline_label)
        sl.addSpacing(20)

        self.stack = QStackedWidget()
        self.pages = {}
        self.page_list = []
        self.nav_buttons = []
        self.section_labels = []

        # The navigation scrolls on its own. With seven technologies the list
        # outgrew an 820-pixel-high window and the last entry was cut in half.
        nav_area = QScrollArea()
        nav_area.setWidgetResizable(True)
        nav_area.setFrameShape(QFrame.NoFrame)
        nav_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        nav_area.setStyleSheet("QScrollArea { background: transparent; }"
                               "QScrollArea > QWidget > QWidget"
                               " { background: transparent; }")
        nav_widget = QWidget()
        nav = QVBoxLayout(nav_widget)
        nav.setContentsMargins(0, 0, 0, 0)
        nav.setSpacing(3)

        index = 0
        for section, page_class in SIDEBAR:
            if page_class is None:
                if self.nav_buttons:
                    nav.addSpacing(8)
                label = QLabel(f"   {section}")
                label.setObjectName("SidebarSection")
                nav.addWidget(label)
                self.section_labels.append(label)
                continue

            page = page_class()
            self.pages[page.NAME] = page
            self.page_list.append(page)
            # Every page sits in a scroll area. Qt's stacked widget takes the
            # widest page's minimum width for the whole window, so one crowded
            # toolbar used to push the entire application off a 1280-pixel
            # screen. Now a crowded page scrolls; the window always fits.
            holder = QScrollArea()
            holder.setWidgetResizable(True)
            holder.setFrameShape(QFrame.NoFrame)
            holder.setWidget(page)
            self.stack.addWidget(holder)
            page.busy.connect(self._set_busy)
            page.status.connect(self._set_status)

            button = SidebarButton(page.TITLE, page.ICON)
            button.setToolTip(page.SUBTITLE)
            button.clicked.connect(
                lambda _checked=False, i=index: self._switch_page(i))
            nav.addWidget(button)
            self.nav_buttons.append(button)
            index += 1

        nav.addStretch()
        nav_area.setWidget(nav_widget)
        sl.addWidget(nav_area, 1)

        cs = catalog_stats()
        rs = rule_stats()
        ls = learn_stats()
        ts = registry_stats()
        self.footer_label = QLabel(
            f"      {ts['total']} tools · {ts['installed']} installed<br>"
            f"      {cs['total']} settings<br>"
            f"      {rs['total']} diagnostic rules<br>"
            f"      {ls['written']}/{ls['target']} Learn topics")
        sl.addWidget(self.footer_label)

        main_layout.addWidget(sidebar)
        main_layout.addWidget(self.stack, 1)

        bar = QStatusBar()
        self.status_label = QLabel("Ready")
        bar.addWidget(self.status_label, 1)
        self.busy_bar = QProgressBar()
        self.busy_bar.setRange(0, 0)
        self.busy_bar.setFixedWidth(130)
        self.busy_bar.setVisible(False)
        bar.addPermanentWidget(self.busy_bar)
        self.catalog_label = QLabel(
            f"catalogue {cs['total']} · user scope "
            f"{cs['user_scope']} · gotchas {cs['gotchas']}")
        bar.addPermanentWidget(self.catalog_label)
        self.setStatusBar(bar)

    def _connect_pages(self) -> None:
        self.pages["overview"].open_page.connect(self.go)
        self.pages["diagnostics"].open_setting.connect(self._open_setting)
        self.pages["learn"].open_setting.connect(self._open_setting)
        self.pages["preferences"].theme_changed.connect(self.set_theme)
        self.pages["preferences"].restart_needed.connect(self._set_status)
        for name, page in self.pages.items():
            if name.startswith("platform-") or name == "install":
                page.open_setting.connect(self._open_setting)

    # --- gezinme -----------------------------------------------------------
    def _switch_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        for i, button in enumerate(self.nav_buttons):
            button.setChecked(i == index)
        page = self.page_list[index] if index < len(self.page_list) else None
        if page is not None and page.NAME not in self._shown:
            self._shown.add(page.NAME)
            page.on_shown()
            log().debug("Sayfa açıldı: %s", page.NAME)

    def go(self, name: str) -> None:
        for i, page_class in enumerate(PAGE_CLASSES):
            if page_class.NAME == name:
                self._switch_page(i)
                return

    def _open_setting(self, key: str) -> None:
        self.go("catalog")
        self.pages["catalog"].focus_key(key)

    # --- tema --------------------------------------------------------------
    def _apply_theme(self) -> None:
        if self._applying_theme:
            return
        self._applying_theme = True
        try:
            theme = self.config.get("theme", "dark")
            self.setStyleSheet(get_theme(
                theme,
                font_family=self.config.get("font_family", ""),
                font_size=self.config.get("font_size", 13),
                primary_family=self.config.get("font_primary_family", ""),
                primary_size=self.config.get("font_primary_size", 22),
                tertiary_family=self.config.get("font_tertiary_family", ""),
                tertiary_size=self.config.get("font_tertiary_size", 11),
            ))
            self._refresh_sidebar_styles()
            for page in self.pages.values():
                try:
                    page.apply_theme()
                except Exception as exc:                     # noqa: BLE001
                    log().warning("Sayfa teması uygulanamadı (%s): %s",
                                  page.NAME, exc)
        finally:
            self._applying_theme = False

    def set_theme(self, name: str) -> None:
        self.config.set("theme", name)
        self._apply_theme()

    def _refresh_sidebar_styles(self) -> None:
        """QSS'in ulaşmadığı satır içi stiller.

        VenvStudio'daki aynı adlı yöntemin karşılığı: kenar çubuğundaki
        etiketler QSS seçicilerine düşmüyor, renkleri elle verilmeli.
        """
        c = self._c()
        self.logo_label.setStyleSheet(f"color: {c['accent']};")
        self.version_label.setStyleSheet(
            f"color: {c['fg_muted']}; font-size: {c['fs_tiny']}px;")
        self.tagline_label.setStyleSheet(
            f"color: {c['fg_muted']}; font-size: {c['fs_tiny']}px;")
        self.footer_label.setStyleSheet(
            f"color: {c['fg_muted']}; font-size: {c['fs_tiny']}px;")
        for label in self.section_labels:
            label.setStyleSheet(
                f"color: {c['fg_muted']}; font-size: {c['fs_tiny']}px;"
                f" font-weight: bold; letter-spacing: 1.2px;"
                f" padding: 2px 0 4px 0;")
        self.catalog_label.setStyleSheet(
            f"color: {c['fg_muted']}; font-size: {c['fs_tiny']}px;")

    # --- durum çubuğu ------------------------------------------------------
    def _set_busy(self, busy: bool) -> None:
        self.busy_bar.setVisible(busy)

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def closeEvent(self, event) -> None:
        self.config.set("window_width", self.width())
        self.config.set("window_height", self.height())
        self.config.set("window_x", self.x())
        self.config.set("window_y", self.y())
        stop_all_jobs()
        super().closeEvent(event)
