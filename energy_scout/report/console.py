"""Красивый вывод результатов в терминал."""
from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..models import Product
from ..pipeline import RunReport

TIER_LABEL = {
    "exclusive": "[bold magenta]ЭКСКЛЮЗИВ[/]",
    "rare": "[bold yellow]РЕДКОЕ[/]",
    "ordinary": "обычный",
}


def print_report(report: RunReport, config, price_changes: dict[int, int | None]) -> None:
    console = Console()
    stats = report.stats()

    summary = (
        f"Найдено: [bold]{stats['total']}[/]  •  "
        f"эксклюзив: [magenta]{stats['exclusive']}[/]  •  "
        f"редкое: [yellow]{stats['rare']}[/]  •  "
        f"с ценой: {stats['with_price']}  •  "
        f"в наличии: {stats['in_stock']}"
    )
    console.print(Panel(summary, title=f"Energy Scout — {config.city}", expand=False))

    for result in report.source_results:
        status = "[green]OK[/]" if result.ok else f"[red]{len(result.errors)} ошиб.[/]"
        shops = ", ".join(result.shops) if result.shops else "—"
        console.print(f"[bold]{result.label}[/] — {status} — товаров: {len(result.products)} — {shops}")
        for err in result.errors:
            console.print(f"  [red]✗ {err}[/]")

    if not report.products:
        console.print("[yellow]Товары не найдены. Проверьте интернет-соединение или放宽 фильтры.[/]")
        return

    table = Table(show_lines=False, expand=False, header_style="bold cyan")
    table.add_column("#", width=3, no_wrap=True)
    table.add_column("Редкость", width=9, no_wrap=True)
    table.add_column("Товар", max_width=46, min_width=12, overflow="fold")
    table.add_column("Магазин", max_width=22, min_width=10, overflow="fold")
    table.add_column("Цена, тг", justify="right", width=10, no_wrap=True)
    table.add_column("За литр", justify="right", width=8, no_wrap=True)
    table.add_column("Наличие", width=8, no_wrap=True)
    table.add_column("Δ цены", justify="right", width=7, no_wrap=True)

    for idx, product in enumerate(report.products, 1):
        table.add_row(*_row(idx, product, price_changes.get(id(product))))
    console.print(table)
    console.print("[dim]Δ цены — изменение относительно прошлого прогона (reports/history.db).[/]")


def _row(idx: int, p: Product, previous: int | None) -> tuple:
    if p.price is None:
        price = "[dim]нет[/]"
        per_l = "—"
    else:
        old = f" [dim]({p.old_price})[/]" if p.old_price else ""
        price = f"{p.price:,}{old}".replace(",", " ")
        per_l = f"{p.price_per_l:,}".replace(",", " ") if p.price_per_l else "—"

    if p.in_stock is True:
        stock = "[green]есть[/]"
    elif p.in_stock is False:
        stock = "[red]нет[/]"
    else:
        stock = "[dim]н/д[/]"

    if previous is None or p.price is None:
        delta = "—"
    elif previous == p.price:
        delta = "="
    elif previous > p.price:
        delta = f"[green]−{previous - p.price}[/]"
    else:
        delta = f"[red]+{p.price - previous}[/]"

    tags = f"\n[dim]{', '.join(p.tags[:3])}[/]" if p.tags else ""
    name = f"{p.name[:90]}{tags}"
    shop = (p.shop_name or "—")[:48]
    return (
        str(idx),
        TIER_LABEL.get(p.rarity_tier, p.rarity_tier),
        name,
        shop,
        price,
        per_l,
        stock,
        delta,
    )
