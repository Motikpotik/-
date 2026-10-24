"""
Marwin (marwin.kz, он же Meloman) — казахстанская сеть с физическим
магазином в Актобе (ТРЦ Keruen City). Сайт отдаёт обычный SSR-HTML,
браузер не нужен. Именно здесь самая широкая линейка импортных Monster
(Польша/Великобритания): Nitro, The Doctor, Ultra Violet, Khaotic и т.п.

Нюанс: на сайте наличие по умолчанию показано для склада/Алматы;
в карточке есть выбор города, в Актобе остатки могут отличаться —
товары не «в корзину» помечаются как отсутствующие.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

from ..html import make_soup
from ..models import Product
from ..normalize import parse_price, parse_volume_l, price_per_liter
from ..rarity import classify_rarity, detect_brand
from .base import BaseSource, SourceResult

BASE = "https://www.marwin.kz"
# Полная категория энергетиков: Monster, Red Bull, Dizzy, Gorilla, LIT, Powercell
CATEGORY_URL = (
    BASE + "/bezalkogol-nye-napitki/jenergeticheskie-napitki/"
)
PRODUCT_HINT = "/jenergeticheskie-napitki/"
MAX_PAGES = 5


class MarwinSource(BaseSource):
    code = "marwin"
    label = "Marwin/Meloman (marwin.kz)"

    def fetch(self) -> SourceResult:
        products: list[Product] = []
        errors: list[str] = []
        seen: set[str] = set()
        url = CATEGORY_URL
        try:
            for _ in range(MAX_PAGES):
                html = self.client.get(url).text
                cards, next_url = self._parse_page(html)
                for card in cards:
                    if card["url"] in seen:
                        continue
                    seen.add(card["url"])
                    product = self._map(card)
                    if product:
                        products.append(product)
                if not next_url:
                    break
                url = urljoin(BASE, next_url)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Marwin: {exc}")
            if self.config.debug:
                self.config.debug.add("Marwin", f"сбор категории упал: {exc}")
        if not products and self.config.debug:
            self.config.debug.add("Marwin", "0 товаров: изменилась вёрстка или пустая категория")
        return SourceResult(self.code, products, errors,
                            ["каталог энергетиков marwin.kz"])

    def _parse_page(self, html: str) -> tuple[list[dict], str | None]:
        soup = make_soup(html)
        cards: list[dict] = []
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]
            name = anchor.get_text(" ", strip=True)
            if PRODUCT_HINT not in href or ".html" not in href or len(name) < 5:
                continue
            container = self._card_container(anchor)
            text = container.get_text(" ", strip=True)
            price = parse_price(text)
            in_stock = "В корзину" in text or "в корзину" in text.lower()
            cards.append({
                "name": name,
                "url": urljoin(BASE, href.split("?")[0]),
                "price": price,
                "in_stock": in_stock,
                "text": text,
            })
        next_link = soup.select_one("a.action.next") or soup.find("a", title=re.compile("Вперёд|Next", re.I))
        next_url = next_link.get("href") if next_link else None
        # дедуп внутри страницы
        unique: dict[str, dict] = {}
        for card in cards:
            unique.setdefault(card["url"], card)
        return list(unique.values()), next_url

    @staticmethod
    def _card_container(anchor):
        node = anchor
        for _ in range(7):
            node = node.parent
            if node is None:
                return anchor
            if "₸" in node.get_text(" ", strip=True):
                return node
        return anchor

    def _map(self, card: dict) -> Product | None:
        name = card["name"]
        lower = name.lower()
        if not any(term in lower for term in self.config.search_terms):
            return None
        if any(bad in lower for bad in self.config.exclusions):
            return None
        price = card["price"]
        volume = parse_volume_l(name)
        tier, tags = classify_rarity(name)
        if not card["in_stock"]:
            tags = tags + ["нет на складе сайта"]
        return Product(
            source="marwin",
            source_id=card["url"].rstrip("/").split("/")[-1],
            name=name,
            price=price,
            old_price=None,
            shop_name="Marwin/Meloman (Актобе, Keruen City)",
            city=self.config.city,
            brand=detect_brand(name),
            volume_l=volume,
            price_per_l=price_per_liter(price, volume),
            url=card["url"],
            in_stock=card["in_stock"],
            rarity_tier=tier,
            tags=tags,
            note="наличие на сайте — склад/выбранный город, в Актобе уточняйте в магазине",
        )
