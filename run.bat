@echo off
REM Запуск Energy Scout на Windows.
REM Первый запуск: создаёт виртуальное окружение и ставит зависимости.
cd /d "%~dp0"

if not exist ".venv" (
  python -m venv .venv
  call .venv\Scripts\activate.bat
  python -m pip install --upgrade pip
  pip install -r requirements.txt
) else (
  call .venv\Scripts\activate.bat
)

python run.py %*
