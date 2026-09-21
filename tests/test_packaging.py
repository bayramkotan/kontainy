"""What ships to PyPI must contain the whole package.

0.0.4 did not: pyproject listed its packages by hand, kontainy/core/providers
was added without being listed, and the published wheel could print its
version but not open its window. The package list is discovered now; these
tests make sure discovery can actually find everything.
"""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
PYPROJECT = (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def test_packages_are_discovered_not_listed():
    assert "[tool.setuptools.packages.find]" in PYPROJECT
    assert not re.search(r"^packages\s*=\s*\[", PYPROJECT, re.M), \
        "a hand-written package list is how 0.0.4 lost a directory"


def test_every_package_directory_has_an_init():
    """Discovery only finds directories with __init__.py. A new folder of
    modules without one would be silently left out of the wheel."""
    missing = []
    for path in (ROOT / "kontainy").rglob("*.py"):
        folder = path.parent
        if not (folder / "__init__.py").is_file():
            missing.append(str(folder.relative_to(ROOT)))
    assert not sorted(set(missing)), f"no __init__.py in: {sorted(set(missing))}"


def test_discovery_finds_every_package():
    # Python 3.12+ virtual environments ship without setuptools, and the CI
    # test job installs only pytest. Skip there; the wheel check in the
    # publish job covers the same ground with the real build.
    import pytest
    find_packages = pytest.importorskip("setuptools").find_packages
    found = set(find_packages(str(ROOT), include=["kontainy", "kontainy.*"]))
    expected = {".".join(p.parent.relative_to(ROOT).parts)
                for p in (ROOT / "kontainy").rglob("__init__.py")}
    assert expected <= found, f"not discovered: {sorted(expected - found)}"
    assert "kontainy.core.providers" in found


def test_console_commands_are_declared():
    for name in ("kontainy", "ky", "kty"):
        assert re.search(rf'^{name}\s*=\s*"kontainy\.__main__:main"',
                         PYPROJECT, re.M), f"missing console command: {name}"
