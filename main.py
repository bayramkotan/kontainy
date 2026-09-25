#!/usr/bin/env python3
"""
kontainy — development launcher

Running from a checkout: ``python main.py``. With no PySide6 it offers to
set the checkout up (a .venv beside this file, kontainy installed into it in
editable mode) and then starts the window from there.

    python main.py            ask, then set up and run
    python main.py --setup    set up without asking
    python main.py --no-setup never set up; print the commands instead

An installed copy uses the ``ky`` / ``kontainy`` commands instead, which
point at ``kontainy.__main__:main``. This file exists only so the repository
can be run without installing anything; it is not part of the distribution.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    from kontainy import bootstrap

    args = sys.argv[1:]
    wants_window = not any(a.startswith("-") and a not in
                           ("--setup", "--no-setup") for a in args)

    if wants_window and not bootstrap.qt_present():
        if "--no-setup" in args:
            print("kontainy needs PySide6:\n"
                  + bootstrap.describe(bootstrap.plan(ROOT)))
            return 1
        code = bootstrap.offer(ROOT, assume_yes="--setup" in args)
        if code != 0:
            return code
        if not bootstrap.in_virtualenv():
            # The current interpreter still has no PySide6; the one in the
            # environment does.
            return bootstrap.relaunch(ROOT)

    sys.argv = [sys.argv[0]] + [a for a in args
                                if a not in ("--setup", "--no-setup")]
    from kontainy.__main__ import main as entry
    return entry()


if __name__ == "__main__":
    sys.exit(main())
