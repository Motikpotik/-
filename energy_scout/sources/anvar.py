"""
Anvar (anvar.kz) — у сети нет публичного каталога с ценами: сайт на Bitrix
содержит только промо-листовки («Супер цена» и т.п.). Адаптер сканирует
страницы листовок и фиксирует упоминания энергетиков. Цена почти всегда
отсутствует — такие записи помечаются и идут в отчёт как «наводка».
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..models import Product
from ..rarity import classify_rarity, detect_brand
from .base import BaseSource, SourceResult

BASE = "https://www.anvar.kz"
CATALOGS_URL = f"{BASE}/stock/catalogs/"
MAX_LEAFLETS = 12
LINK_RE = re.compile(r"/stock/(?:product|catalogs)/")


class AnvarSource(BaseSource):
    code = "anvar_promo"
    label = "Anvar — промо-листовки (anvar.kz)"

    def fetch(self) -> SourceResult:
        errors: list[str] = []
        products: list[Product] = []
        try:
            index_html = self.client.get(CATALOGS_URL).text
            links = self._leaflet_links(index_html)
        except Exception as exc:
            return SourceResult(self.code, [], [f"Anvar: {exc}"], [])

        terms = [t for t in self.config.search_terms if len(t) >= 4]
        for url in links[:MAX_LEAFLETS]:
            try:
                soup = BeautifulSoup(self.client.get(url).text, "lxml")
            except Exception as exc:
                errors.append(f"Anvar {url}: {exc}")
                continue
            text = soup.get_text("\n", strip=True)
            lower = text.lower()
            if not any(term in lower for term in terms):
                continue
            title = (soup.find("h1").get_text(strip=True) if soup.find("h1") else "Листовка Anvar")
            for line in self._matching_lines(text, terms):
                tier, tags = classify_rarity(line)
                products.append(Product(
                    source="anvar_promo",
                    source_id=re.sub(r"\W+", "_", line.lower())[:80],
                    name=line[:160],
                    price=None,
                    old_price=None,
                    shop_name="Anvar (промо-листовка)",
                    city=self.config.city,
                    brand=detect_brand(line),
                    url=url,
                    in_stock=None,
                    rarity_tier=tier,
                    tags=tags + ["цена не указана на сайте"],
                    note=f"листовка: {title}",
                ))
        return SourceResult(self.code, self._dedupe(products), errors, ["промо-листовки Актобе"])

    def _leaflet_links(self, html: str) -> list[str]:
        soup = BeautifulSoup(html, "lxml")
        urls: list[str] = []
        for anchor in soup.find_all("a", href=LINK_RE):
            full = urljoin(BASE, anchor["href"].split("?", 1)[0])
            if full not in urls and full != CATALOGS_URL.rstrip("/"):
                urls.append(full)
        return urls

    @staticmethod
    def _matching_lines(text: str, terms: list[str]) -> list[str]:
        hits: list[str] = []
        for raw_line in text.splitlines():
            line = raw_line.strip(" -—•\t")
            if 8 <= len(line) <= 160 and any(term in line.lower() for term in terms):
                hits.append(line)
        return hits[:30]

    @staticmethod
    def _dedupe(products: list[Product]) -> list[Product]:
        seen: set[str] = set()
        unique = []
        for p in products:
            if p.source_id not in seen:
                seen.add(p.source_id)
                unique.append(p)
        return unique
