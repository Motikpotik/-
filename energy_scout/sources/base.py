"""Базовые контракты источников."""
from __future__ import annotations

import abc
from dataclasses import dataclass

from ..config import Config
from ..http import HttpClient
from ..models import Product


SOURCE_LABELS = {
    "dina": "Dina (dinamarket.kz)",
    "magnum": "Magnum — каталог скидок",
    "marwin": "Marwin/Meloman (marwin.kz)",
    "anvar_promo": "Anvar — промо-листовки",
    "web": "Веб-поиск",
}


@dataclass
class SourceResult:
    code: str
    products: list[Product]
    errors: list[str]
    shops: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def label(self) -> str:
        return SOURCE_LABELS.get(self.code, self.code)


class BaseSource(abc.ABC):
    code: str = "base"
    label: str = "Источник"

    def __init__(self, client: HttpClient, config: Config) -> None:
        self.client = client
        self.config = config

    @abc.abstractmethod
    def fetch(self) -> SourceResult:
        """Собрать сырые товары (фильтрация по ключевым словам — в пайплайне)."""
        raise NotImplementedError
