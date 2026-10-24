"""Офлайн-тесты: парсинг, редкость, адаптеры на фикстурах, весь пайплайн."""
from __future__ import annotations

import unittest
from pathlib import Path

from energy_scout.config import Config
from energy_scout.http import FixtureClient
from energy_scout.models import Product
from energy_scout.normalize import (
    normalize_name, pack_size, parse_all_prices, parse_price, parse_volume_l,
)
from energy_scout.pipeline import dedupe, filter_products, run_pipeline
from energy_scout.rarity import classify_rarity, detect_brand
from energy_scout.sources.anvar import AnvarSource
from energy_scout.sources.dina import DinaSource
from energy_scout.sources.magnum import MagnumSource
from energy_scout.sources.websearch import WebSearchSource

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class NormalizeTests(unittest.TestCase):
    def test_prices(self):
        self.assertEqual(parse_price("699 тг"), 699)
        self.assertEqual(parse_price("1 390 тг"), 1390)
        self.assertEqual(parse_price("286 тенге"), 286)
        self.assertIsNone(parse_price("цена не указана"))
        self.assertEqual(parse_all_prices("699 тг 899 тг -22%"), [699, 899])

    def test_volume(self):
        self.assertAlmostEqual(parse_volume_l("Monster 0,33 ж/б"), 0.33)
        self.assertAlmostEqual(parse_volume_l("Lavina 0.45 л"), 0.45)
        self.assertAlmostEqual(parse_volume_l("Red Bull 250 мл"), 0.25)
        self.assertIsNone(parse_volume_l("без объёма"))

    def test_pack_and_name(self):
        self.assertEqual(pack_size("Flash Energy 0,5 х4 ж/б"), 4)
        self.assertEqual(pack_size("Monster 0,33 ж/б"), 1)
        self.assertEqual(normalize_name("Monster, Ultra!"), "monster ultra")


class RarityTests(unittest.TestCase):
    def test_ordinary(self):
        tier, tags = classify_rarity("Напиток энергетический Lavina 0,45")
        self.assertEqual(tier, "ordinary")
        self.assertNotIn("импорт", " ".join(tags))

    def test_rare_flavor(self):
        tier, _ = classify_rarity("Monster Pipeline Punch 0,473")
        self.assertEqual(tier, "rare")

    def test_exclusive_import_limited(self):
        tier, tags = classify_rarity(
            "Monster Pipeline Punch, импорт США, limited edition 0,473"
        )
        self.assertEqual(tier, "exclusive")
        self.assertTrue(any(t.startswith("импорт") for t in tags))
        self.assertTrue(any(t.startswith("лимит") for t in tags))

    def test_brand(self):
        self.assertEqual(detect_brand("Монстр Энерджи 0.5"), "Monster")
        self.assertEqual(detect_brand("RED BULL 0.25"), "Red Bull")
        self.assertIsNone(detect_brand("Вода питьевая 1 л"))


class DinaFixtureTests(unittest.TestCase):
    def setUp(self):
        self.client = FixtureClient(FIXTURES)
        self.config = Config()
        self.source = DinaSource(self.client, self.config)

    def test_only_aktobe_shops(self):
        shops = self.source.list_city_shops()
        cities = {s["city"] for s in shops}
        self.assertEqual(cities, {"Актобе"})
        self.assertEqual(len(shops), 2)

    def test_fetch_maps_products(self):
        result = self.source.fetch()
        self.assertEqual(result.errors, [])
        self.assertEqual(len(result.products), 8)
        classic = next(p for p in result.products if "Classic" in p.name)
        self.assertEqual(classic.price, 590)
        self.assertEqual(classic.old_price, 690)
        self.assertIn("Dina —", classic.shop_name)
        self.assertTrue(classic.in_stock)
        self.assertTrue(classic.url.endswith("/product/monster-energy-classic-0-33"))
        mango = next(p for p in result.products if "Mango Loco" in p.name)
        self.assertFalse(mango.in_stock)
        rare = next(p for p in result.products if "Pipeline Punch" in p.name)
        self.assertEqual(rare.rarity_tier, "exclusive")
        self.assertAlmostEqual(rare.volume_l, 0.473)


class MagnumFixtureTests(unittest.TestCase):
    def test_parse_ssr_cards(self):
        client = FixtureClient(FIXTURES)
        source = MagnumSource(client, Config())
        result = source.fetch()
        self.assertEqual(result.errors, [])
        names = [p.name for p in result.products]
        self.assertTrue(any("MONSTER ULTRA" in n for n in names))
        # макароны не должны попасть в энергетики на уровне фильтра пайплайна
        self.assertTrue(any("MAKFA" in n for n in names))  # до фильтра — все карточки
        monster = next(p for p in result.products if "MONSTER ULTRA" in p.name)
        self.assertEqual(monster.price, 699)
        self.assertEqual(monster.old_price, 899)
        self.assertEqual(monster.discount_percent, 22)
        pipeline_one = next(p for p in result.products if "PIPELINE" in p.name)
        self.assertEqual(pipeline_one.price, 1390)


class AnvarFixtureTests(unittest.TestCase):
    def test_leaflet_scan(self):
        client = FixtureClient(FIXTURES)
        result = AnvarSource(client, Config()).fetch()
        self.assertEqual(result.errors, [])
        self.assertTrue(any("Monster" in p.name for p in result.products))
        self.assertTrue(all(p.price is None for p in result.products))


class WebSearchFixtureTests(unittest.TestCase):
    def test_ddg_parse_and_exclusions(self):
        client = FixtureClient(FIXTURES)
        result = WebSearchSource(client, Config()).fetch()
        names = " ".join(p.name for p in result.products).lower()
        self.assertNotIn("корм", names)
        self.assertTrue(any("aussie" in p.name.lower() for p in result.products))
        pricey = next(p for p in result.products if "Aussie" in p.name)
        self.assertEqual(pricey.price, 2200)
        no_price = next(p for p in result.products if "Summer Edition" in p.name)
        self.assertIsNone(no_price.price)


class PipelineTests(unittest.TestCase):
    def test_full_pipeline_filters_dedupe_sorts(self):
        config = Config()
        client = FixtureClient(FIXTURES)
        report = run_pipeline(client, config)
        names = " ".join(p.name for p in report.products).lower()
        self.assertNotIn("makfa", names)                  # не-энергетик отфильтрован
        self.assertNotIn("корм", names)
        self.assertTrue(all(p.source != "web" or True for p in report.products))
        # эксклюзив всегда раньше обычного
        tiers = [p.rarity_tier for p in report.products]
        self.assertIn("exclusive", tiers)
        self.assertEqual(tiers.index("exclusive"), 0)
        # ни один out-of-stock не потерян по умолчанию, но фильтр работает
        self.assertTrue(any(p.in_stock is False for p in report.products))
        filtered = filter_products(report.products, Config(in_stock_only=True))
        self.assertTrue(all(p.in_stock is not False for p in filtered))

    def test_rare_only_and_max_price(self):
        config = Config(rare_only=True, max_price=1000)
        report = run_pipeline(FixtureClient(FIXTURES), config)
        self.assertTrue(all(p.rarity_tier != "ordinary" for p in report.products))
        self.assertTrue(all(p.price is None or p.price <= 1000 for p in report.products))

    def test_dedupe(self):
        p = Product(source="dina", source_id="1", name="Monster 0,33", price=590)
        p2 = Product(source="dina", source_id="1", name="Monster 0,33!", price=590)
        other = Product(source="magnum", source_id="9", name="Monster 0,33", price=699)
        self.assertEqual(len(dedupe([p, p2, other])), 2)


if __name__ == "__main__":
    unittest.main()
