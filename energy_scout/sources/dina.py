"""
Dina (dinamarket.kz) — публичный GraphQL-API без авторизации.

Эндпоинт и форма запросов восстановлены по фронтенд-наблюдениям
(магазины → категории → товары с остатками и ценами конкретного магазина).
Цены на сайте зависят от выбранного магазина, поэтому магазин(ы) города
выбираются явно через запрос shops.
"""
from __future__ import annotations

from typing import Any

from ..models import Product
from ..normalize import parse_volume_l, pack_size, price_per_liter
from ..rarity import classify_rarity, detect_brand
from .base import BaseSource, SourceResult

GRAPH_URL = "https://backend.dinamarket.kz/api/v1.1/customer/graph"
GRAPH_HEADERS = {
    "Origin": "https://dinamarket.kz",
    "Referer": "https://dinamarket.kz/",
    "Accept": "application/json",
}
PAGE_SIZE = 24  # сервер урезает _limit до 24

SHOPS_QUERY = "{ shops { id name city { name } } }"
CATEGORIES_QUERY = (
    "query($shopId: ID!) { categories(shop_id: $shopId) { id name } }"
)
PRODUCT_FIELDS = (
    "id xid name slug price oldPrice price_type isWeightProduct "
    "preview { url } images { url } stock { amount } categories { id name }"
)
PRODUCTS_QUERY = (
    "query($shopId: ID!, $page: Int, $limit: Int, $categoryId: ID) {"
    " products(shop_id: $shopId, _page: $page, _limit: $limit,"
    " category_id: $categoryId) {"
    " pageInfo { total } edges { " + PRODUCT_FIELDS + " } } }"
)

ENERGY_CATEGORY_HINTS = ("энергетик", "energy")


class DinaSource(BaseSource):
    code = "dina"
    label = "Dina (dinamarket.kz)"

    def _graph(self, query: str, variables: dict | None = None) -> dict[str, Any]:
        payload = {"query": query, "variables": variables or {}}
        try:
            data = self.client.post_json(GRAPH_URL, payload, extra_headers=GRAPH_HEADERS)
        except Exception as exc:
            if self.config.debug:
                self.config.debug.add("Dina", f"запрос к API упал: {exc}")
            raise
        if data.get("errors"):
            message = "; ".join(str(e.get("message", e)) for e in data["errors"])
            if self.config.debug:
                self.config.debug.add("Dina", f"GraphQL-ошибка: {message}", str(data)[:500])
            raise RuntimeError(message)
        return data.get("data") or {}

    def list_city_shops(self) -> list[dict]:
        """Магазины Dina в нужном городе (для CLI --list-shops)."""
        shops = self._graph(SHOPS_QUERY).get("shops") or []
        aliases = tuple(a.lower() for a in self.config.city_aliases)
        return [
            {"id": str(s.get("id")), "name": s.get("name", ""),
             "city": (s.get("city") or {}).get("name", "")}
            for s in shops
            if any(a in str((s.get("city") or {}).get("name", "")).lower() for a in aliases)
        ]

    def _energy_category(self, shop_id: str) -> dict | None:
        categories = self._graph(CATEGORIES_QUERY, {"shopId": shop_id}).get("categories") or []
        for cat in categories:
            name = str(cat.get("name", "")).lower()
            if any(hint in name for hint in ENERGY_CATEGORY_HINTS):
                return cat
        return None

    def _fetch_shop_products(self, shop: dict) -> list[Product]:
        category = self._energy_category(shop["id"])
        if not category:
            if self.config.debug:
                cats = self._graph(CATEGORIES_QUERY, {"shopId": shop["id"]}).get("categories") or []
                self.config.debug.add(
                    "Dina", "категория энергетиков не найдена",
                    "доступные категории: " + ", ".join(str(c.get("name")) for c in cats[:40]),
                )
            raise RuntimeError(f"категория «Энергетики» не найдена для магазина {shop['name']}")

        products: list[Product] = []
        page = 1
        total = None
        while True:
            data = self._graph(PRODUCTS_QUERY, {
                "shopId": shop["id"], "page": page,
                "limit": PAGE_SIZE, "categoryId": category["id"],
            })
            block = data.get("products") or {}
            edges = block.get("edges") or []
            if total is None:
                total = (block.get("pageInfo") or {}).get("total")
            for edge in edges:
                product = self._map_product(edge, shop)
                if product:
                    products.append(product)
            if len(edges) < PAGE_SIZE:
                break
            if total is not None and page * PAGE_SIZE >= int(total):
                break
            page += 1
        return products

    @staticmethod
    def _map_product(item: dict, shop: dict) -> Product | None:
        name = str(item.get("name") or "").strip()
        price = item.get("price")
        try:
            price = int(round(float(price))) if price is not None else None
        except (TypeError, ValueError):
            price = None
        if not name or not price or price <= 0:
            return None

        old_price = item.get("oldPrice")
        try:
            old_price = int(round(float(old_price))) if old_price else None
        except (TypeError, ValueError):
            old_price = None
        if old_price and old_price <= price:
            old_price = None

        slug = item.get("slug")
        preview = item.get("preview") or {}
        images = item.get("images") or []
        image_url = preview.get("url") or next((i.get("url") for i in images if i.get("url")), None)
        stock = item.get("stock") or {}
        amount = stock.get("amount")
        in_stock = None if amount is None else float(amount) > 0

        volume = parse_volume_l(name)
        per_l = price_per_liter(price, volume)
        tier, tags = classify_rarity(name)
        brand = detect_brand(name)
        multiplier = pack_size(name)
        note = f"упаковка ×{multiplier}" if multiplier > 1 else None

        return Product(
            source="dina",
            source_id=str(item.get("id") or item.get("xid") or slug or name),
            name=name,
            price=price,
            old_price=old_price,
            shop_name=f"Dina — {shop['name']}",
            city=shop.get("city"),
            brand=brand,
            volume_l=volume,
            price_per_l=per_l,
            url=f"https://dinamarket.kz/product/{slug}" if slug else None,
            image_url=image_url,
            in_stock=in_stock,
            rarity_tier=tier,
            tags=tags,
            note=note,
        )

    def fetch(self) -> SourceResult:
        errors: list[str] = []
        try:
            shops = self.list_city_shops()
        except Exception as exc:  # сеть/API недоступны
            return SourceResult(self.code, [], [f"Dina: не удалось получить магазины: {exc}"], [])

        if not shops:
            if self.config.debug:
                try:
                    all_shops = self._graph(SHOPS_QUERY).get("shops") or []
                    sample = [f"{s.get('id')}:{(s.get('city') or {}).get('name')}"
                              for s in all_shops[:15]]
                    self.config.debug.add(
                        "Dina", "магазины города не найдены",
                        f"алиасы={self.config.city_aliases}; пример магазинов API: {sample}",
                    )
                except Exception:
                    pass
            return SourceResult(
                self.code, [],
                [f"Dina: в API не найдено магазинов города по алиасам {self.config.city_aliases}"],
                [],
            )

        selected = shops if self.config.all_shops else shops[:1]
        all_products: list[Product] = []
        for shop in selected:
            try:
                all_products.extend(self._fetch_shop_products(shop))
            except Exception as exc:
                errors.append(f"Dina ({shop['name']}): {exc}")
        return SourceResult(self.code, all_products, errors,
                            [f"{s['name']} ({s['city']})" for s in selected])
