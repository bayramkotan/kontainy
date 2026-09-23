"""Output arrives while the command runs, not after it."""

import sys

import pytest

from kontainy.core.elevate import run_streaming


def test_lines_arrive_one_by_one():
    seen = []
    result = run_streaming(
        [sys.executable, "-c",
         "import sys\nfor i in range(3): print('line', i); sys.stdout.flush()"],
        seen.append, record=False)
    assert result.ok
    assert seen == ["line 0", "line 1", "line 2"]


def test_stderr_is_part_of_the_stream():
    """Package managers write progress to stderr as often as to stdout."""
    seen = []
    run_streaming([sys.executable, "-c",
                   "import sys; print('out'); print('err', file=sys.stderr)"],
                  seen.append, record=False)
    assert "out" in seen and "err" in seen


def test_a_failure_keeps_its_exit_code():
    seen = []
    result = run_streaming([sys.executable, "-c",
                            "import sys; print('nope'); sys.exit(3)"],
                           seen.append, record=False)
    assert not result.ok and result.returncode == 3 and "nope" in seen


def test_a_missing_command_is_reported_not_raised():
    result = run_streaming(["kontainy-no-such-binary"], lambda line: None,
                           record=False)
    assert result.returncode == 127 and "not found" in result.output + result.stderr


@pytest.mark.skipif(sys.platform == "win32", reason="signal timing")
def test_a_runaway_command_is_stopped():
    seen = []
    result = run_streaming(
        [sys.executable, "-c",
         "import time, sys\nwhile True: print('tick'); sys.stdout.flush();"
         " time.sleep(0.05)"],
        seen.append, timeout=0.5, record=False)
    assert seen and any("stopped after" in line for line in seen)
