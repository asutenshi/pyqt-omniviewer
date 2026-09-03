#!/usr/bin/env bash
#
# Установка pyqt-omniviewer на чистую Ubuntu 24.04.
# Запуск:  bash install.sh
#
set -euo pipefail

echo "==> Системные пакеты (apt)"
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip \
    libarchive13 \
    qt6-image-formats-plugins \
    libqt6multimedia6 qt6-multimedia-ffmpeg \
    gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav \
    libmpv2 \
    doxygen

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
