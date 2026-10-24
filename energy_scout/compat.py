"""
Совместимость с мобильными окружениями (a-Shell на iOS).

Проблема: a-Shell поставляет собственный numpy в бандле приложения, и на
Python 3.13 он может падать с TypeError при импорте. openpyxl делает
``try: import numpy except ImportError`` — но TypeError не ловится, и весь
импорт openpyxl рушится.

Решение: если обычный импорт openpyxl упал не из-за ImportError, ставим
meta path finder, который на любой импорт numpy бросает ImportError.
Тогда срабатывает штатная ветка openpyxl «numpy нет» (NUMPY=False) —
его чистый Python-код полностью покрывает запись xlsx, самому Energy
Scout numpy не нужен.
"""
from __future__ import annotations

import sys


class _NumpyBlocker:
    """Импортный finder: делает numpy «не установленным»."""

    def find_spec(self, fullname, path, target=None):
        if fullname == "numpy" or fullname.startswith("numpy."):
            raise ImportError(
                f"numpy отключён Energy Scout: битый билд в этом окружении ({fullname})"
            )
        return None  # остальные импорты работают как обычно


def _purge(prefix: str) -> None:
    for mod_name in list(sys.modules):
        if mod_name == prefix or mod_name.startswith(prefix + "."):
            sys.modules.pop(mod_name, None)


def block_numpy() -> None:
    """Чистит остатки numpy и запрещает его повторный импорт."""
    _purge("numpy")
    if not any(isinstance(finder, _NumpyBlocker) for finder in sys.meta_path):
        sys.meta_path.insert(0, _NumpyBlocker())


def import_openpyxl():
    """
    Импорт openpyxl с автоматическим обходом битого numpy.
    Бросает ImportError с понятным сообщением, если openpyxl действительно
    не установлен или не чинится.
    """
    try:
        import openpyxl
        return openpyxl
    except ImportError as exc:
        raise ImportError(
            "openpyxl не установлен — Excel-отчёт пропущен "
            "(python3 -m pip install openpyxl). CSV и HTML работают как обычно."
        ) from exc
    except Exception:
        # случай a-Shell: импорт openpyxl уронил сломанный numpy
        _purge("openpyxl")
        block_numpy()
        try:
            import openpyxl
            return openpyxl
        except Exception as exc2:
            raise ImportError(
                "openpyxl недоступен в этом окружении "
                f"({type(exc2).__name__}: {exc2}). Excel пропущен, используйте CSV/HTML. "
                "Диагностика: python3 run.py --doctor"
            ) from exc2
