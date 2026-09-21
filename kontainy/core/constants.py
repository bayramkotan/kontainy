"""
kontainy — uygulama sabitleri

SÜRÜM ŞEMASI: XX.XX.XXX — 0.0.1'den başlar. Yama basamağı 999'a kadar gider,
sonra orta hane döner.

⚠️ Sürüm YALNIZCA burada ve pyproject.toml'da tutulur, başka yerde
tekrarlanmaz. Ve YALNIZCA Bayram açıkça "sürümü güncelle" dediğinde
yükseltilir — sormak da yok, beklenir.
"""

APP_NAME = "kontainy"
APP_VERSION = "0.0.5"
APP_TAGLINE = "Every Docker and Podman setting, in one interface"
APP_REPO = "https://github.com/bayramkotan/kontainy"

# Must match [project.scripts] in pyproject.toml.
CLI_NAMES = ("kontainy", "ky", "kty")

# ---------------------------------------------------------------------------
#  Data the Preferences page offers, kept here rather than in the GUI module.
#
#  A list of language codes needs no widget toolkit, and putting it beside the
#  widgets meant a test could not read it without importing Qt. CI runs the
#  suite with PySide6 stubbed, so that import was the difference between
#  passing locally and failing on the runner.
# ---------------------------------------------------------------------------
LANGUAGES = [
    ("en", "English"), ("tr", "Türkçe"), ("de", "Deutsch"),
    ("fr", "Français"), ("es", "Español"), ("it", "Italiano"),
    ("pt", "Português"), ("ru", "Русский"), ("zh", "中文"),
    ("ja", "日本語"), ("ar", "العربية"),
]

TERMINALS = [
    ("", "Auto-detect"),
    ("konsole", "Konsole"), ("gnome-terminal", "GNOME Terminal"),
    ("alacritty", "Alacritty"), ("kitty", "kitty"),
    ("xfce4-terminal", "Xfce Terminal"), ("foot", "foot"),
    ("wezterm", "WezTerm"), ("xterm", "xterm"),
    ("x-terminal-emulator", "System default (Debian)"),
    ("wt.exe", "Windows Terminal"),
]

START_PAGES = [
    ("overview", "Overview"), ("diagnostics", "Diagnostics"),
    ("containers", "Containers"),
    ("platform-docker", "Docker"),
    ("platform-podman", "Podman"),
    ("platform-kubernetes", "Kubernetes"),
    ("platform-libvirt", "KVM / libvirt"),
    ("install", "Install"),
    ("catalog", "Config Catalog"), ("learn", "Learn"),
]
