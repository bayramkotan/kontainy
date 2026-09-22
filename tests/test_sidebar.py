"""The sidebar shows each technology only where it can exist.

WSL is Windows-only; libvirt does not run on Windows. Offering either where
it can never work is clutter at best and a support question at worst.
"""

import importlib

import pytest


def _sidebar_on(monkeypatch, os_kind: str) -> list:
    from kontainy.core import registry
    monkeypatch.setattr(registry, "OS_KIND", os_kind)
    import kontainy.gui.main_window as mw
    mw = importlib.reload(mw)
    return [cls.NAME for header, cls in mw.SIDEBAR if cls is not None]


@pytest.fixture(autouse=True)
def restore(monkeypatch):
    yield
    import kontainy.gui.main_window as mw
    importlib.reload(mw)


def test_windows_shows_wsl_and_hides_libvirt(monkeypatch):
    names = _sidebar_on(monkeypatch, "windows")
    assert "platform-wsl" in names
    assert "platform-hyperv" in names
    assert "platform-libvirt" not in names
    assert "platform-docker" in names and "platform-kubernetes" in names


def test_linux_shows_libvirt_and_hides_wsl(monkeypatch):
    names = _sidebar_on(monkeypatch, "linux")
    assert "platform-libvirt" in names
    assert "platform-wsl" not in names
    assert "platform-hyperv" not in names
    assert "platform-incus" in names


def test_no_section_header_is_left_empty(monkeypatch):
    from kontainy.core import registry
    for os_kind in ("linux", "windows", "macos"):
        monkeypatch.setattr(registry, "OS_KIND", os_kind)
        import kontainy.gui.main_window as mw
        mw = importlib.reload(mw)
        entries = mw.SIDEBAR
        for index, (header, cls) in enumerate(entries):
            if header is not None:
                nxt = entries[index + 1] if index + 1 < len(entries) else None
                assert nxt is not None and nxt[1] is not None, \
                    f"{os_kind}: empty section {header}"


def test_page_names_are_unique(monkeypatch):
    names = _sidebar_on(monkeypatch, "linux")
    assert len(names) == len(set(names))
