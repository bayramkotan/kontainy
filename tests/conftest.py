"""
Test configuration for kontainy.

PySide6 is deliberately NOT installed in CI: the suite runs in under a second
without it, and it covers DECISIONS — catalogue integrity, command
construction, config writing, the context chain, the tool registry — which is
where every bug found so far actually lived. Widgets are not tested.

The stub below must support SUBCLASSING, not just attribute access.

The first version returned instances, so `from PySide6.QtWidgets import
QWidget` gave back an object rather than a class, and the first test that
imported a GUI module died on `class Page(QWidget)` with
`TypeError: __mro_entries__ must return a tuple`. It passed locally, where
PySide6 is installed, and failed on the runner — the same shape of mistake
as the /run/podman permission crash: CI is a different machine, not a second
run.

Prefer keeping Qt-free data out of GUI modules entirely (see
kontainy/core/constants.py) so tests need not import widgets at all. This
stub is the safety net, not the plan.
"""

import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class _StubBase:
    """Stands in for any Qt class: subclassable, callable, tolerant."""

    def __init__(self, *args, **kwargs):
        pass

    def __getattr__(self, name):
        return _StubBase()

    def __call__(self, *args, **kwargs):
        return _StubBase()

    def __or__(self, other):
        return self

    def __ror__(self, other):
        return self


class _StubModule(types.ModuleType):
    """A module that invents a new Qt class for any name asked of it."""

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        # A fresh subclass per name, so `class Page(QWidget)` works.
        stub = type(name, (_StubBase,), {})
        setattr(self, name, stub)
        return stub


def _stub_pyside6():
    if "PySide6" in sys.modules:
        return
    try:
        import PySide6                                        # noqa: F401
        return
    except ModuleNotFoundError:
        pass

    package = _StubModule("PySide6")
    package.__version__ = "0.0.0-stub"
    package.__path__ = []
    for name in ("QtCore", "QtGui", "QtWidgets", "QtSvg", "QtSvgWidgets"):
        module = _StubModule(f"PySide6.{name}")
        sys.modules[f"PySide6.{name}"] = module
        setattr(package, name, module)
    sys.modules["PySide6"] = package


_stub_pyside6()
