"""The window must fit a 1280-pixel-wide screen.

It did not: Qt's stacked widget takes the widest page's minimum width for the
whole window, and one crowded toolbar on the Config Catalog page pushed the
entire application to 1316 pixels. Every page is now wrapped in a scroll area
and the offending toolbars were tightened; this test keeps it that way.

It needs the real PySide6, so it is skipped where CI stubs it out.
"""

import os

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


@pytest.fixture(scope="module")
def window():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from kontainy.gui.main_window import MainWindow
    win = MainWindow()
    win.resize(SCREEN_WIDTH, SCREEN_HEIGHT)
    win.show()
    app.processEvents()
    yield win
    from kontainy.utils.workers import stop_all_jobs
    stop_all_jobs()
    win.close()


def test_window_fits_a_1280_screen(window):
    width = window.minimumSizeHint().width()
    assert width <= SCREEN_WIDTH, (
        f"the window needs {width}px; something on one of the pages is "
        f"forcing it wider than a {SCREEN_WIDTH}px screen")


def test_window_fits_an_800_high_screen(window):
    height = window.minimumSizeHint().height()
    assert height <= SCREEN_HEIGHT, f"the window needs {height}px of height"


def test_every_page_is_wrapped_in_a_scroll_area(window):
    from PySide6.QtWidgets import QScrollArea
    for index in range(window.stack.count()):
        assert isinstance(window.stack.widget(index), QScrollArea)
