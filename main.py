#!/usr/bin/env python3
"""
kontainy — giriş noktası

Kullanım:
    python main.py            GUI
    python main.py --scan     GUI açmadan terminal hedefini ve motorları yazdır
"""

import sys


def cli_scan() -> int:
    from core import discovery
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

    print("\n=== systemd soket birimleri ===")
    for unit, user in [("podman.socket", True), ("podman.socket", False),
                       ("docker.socket", False), ("docker.service", False)]:
        scope = "--user" if user else "system"
        print(f"  {unit:16} {scope:8} {discovery.systemd_unit_state(unit, user)}")
    return 0


def main() -> int:
    if "--scan" in sys.argv:
        return cli_scan()

    from PySide6.QtWidgets import QApplication
    from ui.dashboard import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("kontainy")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
