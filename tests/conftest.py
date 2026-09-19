"""
Test configuration for kontainy.

PySide6 is deliberately NOT required: it is stubbed here so the suite runs in
seconds on a bare runner. The tests cover DECISIONS — catalogue integrity,
command construction, config writing, discovery logic — which is where every
bug found so far actually lived. Widgets are not tested.
"""

import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _stub_pyside6():
    if "PySide6" in sys.modules:
        return
    try:
        import PySide6                                        # noqa: F401
        return
    except ModuleNotFoundError:
        pass

    class _Any:
        def __init__(self, *a, **k):
            pass

        def __getattr__(self, name):
            return _Any()

        def __call__(self, *a, **k):
            return _Any()

    package = types.ModuleType("PySide6")
    for name in ("QtCore", "QtGui", "QtWidgets"):
        module = types.ModuleType(f"PySide6.{name}")
        module.__getattr__ = lambda _n: _Any()
        sys.modules[f"PySide6.{name}"] = module
        setattr(package, name, module)
    sys.modules["PySide6"] = package


_stub_pyside6()
