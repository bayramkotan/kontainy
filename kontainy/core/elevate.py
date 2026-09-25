"""
kontainy — running commands, with and without elevation

The privilege model changed on 2026-09-19. kontainy now performs operations
that need root, but never quietly:

1. The exact command is shown BEFORE anything runs, and can be copied so the
   user can run it themselves instead.
2. Elevation goes through the system dialog — pkexec on Linux, UAC on
   Windows. kontainy never collects, stores or prompts for a password.
3. Every elevated command is written to the command history with its prefix.
4. User-scope work is never elevated. Asking for a password when none is
   needed teaches people to click through the dialog without reading it.
"""

from __future__ import annotations

import os
import shutil
import logging
import subprocess
from dataclasses import dataclass, field

from ..utils.config import history, log


@dataclass
class CommandResult:
    command: str
    returncode: int
    stdout: str = ""
    stderr: str = ""
    elevated: bool = False
    skipped: str = ""          # set when the command was never attempted

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.skipped

    @property
    def output(self) -> str:
        parts = [p for p in (self.stdout.strip(), self.stderr.strip()) if p]
        return "\n".join(parts) or "(no output)"


# ---------------------------------------------------------------------------
#  Elevation backend
# ---------------------------------------------------------------------------
def elevation_tool() -> str:
    """Which system elevation dialog is available, if any.

    pkexec is preferred because it shows a polkit dialog the desktop already
    trusts. sudo is a fallback only when a terminal is attached — from a GUI
    it would block forever waiting for a password nobody can type.
    """
    if os.name == "nt":
        return "uac"
    if shutil.which("pkexec"):
        return "pkexec"
    return ""


def can_elevate() -> bool:
    return bool(elevation_tool())


def elevation_note() -> str:
    tool = elevation_tool()
    if tool == "pkexec":
        return ("Elevation uses pkexec, so your desktop's own authentication "
                "dialog appears. kontainy never sees your password.")
    if tool == "uac":
        return ("Elevation uses the Windows UAC prompt. kontainy never sees "
                "your password.")
    return ("No elevation helper was found (pkexec is missing). The command "
            "is shown so you can run it in a terminal yourself.")


def is_root() -> bool:
    try:
        return os.geteuid() == 0
    except AttributeError:                                   # Windows
        return False


# ---------------------------------------------------------------------------
#  Running
# ---------------------------------------------------------------------------
class _Stopper:
    """A handle on a running command: stop the whole tree, or ask if it lives."""

    def __init__(self, proc):
        self.proc = proc

    def alive(self) -> bool:
        return self.proc.poll() is None

    def stop(self) -> None:
        if not self.alive():
            return
        try:
            if os.name == "nt":
                import signal
                self.proc.send_signal(signal.CTRL_BREAK_EVENT)
                self.proc.terminate()
            else:
                os.killpg(os.getpgid(self.proc.pid), 15)
        except (OSError, ValueError, AttributeError):
            try:
                self.proc.terminate()
            except OSError:
                pass


def run_streaming(command: list, on_line, *, timeout: float = 900.0,
                  note: str = "", record: bool = True,
                  should_stop=None, on_start=None) -> CommandResult:
    """Run a command and hand each line over as it appears.

    An install prints for minutes; capturing it all and showing it at the end
    tells the user nothing while they wait, and looks like a freeze. Output
    is merged — package managers write progress to stderr as often as to
    stdout — and the timeout is generous, because downloading a base image
    on a slow line is not a hang.
    """
    import time as _time
    shown = " ".join(command)
    lines = []
    # Its own process group, so the whole tree can be stopped. Terminating
    # the shell alone is not enough: its children keep the pipe open and the
    # reading loop never ends — a log window would leave a process behind
    # and Qt would abort with "QThread: Destroyed while thread is running".
    extra = {}
    if os.name == "nt":
        extra["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        extra["start_new_session"] = True
    try:
        proc = subprocess.Popen(command, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True,
                                bufsize=1, errors="replace", **extra)
    except FileNotFoundError:
        result = CommandResult(shown, 127, "",
                               f"{command[0]}: command not found")
        if record:
            history().add(shown, note=note, ok=False)
        return result
    except OSError as exc:
        return CommandResult(shown, 1, "", str(exc))

    # The caller gets the process itself: a follow that has gone quiet is
    # blocked reading, so a flag checked between lines would never be seen.
    # Closing the window terminates it directly.
    if on_start is not None:
        on_start(_Stopper(proc))

    deadline = _time.monotonic() + timeout
    try:
        for line in proc.stdout:
            line = line.rstrip("\n")
            lines.append(line)
            on_line(line)
            # A follow never ends on its own; the caller says when to stop,
            # and the process must die with the window that opened it.
            if should_stop is not None and should_stop():
                proc.terminate()
                break
            if _time.monotonic() > deadline:
                proc.kill()
                on_line(f"\u2014 stopped after {timeout:.0f}s")
                break
        proc.wait(timeout=10)
    finally:
        if proc.stdout:
            proc.stdout.close()

    code = proc.returncode or 0
    if should_stop is not None and should_stop():
        code = 0                      # stopped on purpose, not a failure
    result = CommandResult(shown, code, "\n".join(lines), "")
    if record:
        history().add(shown, note=note, ok=result.ok)
    # A command the user asked for is news; a probe is not. `record` already
    # tells them apart: it is what puts a command into the history the user
    # can read back.
    log().log(logging.INFO if record else logging.DEBUG,
              "ran (%s): %s", result.returncode, shown)
    return result


def run(command: list, *, timeout: float = 60.0, note: str = "",
        record: bool = True) -> CommandResult:
    """Run a command as the current user."""
    shown = " ".join(command)
    try:
        proc = subprocess.run(command, capture_output=True, text=True,
                              timeout=timeout)
        result = CommandResult(shown, proc.returncode, proc.stdout,
                               proc.stderr)
    except FileNotFoundError:
        result = CommandResult(shown, 127, "",
                               f"{command[0]}: command not found")
    except subprocess.TimeoutExpired:
        result = CommandResult(shown, 124, "",
                               f"timed out after {timeout:.0f}s")
    except OSError as exc:
        result = CommandResult(shown, 1, "", str(exc))

    if record:
        history().add(shown, note=note, ok=result.ok)
    # A command the user asked for is news; a probe is not. `record` already
    # tells them apart: it is what puts a command into the history the user
    # can read back.
    log().log(logging.INFO if record else logging.DEBUG,
              "ran (%s): %s", result.returncode, shown)
    return result


def run_elevated(command: list, *, timeout: float = 120.0, note: str = "",
                 record: bool = True) -> CommandResult:
    """Run a command with elevation, through the system's own dialog.

    Returns a result with `skipped` set rather than raising when no elevation
    helper exists, so the caller can fall back to showing the command.
    """
    shown = " ".join(command)

    if is_root():
        return run(command, timeout=timeout, note=note, record=record)

    tool = elevation_tool()
    if not tool:
        result = CommandResult(f"sudo {shown}", 1, skipped="no elevation helper")
        if record:
            history().add(f"sudo {shown}", note=f"{note} (not run)", ok=False)
        return result

    if tool == "pkexec":
        # --disable-internal-agent keeps pkexec from trying to prompt on a
        # terminal that is not there; the desktop polkit agent handles it.
        full = ["pkexec", "--disable-internal-agent"] + command
    else:                                                    # Windows
        joined = " ".join(f'"{c}"' if " " in c else c for c in command)
        full = ["powershell", "-NoProfile", "-Command",
                f"Start-Process -Verb RunAs -Wait -FilePath "
                f"'{command[0]}' -ArgumentList '{joined}'"]

    try:
        proc = subprocess.run(full, capture_output=True, text=True,
                              timeout=timeout)
        result = CommandResult(f"sudo {shown}", proc.returncode, proc.stdout,
                               proc.stderr, elevated=True)
        if proc.returncode == 126:
            # polkit's exit code when the user dismisses the dialog.
            result.stderr = "Authentication was cancelled."
    except subprocess.TimeoutExpired:
        result = CommandResult(f"sudo {shown}", 124, "",
                               "timed out waiting for authentication",
                               elevated=True)
    except OSError as exc:
        result = CommandResult(f"sudo {shown}", 1, "", str(exc), elevated=True)

    if record:
        history().add(f"sudo {shown}", note=note, ok=result.ok)
    log().info("ran elevated (%s): %s", result.returncode, shown)  # always
    return result
