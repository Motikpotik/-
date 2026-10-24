"""
Веб-поиск как запасной источник: находит редкие/импортные энергетики,
которые всплывают в каталогах, объявлениях и обзорах города.

Цепочка движков без API-ключа: DuckDuckGo HTML → DuckDuckGo Lite → Bing
(первый работающий побеждает). Если задан SERPAPI_KEY — используется SerpAPI.
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

DDG_HTML_URL = "https://html.duckduckgo.com/html/?q={query}"
DDG_LITE_URL = "https://lite.duckduckgo.com/lite/?q={query}"
BING_URL = "https://www.bing.com/search?q={query}&setlang=ru-RU"
SERP_URL = ("https://serpapi.com/search.json?engine=google&location=Kazakhstan"
            "&q={query}&api_key={key}")

QUERY_BRANDS = ["Monster", "Red Bull", "Burn", "Adrenaline", "Gorilla", "Flash"]


class WebSearchSource(BaseSource):
    code = "web"
    label = "Веб-поиск (DuckDuckGo/Bing)"

    def fetch(self) -> SourceResult:
        queries = self._build_queries()
        products: list[Product] = []
        errors: list[str] = []
        api_key = os.getenv("SERPAPI_KEY")
        for query in queries:
            try:
                results = self._serp(query, api_key) if api_key else self._search_chain(query)
            except Exception as exc:
                errors.append(f"Web ({query}): {exc}")
                if self.config.debug:
                    self.config.debug.add("Web", f"запрос «{query}» упал: {exc}")
                continue
            if not results and self.config.debug:
                self.config.debug.add("Web", f"пустая выдача по запросу «{query}»")
            for title, snippet, url in results:
                product = self._map(query, title, snippet, url)
                if product:
                    products.append(product)
        return SourceResult(self.code, self._dedupe(products), errors, ["поисковая выдача"])

    def _build_queries(self) -> list[str]:
        city = self.config.city
        brands = self.config.extra_queries or QUERY_BRANDS
        queries = [f"{b} энергетик купить {city} цена" for b in brands[: self.config.web_max_queries]]
        if self.config.extra_queries:
            queries += [
                f"{q} энергетический напиток {self.config.city}"
                for q in self.config.extra_queries[: self.config.web_max_queries]
            ]
        return queries[: self.config.web_max_queries]

    # ---------- движки ----------

    def _search_chain(self, query: str) -> list[tuple[str, str, str]]:
        """Последовательно пробует движки, пока какой-то не даст результаты."""
        engines = [
            ("DuckDuckGo HTML", DDG_HTML_URL, self._parse_ddg_html),
            ("DuckDuckGo Lite", DDG_LITE_URL, self._parse_ddg_lite),
            ("Bing", BING_URL, self._parse_bing),
        ]
        last_error: Exception | None = None
        for name, template, parser in engines:
            url = template.format(query=quote_plus(query))
            try:
                html = self.client.get(url).text
                results = parser(html)
                if results:
                    if self.config.debug:
                        self.config.debug.add("Web", f"движок {name} сработал по «{query}»")
                    return results
                if self.config.debug:
                    self.config.debug.add("Web", f"{name} вернул 0 результатов", html[:200])
            except Exception as exc:  # noqa: BLE001 — пробуем следующий движок
                last_error = exc
                if self.config.debug:
                    self.config.debug.add("Web", f"{name} упал: {exc}")
        if last_error:
            raise RuntimeError(f"все движки недоступны, последняя ошибка: {last_error}")
        return []

    def _parse_ddg_html(self, html: str) -> list[tuple[str, str, str]]:
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

    def _parse_ddg_lite(self, html: str) -> list[tuple[str, str, str]]:
        soup = make_soup(html)
        out: list[tuple[str, str, str]] = []
        for link in soup.select("a.result-link"):
            href = link.get("href", "")
            title = link.get_text(" ", strip=True)
            if not href or not title:
                continue
            # сниппет в lite-верстке лежит в соседней строке той же таблицы
            container = link.find_parent("table") or link.find_parent("tr") or link.parent
            snippet = ""
            if container:
                snip_node = container.select_one(".result-snippet")
                if snip_node:
                    snippet = snip_node.get_text(" ", strip=True)
            out.append((title, snippet, href))
        return out

    def _parse_bing(self, html: str) -> list[tuple[str, str, str]]:
        soup = make_soup(html)
        out = []
        for block in soup.select("li.b_algo"):
            link = block.select_one("h2 a")
            if not link:
                continue
            snippet_node = block.select_one(".b_caption p")
            out.append((
                link.get_text(" ", strip=True),
                snippet_node.get_text(" ", strip=True) if snippet_node else "",
                link.get("href", ""),
            ))
        return out

    def _serp(self, query: str, key: str) -> list[tuple[str, str, str]]:
        url = SERP_URL.format(query=quote_plus(query), key=quote_plus(key))
        data = self.client.get(url).json()
        return [
            (item.get("title", ""), item.get("snippet", ""), item.get("link", ""))
            for item in data.get("organic_results", [])
        ]

    # ---------- отображение ----------

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
        seen: set[tuple] = set()
        unique = []
        for p in products:
            key = (p.name.lower(), p.url)
            if key not in seen:
                seen.add(key)
                unique.append(p)
        return unique
