"""
Веб-поиск как запасной источник: находит редкие/импортные энергетики,
которые всплывают в каталогах, объявлениях и обзорах города.

По умолчанию используется бесплатный HTML DuckDuckGo (без ключа).
Если задан переменный окружения SERPAPI_KEY — подключается SerpAPI
(google-результаты, стабильнее, но лимитирован по тарифу).
"""
from __future__ import annotations

import os
import re
from urllib.parse import quote_plus

from ..html import make_soup
from ..models import Product
from ..normalize import parse_all_prices, parse_volume_l, price_per_liter
from ..rarity import classify_rarity, detect_brand
from .base import BaseSource, SourceResult

DDG_URL = "https://html.duckduckgo.com/html/?q={query}"
SERP_URL = "https://serpapi.com/search.json?engine=google&location=Kazakhstan&q={query}&api_key={key}"

# Бренды, по которым строятся точечные запросы
QUERY_BRANDS = ["Monster", "Red Bull", "Burn", "Adrenaline", "Gorilla", "Flash"]


class WebSearchSource(BaseSource):
    code = "web"
    label = "Веб-поиск (DuckDuckGo/SerpAPI)"

    def fetch(self) -> SourceResult:
        queries = self._build_queries()
        products: list[Product] = []
        errors: list[str] = []
        api_key = os.getenv("SERPAPI_KEY")
        for query in queries:
            try:
                results = self._serp(query, api_key) if api_key else self._ddg(query)
            except Exception as exc:
                errors.append(f"Web ({query}): {exc}")
                continue
            for title, snippet, url in results:
                product = self._map(query, title, snippet, url)
                if product:
                    products.append(product)
        return SourceResult(self.code, self._dedupe(products), errors, ["поисковая выдача"])

    def _build_queries(self) -> list[str]:
        city = self.config.city
        brands = [b for b in QUERY_BRANDS]
        # ручные запросы пользователя — в приоритете
        brands = self.config.extra_queries or brands
        queries = [f"{b} энергетик купить {city} цена" for b in brands[: self.config.web_max_queries]]
        if self.config.extra_queries:
            queries += [
                f"{q} энергетический напиток {self.config.city}"
                for q in self.config.extra_queries[: self.config.web_max_queries]
            ]
        return queries[: self.config.web_max_queries]

    def _ddg(self, query: str) -> list[tuple[str, str, str]]:
        html = self.client.get(DDG_URL.format(query=quote_plus(query))).text
        soup = make_soup(html)
        out = []
        for result in soup.select(".result"):
            link = result.select_one(".result__a")
            snippet = result.select_one(".result__snippet")
            if not link:
                continue
            out.append((
                link.get_text(" ", strip=True),
                snippet.get_text(" ", strip=True) if snippet else "",
                link.get("href", ""),
            ))
        return out

    def _serp(self, query: str, key: str) -> list[tuple[str, str, str]]:
        url = SERP_URL.format(query=quote_plus(query), key=quote_plus(key))
        data = self.client.get(url).json()
        out = []
        for item in data.get("organic_results", []):
            out.append((item.get("title", ""), item.get("snippet", ""), item.get("link", "")))
        return out

    def _map(self, query: str, title: str, snippet: str, url: str) -> Product | None:
        text = f"{title} {snippet}"
        lower = text.lower()
        if not any(term in lower for term in self.config.search_terms):
            return None
        if any(bad in lower for bad in self.config.exclusions):
            return None
        prices = parse_all_prices(text)
        name = self._clean_title(title)
        if len(name) < 5:
            return None
        tier, tags = classify_rarity(text)
        price = prices[0] if prices else None
        volume = parse_volume_l(text)
        return Product(
            source="web",
            source_id=re.sub(r"\W+", "_", url or name.lower())[:100],
            name=name,
            price=price,
            old_price=prices[1] if len(prices) > 1 else None,
            shop_name="Веб-поиск",
            city=self.config.city,
            brand=detect_brand(text),
            volume_l=volume,
            price_per_l=price_per_liter(price, volume),
            url=url or None,
            in_stock=None,
            rarity_tier=tier,
            tags=tags + (["найдено поиском, требуется проверка"] if price is None else []),
            note=f"запрос: {query}",
        )

    @staticmethod
    def _clean_title(title: str) -> str:
        title = re.sub(r"\s+[—|-].*?(купить|цена|отзывы|доставка).*$", "", title, flags=re.IGNORECASE)
        return title.strip(" -—|")[:160]

    @staticmethod
    def _dedupe(products: list[Product]) -> list[Product]:
        seen: set[str] = set()
        unique = []
        for p in products:
            key = (p.name.lower(), p.url)
            if key not in seen:
                seen.add(key)
                unique.append(p)
        return unique
