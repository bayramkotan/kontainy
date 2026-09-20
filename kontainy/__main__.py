"""
kontainy — entry point

This module is what ``pip install kontainy`` wires its commands to, and it is
also what ``python -m kontainy`` runs.

⚠️ The package is deliberately named ``kontainy`` rather than ``src``. A
distribution that installs a top-level ``src`` package (or a bare ``main``
module) collides with every other project that does the same, and quietly
shadows anything the user imports by that name. The repository keeps the
package directory at the root for exactly this reason.

Three names install to the same entry point: ``kontainy``, the short ``ky``,
and ``kty`` kept from 0.0.1.

Usage:
    ky                  GUI
    ky --scan           the context chain, every engine, systemd unit states
    ky --doctor         run every diagnostic rule and print the findings
    ky --stats          catalogue, rule and Learn counts
    ky --version        print the version and exit
"""

from __future__ import annotations

import sys


def cli_scan() -> int:
    from kontainy.core import discovery

    print("=== Terminal target ===")
    target = discovery.resolve_cli_target()
    for layer, value, won in target.as_rows():
        print(f"  {'>>' if won else '  '} {layer:38} {value}")
    print(f"  EFFECTIVE: {target.winner}   ({target.winner_layer})\n")

    warn = discovery.docker_shim_warning()
    if warn:
        print(f"!! {warn}\n")

    print("=== Engines found ===")
    endpoints = discovery.discover(probe=True)
    if not endpoints:
        print("  (no socket found)")
    for endpoint in endpoints:
        mark = "*" if endpoint.is_cli_default else " "
        state = (endpoint.title if endpoint.reachable
                 else f"UNREACHABLE — {endpoint.error}")
        print(f" {mark} {endpoint.address}")
        print(f"     found via : {endpoint.source}")
        print(f"     state     : {state}")

    print("\n=== systemd units ===")
    for unit, user in [("podman.socket", True), ("podman.socket", False),
                       ("docker.socket", False), ("docker.service", False)]:
        scope = "--user" if user else "system"
        print(f"  {unit:16} {scope:8} "
              f"{discovery.systemd_unit_state(unit, user)}")
    return 0


def cli_doctor() -> int:
    from kontainy.rules import SEVERITY_ICONS, diagnose

    _env, findings = diagnose(probe=True)
    if not findings:
        print("✅ Nothing found.")
        return 0
    for finding in findings:
        print(f"\n{SEVERITY_ICONS.get(finding.severity, '')}  "
              f"[{finding.id}] {finding.rule.title}")
        for line in finding.explain().splitlines():
            print(f"    {line}")
        if finding.fix_command():
            print(f"    → {finding.fix_command()}")
    print(f"\n{len(findings)} findings.")
    return 0


def cli_stats() -> int:
    from kontainy.core.catalog import stats as catalog_stats
    from kontainy.learn.content import learn_stats
    from kontainy.rules import rule_stats

    print("=== Settings catalogue ===")
    for key, value in catalog_stats().items():
        print(f"  {key:22} {value}")
    print("\n=== Diagnostic rules ===")
    for key, value in rule_stats().items():
        print(f"  {key:22} {value}")
    print("\n=== Learn ===")
    for key, value in learn_stats().items():
        print(f"  {key:22} {value}")
    return 0


def main() -> int:
    if "--version" in sys.argv or "-V" in sys.argv:
        from kontainy.core.constants import APP_NAME, APP_VERSION
        print(f"{APP_NAME} {APP_VERSION}")
        return 0
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        return 0
    if "--scan" in sys.argv:
        return cli_scan()
    if "--doctor" in sys.argv:
        return cli_doctor()
    if "--stats" in sys.argv:
        return cli_stats()

    from PySide6.QtWidgets import QApplication

    from kontainy.core.constants import APP_NAME, APP_VERSION
    from kontainy.gui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    window = MainWindow(version=APP_VERSION)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
