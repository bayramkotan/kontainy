"""
kontainy — uygulama sabitleri

SÜRÜM ŞEMASI: XX.XX.XXX — 0.0.1'den başlar. Yama basamağı 999'a kadar gider,
sonra orta hane döner.

⚠️ Sürüm YALNIZCA burada ve pyproject.toml'da tutulur, başka yerde
tekrarlanmaz. Ve YALNIZCA Bayram açıkça "sürümü güncelle" dediğinde
yükseltilir — sormak da yok, beklenir.
"""

APP_NAME = "kontainy"
APP_VERSION = "0.0.3"
APP_TAGLINE = "Every Docker and Podman setting, in one interface"
APP_REPO = "https://github.com/bayramkotan/kontainy"

# Must match [project.scripts] in pyproject.toml.
CLI_NAMES = ("kontainy", "ky", "kty")
