#!/usr/bin/env bash
#
# Установка pyqt-omniviewer. Поддержаны семейства:
#   - Debian / Ubuntu (apt)   — эталон: чистая Ubuntu 24.04
#   - Fedora / RHEL   (dnf)
# Запуск:  bash install.sh
#
set -euo pipefail

# QtMultimedia-бэкенд (FFmpeg) не ставится системным пакетом: колесо PyQt6 из pip
# уже несёт libffmpegmediaplugin.so и свои libav*/libsw*. Из системы нужны только
# общие GUI/аудио-библиотеки, от которых зависят Qt-плагины (xcb-платформа, звук).

# --- Системные пакеты -------------------------------------------------------

install_apt() {
    echo "==> Системные пакеты (apt)"
    sudo apt-get update
    sudo apt-get install -y --no-install-recommends \
        python3 python3-venv python3-pip \
        libarchive13 \
        qt6-image-formats-plugins \
        libgl1 libegl1 libpulse0 libasound2t64 \
        libfontconfig1 libfreetype6 \
        libxrandr2 libxkbcommon0 libxkbcommon-x11-0 libxcb-cursor0 \
        doxygen
    # Опциональный запасной движок воспроизведения (python-mpv -> libmpv).
    sudo apt-get install -y --no-install-recommends libmpv2 \
        || echo "   (libmpv2 не поставлен — запасной движок mpv будет недоступен)"
}

install_dnf() {
    echo "==> Системные пакеты (dnf)"
    sudo dnf install -y \
        python3 python3-pip \
        libarchive \
        qt6-qtimageformats \
        mesa-libGL mesa-libEGL pulseaudio-libs alsa-lib \
        fontconfig freetype \
        libXrandr libxkbcommon libxkbcommon-x11 xcb-util-cursor \
        doxygen
    # libmpv на Fedora живёт в RPM Fusion — ставим необязательно.
    sudo dnf install -y mpv-libs \
        || echo "   (mpv-libs не поставлен — запасной движок mpv будет недоступен)"
}

if command -v apt-get >/dev/null 2>&1; then
    install_apt
elif command -v dnf >/dev/null 2>&1; then
    install_dnf
else
    echo "Не найден apt-get или dnf. Поставь вручную аналоги:" >&2
    echo "  python3(+venv,+pip), libarchive, qt6 image-formats plugin," >&2
    echo "  libGL/libEGL, pulseaudio/alsa, fontconfig, freetype," >&2
    echo "  libxkbcommon(+x11), xcb-cursor, (опц.) libmpv, doxygen" >&2
    exit 1
fi

# --- Python-окружение ------------------------------------------------------

echo "==> Виртуальное окружение"
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> Python-зависимости (pip)"
pip install --upgrade pip
pip install -r requirements.txt
pip install -e .

echo
echo "Готово. Запуск:"
echo "  source .venv/bin/activate && omniviewer [путь]"
