"""Оркестрация: запуск источников, фильтры, дедупликация и сортировка."""
from __future__ import annotations

from dataclasses import dataclass, field

from .config import Config
from .models import Product
from .normalize import normalize_name
from .sources.anvar import AnvarSource
from .sources.base import BaseSource, SourceResult
from .sources.dina import DinaSource
from .sources.magnum import MagnumSource
from .sources.marwin import MarwinSource
from .sources.websearch import WebSearchSource

TIER_RANK = {"exclusive": 0, "rare": 1, "ordinary": 2}


@dataclass
class RunReport:
    products: list[Product]
    source_results: list[SourceResult] = field(default_factory=list)

    @property
    def errors(self) -> list[str]:
        return [e for r in self.source_results for e in r.errors]

    def stats(self) -> dict:
        stats: dict = {"total": len(self.products)}
        stats["exclusive"] = sum(p.rarity_tier == "exclusive" for p in self.products)
        stats["rare"] = sum(p.rarity_tier == "rare" for p in self.products)
        stats["with_price"] = sum(p.price is not None for p in self.products)
        stats["in_stock"] = sum(p.in_stock is True for p in self.products)
        stats["by_source"] = {}
        for result in self.source_results:
            stats["by_source"][result.code] = len(result.products)
        return stats


def build_sources(client, config: Config) -> list[BaseSource]:
    registry = {
        "dina": DinaSource,
        "magnum": MagnumSource,
        "marwin": MarwinSource,
        "anvar": AnvarSource,
        "web": WebSearchSource,
    }
    sources = []
    for code, enabled in config.sources.items():
        if enabled and code in registry:
            sources.append(registry[code](client, config))
    return sources


def run_pipeline(client, config: Config) -> RunReport:
    results: list[SourceResult] = []
    for source in build_sources(client, config):
        results.append(source.fetch())
    products = [p for r in results for p in r.products]
    products = filter_products(products, config)
    products = dedupe(products)
    products.sort(key=_sort_key)
    return RunReport(products=products, source_results=results)


def filter_products(products: list[Product], config: Config) -> list[Product]:
    terms = config.search_terms
    exclusions = [e.lower() for e in config.exclusions]
    kept: list[Product] = []
    for p in products:
        haystack = f"{p.name} {p.brand or ''}".lower()
        if not any(term in haystack for term in terms):
            continue
        if any(bad in haystack for bad in exclusions):
            continue
        if config.in_stock_only and p.in_stock is False:
            continue
        if config.rare_only and p.rarity_tier == "ordinary":
            continue
        if config.max_price and p.price is not None and p.price > config.max_price:
            continue
        kept.append(p)
    return kept


def dedupe(products: list[Product]) -> list[Product]:
    """Схлопываем одинаковые карточки одного источника/магазина."""
    seen: set[tuple] = set()
    unique: list[Product] = []
    for p in products:
        key = (
            p.source,
            p.shop_name,
            normalize_name(p.name),
            p.volume_l,
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)
    return unique


def _sort_key(p: Product) -> tuple:
    return (
        TIER_RANK.get(p.rarity_tier, 3),
        p.price is None,          # товары с ценой — выше
        p.price or 10**9,
        p.price_per_l or 10**9,
        p.name.lower(),
    )
