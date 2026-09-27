"""The window's half of remote hosts: the selector and the servers dialog.

`ky host` did this from the command line; a server has no display, so
choosing one from the window is the point rather than a convenience.
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


pytestmark = pytest.mark.skipif(not _real_qt(), reason="needs the real PySide6")


@pytest.fixture
def window(monkeypatch):
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from kontainy.gui.main_window import MainWindow
    from kontainy.utils.workers import stop_all_jobs
    widget = MainWindow()
    saved = {"hosts": widget.config.get("ssh_hosts"),
             "active": widget.config.get("active_host")}
    yield widget, app
    widget.config.set("ssh_hosts", saved["hosts"] or [])
    widget.config.set("active_host", saved["active"] or "")
    stop_all_jobs()
    widget.close()


def test_the_selector_says_where_we_are_working(window):
    widget, _app = window
    widget.config.set("active_host", "")
    widget._refresh_host_button()
    assert "This machine" in widget.host_button.text()

    widget.config.set("ssh_hosts", [{"name": "prod",
                                     "target": "deploy@server"}])
    widget.config.set("active_host", "prod")
    widget._refresh_host_button()
    assert "prod" in widget.host_button.text()


def test_the_dialog_lists_added_servers_and_their_options(window):
    widget, app = window
    widget.config.set("ssh_hosts", [
        {"name": "prod", "target": "deploy@server", "port": 2222,
         "jump": "bastion"},
        {"name": "lab", "target": "root@10.0.0.9",
         "identity": "~/.ssh/id_ed25519"}])
    from kontainy.gui.dialogs.hosts import HostsDialog
    dialog = HostsDialog(widget)
    app.processEvents()
    names = [dialog.table.item(row, 0).text()
             for row in range(dialog.table.rowCount())]
    assert names[:2] == ["prod", "lab"]
    options = dialog.table.item(0, 2).text()
    assert "2222" in options and "bastion" in options
    dialog.close()


def test_adding_a_server_stores_no_password(window):
    widget, app = window
    widget.config.set("ssh_hosts", [])
    from kontainy.gui.dialogs.hosts import HostsDialog
    dialog = HostsDialog(widget)
    dialog.name.setText("prod")
    dialog.target.setText("deploy@server")
    dialog.port.setValue(2222)
    dialog._add()
    app.processEvents()
    stored = widget.config.get("ssh_hosts")
    assert stored[0]["target"] == "deploy@server"
    assert stored[0]["port"] == 2222
    assert not any("pass" in key.lower() for key in stored[0]), stored[0]
    dialog.close()


def test_an_ssh_config_alias_is_offered_but_not_deletable(window, monkeypatch):
    """It belongs to the user's ssh setup, not to kontainy."""
    from kontainy.core import hosts
    widget, app = window
    widget.config.set("ssh_hosts", [])
    monkeypatch.setattr(hosts, "ssh_config_hosts", lambda: ["bastion"])
    from kontainy.gui.dialogs.hosts import HostsDialog
    dialog = HostsDialog(widget)
    app.processEvents()
    assert dialog.table.item(0, 0).text() == "bastion"
    assert "ssh/config" in dialog.table.item(0, 3).text()
    dialog.table.selectRow(0)
    app.processEvents()
    assert not dialog.remove_btn.isEnabled()
    dialog.close()


def test_an_unreachable_server_is_not_selected(window, monkeypatch):
    from kontainy.core import hosts
    widget, app = window
    widget.config.set("active_host", "")
    widget.config.set("ssh_hosts", [{"name": "prod",
                                     "target": "deploy@server"}])
    monkeypatch.setattr(hosts.Host, "reach",
                        lambda self: (False, "Nothing is listening on the "
                                             "SSH port."))
    from kontainy.gui.dialogs.hosts import HostsDialog
    dialog = HostsDialog(widget)
    dialog.table.selectRow(0)
    dialog._use()
    app.processEvents()
    assert widget.config.get("active_host") == ""
    assert "Nothing is listening" in dialog.hint.text()
    dialog.close()


def test_choosing_a_server_switches_and_choosing_local_returns(window,
                                                               monkeypatch):
    from kontainy.core import hosts
    widget, app = window
    widget.config.set("ssh_hosts", [{"name": "prod",
                                     "target": "deploy@server"}])
    monkeypatch.setattr(hosts.Host, "reach", lambda self: (True, ""))
    from kontainy.gui.dialogs.hosts import HostsDialog
    dialog = HostsDialog(widget)
    dialog.table.selectRow(0)
    dialog._use()
    app.processEvents()
    assert widget.config.get("active_host") == "prod"

    dialog2 = HostsDialog(widget)
    dialog2._use_local()
    app.processEvents()
    assert widget.config.get("active_host") == ""
