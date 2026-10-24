"""Командная строка Energy Scout."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table

from .config import load_config
from .http import FixtureClient, HttpClient
from .pipeline import run_pipeline
from .report.console import print_report
from .report.files import write_csv, write_html, write_xlsx
from .report.history import PriceHistory
from .sources.dina import DinaSource

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="energy-scout",
        description="Поиск энергетиков (Monster и др.) по магазинам Актобе: цены, редкость, наличие.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--config", default="config.yaml", help="YAML-конфиг (необязательно)")
    parser.add_argument("--demo", action="store_true", help="работа на офлайн-фикстурах, без интернета")
    parser.add_argument("--city", help="город поиска, по умолчанию из конфига (Актобе)")
    parser.add_argument("--query", action="append", default=[],
                        help="доп. поисковое слово, можно повторять, напр. --query monster")
    parser.add_argument("--source", help="источники через запятую: dina,magnum,anvar,web")
    parser.add_argument("--max-price", type=int, help="максимальная цена за единицу, тенге")
    parser.add_argument("--rare-only", action="store_true", help="только редкие и эксклюзивные")
    parser.add_argument("--in-stock-only", action="store_true", help="отбросить товары не в наличии")
    parser.add_argument("--all-shops", action="store_true",
                        help="сканировать все магазины города в Dina, а не один")
    parser.add_argument("--no-web", action="store_true", help="не использовать веб-поиск")
    parser.add_argument("--no-history", action="store_true", help="не писать историю цен в SQLite")
    parser.add_argument("--out", default="reports", help="папка отчётов")
    parser.add_argument("--list-shops", action="store_true",
                        help="показать магазины города в API Dina и выйти")
    parser.add_argument("--compact", action="store_true",
                        help="узкая таблица в консоли (5 колонок) — удобно на телефоне")
    parser.add_argument("--doctor", action="store_true",
                        help="диагностика: версии пакетов и доступность сайтов, затем выход")
    return parser.parse_args(argv)


def _apply_overrides(config, args: argparse.Namespace) -> None:
    if args.city:
        config.city = args.city
    config.extra_queries = args.query
    config.max_price = args.max_price
    config.rare_only = args.rare_only
    config.in_stock_only = args.in_stock_only
    config.all_shops = args.all_shops
    config.output_dir = args.out
    if args.no_web:
        config.sources["web"] = False
    if args.no_history:
        config.use_history = False
    config.compact = args.compact
    if args.source:
        wanted = {s.strip().lower() for s in args.source.split(",") if s.strip()}
        for code in config.sources:
            config.sources[code] = code in wanted


def list_shops(client, config) -> int:
    console = Console()
    source = DinaSource(client, config)
    shops = source.list_city_shops()
    if not shops:
        console.print(f"[yellow]Магазины города {config.city} не найдены.[/]")
        return 1
    table = Table(header_style="bold cyan")
    table.add_column("ID")
    table.add_column("Магазин")
    table.add_column("Город")
    for shop in shops:
        table.add_row(shop["id"], shop["name"], shop["city"])
    console.print(table)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_config(args.config if Path(args.config).exists() else None)
    _apply_overrides(config, args)
    console = Console()

    if args.doctor:
        from .doctor import run_doctor
        return run_doctor()

    client = FixtureClient(FIXTURES_DIR) if args.demo else HttpClient(
        delay=config.delay_seconds,
        timeout=config.timeout_seconds,
        max_retries=config.max_retries,
    )

    try:
        if args.list_shops:
            return list_shops(client, config)

        with client:
            report = run_pipeline(client, config)

        history = None
        price_changes: dict[int, int | None] = {}
        if config.use_history:
            history = PriceHistory(Path(config.output_dir) / "history.db")
            for product in report.products:
                price_changes[id(product)] = history.previous_price(product)
            history.save(report.products)

        print_report(report, config, price_changes)

        out_dir = Path(config.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = _unique_path(out_dir / f"energy_scout_{stamp}.csv")
        xlsx_path = _unique_path(out_dir / f"energy_scout_{stamp}.xlsx")
        html_path = out_dir / "latest_report.html"
        write_csv(csv_path, report.products)
        try:
            write_xlsx(xlsx_path, report)
        except ImportError as exc:
            console.print(f"[yellow]{exc}[/]")
            xlsx_path = None
        write_html(html_path, report.products, config.city)
        if history:
            history.close()

        console.print(PanelReport(csv_path, xlsx_path, html_path))
        if report.errors:
            console.print("[yellow]Часть источников завершилась с ошибками — детали выше.[/]")
        return 0
    except KeyboardInterrupt:
        console.print("\n[yellow]Прервано пользователем.[/]")
        return 130
    except Exception as exc:  # последний рубеж, чтобы пользователь увидел причину
        console.print(f"[red]Критическая ошибка: {exc}[/]")
        if args.demo:
            raise
        return 1
    finally:
        client.close()


def _unique_path(path: Path) -> Path:
    """Если файл за эту же секунду уже создан — добавляем суффикс _2, _3…"""
    if not path.exists():
        return path
    stem, suffix, parent = path.stem, path.suffix, path.parent
    counter = 2
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def PanelReport(csv_path: Path, xlsx_path: Path | None, html_path: Path):
    from rich.panel import Panel
    lines = [
        f"CSV:  [bold]{csv_path}[/]",
        f"XLSX: [bold]{xlsx_path}[/]" if xlsx_path else "XLSX: [yellow]пропущен (нет openpyxl)[/]",
        f"HTML: [bold]{html_path}[/]",
    ]
    return Panel("\n".join(lines), title="Отчёты сохранены", expand=False)


if __name__ == "__main__":
    sys.exit(main())
