"""Модель данных товара."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Product:
    """Один найденный энергетический напиток."""

    source: str                 # dina | magnum | anvar_promo | web
    source_id: str              # стабильный id внутри источника
    name: str
    price: Optional[int]        # тенге, целое
    old_price: Optional[int] = None
    currency: str = "KZT"
    shop_name: Optional[str] = None     # конкретный магазин сети
    city: Optional[str] = None
    brand: Optional[str] = None
    volume_l: Optional[float] = None
    price_per_l: Optional[int] = None
    url: Optional[str] = None
    image_url: Optional[str] = None
    in_stock: Optional[bool] = None     # None = наличие неизвестно
    rarity_tier: str = "ordinary"       # ordinary | rare | exclusive
    tags: list[str] = field(default_factory=list)
    note: Optional[str] = None
    found_at: str = field(default_factory=_utc_now_iso)

    @property
    def discount_percent(self) -> Optional[int]:
        if self.price and self.old_price and self.old_price > self.price:
            return round((self.old_price - self.price) * 100 / self.old_price)
        return None

    def to_dict(self) -> dict:
        return asdict(self)
