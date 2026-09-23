"""
kontainy — logging, crash reports and the banners the command line prints

Modelled on VenvStudio's logger, at kontainy's size. What it gives that a
plain log file does not:

* **Rotating files**, so a long-running session cannot fill a disk, and a
  bug from three sessions ago is still there to read.
* **Crash reports**: an unhandled exception — in the GUI thread, a worker
  thread, or asyncio — is written to its own file with the session's
  context, instead of vanishing with the window.
* **Qt's own warnings** go to the same log. Without this they print to a
  console nobody sees, and a QPainter warning is exactly the kind of clue
  that is missing when a page draws wrong.
* **Banners**, so `ky` prints something a person can read at a glance and
  the log carries the same line without the colours.

Qt-free: the Qt message handler is installed separately, by the window.
"""

from __future__ import annotations

import datetime
import logging
import os
import platform
import sys
import threading
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FILE = "kontainy.log"
CRASH_PREFIX = "crash_"
KEEP_CRASHES_FOR_DAYS = 30
#: 2 MB per file, five older files: about six weeks of ordinary use.
ROTATION = (2 * 1024 * 1024, 5)

_logger: logging.Logger | None = None
_console_handler: list = []
_session = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def log_dir() -> Path:
    from .config import data_dir
    path = data_dir() / "logs"
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        return data_dir()
    return path


def log_path() -> Path:
    return log_dir() / LOG_FILE


def session_context() -> dict:
    """What a crash report needs to be worth reading."""
    from .config import APP_DIR_NAME
    try:
        from ..core.constants import APP_VERSION
    except Exception:                                        # noqa: BLE001
        APP_VERSION = "?"
    context = {
        "kontainy": APP_VERSION,
        "session": _session,
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cwd": os.getcwd(),
        "frozen": bool(getattr(sys, "frozen", False)),
        "log dir": str(log_dir()),
        "data dir": APP_DIR_NAME,
    }
    try:
        import PySide6
        from PySide6.QtCore import __version__ as qt_version
        context["PySide6"] = getattr(PySide6, "__version__", "?")
        context["Qt"] = qt_version
    except Exception:                                        # noqa: BLE001
        context["PySide6"] = "not installed"
    return context


def console_level() -> int:
    """How much kontainy says on screen."""
    name = (os.environ.get("KY_LOG_LEVEL") or "").upper()
    if name in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        return getattr(logging, name)
    interactive = bool(getattr(sys.stderr, "isatty", lambda: False)())
    return logging.INFO if interactive else logging.WARNING


def set_console_level(level: int) -> None:
    for handler in _console_handler:
        handler.setLevel(level)


def timer(what: str, level: int = logging.INFO):
    """Log how long something took — VenvStudio times its page builds too.

        with logs.timer("Overview"):
            ...
    """
    import contextlib
    import time as _time

    @contextlib.contextmanager
    def _run():
        started = _time.perf_counter()
        try:
            yield
        finally:
            setup().log(level, "%s: %.0f ms", what,
                        (_time.perf_counter() - started) * 1000)
    return _run()


def setup() -> logging.Logger:
    """The one logger, with rotation, a file and a console handler."""
    global _logger
    if _logger is not None:
        return _logger

    logger = logging.getLogger("kontainy")
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        formatter = logging.Formatter(
            "%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S")
        size, backups = ROTATION
        try:
            handler = RotatingFileHandler(
                log_path(), maxBytes=size, backupCount=backups,
                encoding="utf-8")
            handler.setLevel(logging.DEBUG)
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        except OSError:
            pass
        console = logging.StreamHandler()
        # Started from a terminal, kontainy narrates what it is doing: which
        # page is building, which engine answered, how long it took. Piped
        # or redirected, only warnings, so a script's output stays clean.
        # KY_LOG_LEVEL overrides both.
        console.setLevel(console_level())
        console.setFormatter(ConsoleFormatter())
        logger.addHandler(console)
        _console_handler.append(console)
    _logger = logger
    return logger


# --- crash reports ----------------------------------------------------------
def write_crash(kind: str, text: str) -> Path | None:
    """One file per crash, named for the moment it happened."""
    path = log_dir() / f"{CRASH_PREFIX}{_session}_{kind}.log"
    lines = [f"kontainy crash report — {kind}",
             datetime.datetime.now().isoformat(timespec="seconds"), ""]
    lines += [f"{key:12} {value}" for key, value in session_context().items()]
    lines += ["", text]
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n\n")
    except OSError:
        return None
    return path


def _report(kind: str, exc_type, exc, tb) -> None:
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    path = write_crash(kind, text)
    setup().critical("%s: %s\n%s", kind, exc, text)
    print(f"\nkontainy hit an unhandled error ({kind}). "
          f"A report was written to:\n  {path or log_path()}\n",
          file=sys.stderr)


def install_hooks() -> None:
    """Catch what would otherwise disappear without a word."""
    previous = sys.excepthook

    def hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            previous(exc_type, exc, tb)
            return
        _report("main", exc_type, exc, tb)
    sys.excepthook = hook

    def thread_hook(args):
        _report(f"thread-{args.thread.name if args.thread else '?'}",
                args.exc_type, args.exc_value, args.exc_traceback)
    threading.excepthook = thread_hook


def install_qt_handler() -> bool:
    """Send Qt's own warnings to the log instead of a console nobody reads."""
    try:
        from PySide6.QtCore import QtMsgType, qInstallMessageHandler
    except ImportError:
        return False

    levels = {QtMsgType.QtDebugMsg: logging.DEBUG,
              QtMsgType.QtInfoMsg: logging.INFO,
              QtMsgType.QtWarningMsg: logging.WARNING,
              QtMsgType.QtCriticalMsg: logging.ERROR,
              QtMsgType.QtFatalMsg: logging.CRITICAL}

    def handler(mode, context, message):
        text = message.strip()
        if not text or "propagateSizeHints" in text:
            return                      # the offscreen plugin's own noise
        where = ""
        if context is not None and context.file:
            where = f" ({Path(context.file).name}:{context.line})"
        setup().log(levels.get(mode, logging.INFO), "Qt: %s%s", text, where)

    qInstallMessageHandler(handler)
    return True


def clean_old_crashes(days: int = KEEP_CRASHES_FOR_DAYS) -> int:
    """Crash reports are worth keeping, but not forever."""
    cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
    removed = 0
    for path in log_dir().glob(f"{CRASH_PREFIX}*.log"):
        try:
            if datetime.datetime.fromtimestamp(path.stat().st_mtime) < cutoff:
                path.unlink()
                removed += 1
        except OSError:
            continue
    return removed


def crash_reports() -> list:
    """Newest first, for Help and for a bug report."""
    try:
        files = sorted(log_dir().glob(f"{CRASH_PREFIX}*.log"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return []
    return files


# --- colour ------------------------------------------------------------------
ANSI = {
    "reset": "\033[0m", "bold": "\033[1m", "dim": "\033[2m",
    "gray": "\033[90m", "red": "\033[31m", "green": "\033[32m",
    "yellow": "\033[33m", "blue": "\033[34m", "magenta": "\033[35m",
    "cyan": "\033[36m",
    "br_red": "\033[91m", "br_green": "\033[92m", "br_yellow": "\033[93m",
    "br_blue": "\033[94m", "br_magenta": "\033[95m", "br_cyan": "\033[96m",
}

#: Dotted module names are Python's convention, not something to read in a
#: log. Short labels instead; anything unmapped loses the kontainy. prefix.
FRIENDLY_NAMES = {
    "kontainy": "kontainy",
    "kontainy.cli": "CLI",
    "kontainy.gui": "Window",
    "kontainy.qt": "Qt",
    "kontainy.providers": "Providers",
    "kontainy.install": "Install",
    "kontainy.worker": "Worker",
}


def colours_available() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    stream = sys.stdout
    if not getattr(stream, "isatty", lambda: False)():
        return False
    if sys.platform == "win32":
        # Windows Terminal and PowerShell 7 understand ANSI; the old console
        # host does not, and prints the escape codes as text.
        return bool(os.environ.get("WT_SESSION")
                    or os.environ.get("TERM_PROGRAM")
                    or int(os.environ.get("PSModulePath", "").count("7") > 0))
    return True


def _paint(text: str, *names: str) -> str:
    if not colours_available():
        return text
    return "".join(ANSI.get(name, "") for name in names) + text + ANSI["reset"]


def friendly(name: str) -> str:
    if name in FRIENDLY_NAMES:
        return FRIENDLY_NAMES[name]
    return name[len("kontainy."):] if name.startswith("kontainy.") else name


class ConsoleFormatter(logging.Formatter):
    """date │ icon LEVEL │ source │ message — the shape VenvStudio uses."""

    COLOURS = {logging.DEBUG: "gray", logging.INFO: "br_cyan",
               logging.WARNING: "yellow", logging.ERROR: "br_red",
               logging.CRITICAL: "br_red"}
    ICONS = {logging.DEBUG: "\u00b7", logging.INFO: "\u2139",
             logging.WARNING: "\u26a0", logging.ERROR: "\u2717",
             logging.CRITICAL: "\u2620"}

    def format(self, record):
        stamp = datetime.datetime.fromtimestamp(record.created).strftime(
            "%d.%m.%Y %H:%M:%S")
        colour = self.COLOURS.get(record.levelno, "gray")
        icon = self.ICONS.get(record.levelno, "\u00b7")
        bar = _paint("\u2502", "dim")
        line = (f"{_paint(stamp, 'gray')} {bar} "
                f"{_paint(f'{icon} {record.levelname:<7}', colour)} {bar} "
                f"{_paint(f'{friendly(record.name):<12}', 'bold')} {bar} "
                f"{record.getMessage()}")
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


# --- banners ------------------------------------------------------------------
STYLES = {
    "welcome": ("\U0001f433", "br_cyan"),
    "start": ("\U0001f680", "br_cyan"),
    "success": ("\u2705", "br_green"),
    "warning": ("\u26a0\ufe0f ", "br_yellow"),
    "error": ("\u274c", "br_red"),
    "info": ("\u2139\ufe0f ", "br_cyan"),
    "command": ("\U0001f4bb", "br_magenta"),
}


def visual_width(text: str) -> int:
    """How many columns a string occupies: emoji take two, accents none."""
    import unicodedata
    width = 0
    for char in text:
        if unicodedata.combining(char):
            continue
        if unicodedata.east_asian_width(char) in ("W", "F") or \
                0x1F300 <= ord(char) <= 0x1FAFF or ord(char) in (0x2705, 0x274C):
            width += 2
        elif ord(char) == 0xFE0F:
            continue
        else:
            width += 1
    return width


def _safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", "replace").decode("ascii"))


def banner(title: str, style: str = "info", details: list | None = None,
           record: bool = True, accent: str = "") -> list:
    """A boxed, coloured banner — and the same content, plain, in the log.

    `accent` is one extra line inside the box, drawn like the title rather
    than dim: used for the `ky` equivalent of whatever just ran.
    """
    icon, colour = STYLES.get(style, STYLES["info"])
    stamp = datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    body = [f"{icon}  {title}"]
    prefix = "   " if style == "command" else "   \u2022 "
    for detail in [f"Date: {stamp}"] + list(details or []):
        body.append(f"{prefix}{detail}")
    if accent:
        body.append(f"   {accent}")

    width = min(max(max(visual_width(line) for line in body) + 4, 44), 78)
    inner = width - 2
    _safe_print(_paint("\u256d" + "\u2500" * inner + "\u256e", colour, "bold"))
    for index, line in enumerate(body):
        pad = " " * max(0, inner - visual_width(line) - 2)
        strong = index == 0 or (accent and index == len(body) - 1)
        edge = _paint("\u2502", colour, "bold") if strong else \
            _paint("\u2502", colour)
        text = _paint(line, colour, "bold") if strong else _paint(line, "dim")
        _safe_print(f"{edge} {text}{pad} {edge}")
    _safe_print(_paint("\u2570" + "\u2500" * inner + "\u256f", colour, "bold"))

    if record:
        setup().info("%s%s", title,
                     "" if not details else " | " + " | ".join(details))
    return body


def banner_start(title, details=None):
    return banner(title, "start", details)


def banner_success(title, details=None):
    return banner(title, "success", details)


def banner_error(title, details=None):
    return banner(title, "error", details)


def banner_warning(title, details=None):
    return banner(title, "warning", details)


def banner_command(command, context: str = "", ky_equivalent: str = "") -> list:
    """The command behind an action, in a box of its own.

    kontainy teaches as much as it automates: whatever is clicked or typed,
    the user should see what they would have typed themselves. The command
    stays on one unbroken line so it can be copied and run.
    """
    if isinstance(command, (list, tuple)):
        command = " ".join(str(part) for part in command)
    command = str(command).strip()
    if not command:
        return []
    from .config import history
    history().add(command, note=context, ok=True)
    title = f"COMMAND \u2014 {context}" if context else "COMMAND"
    return banner(title, "command", [command], record=False,
                  accent=ky_equivalent)
