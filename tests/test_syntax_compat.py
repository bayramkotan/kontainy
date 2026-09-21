"""kontainy supports Python 3.10, so it may not use syntax newer than that.

On 2026-09-20 an f-string carried a backslash inside its braces —
f"{target.winner or '\\u2014'}" — which is legal only from Python 3.12
(PEP 701). Development happened on 3.12, so nothing looked wrong; on 3.10
and 3.11 the whole Engines module refused to compile, which means
`pip install kontainy` on those versions would have produced an application
that never opened. CI caught it only because the test matrix includes 3.10.

This test makes a 3.12 or newer interpreter catch it too, so it fails
locally before a tag is ever pushed.
"""

import io
import pathlib
import sys
import tokenize

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCES = sorted(p for p in (ROOT / "kontainy").rglob("*.py")) + [
    ROOT / "main.py", ROOT / "build.py"]


def _pep701_offences(path: pathlib.Path) -> list:
    """f-string features that only Python 3.12+ accepts.

    Two are checked, the two that actually get written by accident: a
    backslash anywhere inside the braces, and reusing the enclosing quote
    character inside them.
    """
    source = path.read_text(encoding="utf-8")
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    offences = []
    stack = []                         # quote character of each open f-string
    for tok in tokens:
        name = tokenize.tok_name[tok.type]
        if name == "FSTRING_START":
            quote = tok.string.lstrip("fFrRbB")[:1]
            if stack and quote == stack[-1]:
                offences.append((tok.start[0], "reuses the enclosing quote"))
            stack.append(quote)
        elif name == "FSTRING_END":
            if stack:
                stack.pop()
        elif stack and name == "STRING":
            # A plain string literal inside an f-string's braces.
            if "\\" in tok.string:
                offences.append((tok.start[0], "backslash inside the braces"))
            elif tok.string.lstrip("rRbBuU")[:1] == stack[-1]:
                offences.append((tok.start[0], "reuses the enclosing quote"))
    return offences


@pytest.mark.skipif(sys.version_info < (3, 12),
                    reason="older interpreters refuse to compile these "
                           "constructs outright, which is the check")
@pytest.mark.parametrize("path", SOURCES, ids=lambda p: str(p.relative_to(ROOT)))
def test_no_python312_only_fstrings(path):
    offences = _pep701_offences(path)
    assert not offences, (
        f"{path.relative_to(ROOT)} uses f-string syntax that Python 3.10 "
        f"and 3.11 cannot parse: "
        + ", ".join(f"line {line} ({why})" for line, why in offences))


def test_every_module_compiles():
    """Compile the whole package on whatever interpreter runs this. On the
    3.10 CI job this is the check that matters."""
    for path in SOURCES:
        compile(path.read_text(encoding="utf-8"), str(path), "exec")


def test_declared_minimum_matches_the_ci_matrix():
    """If pyproject says 3.10, CI must actually test 3.10."""
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/build.yml").read_text(encoding="utf-8")
    assert 'requires-python = ">=3.10"' in pyproject
    assert '"3.10"' in workflow
