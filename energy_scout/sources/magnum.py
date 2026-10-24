"""
Magnum (magnum.kz) — сайт отдаёт готовый SSR-HTML каталога скидок
(Nuxt), поэтому данные снимаются обычным HTTP-запросом + BeautifulSoup,
без браузера. Город передаётся параметром ?city=<slug>.

Важно: на сайте magnum.kz это «Каталог скидок» (~150 акционных товаров),
а не полный ассортимент. Цены могут отличаться в конкретном магазине —
в отчёте товар помечается соответствующей заметкой.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

from ..html import make_soup
from ..models import Product
from ..normalize import parse_all_prices, parse_volume_l, price_per_liter
from ..rarity import classify_rarity, detect_brand
from .base import BaseSource, SourceResult

BASE = "https://magnum.kz"
PRODUCT_HREF_RE = re.compile(r"/products/(\d+)")
MAX_PAGES = 20


class MagnumSource(BaseSource):
    code = "magnum"
    label = "Magnum — каталог скидок (magnum.kz)"

    def __init__(self, client, config) -> None:
        super().__init__(client, config)
        self.city_slug = self._city_slug()

    def _city_slug(self) -> str:
        alias = (self.config.city_aliases[0] if self.config.city_aliases else "akto").lower()
        # транслит-подсказка для основных городов; Актобе → aktobe
        mapping = {"акто": "aktobe", "ақтө": "aktobe", "akto": "aktobe"}
        return mapping.get(alias, "aktobe")

    def _parse_page(self, html: str) -> dict[str, dict]:
        soup = make_soup(html)
        found: dict[str, dict] = {}

        # 1) JSON-LD как самый надёжный источник, если разметка присутствует
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            try:
                import json
                data = json.loads(script.string or "{}")
            except (ValueError, TypeError):
                continue
            items = data if isinstance(data, list) else [data]
            for block in items:
                if not isinstance(block, dict) or block.get("@type") != "Product":
                    continue
                offers = block.get("offers") or {}
                pid = str(block.get("sku") or block.get("url") or block.get("name"))
                found[pid] = {
                    "name": str(block.get("name") or "").strip(),
                    "price": self._to_int(offers.get("price")),
                    "old_price": None,
                    "url": block.get("url"),
                    "image": block.get("image"),
                }

        # 2) Основной путь: ссылки /products/<id>
        for anchor in soup.find_all("a", href=PRODUCT_HREF_RE):
            match = PRODUCT_HREF_RE.search(anchor.get("href", ""))
            if not match:
                continue
            pid = match.group(1)
            if pid in found and found[pid].get("name"):
                continue
            card = self._card_container(anchor)
            text = card.get_text(" ", strip=True) if card else anchor.get_text(" ", strip=True)
            prices = parse_all_prices(text)
            img = card.find("img") if card else anchor.find("img")
            name = self._extract_name(anchor, img, text)
            found[pid] = {
                "name": name,
                "price": prices[0] if prices else None,
                "old_price": prices[1] if len(prices) > 1 else None,
                "url": urljoin(BASE, anchor["href"]),
                "image": img.get("src") if img and img.get("src") else None,
            }
        return found

    @staticmethod
    def _card_container(anchor):
        """Поднимаемся вверх до ближайшей карточки, внутри которой есть цена."""
        node = anchor
        for _ in range(6):
            node = node.parent
            if node is None:
                return anchor
            if "тг" in node.get_text(" ", strip=True) and node.find("img"):
                return node
        return anchor

    @staticmethod
    def _extract_name(anchor, img, fallback_text: str) -> str:
        if img and img.get("alt"):
            alt = img["alt"].strip()
            if len(alt) > 5:
                return alt
        text = anchor.get_text(" ", strip=True)
        text = re.sub(r"быстрый просмотр", "", text, flags=re.IGNORECASE).strip()
        if len(text) > 5:
            return text
        # выкидываем хвосты с ценами из текста карточки
        cleaned = re.split(r"\d[\d\s ]*\s*тг", fallback_text, maxsplit=1)[0]
        return cleaned.strip(" -—") or fallback_text[:120]

    @staticmethod
    def _to_int(value) -> int | None:
        try:
            return int(round(float(value)))
        except (TypeError, ValueError):
            return None

    def fetch(self) -> SourceResult:
        products: list[Product] = []
        errors: list[str] = []
        seen: set[str] = set()
        try:
            for page in range(1, MAX_PAGES + 1):
                url = f"{BASE}/catalog?city={self.city_slug}"
                if page > 1:
                    url += f"&page={page}"
                html = self.client.get(url).text
                cards = self._parse_page(html)
                new_ids = [pid for pid in cards if pid not in seen]
                if not new_ids:
                    break
                for pid in new_ids:
                    seen.add(pid)
                    data = cards[pid]
                    product = self._map(pid, data)
                    if product:
                        products.append(product)
        except Exception as exc:
            errors.append(f"Magnum: {exc}")
            if self.config.debug:
                self.config.debug.add("Magnum", f"сбор каталога упал: {exc}")
        if not products and self.config.debug:
            self.config.debug.add(
                "Magnum", "0 товаров: изменилась вёрстка или нет акций по напиткам",
            )
        return SourceResult(self.code, products, errors,
                            [f"каталог скидок, город {self.city_slug}"])

    def _map(self, pid: str, data: dict) -> Product | None:
        name = data.get("name") or ""
        price = data.get("price")
        if not name or not price:
            return None
        volume = parse_volume_l(name)
        tier, tags = classify_rarity(name)
        return Product(
            source="magnum",
            source_id=pid,
            name=name,
            price=price,
            old_price=data.get("old_price"),
            shop_name="Magnum (акционный каталог)",
            city=self.config.city,
            brand=detect_brand(name),
            volume_l=volume,
            price_per_l=price_per_liter(price, volume),
            url=data.get("url"),
            image_url=data.get("image"),
            in_stock=None,
            rarity_tier=tier,
            tags=tags,
            note="цена акционного каталога, проверьте в магазине Актобе",
        )
