#!/bin/sh
# ============================================================
#  Energy Scout для iPhone/iPad — запуск в приложении a-Shell
#  (бесплатный терминал с Python 3 в App Store).
#
#  Установка проекта на телефон:
#   1. Скачайте ZIP репозитория (GitHub → Code → Download ZIP),
#      распакуйте в «Файлах» в папку a-Shell (On My iPhone → a-Shell).
#   2. В a-Shell перейдите в папку:  cd energy-scout
#   3. Первый запуск:                 sh run_ios.sh --demo
#   4. Боевой прогон:                 sh run_ios.sh
# ============================================================
cd "$(dirname "$0")" || exit 1

# lxml/PyYAML не обязательны: парсер уйдёт на html.parser,
# конфиг — на значения по умолчанию. Ставим только нужное.
python3 -c "import httpx, bs4, rich" 2>/dev/null || \
  pip install httpx beautifulsoup4 rich
python3 -c "import openpyxl" 2>/dev/null || \
  echo "openpyxl не установлен — Excel-отчёт будет пропущен (pip install openpyxl)"

python3 run.py --compact "$@"
