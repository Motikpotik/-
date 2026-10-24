"""Сбор отладочных сообщений источников и запись их в лог-файл."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path


class DebugLog:
    """Накапливает диагностические записи и сохраняет их в файл."""

    def __init__(self) -> None:
        self.entries: list[str] = []

    def add(self, source: str, message: str, excerpt: str | None = None) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.entries.append(f"[{stamp}] {source}: {message}")
        if excerpt:
            clipped = excerpt.strip().replace("\n", " ")[:500]
            self.entries.append(f"    ↳ {clipped}")

    def write(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        header = (
            f"Energy Scout — отладочный лог {datetime.now():%Y-%m-%d %H:%M:%S}\n"
            f"Записей: {len(self.entries)}\n" + "=" * 60 + "\n"
        )
        path.write_text(header + "\n".join(self.entries) + "\n", encoding="utf-8")
        return path
