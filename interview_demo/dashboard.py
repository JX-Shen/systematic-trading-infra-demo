from __future__ import annotations

import shutil
from dataclasses import dataclass, field

from rich import box
from rich.console import Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from interview_demo.models import Bar, Signal

SIGNAL_MODEL_COLUMNS = ("dummy1_momentum", "dummy2_meanrev", "dummy3_reversal")
VISIBLE_HISTORY_ROWS = 12
TABLE_PANEL_HEIGHT = VISIBLE_HISTORY_ROWS + 5
CORE_TABLE_HEIGHT = TABLE_PANEL_HEIGHT
HEADER_HEIGHT = 5
EVENT_BUS_TABLE_OVERHEAD = 5
MIN_EVENT_BUS_ROWS = 6


@dataclass
class DashboardState:
    source: str = "-"
    bars_count: int = 0
    start: str = "-"
    end: str = "-"
    current_bar: Bar | None = None
    market_rows: list[tuple[str, str, str, str, str, str, str, str]] = field(default_factory=list)
    signal_rows: list[tuple[str, str, str, str, str]] = field(default_factory=list)
    portfolio_rows: list[tuple[str, str, str, str]] = field(default_factory=list)
    activity_rows: list[tuple[str, str]] = field(default_factory=list)
    status: str = "Ready"
    recon_rows: list[tuple[str, str, str, str, str, str, str, str]] = field(default_factory=list)
    metric_rows: list[tuple[str, str]] = field(default_factory=list)


class DemoDashboard:
    """Fixed-position Rich dashboard for the interview demo."""

    def __init__(self, refresh_per_second: int = 12) -> None:
        self.state = DashboardState()
        self.refresh_per_second = refresh_per_second
        self._live: Live | None = None

    def __enter__(self) -> "DemoDashboard":
        self._live = Live(
            self.render(),
            refresh_per_second=self.refresh_per_second,
            screen=True,
            transient=False,
        )
        self._live.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._live is not None:
            self._live.__exit__(exc_type, exc, tb)
            self._live = None

    def refresh(self) -> None:
        if self._live is not None:
            self._live.update(self.render(), refresh=True)

    def set_source(self, source: str, bars_count: int, first: Bar, last: Bar) -> None:
        self.state.source = source
        self.state.bars_count = bars_count
        self.state.start = first.timestamp.strftime("%Y-%m-%d %H:%M")
        self.state.end = last.timestamp.strftime("%Y-%m-%d %H:%M")
        self.add_activity("data", f"Loaded {bars_count} bars for {first.symbol}")
        self.refresh()

    def set_status(self, status: str) -> None:
        self.state.status = status
        self.refresh()

    def set_market_bar(self, bar: Bar, portfolio_row: tuple[str, str, str, str] | None = None) -> None:
        if self.state.current_bar is not None:
            self.complete_market_bar(self.state.current_bar, refresh=False)
        self.state.current_bar = bar
        cycle_time = bar.timestamp.strftime("%H:%M")
        self.state.market_rows.append(
            (
                cycle_time,
                bar.symbol,
                f"{bar.open:.2f}",
                "...",
                "...",
                "...",
                "...",
                "...",
            )
        )
        self.state.market_rows = self.state.market_rows[-VISIBLE_HISTORY_ROWS:]
        self.state.signal_rows.append((cycle_time, "...", "...", "...", "..."))
        self.state.signal_rows = self.state.signal_rows[-VISIBLE_HISTORY_ROWS:]
        self.state.portfolio_rows.append(portfolio_row or (cycle_time, "0", "0", "-"))
        self.state.portfolio_rows = self.state.portfolio_rows[-VISIBLE_HISTORY_ROWS:]
        self.add_activity("market", f"{bar.timestamp:%H:%M} open={bar.open:.2f}")
        self.refresh()

    def complete_market_bar(self, bar: Bar, refresh: bool = True) -> None:
        cycle_time = bar.timestamp.strftime("%H:%M")
        for index in range(len(self.state.market_rows) - 1, -1, -1):
            row = self.state.market_rows[index]
            if row[0] != cycle_time:
                continue
            self.state.market_rows[index] = (
                cycle_time,
                bar.symbol,
                f"{bar.open:.2f}",
                f"{bar.high:.2f}",
                f"{bar.low:.2f}",
                f"{bar.close:.2f}",
                f"{bar.volume:,}",
                row[-1],
            )
            self.add_activity("market", f"{bar.timestamp:%H:%M} close={bar.close:.2f}")
            if refresh:
                self.refresh()
            return

    def set_signals(self, bar: Bar, signals: list[Signal], signal_positions: dict[str, int]) -> None:
        if self.state.market_rows:
            last = self.state.market_rows[-1]
            self.state.market_rows[-1] = (*last[:-1], str(len(signals)))
        self._upsert_signal_row(
            (
                bar.timestamp.strftime("%H:%M"),
                self._format_signal_target(signal_positions.get("dummy1_momentum", 0)),
                self._format_signal_target(signal_positions.get("dummy2_meanrev", 0)),
                self._format_signal_target(signal_positions.get("dummy3_reversal", 0)),
                self._format_qty(sum(signal_positions.values())),
            )
        )
        for signal in signals:
            self.add_activity("signal", f"{bar.timestamp:%H:%M} {signal.strategy_id} {signal.side.value.upper()}: {signal.reason}")
        if not signals:
            self.add_activity("signal", f"{bar.timestamp:%H:%M} none")
        self.refresh()

    def set_portfolio_row(self, row: tuple[str, str, str, str]) -> None:
        if self.state.portfolio_rows and self.state.portfolio_rows[-1][0] == row[0]:
            self.state.portfolio_rows[-1] = row
        else:
            self.state.portfolio_rows.append(row)
        self.state.portfolio_rows = self.state.portfolio_rows[-VISIBLE_HISTORY_ROWS:]
        self.refresh()

    def _upsert_signal_row(self, row: tuple[str, str, str, str, str]) -> None:
        if self.state.signal_rows and self.state.signal_rows[-1][0] == row[0]:
            self.state.signal_rows[-1] = row
        else:
            self.state.signal_rows.append(row)
        self.state.signal_rows = self.state.signal_rows[-VISIBLE_HISTORY_ROWS:]

    def set_reconciliation_row(self, row: tuple[str, str, str, str, str, str, str, str]) -> None:
        if self.state.recon_rows and self.state.recon_rows[-1][0] == row[0]:
            self.state.recon_rows[-1] = row
        else:
            self.state.recon_rows.append(row)
        self.state.recon_rows = self.state.recon_rows[-VISIBLE_HISTORY_ROWS:]
        self.refresh()

    def set_metrics(self, rows: list[tuple[str, str]]) -> None:
        self.state.metric_rows = rows
        self.refresh()

    def add_activity(self, area: str, message: str) -> None:
        self.state.activity_rows.append((area, message))
        self.state.activity_rows = self.state.activity_rows[-100:]

    def render(self) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=5),
            Layout(name="main", size=CORE_TABLE_HEIGHT),
            Layout(name="bottom", ratio=1),
        )
        layout["main"].split_row(
            Layout(name="market", ratio=4),
            Layout(name="signals", ratio=3),
            Layout(name="workspace", ratio=4),
        )
        layout["bottom"].split_row(
            Layout(name="event_bus", ratio=5),
            Layout(name="recon_pnl", ratio=4),
        )
        layout["header"].update(self._header_panel())
        layout["market"].update(self._market_panel())
        layout["signals"].update(self._signals_panel())
        layout["workspace"].update(self._portfolio_panel())
        layout["event_bus"].update(self._activity_panel())
        layout["recon_pnl"].update(self._recon_pnl_panel())
        return layout

    def _header_panel(self) -> Panel:
        grid = Table.grid(expand=True)
        grid.add_column(ratio=1)
        grid.add_column(ratio=1)
        grid.add_column(ratio=1)
        grid.add_row(
            Text("Interview Trading Demo", style="bold cyan"),
            Text(f"Bars: {self.state.bars_count} | {self.state.start} -> {self.state.end}", style="white"),
            Text(self.state.status, style="bold yellow"),
        )
        grid.add_row(
            Text(f"Source: {self.state.source}", style="dim"),
            Text("Market replay + portfolio workspace", style="dim"),
            Text("Fixed dashboard mode", style="dim"),
        )
        return Panel(grid, border_style="cyan")

    def _market_panel(self) -> Panel:
        table = Table(expand=True, box=box.SIMPLE_HEAVY)
        table.add_column("Time", style="cyan", no_wrap=True)
        table.add_column("Symbol", no_wrap=True)
        table.add_column("Open", justify="right")
        table.add_column("High", justify="right")
        table.add_column("Low", justify="right")
        table.add_column("Close", justify="right")
        table.add_column("Vol", justify="right")
        table.add_column("Sig", justify="right")
        rows = self.state.market_rows or [("-", "-", "-", "-", "-", "-", "-", "-")]
        for row in self._pad_rows(rows, 8):
            table.add_row(*row)
        return Panel(table, title="Market (1h / 12 bars)", border_style="blue")

    def _signals_panel(self) -> Panel:
        table = Table(expand=True, box=box.SIMPLE_HEAVY)
        table.add_column("Time", style="cyan", no_wrap=True)
        table.add_column("Momentum", justify="center", no_wrap=True)
        table.add_column("MeanRev", justify="center", no_wrap=True)
        table.add_column("Reversal", justify="center", no_wrap=True)
        table.add_column("Agg", justify="right")
        rows = self.state.signal_rows or [("-", "-", "-", "-", "-")]
        for row in self._pad_rows(rows, 5):
            table.add_row(*row)
        return Panel(table, title="Signal Targets (1h / 12 bars)", border_style="green")

    @staticmethod
    def _format_qty(qty: int) -> str:
        if qty > 0:
            return f"[green]+{qty}[/green]"
        if qty < 0:
            return f"[red]{qty}[/red]"
        return "0"

    @staticmethod
    def _format_signal_target(qty: int) -> str:
        if qty > 0:
            return "[green]BUY[/green]"
        if qty < 0:
            return "[red]SELL[/red]"
        return "[yellow]FLAT[/yellow]"

    def _portfolio_panel(self) -> Panel:
        table = Table(expand=True, box=box.SIMPLE_HEAVY)
        table.add_column("Time", style="cyan", no_wrap=True, width=5)
        table.add_column("Target", justify="right", no_wrap=True)
        table.add_column("Broker", justify="right", no_wrap=True)
        table.add_column("Order Placed", no_wrap=True)
        rows = self.state.portfolio_rows or [("-", "-", "-", "-")]
        for row in self._pad_rows(rows, 4):
            table.add_row(*row)
        return Panel(table, title="Portfolio Workspace (Target | Broker | Order)", border_style="magenta")

    def _activity_panel(self) -> Panel:
        table = Table(expand=True, box=box.SIMPLE_HEAVY)
        table.add_column("Area", style="cyan", no_wrap=True, width=12)
        table.add_column("Event")
        rows = self._activity_rows()
        for area, message in rows:
            table.add_row(area, message)
        return Panel(table, title="Event Bus", border_style="white")

    def _activity_rows(self) -> list[tuple[str, str]]:
        rows = list(self.state.activity_rows)
        rows = rows or [("-", "No activity yet")]
        return self._tail_activity_rows(rows, self._visible_activity_lines())

    def _visible_activity_lines(self) -> int:
        terminal_rows = shutil.get_terminal_size(fallback=(120, 40)).lines
        event_bus_height = terminal_rows - HEADER_HEIGHT - CORE_TABLE_HEIGHT
        visible_rows = event_bus_height - EVENT_BUS_TABLE_OVERHEAD
        return max(MIN_EVENT_BUS_ROWS, visible_rows)

    @staticmethod
    def _tail_activity_rows(rows: list[tuple[str, str]], line_budget: int) -> list[tuple[str, str]]:
        selected: list[tuple[str, str]] = []
        remaining = line_budget
        for row in reversed(rows):
            row_height = max(1, row[1].count("\n") + 1)
            if selected and row_height > remaining:
                break
            selected.append(row)
            remaining -= row_height
            if remaining <= 0:
                break
        return list(reversed(selected))

    def _recon_pnl_panel(self) -> Panel:
        parts = []
        if self.state.recon_rows:
            recon = Table(title="5-minute Recon / PnL", expand=True, box=box.SIMPLE_HEAVY)
            recon.add_column("Time", style="cyan", no_wrap=True)
            recon.add_column("Target", justify="right", no_wrap=True)
            recon.add_column("Broker", justify="right", no_wrap=True)
            recon.add_column("Diff", justify="right", no_wrap=True)
            recon.add_column("Status", no_wrap=True)
            recon.add_column("Mark", justify="right", no_wrap=True)
            recon.add_column("PnL", justify="right", no_wrap=True)
            recon.add_column("DD", justify="right", no_wrap=True)
            for row in self._pad_rows(self.state.recon_rows, 8):
                recon.add_row(*row)
            parts.append(recon)

        if self.state.metric_rows:
            metrics = Table(title="Final Metrics", expand=True, box=box.SIMPLE_HEAVY)
            metrics.add_column("Metric", style="cyan")
            metrics.add_column("Value", justify="right")
            for row in self.state.metric_rows:
                metrics.add_row(*row)
            parts.append(metrics)

        if not parts:
            parts.append(Text("Reconciliation and PnL appear here after replay.", style="dim"))
        return Panel(Group(*parts), title="Recon / PnL", border_style="yellow")

    @staticmethod
    def _pad_rows(rows: list[tuple[str, ...]], column_count: int) -> list[tuple[str, ...]]:
        padded = list(rows[-VISIBLE_HISTORY_ROWS:])
        blank = tuple("" for _ in range(column_count))
        while len(padded) < VISIBLE_HISTORY_ROWS:
            padded.append(blank)
        return padded
