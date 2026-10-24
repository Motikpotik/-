#!/usr/bin/env bash
# Запуск Energy Scout на Linux/macOS.
# Первый запуск: создаёт виртуальное окружение и ставит зависимости.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
  ./.venv/bin/pip install --upgrade pip
  ./.venv/bin/pip install -r requirements.txt
fi

exec ./.venv/bin/python run.py "$@"
