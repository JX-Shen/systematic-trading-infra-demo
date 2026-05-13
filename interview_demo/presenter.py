from __future__ import annotations

from typing import Iterable

from interview_demo.models import Bar, OrderIntent, PositionIntent, Signal
from interview_demo.reconciliation import ReconciliationReport


class Presenter:
    def __init__(self) -> None:
        from rich import box
        from rich.console import Console
        from rich.panel import Panel
        from rich.rule import Rule
        from rich.table import Table
        from rich.text import Text

        self.box = box
        self.console = Console()
        self.Panel = Panel
        self.Rule = Rule
        self.Table = Table
        self.Text = Text

    def section(self, title: str) -> None:
        self.console.print(self.Rule(f"[bold cyan]{title}[/bold cyan]"))

    def step(self, label: str) -> None:
        self.console.print(f"\n[bold yellow]step[/bold yellow] {label}")

    def header(self, source: str, bars_count: int, first: Bar, last: Bar) -> None:
        table = self.Table.grid(padding=(0, 2))
        table.add_column(style="bold cyan")
        table.add_column()
        table.add_row("source", source)
        table.add_row("bars", str(bars_count))
        table.add_row("symbol", first.symbol)
        table.add_row("start", first.timestamp.strftime("%Y-%m-%d %H:%M"))
        table.add_row("end", last.timestamp.strftime("%Y-%m-%d %H:%M"))
        self.console.print(self.Panel(table, title="Data Source", border_style="cyan"))

    def cycle(self, bar: Bar, signals_count: int) -> None:
        signal_style = "green" if signals_count else "dim"
        table = self.Table(title="Market", box=self.box.SIMPLE_HEAVY)
        table.add_column("Time", style="cyan", no_wrap=True)
        table.add_column("Symbol", no_wrap=True)
        table.add_column("Open", justify="right")
        table.add_column("High", justify="right")
        table.add_column("Low", justify="right")
        table.add_column("Close", justify="right")
        table.add_column("Volume", justify="right")
        table.add_column("Signals", justify="right")
        table.add_row(
            bar.timestamp.strftime("%Y-%m-%d %H:%M"),
            bar.symbol,
            f"{bar.open:.2f}",
            f"{bar.high:.2f}",
            f"{bar.low:.2f}",
            f"{bar.close:.2f}",
            f"{bar.volume:,}",
            f"[{signal_style}]{signals_count}[/{signal_style}]",
        )
        self.console.print(table)

    def no_signal(self) -> None:
        self.workspace(
            [
                ("Signals", "No new signal"),
                ("Portfolio", "No position change"),
                ("Execution", "No provider action"),
            ]
        )

    def signals(self, bar: Bar, signals: Iterable[Signal]) -> None:
        table = self.Table(title=f"Signals at {bar.timestamp:%H:%M}", box=self.box.SIMPLE_HEAVY)
        table.add_column("Strategy", style="cyan", no_wrap=True)
        table.add_column("Side", justify="center")
        table.add_column("Reason")
        for signal in signals:
            style = "green" if signal.target_qty > 0 else "red" if signal.target_qty < 0 else "yellow"
            table.add_row(signal.strategy_id, f"[{style}]{signal.side.value.upper()}[/{style}]", signal.reason)
        self.console.print(table)

    def portfolio_intents(self, intents: list[PositionIntent], net_qty: int) -> None:
        table = self.Table(title="Portfolio Lifecycle + Netting", box=self.box.SIMPLE_HEAVY)
        table.add_column("Strategy", style="cyan", no_wrap=True)
        table.add_column("From", justify="right")
        table.add_column("To", justify="right")
        table.add_column("Delta", justify="right")
        for intent in intents:
            table.add_row(
                intent.strategy_id,
                f"{intent.from_qty:+d}",
                f"{intent.to_qty:+d}",
                f"{intent.delta_qty:+d}",
            )
        table.caption = f"net provider order qty = {net_qty:+d}"
        self.console.print(table)

    def workspace(self, rows: list[tuple[str, ...]]) -> None:
        table = self.Table(title="Workspace", box=self.box.SIMPLE_HEAVY)
        table.add_column("Area", style="cyan", no_wrap=True)
        table.add_column("Item", no_wrap=True)
        table.add_column("State")
        for row in rows:
            if len(row) == 2:
                area, state = row
                table.add_row(area, "-", state)
            else:
                area, item, state = row[:3]
                table.add_row(area, item, state)
        self.console.print(table)

    def no_position_change(self) -> None:
        self.console.print("[yellow]portfolio[/yellow] signals produced no position change")

    def internal_netting(self) -> None:
        self.console.print(
            self.Panel(
                "[bold magenta]Internal netting only[/bold magenta]\nNo provider action required.",
                title="Portfolio Decision",
                border_style="magenta",
            )
        )

    def execution_fill(self, intent: OrderIntent, fill_price: float) -> None:
        table = self.Table(title="Execution", box=self.box.SIMPLE_HEAVY)
        table.add_column("Order ID", style="cyan")
        table.add_column("Qty", justify="right")
        table.add_column("State Path")
        table.add_column("Fill", justify="right")
        table.add_row(
            intent.order_id,
            f"{intent.qty:+d}",
            "[dim]PENDING[/dim] -> SUBMITTED -> WORKING -> [bold green]FILLED[/bold green]",
            f"{fill_price:.2f}",
        )
        self.console.print(table)

    def execution_reject(self, intent: OrderIntent, reason: str | None) -> None:
        table = self.Table(title="Execution", box=self.box.SIMPLE_HEAVY)
        table.add_column("Order ID", style="cyan")
        table.add_column("Qty", justify="right")
        table.add_column("State Path")
        table.add_column("Reason")
        table.add_row(
            intent.order_id,
            f"{intent.qty:+d}",
            "[dim]PENDING[/dim] -> SUBMITTED -> WORKING -> [bold red]REJECTED[/bold red]",
            reason or "-",
        )
        self.console.print(table)

    def reconciliation(self, result: ReconciliationReport) -> None:
        status = "[bold green]PASS[/bold green]" if result.passed else "[bold red]FAIL[/bold red]"
        table = self.Table(title="Reconciliation", box=self.box.SIMPLE_HEAVY)
        table.add_column("Status")
        table.add_column("Target Pos", justify="right")
        table.add_column("Provider Pos", justify="right")
        table.add_column("Diff", justify="right")
        table.add_column("Suspected Source")
        table.add_column("Message")
        table.add_row(
            status,
            f"{result.target_position:+d}",
            f"{result.provider_state_position:+d}",
            f"{result.diff:+d}",
            result.suspected_source,
            result.message,
        )
        if result.related_event_ids:
            table.caption = f"related event ids: {', '.join(str(event_id) for event_id in result.related_event_ids)}"
        self.console.print(table)

    def metrics(self, rows: list[tuple[str, str]]) -> None:
        table = self.Table(title="Performance Output", box=self.box.SIMPLE_HEAVY)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")
        for name, value in rows:
            table.add_row(name, value)
        self.console.print(table)

    def line(self, message: str) -> None:
        self.console.print(message)


presenter = Presenter()
