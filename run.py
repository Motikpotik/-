#!/usr/bin/env python3
"""Точка входа Energy Scout.

Примеры:
    python run.py                          # полный прогон по Актобе
    python run.py --query monster          # добавить Monster в приоритет
    python run.py --rare-only --max-price 2000
    python run.py --source dina --all-shops
    python run.py --demo                   # без интернета, на фикстурах
"""
from energy_scout.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
