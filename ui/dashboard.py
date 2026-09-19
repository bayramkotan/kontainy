"""
kontainy — Ana pencere
============================

Sekmeler:
  🔌 Motorlar     — keşfedilen tüm soketler + terminalin gerçek hedefi
  📦 Container'lar — TÜM motorlardaki container'lar tek tabloda, Motor sütunuyla
  ⚙️ Ayarlar      — settings_catalog'un tamamı: arama, süzme, açıklama, tuzak
  ⚠️ Tuzaklar     — bilinmediğinde saat yakan ayarların listesi

Ayar paneli elle yazılmaz; core/settings_catalog.py'den üretilir.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtGui import QFont, QColor, QAction
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QTabWidget, QPushButton, QLineEdit,
    QComboBox, QTextBrowser, QSplitter, QHeaderView, QAbstractItemView,
    QGroupBox, QMessageBox, QStatusBar,
)

from core import discovery
from core.api import EngineError
from core.settings_catalog import (
    ALL_SETTINGS, SURFACE_TITLES, DANGER_TITLES, search as catalog_search,
    with_gotchas, stats,
)

DANGER_COLOR = {0: None, 1: QColor("#8a6d00"), 2: QColor("#a33")}


# ---------------------------------------------------------------------------
#  Arka plan işçileri — GUI hiçbir zaman soket beklemez
# ---------------------------------------------------------------------------
class DiscoveryWorker(QObject):
    done = Signal(list)
    failed = Signal(str)

    def run(self):
        try:
            self.done.emit(discovery.discover(probe=True))
        except Exception as exc:                      # noqa: BLE001
            self.failed.emit(str(exc))


class ContainerWorker(QObject):
    done = Signal(list)

    def __init__(self, endpoints):
        super().__init__()
        self.endpoints = endpoints

    def run(self):
        rows = []
        for ep in self.endpoints:
            if not ep.reachable:
                continue
            client = discovery.client_for(ep)
            try:
                for c in client.containers(all_=True):
                    names = c.get("Names") or []
                    name = (names[0] if names else c.get("Id", "")[:12]).lstrip("/")
                    rows.append({
                        "engine": ep.title,
                        "endpoint": ep.address,
                        "name": name,
                        "image": c.get("Image", ""),
                        "state": c.get("State", ""),
                        "status": c.get("Status", ""),
                        "id": c.get("Id", "")[:12],
                    })
            except EngineError:
                continue
        self.done.emit(rows)


# Çalışan (thread, worker) çiftleri burada tutulur.
#
# Bu liste SÜS DEĞİL: referans tutulmazsa run_in_thread döner dönmez Python
# worker'ı (ve QThread'i) çöpe atar, C++ tarafı çalışan iş parçacığının
# altından silinir ve uygulama "QThread: Destroyed while thread is still
# running / Aborted (core dumped)" ile çöker.
#
# Referansı çağıranın kendi üzerinde tutmak yetmez — worker'ın kendisi de
# saklanmalıdır, çünkü moveToThread sahiplik devretmez.
_LIVE_JOBS: list = []


def run_in_thread(parent, worker: QObject, slot):
    """Bir worker'ı arka planda çalıştırır ve bitene kadar canlı tutar."""
    thread = QThread()
    worker.moveToThread(thread)
    job = (thread, worker)
    _LIVE_JOBS.append(job)

    thread.started.connect(worker.run)
    worker.done.connect(slot)
    worker.done.connect(thread.quit)
    if hasattr(worker, "failed"):
        worker.failed.connect(thread.quit)

    def _release():
        if job in _LIVE_JOBS:
            _LIVE_JOBS.remove(job)

    thread.finished.connect(_release)
    thread.start()
    return thread


def stop_all_jobs(wait_ms: int = 3000) -> None:
    """Kapanışta çalışan tüm iş parçacıklarını düzgünce sonlandırır."""
    for thread, _worker in list(_LIVE_JOBS):
        thread.quit()
        thread.wait(wait_ms)
    _LIVE_JOBS.clear()


# ---------------------------------------------------------------------------
#  Sekme: Motorlar
# ---------------------------------------------------------------------------
class EnginesTab(QWidget):
    engines_ready = Signal(list)

    def __init__(self):
        super().__init__()
        self.endpoints = []
        layout = QVBoxLayout(self)

        # --- Terminalin gerçek hedefi ---
        target_box = QGroupBox("Terminaliniz şu an nereye bakıyor?")
        tb = QVBoxLayout(target_box)
        self.target_table = QTableWidget(0, 3)
        self.target_table.setHorizontalHeaderLabels(["Katman", "Değer", "Kazanan"])
        self.target_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch)
        self.target_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.target_table.setMaximumHeight(150)
        tb.addWidget(self.target_table)
        self.target_note = QLabel()
        self.target_note.setWordWrap(True)
        tb.addWidget(self.target_note)
        layout.addWidget(target_box)

        # --- Bulunan motorlar ---
        bar = QHBoxLayout()
        self.refresh_btn = QPushButton("🔄 Yeniden Tara")
        self.refresh_btn.clicked.connect(self.refresh)
        bar.addWidget(self.refresh_btn)
        bar.addStretch()
        layout.addLayout(bar)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Adres", "Kaynak", "Motor", "Durum", "CLI Hedefi"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.table)

        self.refresh()

    def refresh(self):
        self.refresh_btn.setEnabled(False)
        self._fill_target()
        worker = DiscoveryWorker()
        worker.failed.connect(lambda m: self.refresh_btn.setEnabled(True))
        run_in_thread(self, worker, self._fill_engines)

    def _fill_target(self):
        target = discovery.resolve_cli_target()
        self.target_table.setRowCount(0)
        for layer, value, won in target.as_rows():
            r = self.target_table.rowCount()
            self.target_table.insertRow(r)
            for col, text in enumerate([layer, value, "✅" if won else ""]):
                item = QTableWidgetItem(text)
                if won:
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
                self.target_table.setItem(r, col, item)

        note = (f"Etkin hedef: <b>{target.winner or '—'}</b> "
                f"&nbsp;·&nbsp; kaynak: {target.winner_layer}")
        if target.winner_layer.startswith("DOCKER_HOST"):
            note += ("<br><span style='color:#a33'>DOCKER_HOST ayarlı olduğu için "
                     "<code>docker context use</code> komutu hiçbir etki yapmaz. "
                     "Context'i kullanmak için önce bu değişkeni kaldırın: "
                     "<code>unset DOCKER_HOST</code></span>")
        shim = discovery.docker_shim_warning()
        if shim:
            note += f"<br><span style='color:#8a6d00'>{shim}</span>"
        self.target_note.setText(note)

    def _fill_engines(self, endpoints):
        self.endpoints = endpoints
        self.table.setRowCount(0)
        for ep in endpoints:
            r = self.table.rowCount()
            self.table.insertRow(r)
            state = ep.title if ep.reachable else f"❌ {ep.error[:60]}"
            cells = [ep.address, ep.source, ep.family, state,
                     "⬅ terminal buraya gidiyor" if ep.is_cli_default else ""]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if not ep.reachable:
                    item.setForeground(QColor("#a33"))
                self.table.setItem(r, col, item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.refresh_btn.setEnabled(True)
        self.engines_ready.emit(endpoints)


# ---------------------------------------------------------------------------
#  Sekme: Container'lar — bütün motorlar tek tabloda
# ---------------------------------------------------------------------------
class ContainersTab(QWidget):
    def __init__(self):
        super().__init__()
        self.endpoints = []
        self.rows = []
        layout = QVBoxLayout(self)

        bar = QHBoxLayout()
        self.refresh_btn = QPushButton("🔄 Yenile")
        self.refresh_btn.clicked.connect(self.refresh)
        bar.addWidget(self.refresh_btn)
        for label, action in [("▶ Başlat", "start"), ("■ Durdur", "stop"),
                              ("↻ Yeniden Başlat", "restart")]:
            btn = QPushButton(label)
            btn.clicked.connect(lambda _=False, a=action: self._act(a))
            bar.addWidget(btn)
        bar.addStretch()
        self.count_label = QLabel("—")
        bar.addWidget(self.count_label)
        layout.addLayout(bar)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Motor", "Ad", "Imaj", "Durum", "Statü", "ID"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.table)

        self.hint = QLabel(
            "Bu tablo context'e bakmaz — bulunan HER motora ayrı ayrı bağlanır. "
            "Bir container hiçbir zaman 'kaybolmaz', yalnızca başka bir motorda olur.")
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)

    def set_endpoints(self, endpoints):
        self.endpoints = endpoints
        self.refresh()

    def refresh(self):
        if not self.endpoints:
            return
        self.refresh_btn.setEnabled(False)
        run_in_thread(self, ContainerWorker(self.endpoints), self._fill)

    def _fill(self, rows):
        self.rows = rows
        self.table.setRowCount(0)
        for row in rows:
            r = self.table.rowCount()
            self.table.insertRow(r)
            cells = [row["engine"], row["name"], row["image"],
                     row["state"], row["status"], row["id"]]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(str(text))
                if col == 3:
                    item.setForeground(QColor("#2a7") if text == "running"
                                       else QColor("#888"))
                self.table.setItem(r, col, item)
        running = sum(1 for x in rows if x["state"] == "running")
        self.count_label.setText(f"{len(rows)} container · {running} çalışıyor")
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.refresh_btn.setEnabled(True)

    def _act(self, action: str):
        r = self.table.currentRow()
        if r < 0 or r >= len(self.rows):
            return
        row = self.rows[r]
        ep = next((e for e in self.endpoints if e.address == row["endpoint"]), None)
        if ep is None:
            return
        client = discovery.client_for(ep)
        try:
            getattr(client, action)(row["id"])
        except EngineError as exc:
            QMessageBox.warning(self, "İşlem başarısız", str(exc))
            return
        self.refresh()


# ---------------------------------------------------------------------------
#  Sekme: Ayarlar — katalogdan üretilir
# ---------------------------------------------------------------------------
class SettingsTab(QWidget):
    def __init__(self, only_gotchas: bool = False):
        super().__init__()
        self.only_gotchas = only_gotchas
        self.items = with_gotchas() if only_gotchas else list(ALL_SETTINGS)
        layout = QVBoxLayout(self)

        bar = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText(
            "Ara: anahtar, başlık, açıklama, CLI bayrağı, etiket…")
        self.search_box.textChanged.connect(self._apply)
        bar.addWidget(self.search_box, 3)

        self.engine_filter = QComboBox()
        self.engine_filter.addItems(["Tüm motorlar", "docker", "podman", "both"])
        self.engine_filter.currentIndexChanged.connect(self._apply)
        bar.addWidget(self.engine_filter, 1)

        self.surface_filter = QComboBox()
        self.surface_filter.addItem("Tüm yüzeyler", None)
        for key, title in SURFACE_TITLES.items():
            self.surface_filter.addItem(title, key)
        self.surface_filter.currentIndexChanged.connect(self._apply)
        bar.addWidget(self.surface_filter, 1)

        self.danger_filter = QComboBox()
        self.danger_filter.addItems(["Tüm risk düzeyleri", "Güvenli",
                                     "Dikkat", "Tehlikeli"])
        self.danger_filter.currentIndexChanged.connect(self._apply)
        bar.addWidget(self.danger_filter, 1)
        layout.addLayout(bar)

        splitter = QSplitter(Qt.Horizontal)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Anahtar", "Başlık", "Motor", "Yüzey", "Kapsam", "Risk"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.currentCellChanged.connect(self._show_detail)
        splitter.addWidget(self.table)

        self.detail = QTextBrowser()
        self.detail.setOpenExternalLinks(True)
        splitter.addWidget(self.detail)
        splitter.setSizes([620, 480])
        layout.addWidget(splitter)

        self.count_label = QLabel()
        layout.addWidget(self.count_label)

        self._apply()

    def _filtered(self):
        rows = self.items
        text = self.search_box.text().strip()
        if text:
            hits = set(id(s) for s in catalog_search(text))
            rows = [s for s in rows if id(s) in hits]
        engine = self.engine_filter.currentText()
        if engine != "Tüm motorlar":
            rows = [s for s in rows if s.engine == engine]
        surface = self.surface_filter.currentData()
        if surface:
            rows = [s for s in rows if s.surface == surface]
        di = self.danger_filter.currentIndex()
        if di > 0:
            rows = [s for s in rows if s.danger == di - 1]
        return rows

    def _apply(self):
        self.filtered = self._filtered()
        self.table.setRowCount(0)
        for s in self.filtered:
            r = self.table.rowCount()
            self.table.insertRow(r)
            cells = [s.key, s.title, s.engine, SURFACE_TITLES.get(s.surface, s.surface),
                     "kullanıcı" if s.privilege == "user" else "root",
                     DANGER_TITLES[s.danger]]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                color = DANGER_COLOR.get(s.danger)
                if color and col == 5:
                    item.setForeground(color)
                self.table.setItem(r, col, item)
        self.table.resizeColumnsToContents()
        self.count_label.setText(
            f"{len(self.filtered)} / {len(self.items)} ayar gösteriliyor")
        if self.filtered:
            self.table.selectRow(0)

    def _show_detail(self, row, *_):
        if row < 0 or row >= len(self.filtered):
            self.detail.clear()
            return
        s = self.filtered[row]
        parts = [
            f"<h2 style='margin-bottom:2px'>{s.title}</h2>",
            f"<code style='font-size:12pt'>{s.key}</code>",
            f"<p>{s.desc}</p>",
            "<table cellpadding='4'>",
            f"<tr><td><b>Motor</b></td><td>{s.engine}</td></tr>",
            f"<tr><td><b>Yüzey</b></td><td>"
            f"{SURFACE_TITLES.get(s.surface, s.surface)}</td></tr>",
            f"<tr><td><b>Tür</b></td><td>{s.vtype}</td></tr>",
        ]
        if s.default is not None:
            parts.append(f"<tr><td><b>Varsayılan</b></td><td><code>{s.default}</code>"
                         f"</td></tr>")
        if s.choices:
            parts.append("<tr><td><b>Seçenekler</b></td><td>"
                         + ", ".join(f"<code>{c}</code>" for c in s.choices)
                         + "</td></tr>")
        if s.cli:
            parts.append(f"<tr><td><b>CLI karşılığı</b></td><td><code>{s.cli}</code>"
                         f"</td></tr>")
        parts.append(f"<tr><td><b>Dosya</b></td><td>{s.file}</td></tr>")
        parts.append("<tr><td><b>Kapsam</b></td><td>"
                     + ("kullanıcı — kontainy doğrudan yazabilir"
                        if s.privilege == "user"
                        else "root — salt okunur gösterilir, komut verilir")
                     + "</td></tr>")
        parts.append(f"<tr><td><b>Yeniden başlatma</b></td><td>"
                     f"{'gerekli' if s.restart else 'gerekmez'}</td></tr>")
        parts.append(f"<tr><td><b>Risk</b></td><td>{DANGER_TITLES[s.danger]}</td></tr>")
        parts.append("</table>")

        if s.gotcha:
            parts.append(
                "<div style='background:#fff6e0;border-left:4px solid #e0a800;"
                "padding:8px;margin-top:10px'>"
                f"<b>⚠️ Tuzak</b><br>{s.gotcha}</div>")
        if s.tags:
            parts.append("<p style='color:#777'>Etiketler: "
                         + ", ".join(s.tags) + "</p>")
        if s.docs:
            parts.append(f"<p><a href='{s.docs}'>Resmî dokümantasyon →</a></p>")
        self.detail.setHtml("".join(parts))


# ---------------------------------------------------------------------------
#  Ana pencere
# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("kontainy")
        self.resize(1280, 820)

        tabs = QTabWidget()
        self.engines_tab = EnginesTab()
        self.containers_tab = ContainersTab()
        self.engines_tab.engines_ready.connect(self.containers_tab.set_endpoints)

        tabs.addTab(self.engines_tab, "🔌 Motorlar")
        tabs.addTab(self.containers_tab, "📦 Container'lar")
        tabs.addTab(SettingsTab(), "⚙️ Ayarlar")
        tabs.addTab(SettingsTab(only_gotchas=True), "⚠️ Tuzaklar")
        self.setCentralWidget(tabs)

        st = stats()
        self.status = QStatusBar()
        bar = self.status
        bar.showMessage(
            f"Katalog: {st['toplam']} ayar "
            f"(docker {st['docker']} · podman {st['podman']} · ortak {st['ortak']}) "
            f"— {st['kullanici_kapsami']} tanesi root gerektirmez, "
            f"{st['tuzakli']} tanesinde tuzak notu var")
        self.setStatusBar(bar)

    def closeEvent(self, event):
        """Çalışan iş parçacıkları bitmeden pencere kapanmaz."""
        stop_all_jobs()
        super().closeEvent(event)
