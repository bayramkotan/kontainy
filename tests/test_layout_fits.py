"""The window, and every page in it, must fit a 1280x800 screen.

History, so the next change does not repeat it:

* Qt's stacked widget gives the window the width of its widest page, and a
  crowded toolbar once pushed the whole application to 1316 pixels. Every
  page now sits in a scroll area, so the window always fits.
* That made the window test pass while pages still overflowed their own
  area and scrolled sideways. The early page tests compared against 1280,
  but a page only gets the screen minus the sidebar — about 1048 pixels.
  Linux passed with the Config Catalog already at 1084; Windows, with wider
  fonts, failed on Containers and Docker. Pages are now measured against
  the space they really get.
* Toolbars and button rows use a flow layout, so a page is as wide as its
  widest single item, not all its buttons together.
* Every label wraps by default, so no text can widen a page.
* Qt does not recompute a hidden widget's layout when its text changes, so
  each page is opened before it is measured.

Windows' fonts are wider than Linux's. The checks run a second time with the
application font enlarged, so a Linux CI run sees what Windows would.

Needs the real PySide6; skipped where CI stubs it out.
"""

import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _real_qt() -> bool:
    try:
        import PySide6
    except ImportError:
        return False
    return getattr(PySide6, "__version__", "") != "0.0.0-stub"


pytestmark = pytest.mark.skipif(not _real_qt(),
                                reason="needs the real PySide6")

SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 800
WINDOWS_FONT_SCALE = 1.3
LONG_COMMAND = "Get-VM | Select-Object " + ", ".join(
    f"@{{n='Field{i}';e={{$_.Property{i}.ToString()}}}}" for i in range(40))
FILLER = " ".join(["unix:///home/someone/.docker/desktop/docker.sock"] * 30)


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def window(app):
    from kontainy.gui.main_window import MainWindow
    from kontainy.utils.workers import stop_all_jobs
    win = MainWindow()
    win.resize(SCREEN_WIDTH, SCREEN_HEIGHT)
    win.show()
    app.processEvents()
    yield win
    stop_all_jobs()
    win.close()


def _settle(app, rounds: int = 5) -> None:
    for _ in range(rounds):
        app.processEvents()


def _available(window) -> int:
    """The width a page actually gets: the screen minus the sidebar."""
    return window.stack.width()


def _culprits(page, limit: int = 5) -> str:
    """The widest visible widgets on a page — what to fix when a test fails."""
    from PySide6.QtWidgets import QLabel, QWidget
    rows = []
    for child in page.findChildren(QWidget):
        if not child.isVisibleTo(page):
            continue
        text = child.text()[:50] if isinstance(child, QLabel) else ""
        rows.append((child.minimumSizeHint().width(), type(child).__name__,
                     child.objectName(), text))
    rows.sort(reverse=True)
    return "; ".join(f"{w}px {kind}{'#' + name if name else ''}"
                     f"{' ' + repr(text) if text else ''}"
                     for w, kind, name, text in rows[:limit])


def _check_every_page(window, app, prepare) -> None:
    limit = _available(window)
    for name, page in window.pages.items():
        window.go(name)
        _settle(app)
        prepare(page)
        _settle(app)
        width = page.minimumSizeHint().width()
        assert width <= limit, (
            f"{name} needs {width}px but gets {limit}px. Widest: "
            f"{_culprits(page)}")


@pytest.fixture
def wider_font(app):
    """Enlarge the application font the way Windows' Segoe UI renders wider."""
    from PySide6.QtGui import QFont
    original = QFont(app.font())
    bigger = QFont(original)
    bigger.setPointSizeF(original.pointSizeF() * WINDOWS_FONT_SCALE)
    app.setFont(bigger)
    yield
    app.setFont(original)


def _nothing(page):
    pass


def _long_command(page):
    page.show_command(LONG_COMMAND, record=False)


def _fill_labels(page):
    from PySide6.QtWidgets import QLabel
    for label in page.findChildren(QLabel):
        if label.isVisibleTo(page) and not label.property("noWrap"):
            label.setText(FILLER)


# --- the window ---------------------------------------------------------------
def test_window_fits_a_1280_screen(window):
    assert window.minimumSizeHint().width() <= SCREEN_WIDTH


def test_window_fits_an_800_high_screen(window):
    assert window.minimumSizeHint().height() <= SCREEN_HEIGHT


def test_every_page_is_wrapped_in_a_scroll_area(window):
    from PySide6.QtWidgets import QScrollArea
    for index in range(window.stack.count()):
        assert isinstance(window.stack.widget(index), QScrollArea)


# --- every page within the space it really gets ----------------------------------
def test_every_page_fits_its_area(window, app):
    _check_every_page(window, app, _nothing)


def test_a_long_command_does_not_widen_any_page(window, app):
    _check_every_page(window, app, _long_command)


def test_no_label_anywhere_can_widen_a_page(window, app):
    _check_every_page(window, app, _fill_labels)


# --- and again with Windows-sized fonts ------------------------------------------
def test_every_page_fits_with_windows_sized_fonts(window, app, wider_font):
    _check_every_page(window, app, _nothing)


def test_long_texts_fit_with_windows_sized_fonts(window, app, wider_font):
    _check_every_page(window, app, _fill_labels)


# --- background jobs at shutdown ----------------------------------------------------
def test_a_running_job_survives_shutdown(app):
    """stop_all_jobs used to clear the list after a fixed wait, so a job still
    running lost its last reference and Qt aborted with 'QThread: Destroyed
    while thread is still running' — seen on Windows.

    Jobs started by earlier tests (Windows' Hyper-V probe runs PowerShell and
    takes a while) are drained first: the first version of this test assumed
    the queue was empty and failed on Windows with 2 instead of 1.
    """
    from kontainy.utils import workers
    workers.stop_all_jobs()
    assert workers.active_job_count() == 0, "earlier jobs did not drain"

    done = []
    workers.run_job(workers.CallableJob(lambda: time.sleep(1.0) or "ok"),
                    lambda result: done.append(result))
    left = workers.stop_all_jobs(timeout_ms=100)
    assert left == 1, "a job still running must be reported"
    assert workers.active_job_count() == 1, "and must stay referenced"
    for _ in range(100):
        app.processEvents()
        time.sleep(0.03)
        if done:
            break
    assert done == ["ok"]
    assert workers.stop_all_jobs() == 0
