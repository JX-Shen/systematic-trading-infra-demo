from __future__ import annotations

import os
import sys
from datetime import datetime
from itertools import count
from typing import Callable

from interview_demo.data import load_march_brent_bars
from interview_demo.dashboard import DemoDashboard
from interview_demo.execution import MockBroker, OrderManager, OrderState
from interview_demo.models import Bar, Fill, OrderIntent, Signal, SignalSide, SYMBOL
from interview_demo.performance import max_drawdown, sharpe_like
from interview_demo.presenter import presenter
from interview_demo.portfolio import PortfolioManager
from interview_demo.reconciliation import reconcile_positions
from interview_demo.strategies import default_strategies


class Stepper:
    def __init__(self, enabled: bool, on_step: Callable[[str], None] | None = None) -> None:
        self.enabled = enabled
        self.finish = False
        self.run_cycle_id: object | None = None
        self.on_step = on_step

    def pause(self, label: str, cycle_id: object | None = None) -> None:
        if not self.enabled or self.finish:
            return
        if self.run_cycle_id is not None and cycle_id == self.run_cycle_id:
            return
        if self.run_cycle_id is not None and cycle_id != self.run_cycle_id:
            self.run_cycle_id = None

        if self.on_step is not None:
            self.on_step(label)
        else:
            presenter.step(label)
        key = self._read_key()
        if key == "\x1b":
            self.finish = True
        elif key in ("\n", "\r") and cycle_id is not None:
            self.run_cycle_id = cycle_id

    def _read_key(self) -> str:
        if not sys.stdin.isatty():
            input("Press Enter to continue...")
            return "\n"

        if os.name == "nt":
            return self._read_windows_key()
        return self._read_posix_key()

    def _read_windows_key(self) -> str:
        import msvcrt

        key = msvcrt.getwch()
        print()
        if key == "\x00" or key == "\xe0":
            msvcrt.getwch()
            return ""
        return key

    def _read_posix_key(self) -> str:
        import termios
        import tty

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            key = sys.stdin.read(1)
            print()
            return key
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def run_full_demo(step: bool = False) -> None:
    if step:
        _run_full_demo_dashboard()
        return

    stepper = Stepper(step)
    bars, source = load_march_brent_bars()
    strategies = default_strategies()
    portfolio = PortfolioManager()
    order_manager = OrderManager(MockBroker(slippage=0.02))
    order_ids = count(1)
    equity_curve: list[float] = []
    signal_count = 0

    presenter.section("FULL DEMO: March Brent C1 5-minute replay")
    presenter.header(source, len(bars), bars[0], bars[-1])
    stepper.pause("Data source loaded. Next: replay bars into strategies.")

    for bar in bars:
        signals = [signal for strategy in strategies if (signal := strategy.on_bar(bar))]
        cycle_id = bar.timestamp
        if step:
            presenter.cycle(bar, len(signals))
            stepper.pause("5-minute bar loaded.", cycle_id=cycle_id)
            if not signals:
                presenter.no_signal()
        if signals:
            stepper.pause(
                f"Signal event at {bar.timestamp:%Y-%m-%d %H:%M}. Next: show strategy output.",
                cycle_id=cycle_id,
            )
            signal_count += len(signals)
            if not step:
                presenter.cycle(bar, len(signals))
            presenter.signals(bar, signals)

            stepper.pause("Signals emitted. Next: portfolio lifecycle and netting.", cycle_id=cycle_id)
            intents = portfolio.build_intents(signals)
            if not intents:
                presenter.workspace(
                    [
                        ("Portfolio", "-", "Signals produced no position change"),
                        ("Execution", "-", "No broker action"),
                    ]
                )
            else:
                net_qty = sum(intent.delta_qty for intent in intents)

                if net_qty == 0:
                    stepper.pause(
                        "Net order quantity is zero. Next: apply internal netting without broker flow.",
                        cycle_id=cycle_id,
                    )
                    portfolio.apply_intents(intents, bar.close, "internal_netting")
                    presenter.workspace(
                        _intent_workspace_rows(intents)
                        + [
                            ("Netting", bar.symbol, f"Net broker order qty = {net_qty:+d}"),
                            ("Decision", "Internal", "No broker order required"),
                            ("Position", "Aggregate", f"{portfolio.aggregate_position:+d}"),
                        ]
                    )
                else:
                    stepper.pause(
                        "Net demand remains. Next: route order intent to mock execution.",
                        cycle_id=cycle_id,
                    )
                    order_intent = OrderIntent(
                        order_id=f"ORD-{next(order_ids):04d}",
                        symbol=bar.symbol,
                        qty=net_qty,
                        reference_price=bar.close,
                        reason="net portfolio demand",
                    )
                    order = order_manager.submit(order_intent)
                    if order.state == OrderState.FILLED and order.fill:
                        portfolio.apply_intents(intents, order.fill.price, "broker_fill")
                        execution_state = (
                            f"qty={order.intent.qty:+d} PENDING -> SUBMITTED -> WORKING -> [bold green]FILLED[/bold green] "
                            f"@ {order.fill.price:.2f}"
                        )
                    else:
                        execution_state = (
                            f"qty={order.intent.qty:+d} PENDING -> SUBMITTED -> WORKING -> [bold red]REJECTED[/bold red] "
                            f"({order.reject_reason})"
                        )
                    presenter.workspace(
                        _intent_workspace_rows(intents)
                        + [
                            ("Netting", bar.symbol, f"Net broker order qty = {net_qty:+d}"),
                            ("Execution", order.intent.order_id, execution_state),
                            ("Position", "Aggregate", f"{portfolio.aggregate_position:+d}"),
                        ]
                    )
                stepper.pause("State updated. Next: continue replay.", cycle_id=cycle_id)

        equity_curve.append(portfolio.total_pnl(bar.close))

    if signal_count == 0:
        raise RuntimeError("Demo data did not trigger any signals")
    if not order_manager.fills:
        raise RuntimeError("Demo data did not produce any broker fills")

    final_price = bars[-1].close
    result = reconcile_positions(portfolio.aggregate_position, order_manager.fills)

    stepper.pause("Replay complete. Next: reconciliation and performance output.")
    presenter.reconciliation(result)
    _print_metrics(portfolio, equity_curve, final_price)


def _run_full_demo_dashboard() -> None:
    bars, source = load_march_brent_bars()
    strategies = default_strategies()
    portfolio = PortfolioManager()
    order_manager = OrderManager(MockBroker(slippage=0.02))
    order_ids = count(1)
    equity_curve: list[float] = []
    signal_count = 0
    signal_positions = {
        "dummy1_momentum": 0,
        "dummy2_meanrev": 0,
        "dummy3_reversal": 0,
    }
    pending_recon_row: tuple[str, str, str, str, str, str, str, str] | None = None

    with DemoDashboard() as dashboard:
        stepper = Stepper(True, on_step=dashboard.set_status)
        dashboard.set_source(source, len(bars), bars[0], bars[-1])
        dashboard.set_status("Ready. Next: load the first 5-minute bar.")

        for bar in bars:
            cycle_id = bar.timestamp
            stepper.pause(
                f"Next: load {bar.timestamp:%H:%M} market open.",
                cycle_id=cycle_id,
            )
            cycle_time = bar.timestamp.strftime("%H:%M")
            dashboard.set_market_bar(
                bar,
                _portfolio_dashboard_row(
                    cycle_time,
                    theory_qty=sum(signal_positions.values()),
                    actual_qty=_broker_actual_position(order_manager),
                    order_state="-",
                ),
            )
            if pending_recon_row is not None:
                dashboard.set_reconciliation_row(pending_recon_row)
                pending_recon_row = None
            dashboard.set_reconciliation_row(
                _reconciliation_dashboard_row(
                    cycle_time,
                    theory_qty=sum(signal_positions.values()),
                    actual_qty=_broker_actual_position(order_manager),
                    mark_price=bar.open,
                    pnl=portfolio.total_pnl(bar.open),
                    equity_curve=equity_curve + [portfolio.total_pnl(bar.open)],
                )
            )
            stepper.pause(
                f"Next: evaluate signals for {bar.timestamp:%H:%M}.",
                cycle_id=cycle_id,
            )
            signals = [signal for strategy in strategies if (signal := strategy.on_bar(bar))]
            for signal in signals:
                signal_positions[signal.strategy_id] = signal.target_qty
            dashboard.set_signals(bar, signals, signal_positions)
            dashboard.set_portfolio_row(
                _portfolio_dashboard_row(
                    cycle_time,
                    theory_qty=sum(signal_positions.values()),
                    actual_qty=_broker_actual_position(order_manager),
                    order_state="-",
                )
            )
            dashboard.set_reconciliation_row(
                _reconciliation_dashboard_row(
                    cycle_time,
                    theory_qty=sum(signal_positions.values()),
                    actual_qty=_broker_actual_position(order_manager),
                    mark_price=bar.open,
                    pnl=portfolio.total_pnl(bar.open),
                    equity_curve=equity_curve + [portfolio.total_pnl(bar.open)],
                )
            )

            if signals:
                stepper.pause(
                    f"Next: apply portfolio lifecycle for {bar.timestamp:%H:%M}.",
                    cycle_id=cycle_id,
                )
                signal_count += len(signals)
                intents = portfolio.build_intents(signals)
                if not intents:
                    dashboard.add_activity("portfolio", f"{cycle_time} signal produced no position change")
                else:
                    net_qty = sum(intent.delta_qty for intent in intents)
                    if net_qty == 0:
                        stepper.pause(
                            "Net order quantity is zero. Next: apply internal netting without broker flow.",
                            cycle_id=cycle_id,
                        )
                        portfolio.apply_intents(intents, bar.close, "internal_netting")
                        dashboard.set_portfolio_row(
                            _portfolio_dashboard_row(
                                cycle_time,
                                theory_qty=sum(signal_positions.values()),
                                actual_qty=_broker_actual_position(order_manager),
                                order_state="internal net",
                            )
                        )
                        dashboard.set_reconciliation_row(
                            _reconciliation_dashboard_row(
                                cycle_time,
                                theory_qty=sum(signal_positions.values()),
                                actual_qty=_broker_actual_position(order_manager),
                                mark_price=bar.open,
                                pnl=portfolio.total_pnl(bar.open),
                                equity_curve=equity_curve + [portfolio.total_pnl(bar.open)],
                            )
                        )
                        _add_portfolio_transition_activity(dashboard, cycle_time, intents)
                        dashboard.add_activity("netting", f"{cycle_time} net {net_qty:+d}; internal match, broker skipped")
                    else:
                        stepper.pause(
                            "Net demand remains. Next: route order intent to mock execution.",
                            cycle_id=cycle_id,
                        )
                        order_intent = OrderIntent(
                            order_id=f"ORD-{next(order_ids):04d}",
                            symbol=bar.symbol,
                            qty=net_qty,
                            reference_price=bar.close,
                            reason="net portfolio demand",
                        )
                        order = order_manager.submit(order_intent)
                        if order.state == OrderState.FILLED and order.fill:
                            portfolio.apply_intents(intents, order.fill.price, "broker_fill")
                            order_state = f"{order.intent.order_id} {order.intent.qty:+d} FILLED"
                            dashboard.add_activity(
                                "execution",
                                f"{cycle_time} {order.intent.order_id} {order.intent.qty:+d} filled @ {order.fill.price:.2f}",
                            )
                        else:
                            order_state = f"{order.intent.order_id} {order.intent.qty:+d} REJECT"
                            dashboard.add_activity(
                                "execution",
                                f"{cycle_time} {order.intent.order_id} {order.intent.qty:+d} rejected",
                            )
                        dashboard.add_activity("netting", f"{cycle_time} net broker order qty {net_qty:+d}")
                        dashboard.set_portfolio_row(
                            _portfolio_dashboard_row(
                                cycle_time,
                                theory_qty=sum(signal_positions.values()),
                                actual_qty=_broker_actual_position(order_manager),
                                order_state=order_state,
                            )
                        )
                        dashboard.set_reconciliation_row(
                            _reconciliation_dashboard_row(
                                cycle_time,
                                theory_qty=sum(signal_positions.values()),
                                actual_qty=_broker_actual_position(order_manager),
                                mark_price=bar.open,
                                pnl=portfolio.total_pnl(bar.open),
                                equity_curve=equity_curve + [portfolio.total_pnl(bar.open)],
                            )
                        )
                        _add_portfolio_transition_activity(dashboard, cycle_time, intents)

            cycle_pnl = portfolio.total_pnl(bar.close)
            pending_recon_row = _reconciliation_dashboard_row(
                cycle_time,
                theory_qty=sum(signal_positions.values()),
                actual_qty=_broker_actual_position(order_manager),
                mark_price=bar.close,
                pnl=cycle_pnl,
                equity_curve=equity_curve + [cycle_pnl],
            )
            equity_curve.append(cycle_pnl)

        if signal_count == 0:
            raise RuntimeError("Demo data did not trigger any signals")
        if not order_manager.fills:
            raise RuntimeError("Demo data did not produce any broker fills")

        final_price = bars[-1].close
        result = reconcile_positions(portfolio.aggregate_position, order_manager.fills)
        stepper.pause("Next: run reconciliation and performance summary.")
        if pending_recon_row is not None:
            dashboard.complete_market_bar(bars[-1])
            dashboard.set_reconciliation_row(pending_recon_row)
        dashboard.add_activity("recon", result.message)
        dashboard.set_metrics(_metric_rows(portfolio, equity_curve, final_price))
        dashboard.set_status("Replay complete. Reconciliation and metrics are ready.")
        stepper.pause("Replay complete. Press Esc to leave dashboard.")


def run_market_signal_scenario(step: bool = False) -> None:
    stepper = Stepper(step)
    bars, source = load_march_brent_bars()
    strategies = default_strategies()
    total = 0

    presenter.section("SCENARIO: market data -> signals")
    presenter.header(source, len(bars), bars[0], bars[-1])
    stepper.pause("Market data loaded. Next: emit bars into strategies.")
    for bar in bars:
        for strategy in strategies:
            signal = strategy.on_bar(bar)
            if signal:
                total += 1
                presenter.cycle(bar, 1)
                presenter.signals(bar, [signal])
                stepper.pause("Signal emitted. Next: continue market replay.")
    presenter.line(f"[bold]summary[/bold] total_signals={total}")
    if total == 0:
        raise RuntimeError("Market-signal scenario produced no signals")


def run_netting_scenario(step: bool = False) -> None:
    stepper = Stepper(step)
    portfolio = PortfolioManager()
    price = 82.50
    signals = [
        Signal("strategy_A", SYMBOL, SignalSide.BUY, "manual netting scenario"),
        Signal("strategy_B", SYMBOL, SignalSide.SELL, "manual netting scenario"),
    ]

    presenter.section("SCENARIO: cross-strategy netting")
    presenter.cycle(
        Bar(
            timestamp=datetime(2026, 3, 2, 9, 20),
            symbol=SYMBOL,
            open=price,
            high=price,
            low=price,
            close=price,
            volume=0,
        ),
        len(signals),
    )
    presenter.signals(
        Bar(
            timestamp=datetime(2026, 3, 2, 9, 20),
            symbol=SYMBOL,
            open=price,
            high=price,
            low=price,
            close=price,
            volume=0,
        ),
        signals,
    )
    stepper.pause("Opposing strategy signals created. Next: portfolio builds intents.")

    intents = portfolio.build_intents(signals)
    net_qty = sum(intent.delta_qty for intent in intents)
    stepper.pause("Net quantity computed. Next: apply internal netting.")

    if net_qty == 0:
        portfolio.apply_intents(intents, price, "internal_netting")
    position_text = "; ".join(
        f"{strategy_id} qty={position.qty:+d} avg={position.avg_price:.2f}"
        for strategy_id, position in sorted(portfolio.positions.items())
    )
    presenter.workspace(
        _intent_workspace_rows(intents)
        + [
            ("Netting", SYMBOL, f"Net broker order qty = {net_qty:+d}"),
            ("Decision", "Internal", "No broker order required"),
            ("Positions", "Strategy-level", position_text),
        ]
    )


def run_execution_scenario(step: bool = False) -> None:
    stepper = Stepper(step)
    broker = MockBroker(slippage=0.02)
    order_manager = OrderManager(broker)

    presenter.section("SCENARIO: execution order state machine")
    accepted = OrderIntent("ORD-ACCEPT", SYMBOL, +1, 82.40, "accepted path")
    stepper.pause("Accepted order intent prepared. Next: submit to mock broker.")
    accepted_order = order_manager.submit(accepted)
    _print_order(accepted_order)

    broker.reject_next = True
    rejected = OrderIntent("ORD-REJECT", SYMBOL, -1, 82.35, "reject path")
    stepper.pause("Reject path prepared. Next: submit and show explicit rejected state.")
    rejected_order = order_manager.submit(rejected)
    _print_order(rejected_order)


def run_reconciliation_scenario(step: bool = False) -> None:
    stepper = Stepper(step)
    fills = [
        Fill("ORD-0001", SYMBOL, +1, 82.42, "mock_broker"),
        Fill("ORD-0002", SYMBOL, -1, 82.90, "mock_broker"),
        Fill("ORD-0003", SYMBOL, +1, 83.00, "mock_broker"),
    ]

    presenter.section("SCENARIO: reconciliation")
    stepper.pause("Broker fill log prepared. Next: run passing reconciliation.")
    passing = reconcile_positions(+1, fills)
    presenter.reconciliation(passing)

    stepper.pause("Passing case shown. Next: run deliberate mismatch.")
    mismatch = reconcile_positions(0, fills)
    presenter.reconciliation(mismatch)


def _print_metrics(portfolio: PortfolioManager, equity_curve: list[float], final_price: float) -> None:
    presenter.metrics(_metric_rows(portfolio, equity_curve, final_price))


def _metric_rows(portfolio: PortfolioManager, equity_curve: list[float], final_price: float) -> list[tuple[str, str]]:
    rows = [
        ("total_pnl", f"{portfolio.total_pnl(final_price):,.2f}"),
        ("max_drawdown", f"{max_drawdown(equity_curve):,.2f}"),
        ("sharpe_like", f"{sharpe_like(equity_curve):.2f}"),
        ("total_strategy_trades", str(portfolio.total_trades)),
        ("closed_trades", str(portfolio.closed_trades)),
        ("win_rate", f"{portfolio.win_rate:.1%}"),
    ]
    for strategy_id, pnl in portfolio.pnl_by_strategy(final_price).items():
        rows.append((f"{strategy_id}_pnl", f"{pnl:,.2f}"))
    return rows


def _print_order(order) -> None:
    if order.state == OrderState.FILLED and order.fill:
        presenter.execution_fill(order.intent, order.fill.price)
    else:
        presenter.execution_reject(order.intent, order.reject_reason)


def _intent_workspace_rows(intents: list, cycle_time: str | None = None) -> list[tuple]:
    return [
        (
            cycle_time,
            "Portfolio",
            intent.strategy_id,
            f"{intent.from_qty:+d} -> {intent.to_qty:+d} (delta {intent.delta_qty:+d})",
        ) if cycle_time is not None else (
            "Portfolio",
            intent.strategy_id,
            f"{intent.from_qty:+d} -> {intent.to_qty:+d} (delta {intent.delta_qty:+d})",
        )
        for intent in intents
    ]


def _portfolio_dashboard_row(
    cycle_time: str,
    theory_qty: int,
    actual_qty: int,
    order_state: str,
) -> tuple[str, str, str, str]:
    return (
        cycle_time,
        _format_qty(theory_qty),
        _format_qty(actual_qty),
        order_state,
    )


def _reconciliation_dashboard_row(
    cycle_time: str,
    theory_qty: int,
    actual_qty: int,
    mark_price: float,
    pnl: float,
    equity_curve: list[float],
) -> tuple[str, str, str, str, str, str, str, str]:
    diff = theory_qty - actual_qty
    if diff == 0:
        status = "[green]OK[/green]"
    else:
        status = "[yellow]PENDING[/yellow]"
    return (
        cycle_time,
        _format_qty(theory_qty),
        _format_qty(actual_qty),
        _format_qty(diff),
        status,
        f"{mark_price:.2f}",
        _format_money(pnl),
        _format_money(max_drawdown(equity_curve)),
    )


def _broker_actual_position(order_manager: OrderManager) -> int:
    return sum(fill.qty for fill in order_manager.fills)


def _format_qty(qty: int) -> str:
    if qty == 0:
        return "0"
    return f"{qty:+d}"


def _format_money(value: float) -> str:
    if value > 0:
        return f"+{value:,.2f}"
    return f"{value:,.2f}"


def _add_portfolio_transition_activity(dashboard, cycle_time: str, intents: list) -> None:
    for intent in intents:
        dashboard.add_activity(
            "portfolio",
            f"{cycle_time} {intent.strategy_id} {intent.from_qty:+d}->{intent.to_qty:+d} ({intent.delta_qty:+d})",
        )
