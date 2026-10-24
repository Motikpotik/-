"""Разбор цен, объёмов и нормализация названий."""
from __future__ import annotations

import re
from typing import Optional

# "1 499 тг", "1,499 ₸", "286 тенге", "699тг."
PRICE_RE = re.compile(r"(\d[\d  \s]{0,12}\d|\d)\s*(?:тг|тенге|₸|KZT|т\.?г\.?)", re.IGNORECASE)
# Любое число рядом с валютой/«тг»
ANY_NUMBER_RE = re.compile(r"\d[\d\s  .,]*\d|\d")
VOLUME_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(мл|ml|л\.?|l)(?![а-яa-z])",
    re.IGNORECASE,
)
# «0,33 ж/б», «0.45» — объём в литрах без явной единицы (частая маркировка в КЗ).
BARE_VOLUME_RE = re.compile(r"(?<![\d.])(\d+[.,]\d+)\s*(?:ж/б|жб|пэт|бут|бан|$|[\s(])", re.IGNORECASE)
MULTIPACK_RE = re.compile(r"[xх*×]\s*(\d+)\s*(?:шт|бан|bank|pcs)?", re.IGNORECASE)


def parse_price(text: str | None) -> Optional[int]:
    """Достаёт первую цену в тенге из строки. None, если цены нет."""
    if not text:
        return None
    match = PRICE_RE.search(text)
    if not match:
        return None
    raw = match.group(1)
    digits = re.sub(r"[^\d]", "", raw)
    if not digits:
        return None
    value = int(digits)
    return value if 10 <= value <= 1_000_000 else None


def parse_all_prices(text: str | None) -> list[int]:
    """Все цены из текста по порядку (текущая, старая)."""
    if not text:
        return []
    prices = []
    for match in PRICE_RE.finditer(text):
        digits = re.sub(r"[^\d]", "", match.group(1))
        if digits:
            value = int(digits)
            if 10 <= value <= 1_000_000:
                prices.append(value)
    return prices


def parse_volume_l(name: str) -> Optional[float]:
    """Объём одной банки/бутылки в литрах. 0.33, 0.45, 0.5, 1 и т.п."""
    if not name:
        return None
    match = VOLUME_RE.search(name)
    if match:
        value = float(match.group(1).replace(",", "."))
        unit = match.group(2).lower()
        if unit in ("мл", "ml"):
            value /= 1000.0
    else:
        bare = BARE_VOLUME_RE.search(name)
        if not bare:
            return None
        value = float(bare.group(1).replace(",", "."))
        # без единицы измерения осмысленны только литры в диапазоне 0.05–2 л
        if not 0.05 <= value <= 2.0:
            return None
    if value <= 0 or value > 10:
        return None
    return round(value, 3)


def pack_size(name: str) -> int:
    """Сколько банок в упаковке, если название вида «... x4 ...»."""
    match = MULTIPACK_RE.search(name or "")
    if not match:
        return 1
    n = int(match.group(1))
    return n if 2 <= n <= 48 else 1


def price_per_liter(price: int | None, volume_l: float | None) -> Optional[int]:
    if not price or not volume_l:
        return None
    return round(price / volume_l)


def normalize_name(name: str) -> str:
    """Ключ для дедупликации: нижний регистр, без пунктуации и лишних пробелов."""
    text = (name or "").lower()
    text = re.sub(r"[«»\"'`()\[\]{}.,!?;:_/\\|–—\-]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text
