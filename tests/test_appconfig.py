"""The applications' own settings — Docker Desktop, WSL, VMware, VirtualBox.

Bayram, 2026-09-25: "ky'den Docker Desktop, KVM, VirtualBox, VMware Pro
içinde config'lere ulaşıp değiştirebilelim."
"""

import json

import pytest

from kontainy.core import appconfig as ac

WSLCONFIG = """# my own note
[wsl2]
memory = 8GB
processors = 4
"""


# --- reading -----------------------------------------------------------------
def test_ini_is_read_with_its_sections():
    values = ac.parse_ini(WSLCONFIG)
    assert values["wsl2.memory"] == "8GB"
    assert values["wsl2.processors"] == "4"


def test_vmware_key_value_is_read():
    values = ac.parse_keyvalue('prefvmx.minVmMemPct = "75"\n# comment\n')
    assert values["prefvmx.minVmMemPct"] == "75"


def test_virtualbox_xml_is_read():
    xml = ('<VirtualBox><Global><SystemProperties '
           'defaultMachineFolder="/home/b/VMs"/></Global></VirtualBox>')
    assert ac.parse_xml(xml)["SystemProperties.defaultMachineFolder"] \
        == "/home/b/VMs"


def test_docker_desktop_values_come_from_its_json(tmp_path, monkeypatch):
    path = tmp_path / "settings-store.json"
    path.write_text(json.dumps({"MemoryMiB": 8192}), encoding="utf-8")
    monkeypatch.setitem(ac.DOCKER_DESKTOP.paths, "linux", [str(path)])
    monkeypatch.setattr("kontainy.core.registry.OS_KIND", "linux")
    values = ac.read_values(ac.DOCKER_DESKTOP)
    assert values["MemoryMiB"] == 8192


# --- the INI writer ----------------------------------------------------------
def test_writing_ini_keeps_comments_and_order(tmp_path):
    path = tmp_path / ".wslconfig"
    path.write_text(WSLCONFIG, encoding="utf-8")
    text = ac.set_ini_key(path, "wsl2.memory", "16GB")
    assert "# my own note" in text, "a user's comment is not ours to delete"
    assert "memory = 16GB" in text and "8GB" not in text
    assert text.index("memory") < text.index("processors"), "order kept"


def test_a_missing_key_is_appended_to_its_section(tmp_path):
    path = tmp_path / ".wslconfig"
    path.write_text(WSLCONFIG, encoding="utf-8")
    text = ac.set_ini_key(path, "wsl2.nestedVirtualization", "true")
    assert "nestedVirtualization = true" in text
    assert ac.parse_ini(text)["wsl2.memory"] == "8GB", "nothing else moved"


def test_a_missing_section_is_created(tmp_path):
    path = tmp_path / ".wslconfig"
    path.write_text(WSLCONFIG, encoding="utf-8")
    text = ac.set_ini_key(path, "experimental.autoMemoryReclaim", "gradual")
    assert "[experimental]" in text
    assert ac.parse_ini(text)["experimental.autoMemoryReclaim"] == "gradual"


# --- writing through an action -----------------------------------------------
def test_a_write_backs_the_file_up_first(tmp_path, monkeypatch):
    path = tmp_path / "settings-store.json"
    path.write_text(json.dumps({"MemoryMiB": 2048}), encoding="utf-8")
    monkeypatch.setitem(ac.DOCKER_DESKTOP.paths, "linux", [str(path)])
    monkeypatch.setattr("kontainy.core.registry.OS_KIND", "linux")
    key = next(k for k in ac.DOCKER_DESKTOP.keys if k.key == "MemoryMiB")
    action = ac.write_action(ac.DOCKER_DESKTOP, key, "8192")
    message = action.func()
    assert json.loads(path.read_text())["MemoryMiB"] == 8192
    assert "previous file is kept" in message
    assert list(tmp_path.glob("*.bak*")), "no backup was written"


def test_a_dangerous_key_is_marked_and_explained():
    key = next(k for k in ac.DOCKER_DESKTOP.keys
               if k.key == "ExposeDockerAPIOnTCP2375")
    assert key.danger
    assert "owns the machine" in key.gotcha
    action = ac.write_action(ac.DOCKER_DESKTOP, key, "true")
    assert action.destructive, "an exposed API must ask twice"


def test_a_key_the_app_overwrites_says_so():
    key = next(k for k in ac.DOCKER_DESKTOP.keys if k.key == "MemoryMiB")
    assert key.close_first
    action = ac.write_action(ac.DOCKER_DESKTOP, key, "4096")
    assert "shut down" in action.explanation


def test_a_read_only_application_is_never_written(monkeypatch):
    monkeypatch.setattr("kontainy.core.registry.OS_KIND", "linux")
    key = ac.VIRTUALBOX.keys[0]
    action = ac.write_action(ac.VIRTUALBOX, key, "/tmp/VMs")
    assert action.func is None and not action.command
    assert "does not write" in action.explanation
    assert "VBoxManage" in key.gotcha, "say the supported way instead"


def test_every_key_says_what_it_does():
    for app in ac.ALL_APPS:
        for key in app.keys:
            assert len(key.what) > 25, f"{app.id}/{key.key}: no explanation"
            assert key.vtype in ("str", "int", "bool", "path")


def test_each_application_knows_where_its_file_lives():
    for app in ac.ALL_APPS:
        assert app.paths, f"{app.id}: no path at all"
        for system, paths in app.paths.items():
            assert system in ("windows", "linux", "macos")
            assert all(paths)
