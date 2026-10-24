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
#
#  Диагностика, если что-то не работает:  python3 run.py --doctor
# ============================================================
cd "$(dirname "$0")" || exit 1

# В a-Shell интерпретатор называется python3; на всякий случай — fallback на python.
if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "Python не найден. Установите a-Shell из App Store."
  exit 1
fi
echo "==> Интерпретатор: $($PY --version 2>&1)"

# ВАЖНО: ставим пакеты через "$PY -m pip", а не голым pip —
# иначе pip может относиться к другому окружению, чем python3.
if ! $PY -c "import httpx, bs4, rich" 2>/dev/null; then
  echo "==> Устанавливаю обязательные пакеты (httpx, beautifulsoup4, rich)…"
  $PY -m pip install httpx beautifulsoup4 rich || {
    echo "Ошибка установки пакетов. Запустите диагностику: $PY run.py --doctor"
    exit 1
  }
fi

# Опциональные пакеты: без них скрипт работает (см. README).
# Важно: в a-Shell openpyxl может падать из-за сломанного numpy —
# внутри Energy Scout этот случай обходится заглушкой, проверка ниже общая.
if $PY -c "import openpyxl" 2>/dev/null; then
  echo "==> openpyxl есть — Excel-отчёт будет создан"
else
  echo "==> openpyxl недоступен напрямую — Energy Scout попробует совместимый режим"
  echo "    (если Excel не создастся: $PY -m pip install openpyxl, иначе работают CSV/HTML)"
fi
$PY -c "import lxml" 2>/dev/null \
  && echo "==> lxml есть — быстрый HTML-парсер" \
  || echo "==> lxml нет — используется встроенный html.parser (медленнее, но работает)"
$PY -c "import yaml" 2>/dev/null \
  && echo "==> PyYAML есть — config.yaml поддерживается" \
  || echo "==> PyYAML нет — работают значения по умолчанию и флаги команды"

echo "==> Запуск: $PY run.py --compact $*"
"$PY" run.py --compact "$@"
exit $?
