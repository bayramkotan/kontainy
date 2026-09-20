#!/usr/bin/env python3
"""
kontainy — development launcher

Running from a checkout: ``python main.py [--scan|--doctor|--stats]``.

An installed copy uses the ``kontainy`` / ``kty`` commands instead, which
point at ``kontainy.__main__:main``. This file exists only so the repository
can be run without installing anything; it is not part of the distribution.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from kontainy.__main__ import main   # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
