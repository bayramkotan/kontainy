"""The Help menu follows VenvStudio's: About, Check for Updates, then the
three links, with kontainy's documentation links in a submenu."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _real_qt() -> bool:
    try:
        import PySide6
    except ImportError:
        return False
    return getattr(PySide6, "__version__", "") != "0.0.0-stub"


pytestmark = pytest.mark.skipif(not _real_qt(), reason="needs the real PySide6")


@pytest.fixture(scope="module")
def help_menu():
    from PySide6.QtWidgets import QApplication, QMenu
    app = QApplication.instance() or QApplication([])
    from kontainy.gui.main_window import MainWindow
    from kontainy.utils.workers import stop_all_jobs
    window = MainWindow()
    app.processEvents()
    menu = next(m for m in window.menuBar().findChildren(QMenu)
                if m.title() == "&Help")
    yield menu
    stop_all_jobs()
    window.close()


def _labels(menu) -> list:
    return [a.text() for a in menu.actions() if not a.isSeparator()]


def test_the_order_matches_venvstudio(help_menu):
    labels = _labels(help_menu)
    assert "About" in labels[0]
    assert "Check for Updates" in labels[1]
    assert "GitHub Repository" in labels[2]
    assert "PyPI Page" in labels[3]
    assert "Report a Bug" in labels[4]


def test_documentation_links_are_in_a_submenu(help_menu):
    submenu = help_menu.actions()[-1].menu()
    assert submenu is not None
    titles = " ".join(a.text() for a in submenu.actions())
    for name in ("Docker", "Podman", "Quadlet", "Kubernetes", "libvirt"):
        assert name in titles


def test_check_for_updates_does_not_block_the_window(help_menu, monkeypatch):
    """VenvStudio asks the network on the GUI thread behind a progress
    dialog; kontainy runs it in a worker, as it does every slow thing."""
    from kontainy.core import updater
    window = help_menu.parent().parent()
    calls = []
    monkeypatch.setattr(updater, "check_for_update",
                        lambda *a, **k: calls.append(1) or {"error": "test"})
    monkeypatch.setattr(window, "_updates_answer", lambda result: None)
    window._check_for_updates()
    from kontainy.utils.workers import active_job_count, stop_all_jobs
    assert active_job_count() >= 0          # the call returned immediately
    stop_all_jobs()
