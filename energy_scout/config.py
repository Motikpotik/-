"""Конфигурация: значения по умолчанию + опциональный config.yaml."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


DEFAULT_KEYWORDS = [
    "энергетическ", "energy drink", "monster", "монстр",
    "red bull", "ред булл", "burn", "адреналин", "adrenaline",
    "gorilla", "горилла", "flash", "торнадо", "tornado",
    "e-on", "dizzy", "lavina", "nitro",
]

DEFAULT_EXCLUSIONS = [
    "корм", "для кошек", "для собак", "игрушк", "сувенир",
    "шампунь", "гели для душа", "наклейк", "журнал",
]

DEFAULT_SOURCES = {
    "dina": True,
    "magnum": True,
    "anvar": True,
    "web": True,
}


@dataclass
class Config:
    city: str = "Актобе"
    city_aliases: list[str] = field(default_factory=lambda: ["акто", "ақтө", "akto"])
    all_shops: bool = False
    sources: dict[str, bool] = field(default_factory=lambda: dict(DEFAULT_SOURCES))
    keywords: list[str] = field(default_factory=lambda: list(DEFAULT_KEYWORDS))
    exclusions: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUSIONS))
    delay_seconds: float = 0.4
    timeout_seconds: float = 25.0
    max_retries: int = 3
    web_max_queries: int = 6
    # параметры CLI (не из yaml)
    extra_queries: list[str] = field(default_factory=list)
    max_price: int | None = None
    rare_only: bool = False
    in_stock_only: bool = False
    output_dir: str = "reports"
    use_history: bool = True

    @property
    def search_terms(self) -> list[str]:
        terms = list(self.keywords) + [q.lower() for q in self.extra_queries]
        # без дублей, сохраняя порядок
        seen: set[str] = set()
        result = []
        for t in terms:
            t = t.strip().lower()
            if t and t not in seen:
                seen.add(t)
                result.append(t)
        return result


def load_config(path: str | Path | None) -> Config:
    cfg = Config()
    if not path:
        return cfg
    p = Path(path)
    if not p.exists():
        return cfg
    data: dict[str, Any] = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    for key, value in data.items():
        if hasattr(cfg, key) and value is not None:
            setattr(cfg, key, value)
    return cfg
