#!/usr/bin/env python3
"""
kontainy — giriş noktası

Kullanım:
    python main.py            GUI
    python main.py --scan     terminal hedefi + motorlar + systemd durumu
    python main.py --doctor   teşhis kurallarını çalıştır, bulguları yazdır
    python main.py --stats    katalog, kural ve Learn istatistikleri
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def cli_scan() -> int:
    from src.core import discovery

    print("=== Terminal hedefi ===")
    target = discovery.resolve_cli_target()
    for layer, value, won in target.as_rows():
        print(f"  {'>>' if won else '  '} {layer:38} {value}")
    print(f"  ETKİN: {target.winner}   ({target.winner_layer})\n")

    warn = discovery.docker_shim_warning()
    if warn:
        print(f"!! {warn}\n")

    print("=== Bulunan motorlar ===")
    endpoints = discovery.discover(probe=True)
    if not endpoints:
        print("  (hiçbir soket bulunamadı)")
    for ep in endpoints:
        mark = "*" if ep.is_cli_default else " "
        state = ep.title if ep.reachable else f"ERİŞİLEMİYOR — {ep.error}"
        print(f" {mark} {ep.address}")
        print(f"     kaynak : {ep.source}")
        print(f"     durum  : {state}")

    print("\n=== systemd birimleri ===")
    for unit, user in [("podman.socket", True), ("podman.socket", False),
                       ("docker.socket", False), ("docker.service", False)]:
        scope = "--user" if user else "system"
        print(f"  {unit:16} {scope:8} {discovery.systemd_unit_state(unit, user)}")
    return 0


def cli_doctor() -> int:
    from src.rules import SEVERITY_ICONS, diagnose

    _env, findings = diagnose(probe=True)
    if not findings:
        print("✅ Bulgu yok.")
        return 0
    for f in findings:
        print(f"\n{SEVERITY_ICONS.get(f.severity, '')}  [{f.id}] {f.rule.title}")
        for line in f.explain().splitlines():
            print(f"    {line}")
        if f.fix_command():
            print(f"    → {f.fix_command()}")
    print(f"\n{len(findings)} bulgu.")
    return 0


def cli_stats() -> int:
    from src.core.catalog import stats as catalog_stats
    from src.learn.content import learn_stats
    from src.rules import rule_stats

    print("=== Ayar kataloğu ===")
    for k, v in catalog_stats().items():
        print(f"  {k:22} {v}")
    print("\n=== Teşhis kuralları ===")
    for k, v in rule_stats().items():
        print(f"  {k:22} {v}")
    print("\n=== Learn ===")
    for k, v in learn_stats().items():
        print(f"  {k:22} {v}")
    return 0


def main() -> int:
    if "--scan" in sys.argv:
        return cli_scan()
    if "--doctor" in sys.argv:
        return cli_doctor()
    if "--stats" in sys.argv:
        return cli_stats()

    from PySide6.QtWidgets import QApplication

    from src.core.constants import APP_NAME, APP_VERSION
    from src.gui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    window = MainWindow(version=APP_VERSION)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
