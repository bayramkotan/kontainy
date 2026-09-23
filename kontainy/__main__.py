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

import os
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


# The system libraries Qt needs for any window at all, by distribution.
# PySide6 bundles Qt itself but not these; a minimal install or a container
# image often lacks them, and the raw error is a bare "libEGL.so.1: cannot
# open shared object file". Found when the CI runner hit exactly that.
QT_SYSTEM_PACKAGES = {
    "debian": "sudo apt install libegl1 libgl1 libxkbcommon0 libfontconfig1 libdbus-1-3",
    "fedora": "sudo dnf install mesa-libEGL mesa-libGL libxkbcommon fontconfig dbus-libs",
    "arch": "sudo pacman -S --needed libglvnd libxkbcommon fontconfig dbus",
    "suse": "sudo zypper install libEGL1 libGL1 libxkbcommon0 fontconfig libdbus-1-3",
    "alpine": "sudo apk add mesa-egl mesa-gl libxkbcommon fontconfig dbus-libs",
}


def qt_missing_message(exc: Exception) -> str:
    """Turn a failed Qt import into something a person can act on."""
    text = str(exc)
    if "No module named" in text:
        return (f"kontainy could not start its window: {text}\n\n"
                f"PySide6 is not installed in this environment:\n"
                f"    pip install PySide6\n\n"
                f"The command-line modes still work: ky --scan, ky --doctor, "
                f"ky --stats")
    from kontainy.core.registry import OS_FAMILY, OS_KIND, OS_LABEL
    lines = [f"kontainy could not start its window: {text}", "",
             "Qt is installed, but a system library it needs is missing."]
    if OS_KIND == "linux":
        command = QT_SYSTEM_PACKAGES.get(OS_FAMILY)
        if command:
            lines += [f"On {OS_LABEL}, install them with:", f"    {command}"]
        else:
            lines += ["Install your distribution's packages for EGL, OpenGL,",
                      "xkbcommon, fontconfig and D-Bus. For example:"]
            lines += [f"    {c}" for c in QT_SYSTEM_PACKAGES.values()]
    lines += ["", "The command-line modes still work: ky --scan, ky --doctor, "
                  "ky --stats"]
    return "\n".join(lines)


def _cli(command) -> int:
    """Run a command-line mode, quietly stopping if the reader goes away.

    `ky --stats | head -3` closed the pipe after three lines, the next print
    raised BrokenPipeError, and a traceback landed in the terminal — and in
    the CI log, which pipes exactly that. A closed pipe is the reader saying
    it has enough; the Unix convention is to stop without a word.
    """
    import errno
    try:
        code = command()
        sys.stdout.flush()
        return code
    except OSError as exc:
        # POSIX reports a vanished reader as EPIPE (BrokenPipeError).
        # Windows usually reports it as EINVAL, "Invalid argument", when the
        # buffered output is flushed. Anything else is a real error.
        if not (isinstance(exc, BrokenPipeError)
                or exc.errno in (errno.EPIPE, errno.EINVAL)):
            raise
        # Point stdout at nothing so the interpreter's own flush at exit
        # does not raise the same error a second time.
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        return 0


def main() -> int:
    # Before anything else: an unhandled error must land in a crash report
    # rather than vanish with the window or the thread that raised it.
    from kontainy.utils import logs
    logs.install_hooks()
    logs.clean_old_crashes()

    args = sys.argv[1:]
    # The original flags keep working for scripts written against 0.0.x.
    for flag, command in (("--scan", cli_scan), ("--doctor", cli_doctor),
                          ("--stats", cli_stats)):
        if flag in args:
            return _cli(command)
    if args:
        from kontainy import cli
        code = _cli(lambda: cli.main(args))
        if code != -1:                  # -1: "ky gui" asked for the window
            return code
    return gui_main()


def gui_main() -> int:
    """Open the window. Also the entry point of kontainy-gui, which Windows
    starts without a console window."""
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        print(qt_missing_message(exc), file=sys.stderr)
        return 1

    from kontainy.core.constants import APP_NAME, APP_VERSION
    from kontainy.gui.main_window import MainWindow
    from kontainy.utils import logs

    logs.install_qt_handler()          # Qt's warnings into kontainy's log
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    window = MainWindow(version=APP_VERSION)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
