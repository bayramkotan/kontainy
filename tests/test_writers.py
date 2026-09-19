"""Writing configuration is the part that can break a user's daemon."""

import json

import pytest

from src.core import writers


def test_toml_edit_preserves_comments(tmp_path):
    path = tmp_path / "containers.conf"
    path.write_text('# distribution defaults\n[containers]\n'
                    '# what log_driver does\nlog_driver = "journald"\n',
                    encoding="utf-8")
    writers.write_toml_key(path, "containers.log_driver", "k8s-file")
    text = path.read_text(encoding="utf-8")
    assert "# distribution defaults" in text
    assert "# what log_driver does" in text
    assert 'log_driver = "k8s-file"' in text


def test_toml_new_key_lands_in_its_section(tmp_path):
    path = tmp_path / "containers.conf"
    path.write_text('[containers]\nlog_driver = "journald"\n\n'
                    '[engine]\nruntime = "crun"\n', encoding="utf-8")
    writers.write_toml_key(path, "containers.cgroup_manager", "systemd")
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines.index('cgroup_manager = "systemd"') < lines.index("[engine]")


def test_toml_new_section_is_appended(tmp_path):
    path = tmp_path / "containers.conf"
    path.write_text('[containers]\nlog_driver = "journald"\n', encoding="utf-8")
    writers.write_toml_key(path, "network.firewall_driver", "nftables")
    text = path.read_text(encoding="utf-8")
    assert "[network]" in text and 'firewall_driver = "nftables"' in text


def test_backup_is_taken(tmp_path):
    path = tmp_path / "containers.conf"
    path.write_text('[containers]\nlog_driver = "journald"\n', encoding="utf-8")
    result = writers.write_toml_key(path, "containers.log_driver", "none")
    assert result.backup is not None and result.backup.is_file()
    assert "journald" in result.backup.read_text(encoding="utf-8")


def test_json_nested_key(tmp_path):
    path = tmp_path / "config.json"
    writers.write_json_key(path, "proxies.default.httpProxy", "http://p:3128")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["proxies"]["default"]["httpProxy"] == "http://p:3128"


def test_invalid_json_is_not_overwritten(tmp_path):
    path = tmp_path / "daemon.json"
    path.write_text("{ this is not json", encoding="utf-8")
    with pytest.raises(writers.WriteRefused):
        writers.write_json_key(path, "log-driver", "local")
    assert path.read_text(encoding="utf-8") == "{ this is not json"


def test_coerce_types():
    assert writers.coerce("true", "bool") is True
    assert writers.coerce("no", "bool") is False
    assert writers.coerce("42", "int") == 42
    assert writers.coerce('["a"]', "list") == ["a"]


def test_write_refused_without_a_writable_layer():
    setting = type("S", (), {"file": "podman.containers", "vtype": "str",
                             "key": "containers.log_driver"})()
    with pytest.raises(writers.WriteRefused):
        writers.write_setting(setting, None, "journald")
