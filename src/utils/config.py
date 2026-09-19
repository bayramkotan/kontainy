"""
kontainy — Ayar deposu, günlük ve komut geçmişi
================================================

Üçü de VenvStudio'daki karşılıklarının aynısı:

* **config**  — kontainy'nin KENDİ ayarları (tema, dil, hangi sayfa açılsın).
  Yönetilen konteyner ayarlarıyla karıştırılmamalı; onlar katalogda.
* **log**     — yutulan hata kalmasın diye. Sessiz `except` = kaybedilmiş tur.
* **history** — yapılan her işlemin CLI karşılığı. EĞİTSEL DİREĞİN KENDİSİ:
  kullanıcı kontainy olmadan da aynı işi yapabilmeli.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path

APP_DIR_NAME = "kontainy"


# ---------------------------------------------------------------------------
#  Yollar — XDG'ye uyar, Windows'ta APPDATA kullanır
# ---------------------------------------------------------------------------
def config_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    path = base / APP_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def data_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    path = base / APP_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


CONFIG_FILE = "config.json"
HISTORY_FILE = "command_history.jsonl"
LOG_FILE = "kontainy.log"


# ---------------------------------------------------------------------------
#  Ayarlar
# ---------------------------------------------------------------------------
DEFAULTS = {
    # Tema adları src/gui/styles.py::THEME_OPTIONS ile aynıdır (13 tema).
    "theme": "dark",
    "language": "tr",
    "start_page": "engines",

    # Üç kademeli yazı tipi sistemi — VenvStudio ile aynı sözleşme, px.
    "font_family": "",
    "font_size": 13,              # secondary — taban
    "font_primary_family": "",
    "font_primary_size": 22,      # başlıklar
    "font_tertiary_family": "",
    "font_tertiary_size": 11,     # küçük metin
    # Eğitici gövde paletin fs_learn değerini kullanır (font_size + 5, en az
    # 18px) ve küçültülmez — bkz. KONTAINY_TODO → BÖLÜM 1.

    # Pencere konumu ve boyutu kapanışta saklanır.
    "window_width": 1280,
    "window_height": 820,
    "window_x": None,
    "window_y": None,

    "probe_timeout": 4.0,
    "auto_refresh_seconds": 0,    # 0 = kapalı; olay akışı gelince gereksiz olacak
    "show_command_strip": True,
    "confirm_destructive": True,
}


class Config:
    """JSON tabanlı, atomik yazan basit ayar deposu."""

    def __init__(self, path: Path = None):
        self.path = path or (config_dir() / CONFIG_FILE)
        self._data = dict(DEFAULTS)
        self.load()

    def load(self) -> None:
        if not self.path.is_file():
            return
        try:
            stored = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(stored, dict):
                self._data.update(stored)
        except (OSError, json.JSONDecodeError) as exc:
            log().warning("Ayar dosyası okunamadı (%s): %s", self.path, exc)

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(self._data, indent=2, ensure_ascii=False),
                           encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError as exc:
            log().error("Ayar dosyası yazılamadı (%s): %s", self.path, exc)

    def get(self, key: str, default=None):
        return self._data.get(key, DEFAULTS.get(key, default))

    def set(self, key: str, value) -> None:
        self._data[key] = value
        self.save()

    def as_dict(self) -> dict:
        return dict(self._data)


_config: Config | None = None


def config() -> Config:
    global _config
    if _config is None:
        _config = Config()
    return _config


# ---------------------------------------------------------------------------
#  Günlük
# ---------------------------------------------------------------------------
_logger: logging.Logger | None = None


def log() -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger

    logger = logging.getLogger("kontainy")
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        fmt = logging.Formatter(
            "%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S")
        try:
            fh = logging.FileHandler(data_dir() / LOG_FILE, encoding="utf-8")
            fh.setLevel(logging.DEBUG)
            fh.setFormatter(fmt)
            logger.addHandler(fh)
        except OSError:
            pass
        sh = logging.StreamHandler()
        sh.setLevel(logging.WARNING)
        sh.setFormatter(fmt)
        logger.addHandler(sh)
    _logger = logger
    return logger


def log_path() -> Path:
    return data_dir() / LOG_FILE


# ---------------------------------------------------------------------------
#  Komut geçmişi — eğitsel direk
# ---------------------------------------------------------------------------
class CommandHistory:
    """Yapılan her işlemin CLI karşılığını kalıcı olarak saklar.

    kontainy arayüzden bir şey yaptığında, kullanıcının terminalde
    yazabileceği KARŞILIĞI buraya düşer. Uydurma bayrak yazılmaz —
    gösterilen komut gerçekten çalışan komuttur.
    """

    def __init__(self, path: Path = None, limit: int = 2000):
        self.path = path or (data_dir() / HISTORY_FILE)
        self.limit = limit
        self._entries: list = []
        self.load()

    def load(self) -> None:
        if not self.path.is_file():
            return
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return
        for line in lines[-self.limit:]:
            try:
                self._entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    def add(self, command: str, *, engine: str = "", note: str = "",
            ok: bool = True) -> dict:
        entry = {
            "at": datetime.now().isoformat(timespec="seconds"),
            "command": command,
            "engine": engine,
            "note": note,
            "ok": ok,
        }
        self._entries.append(entry)
        try:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as exc:
            log().warning("Komut geçmişi yazılamadı: %s", exc)
        return entry

    def entries(self, limit: int = None) -> list:
        return self._entries[-limit:] if limit else list(self._entries)

    def clear(self) -> None:
        self._entries.clear()
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            pass


_history: CommandHistory | None = None


def history() -> CommandHistory:
    global _history
    if _history is None:
        _history = CommandHistory()
    return _history
