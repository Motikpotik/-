"""История цен в SQLite: сравнение текущего прогона с предыдущим."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ..models import Product

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    source      TEXT NOT NULL,
    source_id   TEXT NOT NULL,
    shop_name   TEXT NOT NULL DEFAULT '',
    name        TEXT NOT NULL,
    price       INTEGER,
    seen_at     TEXT NOT NULL,
    run_id      TEXT NOT NULL,
    PRIMARY KEY (source, source_id, shop_name, run_id)
);
CREATE TABLE IF NOT EXISTS runs (
    run_id   TEXT PRIMARY KEY,
    started_at TEXT NOT NULL
);
"""


class PriceHistory:
    def __init__(self, db_path: str | Path) -> None:
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.executescript(SCHEMA)
        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        self.conn.execute(
            "INSERT OR IGNORE INTO runs(run_id, started_at) VALUES (?, ?)",
            (self.run_id, datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
        self.conn.commit()

    def previous_price(self, product: Product) -> int | None:
        """Последняя известная цена товара до текущего прогона."""
        row = self.conn.execute(
            """
            SELECT price FROM snapshots
            WHERE source = ? AND source_id = ?
              AND shop_name = ?
              AND run_id != ? AND price IS NOT NULL
            ORDER BY seen_at DESC LIMIT 1
            """,
            (product.source, product.source_id, product.shop_name or "", self.run_id),
        ).fetchone()
        return row[0] if row else None

    def save(self, products: list[Product]) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.conn.executemany(
            """
            INSERT OR REPLACE INTO snapshots
                (source, source_id, shop_name, name, price, seen_at, run_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (p.source, p.source_id, p.shop_name or "", p.name, p.price, now, self.run_id)
                for p in products
            ],
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
