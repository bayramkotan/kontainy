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


class StreamJob(Job):
    """A job that reports lines while it works.

    The function is given an `emit` callable; whatever it passes arrives on
    the `progress` signal, in the GUI thread, as it happens.
    """

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self) -> None:
        try:
            self.done.emit(self._fn(self.progress.emit, *self._args,
                                    **self._kwargs))
        except Exception as exc:                             # noqa: BLE001
            self.failed.emit(str(exc))


def run_job(job: Job, on_done, on_failed=None, on_progress=None) -> QThread:
    """Bir Job'u arka planda çalıştırır ve bitene kadar canlı tutar."""
    thread = QThread()
    job.moveToThread(thread)
    entry = (thread, job)
    _LIVE_JOBS.append(entry)

    thread.started.connect(job.run)
    if on_progress is not None:
        job.progress.connect(on_progress)
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


def stop_all_jobs(timeout_ms: int = 25000) -> int:
    """Wait for background jobs at shutdown; return how many are still running.

    The first version waited three seconds per job and then cleared the list
    whatever had happened. A job still running — a PowerShell probe of
    Hyper-V takes longer than that on Windows — lost its last reference, was
    garbage-collected mid-flight, and Qt aborted with "QThread: Destroyed
    while thread is still running", the same crash this module was written
    to prevent. It was seen at the end of a test run on Windows.

    Now: one overall deadline, generous enough for every CLI timeout used in
    kontainy (the longest is 20 seconds), and a job that is still running is
    NEVER dropped from the list. Keeping the reference is what keeps Qt from
    destroying a live thread; the job finishes on its own and releases itself
    through thread.finished as usual.
    """
    import time as _time
    deadline = _time.monotonic() + timeout_ms / 1000.0
    for thread, _job in list(_LIVE_JOBS):
        thread.quit()
        remaining = int(max(0.0, deadline - _time.monotonic()) * 1000)
        thread.wait(remaining)
    still_running = [(t, j) for t, j in _LIVE_JOBS if t.isRunning()]
    _LIVE_JOBS[:] = still_running
    return len(still_running)
