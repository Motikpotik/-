"""Диагностика окружения: версии пакетов и доступность сайтов-источников."""
from __future__ import annotations

import importlib
import platform
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

PACKAGE_CHECKS = [
    ("httpx", "обязательный — HTTP-запросы"),
    ("bs4", "обязательный — разбор HTML"),
    ("lxml", "опциональный — быстрый парсер HTML"),
    ("rich", "обязательный — таблицы в консоли"),
    ("openpyxl", "опциональный — Excel-отчёт"),
    ("yaml", "опциональный — config.yaml"),
]

SITE_CHECKS = [
    ("Dina API", "https://backend.dinamarket.kz/health"),
    ("Dina сайт", "https://dinamarket.kz/ru/catalog"),
    ("Magnum", "https://magnum.kz/catalog?city=aktobe"),
    ("Anvar", "https://www.anvar.kz/stock/catalogs/"),
    ("DuckDuckGo", "https://html.duckduckgo.com/html/?q=test"),
]


def run_doctor() -> int:
    console = Console()
    console.print(Panel(
        f"Python {sys.version.split()[0]}  •  {platform.platform()}",
        title="Energy Scout — диагностика", expand=False,
    ))

    table = Table(header_style="bold cyan", expand=False)
    table.add_column("Пакет")
    table.add_column("Статус")
    table.add_column("Версия / примечание")
    for module, note in PACKAGE_CHECKS:
        try:
            imported = importlib.import_module(module)
            version = getattr(imported, "__version__", "установлен")
            table.add_row(module, "[green]OK[/]", f"{version} — {note}")
        except ImportError:
            optional = "опциональн" in note
            status = "[yellow]нет[/]" if optional else "[red]НЕТ[/]"
            table.add_row(module, status, note)
    console.print(table)

    net = Table(header_style="bold cyan", expand=False)
    net.add_column("Источник")
    net.add_column("Доступность")
    try:
        import httpx
    except ImportError:
        console.print("[red]httpx не установлен — сетевые проверки пропущены.[/]")
        return 1

    for name, url in SITE_CHECKS:
        try:
            resp = httpx.get(url, timeout=10, follow_redirects=True,
                             headers={"User-Agent": "EnergyScout/1.0 (doctor)"})
            net.add_row(name, f"[green]HTTP {resp.status_code}[/]", url)
        except Exception as exc:  # noqa: BLE001 — диагностика показывает любую ошибку
            net.add_row(name, "[red]недоступен[/]", f"{type(exc).__name__}: {exc}")
    console.print(net)
    console.print(
        "[dim]Если пакет помечен «нет», поставьте его командой того же интерпретатора:\n"
        "python3 -m pip install openpyxl lxml PyYAML[/]"
    )
    return 0
