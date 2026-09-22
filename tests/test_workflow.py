"""Checks on the release workflow's own shell scripts.

The Python tests never see these scripts, and they have broken releases:

* v0.0.3: the AppImage smoke test ran `timeout "$APP"` without "./", so the
  file was looked up in PATH and never executed.
* v0.0.6: when the installed-wheel step was inserted in 0.0.5, the lines
  that followed the insertion point in the previous step slid to the end of
  the new one, after `cd /tmp`. They looked for dist/, which is not in /tmp,
  and publish-pypi failed after every other job had passed.

The rule these tests enforce: a step that leaves the checkout does so in a
subshell, and nothing after a bare `cd` refers to dist/.
"""

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "build.yml"


def _steps():
    yaml = pytest.importorskip("yaml")
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for job_name, job in data["jobs"].items():
        for step in job.get("steps", []):
            if "run" in step:
                yield f"{job_name} / {step.get('name', '?')}", step["run"]


def dist_after_bare_cd(script: str) -> list:
    """Lines that refer to dist/ after a `cd` outside any subshell."""
    depth, moved, offenders = 0, False, []
    for number, raw in enumerate(script.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line == "(":
            depth += 1
            continue
        if line == ")":
            depth = max(0, depth - 1)
            continue
        if depth == 0 and re.match(r"cd\s+(?!\$GITHUB_WORKSPACE)", line):
            moved = True
            continue
        if moved and re.search(r"""\bdist\b(?![-_])""", line):
            offenders.append(f"line {number}: {raw.strip()}")
    return offenders


def test_no_step_refers_to_dist_after_leaving_the_checkout():
    problems = []
    for where, script in _steps():
        for offence in dist_after_bare_cd(script):
            problems.append(f"{where}: {offence}")
    assert not problems, "\n".join(problems)


def test_the_check_catches_the_0_0_6_failure():
    """The exact shape that broke publish-pypi in v0.0.6."""
    broken = ("python -m venv /tmp/wheel-check\n"
              "/tmp/wheel-check/bin/pip install -q dist/*.whl\n"
              "cd /tmp\n"
              "/tmp/wheel-check/bin/ky --version\n"
              "python - <<'PY'\n"
              "wheel = next(f for f in os.listdir(\"dist\"))\n"
              "PY\n")
    assert dist_after_bare_cd(broken), "the v0.0.6 failure must be caught"


def test_a_subshell_cd_is_allowed():
    fixed = ("/tmp/wheel-check/bin/pip install -q dist/*.whl\n"
             "(\n"
             "  cd /tmp\n"
             "  /tmp/wheel-check/bin/ky --version\n"
             ")\n"
             "ls dist\n")
    assert dist_after_bare_cd(fixed) == []


def test_top_level_wheel_check_lives_in_verify():
    for where, script in _steps():
        if "top-level entries" in script:
            assert where.endswith("Verify the distribution"), where


def test_appimage_is_run_with_a_path():
    """v0.0.3: `timeout "$APP"` looked the file up in PATH."""
    for where, script in _steps():
        for line in script.splitlines():
            if "timeout" in line and "$APP" in line:
                assert '"./$APP"' in line, f"{where}: {line.strip()}"
