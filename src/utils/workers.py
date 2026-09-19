"""
kontainy — Arka plan işleri
============================

GUI hiçbir zaman sokete karşı beklemez. Her uzun iş bir QThread'e taşınır ve
sonucu sinyalle döner.

⚠️ BU DOSYANIN VAR OLMA SEBEBİ BİR ÇÖKME
----------------------------------------
v0.1.0'da uygulama açılışta `QThread: Destroyed while thread is still running
/ Aborted (core dumped)` ile çöktü. Sebep: worker nesnesine Python tarafında
hiçbir referans kalmıyordu. Yardımcı fonksiyon döner dönmez çöp toplayıcı
worker'ı (ve QThread'i) yok etti, C++ nesnesi ÇALIŞAN bir iş parçacığının
altından silindi.

`moveToThread` sahiplik devretmez. `QThread(parent)` vermek de yetmez —
worker ayrı bir nesnedir.

KURAL: `(thread, worker)` çifti modül seviyesindeki `_LIVE_JOBS` listesinde
tutulur ve yalnızca `thread.finished` sinyalinde çıkarılır. Yeni bir arka
plan işi eklerken elle `QThread()` yaratılmaz; `run_job()` kullanılır.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal

# (thread, worker) çiftleri — referans tutulmazsa uygulama çöker (yukarı bak)
_LIVE_JOBS: list = []


class Job(QObject):
    """Arka plan işlerinin taban sınıfı.

    Alt sınıf `run()` yazar ve işi bitince `done` sinyalini yayar.
    Hata olursa `failed` yayılır; ikisi de iş parçacığını sonlandırır.
    """

    done = Signal(object)
    failed = Signal(str)
    progress = Signal(str)

    def run(self) -> None:                                   # pragma: no cover
        raise NotImplementedError


class CallableJob(Job):
    """Herhangi bir fonksiyonu arka planda çalıştırır.

    Basit işler için alt sınıf yazmaya gerek bırakmaz:
        run_job(CallableJob(lambda: client.containers()), self._fill)
    """

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self) -> None:
        try:
            self.done.emit(self._fn(*self._args, **self._kwargs))
        except Exception as exc:                             # noqa: BLE001
            self.failed.emit(str(exc))


def run_job(job: Job, on_done, on_failed=None) -> QThread:
    """Bir Job'u arka planda çalıştırır ve bitene kadar canlı tutar."""
    thread = QThread()
    job.moveToThread(thread)
    entry = (thread, job)
    _LIVE_JOBS.append(entry)

    thread.started.connect(job.run)
    job.done.connect(on_done)
    job.done.connect(thread.quit)
    if on_failed is not None:
        job.failed.connect(on_failed)
    job.failed.connect(thread.quit)

    def _release():
        if entry in _LIVE_JOBS:
            _LIVE_JOBS.remove(entry)

    thread.finished.connect(_release)
    thread.start()
    return thread


def active_job_count() -> int:
    """Durum çubuğundaki iş göstergesi için."""
    return len(_LIVE_JOBS)


def stop_all_jobs(wait_ms: int = 3000) -> None:
    """Kapanışta çalışan tüm iş parçacıklarını düzgünce sonlandırır."""
    for thread, _job in list(_LIVE_JOBS):
        thread.quit()
        thread.wait(wait_ms)
    _LIVE_JOBS.clear()
