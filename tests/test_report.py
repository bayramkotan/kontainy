"""The system report — what someone pastes into a bug report.

It was a tab of the About dialog, where nobody writing a bug report would
look. It belongs on the Diagnostics page, beside what is wrong, and on the
command line for a server with no window.
"""

import pytest

from kontainy.core import report


def test_the_report_names_the_versions_that_matter():
    text = report.build()
    for key in ("kontainy", "python", "platform", "machine"):
        assert key in text


def test_it_lists_every_technology_with_its_state():
    text = report.build()
    from kontainy.core.providers import PROVIDERS
    for provider in PROVIDERS:
        if provider.shown_here():
            assert provider.name in text


def test_an_unreachable_engine_says_so_briefly(monkeypatch):
    """A whole Go traceback in a report helps nobody; one line does."""
    from kontainy.core.providers import base
    from kontainy.core.providers.containers import DockerProvider
    monkeypatch.setattr(DockerProvider, "shown_here", lambda self: True)
    monkeypatch.setattr(DockerProvider, "available", lambda self: True)
    monkeypatch.setattr(DockerProvider, "version", lambda self: "29.8.0")
    monkeypatch.setattr(DockerProvider, "targets", lambda self: [
        base.Target("default", "unix:///var/run/docker.sock", True)])
    monkeypatch.setattr(DockerProvider, "objects", lambda self, t: base.Listing(
        columns=[], rows=[], command="docker ps",
        error="Cannot connect to the Docker daemon at unix:///var/run/"
              "docker.sock.\nIs the docker daemon running?"))
    line = [l for l in report.technologies() if l[0] == "Docker"][0][1]
    assert "unreachable" in line
    assert "\n" not in line and len(line) < 120


def test_the_overriding_environment_variables_are_shown(monkeypatch):
    monkeypatch.setenv("DOCKER_HOST", "ssh://me@box")
    assert ("DOCKER_HOST", "ssh://me@box") in report.environment()


def test_the_short_form_leaves_out_the_tool_list():
    assert "Tools installed" in report.build(full=True)
    assert "Tools installed" not in report.build(full=False)


def test_it_points_at_the_log_and_any_crash_reports():
    from kontainy.utils import logs
    text = report.build()
    assert str(logs.log_path()) in text
    assert "crash reports" in text


def test_the_report_needs_no_qt():
    import subprocess
    import sys
    code = ("import sys; sys.modules['PySide6'] = None\n"
            "from kontainy.core import report\n"
            "print(report.build(full=False))")
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True,
                          text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert "kontainy system report" in proc.stdout


def test_the_cli_prints_it():
    import pathlib
    import subprocess
    import sys
    root = pathlib.Path(__file__).resolve().parents[1]
    proc = subprocess.run([sys.executable, "-m", "kontainy", "report",
                           "--short"], capture_output=True, text=True,
                          cwd=str(root), timeout=120)
    assert proc.returncode == 0
    assert "kontainy system report" in proc.stdout
