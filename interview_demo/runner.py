from __future__ import annotations

import os
import sys
from datetime import datetime
from itertools import count
from pathlib import Path
from typing import Callable

from interview_demo.data import load_fixture_bars
from interview_demo.dashboard import DemoDashboard
from interview_demo.events import EventLog, replay_provider_confirmed_position
from interview_demo.execution import (
    OrderManager,
    OrderState,
    ProviderBehavior,
    ProviderCallbackState,
    SimulatedProvider,
    route_order_intent,
)
from interview_demo.models import Bar, Fill, OrderIntent, Signal, SignalSide, SYMBOL
from interview_demo.performance import max_drawdown, sharpe_like
from interview_demo.presenter import presenter
from interview_demo.portfolio import PortfolioManager
from interview_demo.reconciliation import reconcile_positions
from interview_demo.risk import RiskGate
from interview_demo.strategies import default_strategies


TRACE_PATH = Path("artifacts/latest-run/events.jsonl")


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
    bars, source = load_fixture_bars()
    strategies = default_strategies()
    portfolio = PortfolioManager()
    provider = SimulatedProvider(slippage=0.02)
    order_manager = OrderManager(provider)
    risk_gate = RiskGate(
        max_aggregate_position=3,
        max_order_size=3,
        enabled_symbols={SYMBOL},
        session_enabled=True,
    )
    event_log = EventLog()
    order_ids = count(1)
    equity_curve: list[float] = []
    signal_count = 0

    presenter.section("FULL DEMO: local 5-minute fixture replay")
    presenter.header(source, len(bars), bars[0], bars[-1])
    event_log.append(
        "market_event_loaded",
        {
            "source": source,
            "bars_count": len(bars),
            "symbol": bars[0].symbol,
        },
    )
    stepper.pause("Data source loaded. Next: replay bars into strategies.")

    for bar in bars:
        event_log.append(
            "market_event_loaded",
            {
                "timestamp": bar.timestamp.isoformat(),
                "symbol": bar.symbol,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            },
        )
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
            for signal in signals:
                event_log.append(
                    "signal_emitted",
                    {
                        "timestamp": bar.timestamp.isoformat(),
                        "strategy_id": signal.strategy_id,
                        "symbol": signal.symbol,
                        "side": signal.side.value,
                        "target_qty": signal.target_qty,
                    },
                )

            stepper.pause("Signals emitted. Next: portfolio lifecycle and netting.", cycle_id=cycle_id)
            intents = portfolio.build_intents(signals)
            intent_event = event_log.append(
                "portfolio_intent_built",
                {
                    "timestamp": bar.timestamp.isoformat(),
                    "intent_count": len(intents),
                    "aggregate_position_before": portfolio.aggregate_position,
                    "intents": [
                        {
                            "strategy_id": intent.strategy_id,
                            "symbol": intent.symbol,
                            "from_qty": intent.from_qty,
                            "to_qty": intent.to_qty,
                            "delta_qty": intent.delta_qty,
                        }
                        for intent in intents
                    ],
                },
            )
            if not intents:
                presenter.workspace(
                    [
                        ("Portfolio", "-", "Signals produced no position change"),
                        ("Execution", "-", "No provider action"),
                    ]
                )
            else:
                net_qty = sum(intent.delta_qty for intent in intents)

                if net_qty == 0:
                    stepper.pause(
                        "Net order quantity is zero. Next: apply internal netting without provider flow.",
                        cycle_id=cycle_id,
                    )
                    portfolio.apply_intents(intents, bar.close, "internal_netting")
                    presenter.workspace(
                        _intent_workspace_rows(intents)
                        + [
                            ("Netting", bar.symbol, f"Net provider order qty = {net_qty:+d}"),
                            ("Decision", "Internal", "No provider order required"),
                            ("Position", "Aggregate", f"{portfolio.aggregate_position:+d}"),
                        ]
                    )
                else:
                    stepper.pause(
                        "Net demand remains. Next: route order intent to simulated provider.",
                        cycle_id=cycle_id,
                    )
                    order_intent = OrderIntent(
                        order_id=f"ORD-{next(order_ids):04d}",
                        symbol=bar.symbol,
                        qty=net_qty,
                        reference_price=bar.close,
                        reason="net portfolio demand",
                    )
                    routed = route_order_intent(
                        intent=order_intent,
                        current_aggregate_position=portfolio.aggregate_position,
                        risk_gate=risk_gate,
                        order_manager=order_manager,
                    )
                    risk_event = event_log.append(
                        "risk_decision",
                        {
                            "order_id": order_intent.order_id,
                            "accepted": routed.risk_decision.accepted,
                            "code": routed.risk_decision.code,
                            "message": routed.risk_decision.message,
                        },
                        related_event_ids=[intent_event.event_id],
                    )
                    if not routed.routed or not routed.order:
                        execution_state = (
                            f"qty={order_intent.qty:+d} [bold red]RISK_REJECT[/bold red] "
                            f"({routed.risk_decision.message})"
                        )
                        order = None
                    else:
                        order = routed.order
                        event_log.append(
                            "order_submitted",
                            {
                                "order_id": order.intent.order_id,
                                "symbol": order.intent.symbol,
                                "qty": order.intent.qty,
                                "reference_price": order.intent.reference_price,
                            },
                            related_event_ids=[risk_event.event_id],
                        )
                        callback = order.callback
                        if callback is not None:
                            event_log.append(
                                "provider_callback",
                                {
                                    "order_id": callback.order_id,
                                    "symbol": callback.symbol,
                                    "state": callback.state.value,
                                    "requested_qty": callback.requested_qty,
                                    "filled_qty": callback.filled_qty,
                                    "price": callback.price,
                                    "reason": callback.reason,
                                    "provider_confirmed_position": callback.provider_confirmed_position,
                                },
                                related_event_ids=[risk_event.event_id],
                            )
                    if order and order.state == OrderState.FILLED and order.fill:
                        portfolio.apply_intents(intents, order.fill.price, "provider_fill")
                        execution_state = (
                            f"qty={order.intent.qty:+d} PENDING -> SUBMITTED -> WORKING -> [bold green]FILLED[/bold green] "
                            f"@ {order.fill.price:.2f}"
                        )
                    elif order and order.state == OrderState.PARTIALLY_FILLED and order.fill:
                        execution_state = (
                            f"qty={order.intent.qty:+d} PENDING -> SUBMITTED -> WORKING -> [bold yellow]PARTIALLY FILLED[/bold yellow] "
                            f"filled={order.fill.qty:+d} residual={order.residual_qty:+d} @ {order.fill.price:.2f}; "
                            "portfolio transition held for reconciliation"
                        )
                    else:
                        order_text = f"qty={order_intent.qty:+d}" if order is None else f"qty={order.intent.qty:+d}"
                        reject_reason = (
                            routed.risk_decision.message
                            if order is None
                            else (order.reject_reason or "provider callback rejected")
                        )
                        execution_state = (
                            f"{order_text} PENDING -> SUBMITTED -> WORKING -> [bold red]REJECTED[/bold red] "
                            f"({reject_reason})"
                        )
                    presenter.workspace(
                        _intent_workspace_rows(intents)
                        + [
                            ("Netting", bar.symbol, f"Net provider order qty = {net_qty:+d}"),
                            ("Execution", order_intent.order_id, execution_state),
                            ("Position", "Aggregate", f"{portfolio.aggregate_position:+d}"),
                        ]
                    )
                stepper.pause("State updated. Next: continue replay.", cycle_id=cycle_id)

        equity_curve.append(portfolio.total_pnl(bar.close))

    if signal_count == 0:
        raise RuntimeError("Demo data did not trigger any signals")
    if not order_manager.fills:
        raise RuntimeError("Demo data did not produce any provider fills")

    final_price = bars[-1].close
    callback_event_ids = [
        event.event_id for event in event_log.events if event.event_type == "provider_callback"
    ]
    result = reconcile_positions(
        portfolio.aggregate_position,
        order_manager.fills,
        provider_state_position=provider.provider_confirmed_position,
        related_event_ids=callback_event_ids,
    )
    event_log.append(
        "reconciliation_result",
        {
            "target_position": result.target_position,
            "provider_state_position": result.provider_state_position,
            "diff": result.diff,
            "status": result.status.value,
            "suspected_source": result.suspected_source,
            "related_event_ids": list(result.related_event_ids),
        },
    )
    trace_path = event_log.write_jsonl(TRACE_PATH)

    stepper.pause("Replay complete. Next: reconciliation and performance output.")
    presenter.reconciliation(result)
    presenter.line(f"trace output: {trace_path}")
    _print_metrics(portfolio, equity_curve, final_price)


def _run_full_demo_dashboard() -> None:
    bars, source = load_fixture_bars()
    strategies = default_strategies()
    portfolio = PortfolioManager()
    order_manager = OrderManager(SimulatedProvider(slippage=0.02))
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
                    actual_qty=_provider_actual_position(order_manager),
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
                    actual_qty=_provider_actual_position(order_manager),
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
                    actual_qty=_provider_actual_position(order_manager),
                    order_state="-",
                )
            )
            dashboard.set_reconciliation_row(
                _reconciliation_dashboard_row(
                    cycle_time,
                    theory_qty=sum(signal_positions.values()),
                    actual_qty=_provider_actual_position(order_manager),
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
                            "Net order quantity is zero. Next: apply internal netting without provider flow.",
                            cycle_id=cycle_id,
                        )
                        portfolio.apply_intents(intents, bar.close, "internal_netting")
                        dashboard.set_portfolio_row(
                            _portfolio_dashboard_row(
                                cycle_time,
                                theory_qty=sum(signal_positions.values()),
                                actual_qty=_provider_actual_position(order_manager),
                                order_state="internal net",
                            )
                        )
                        dashboard.set_reconciliation_row(
                            _reconciliation_dashboard_row(
                                cycle_time,
                                theory_qty=sum(signal_positions.values()),
                                actual_qty=_provider_actual_position(order_manager),
                                mark_price=bar.open,
                                pnl=portfolio.total_pnl(bar.open),
                                equity_curve=equity_curve + [portfolio.total_pnl(bar.open)],
                            )
                        )
                        _add_portfolio_transition_activity(dashboard, cycle_time, intents)
                        dashboard.add_activity("netting", f"{cycle_time} net {net_qty:+d}; internal match, provider skipped")
                    else:
                        stepper.pause(
                            "Net demand remains. Next: route order intent to simulated provider.",
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
                            portfolio.apply_intents(intents, order.fill.price, "provider_fill")
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
                        dashboard.add_activity("netting", f"{cycle_time} net provider order qty {net_qty:+d}")
                        dashboard.set_portfolio_row(
                            _portfolio_dashboard_row(
                                cycle_time,
                                theory_qty=sum(signal_positions.values()),
                                actual_qty=_provider_actual_position(order_manager),
                                order_state=order_state,
                            )
                        )
                        dashboard.set_reconciliation_row(
                            _reconciliation_dashboard_row(
                                cycle_time,
                                theory_qty=sum(signal_positions.values()),
                                actual_qty=_provider_actual_position(order_manager),
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
                actual_qty=_provider_actual_position(order_manager),
                mark_price=bar.close,
                pnl=cycle_pnl,
                equity_curve=equity_curve + [cycle_pnl],
            )
            equity_curve.append(cycle_pnl)

        if signal_count == 0:
            raise RuntimeError("Demo data did not trigger any signals")
        if not order_manager.fills:
            raise RuntimeError("Demo data did not produce any provider fills")

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
    bars, source = load_fixture_bars()
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
            ("Netting", SYMBOL, f"Net provider order qty = {net_qty:+d}"),
            ("Decision", "Internal", "No provider order required"),
            ("Positions", "Strategy-level", position_text),
        ]
    )


def run_execution_scenario(step: bool = False) -> None:
    stepper = Stepper(step)
    provider = SimulatedProvider(slippage=0.02)
    order_manager = OrderManager(provider)

    presenter.section("SCENARIO: execution order state machine")
    accepted = OrderIntent("ORD-ACCEPT", SYMBOL, +1, 82.40, "accepted path")
    stepper.pause("Accepted order intent prepared. Next: submit to simulated provider.")
    accepted_order = order_manager.submit(accepted)
    _print_order(accepted_order)

    provider.queue_provider_reject()
    rejected = OrderIntent("ORD-REJECT", SYMBOL, -1, 82.35, "reject path")
    stepper.pause("Reject path prepared. Next: submit and show explicit rejected state.")
    rejected_order = order_manager.submit(rejected)
    _print_order(rejected_order)

    provider.queue_partial_fill(fill_ratio=0.5)
    partial = OrderIntent("ORD-PARTIAL", SYMBOL, +2, 82.50, "partial fill path")
    stepper.pause("Partial path prepared. Next: submit and show residual quantity.")
    partial_order = order_manager.submit(partial)
    _print_order(partial_order)


def run_reconciliation_scenario(step: bool = False) -> None:
    stepper = Stepper(step)
    fills = [
        Fill("ORD-0001", SYMBOL, +1, 82.42, "provider_fill"),
        Fill("ORD-0002", SYMBOL, -1, 82.90, "provider_fill"),
        Fill("ORD-0003", SYMBOL, +1, 83.00, "provider_fill"),
    ]

    presenter.section("SCENARIO: reconciliation")
    stepper.pause("Provider fill log prepared. Next: run passing reconciliation.")
    passing = reconcile_positions(+1, fills)
    presenter.reconciliation(passing)

    stepper.pause("Passing case shown. Next: run deliberate mismatch.")
    mismatch = reconcile_positions(
        0,
        fills,
        provider_state_position=+2,
        related_event_ids=[101, 102, 103],
    )
    presenter.reconciliation(mismatch)


def run_risk_reject_scenario(step: bool = False) -> None:
    stepper = Stepper(step)
    event_log = EventLog()
    provider = SimulatedProvider(slippage=0.02)
    order_manager = OrderManager(provider)
    risk_gate = RiskGate(
        max_aggregate_position=2,
        max_order_size=1,
        enabled_symbols={SYMBOL},
        session_enabled=True,
    )
    order_intent = OrderIntent("ORD-RISK-REJECT", SYMBOL, +2, 82.30, "risk gate scenario")

    presenter.section("SCENARIO: risk-reject")
    event_log.append(
        "market_event_loaded",
        {"source": "manual fixture", "bars_count": 1, "symbol": SYMBOL},
    )
    event_log.append(
        "signal_emitted",
        {"strategy_id": "scenario_risk", "symbol": SYMBOL, "side": "buy", "target_qty": +2},
    )
    intent_event = event_log.append(
        "portfolio_intent_built",
        {"intent_count": 1, "order_id": order_intent.order_id, "qty": order_intent.qty},
    )
    stepper.pause("Order intent prepared. Next: evaluate risk gate.")

    routed = route_order_intent(
        intent=order_intent,
        current_aggregate_position=0,
        risk_gate=risk_gate,
        order_manager=order_manager,
    )
    event_log.append(
        "risk_decision",
        {
            "order_id": order_intent.order_id,
            "accepted": routed.risk_decision.accepted,
            "code": routed.risk_decision.code,
            "message": routed.risk_decision.message,
            "related_intent_event_id": intent_event.event_id,
        },
    )
    presenter.workspace(
        [
            ("Risk", order_intent.order_id, f"{routed.risk_decision.code}: {routed.risk_decision.message}"),
            ("Execution", "-", "Provider not called"),
            ("Provider", "submit_count", str(provider.submit_count)),
        ]
    )

    report = reconcile_positions(0, order_manager.fills, provider_state_position=provider.provider_confirmed_position)
    event_log.append(
        "reconciliation_result",
        {
            "target_position": report.target_position,
            "provider_state_position": report.provider_state_position,
            "diff": report.diff,
            "status": report.status.value,
            "suspected_source": report.suspected_source,
            "related_event_ids": [],
        },
    )
    trace_path = event_log.write_jsonl(TRACE_PATH)
    presenter.line(f"trace output: {trace_path}")


def run_provider_reject_scenario(step: bool = False) -> None:
    stepper = Stepper(step)
    event_log = EventLog()
    provider = SimulatedProvider(slippage=0.02)
    order_manager = OrderManager(provider)
    risk_gate = RiskGate(
        max_aggregate_position=2,
        max_order_size=2,
        enabled_symbols={SYMBOL},
        session_enabled=True,
    )
    provider.queue_provider_reject()
    order_intent = OrderIntent("ORD-PROVIDER-REJECT", SYMBOL, +1, 82.30, "provider reject scenario")

    presenter.section("SCENARIO: provider-reject")
    event_log.append(
        "market_event_loaded",
        {"source": "manual fixture", "bars_count": 1, "symbol": SYMBOL},
    )
    event_log.append(
        "signal_emitted",
        {"strategy_id": "scenario_provider_reject", "symbol": SYMBOL, "side": "buy", "target_qty": +1},
    )
    intent_event = event_log.append(
        "portfolio_intent_built",
        {"intent_count": 1, "order_id": order_intent.order_id, "qty": order_intent.qty},
    )
    stepper.pause("Order intent prepared. Next: route to provider through risk gate.")

    routed = route_order_intent(
        intent=order_intent,
        current_aggregate_position=0,
        risk_gate=risk_gate,
        order_manager=order_manager,
    )
    risk_event = event_log.append(
        "risk_decision",
        {
            "order_id": order_intent.order_id,
            "accepted": routed.risk_decision.accepted,
            "code": routed.risk_decision.code,
            "message": routed.risk_decision.message,
            "related_intent_event_id": intent_event.event_id,
        },
    )
    if routed.order is not None:
        event_log.append(
            "order_submitted",
            {
                "order_id": routed.order.intent.order_id,
                "symbol": routed.order.intent.symbol,
                "qty": routed.order.intent.qty,
                "reference_price": routed.order.intent.reference_price,
                "risk_event_id": risk_event.event_id,
            },
        )
        callback = routed.order.callback
        if callback is not None:
            callback_event = event_log.append(
                "provider_callback",
                {
                    "order_id": callback.order_id,
                    "symbol": callback.symbol,
                    "state": callback.state.value,
                    "requested_qty": callback.requested_qty,
                    "filled_qty": callback.filled_qty,
                    "price": callback.price,
                    "reason": callback.reason,
                    "provider_confirmed_position": callback.provider_confirmed_position,
                },
            )
            related_event_ids = [callback_event.event_id]
        else:
            related_event_ids = []
    else:
        related_event_ids = []

    presenter.workspace(
        [
            ("Risk", order_intent.order_id, routed.risk_decision.message),
            ("Execution", order_intent.order_id, f"state={routed.order.state.value}" if routed.order else "not routed"),
            ("Portfolio", "aggregate_position", "0"),
        ]
    )
    report = reconcile_positions(
        0,
        order_manager.fills,
        provider_state_position=provider.provider_confirmed_position,
        related_event_ids=related_event_ids,
    )
    event_log.append(
        "reconciliation_result",
        {
            "target_position": report.target_position,
            "provider_state_position": report.provider_state_position,
            "diff": report.diff,
            "status": report.status.value,
            "suspected_source": report.suspected_source,
            "related_event_ids": related_event_ids,
        },
    )
    trace_path = event_log.write_jsonl(TRACE_PATH)
    presenter.line(f"trace output: {trace_path}")


def run_partial_fill_scenario(step: bool = False) -> None:
    stepper = Stepper(step)
    event_log = EventLog()
    provider = SimulatedProvider(slippage=0.02)
    order_manager = OrderManager(provider)
    risk_gate = RiskGate(
        max_aggregate_position=3,
        max_order_size=3,
        enabled_symbols={SYMBOL},
        session_enabled=True,
    )
    provider.queue_partial_fill(fill_ratio=0.5)
    order_intent = OrderIntent("ORD-PARTIAL-FILL", SYMBOL, +2, 82.30, "partial fill scenario")

    presenter.section("SCENARIO: partial-fill")
    event_log.append(
        "market_event_loaded",
        {"source": "manual fixture", "bars_count": 1, "symbol": SYMBOL},
    )
    event_log.append(
        "signal_emitted",
        {"strategy_id": "scenario_partial", "symbol": SYMBOL, "side": "buy", "target_qty": +2},
    )
    intent_event = event_log.append(
        "portfolio_intent_built",
        {"intent_count": 1, "order_id": order_intent.order_id, "qty": order_intent.qty},
    )
    stepper.pause("Partial fill setup ready. Next: route order.")

    routed = route_order_intent(
        intent=order_intent,
        current_aggregate_position=0,
        risk_gate=risk_gate,
        order_manager=order_manager,
    )
    risk_event = event_log.append(
        "risk_decision",
        {
            "order_id": order_intent.order_id,
            "accepted": routed.risk_decision.accepted,
            "code": routed.risk_decision.code,
            "message": routed.risk_decision.message,
            "related_intent_event_id": intent_event.event_id,
        },
    )
    callback_event_ids: list[int] = []
    if routed.order is not None:
        event_log.append(
            "order_submitted",
            {
                "order_id": routed.order.intent.order_id,
                "symbol": routed.order.intent.symbol,
                "qty": routed.order.intent.qty,
                "reference_price": routed.order.intent.reference_price,
                "risk_event_id": risk_event.event_id,
            },
        )
        callback = routed.order.callback
        if callback is not None:
            callback_event = event_log.append(
                "provider_callback",
                {
                    "order_id": callback.order_id,
                    "symbol": callback.symbol,
                    "state": callback.state.value,
                    "requested_qty": callback.requested_qty,
                    "filled_qty": callback.filled_qty,
                    "price": callback.price,
                    "reason": callback.reason,
                    "provider_confirmed_position": callback.provider_confirmed_position,
                },
            )
            callback_event_ids.append(callback_event.event_id)
    presenter.workspace(
        [
            ("Execution", order_intent.order_id, f"state={routed.order.state.value}" if routed.order else "not routed"),
            (
                "Execution",
                "residual_qty",
                str(routed.order.residual_qty if routed.order is not None else 0),
            ),
            ("Provider", "provider_confirmed_position", f"{provider.provider_confirmed_position:+d}"),
        ]
    )
    report = reconcile_positions(
        +2,
        order_manager.fills,
        provider_state_position=provider.provider_confirmed_position,
        related_event_ids=callback_event_ids,
    )
    event_log.append(
        "reconciliation_result",
        {
            "target_position": report.target_position,
            "provider_state_position": report.provider_state_position,
            "diff": report.diff,
            "status": report.status.value,
            "suspected_source": report.suspected_source,
            "related_event_ids": callback_event_ids,
        },
    )
    presenter.reconciliation(report)
    trace_path = event_log.write_jsonl(TRACE_PATH)
    presenter.line(f"trace output: {trace_path}")


def run_reconciliation_mismatch_scenario(step: bool = False) -> None:
    stepper = Stepper(step)
    event_log = EventLog()
    provider = SimulatedProvider(slippage=0.02)
    order_manager = OrderManager(provider)
    provider.queue_behavior(
        ProviderBehavior(
            state=ProviderCallbackState.FILLED,
            provider_confirmed_position=+2,
        )
    )
    order = order_manager.submit(
        OrderIntent("ORD-MISMATCH", SYMBOL, +1, 82.30, "reconciliation mismatch scenario")
    )
    presenter.section("SCENARIO: reconciliation-mismatch")
    stepper.pause("Mismatch setup ready. Next: compare target and provider-confirmed state.")
    event_log.append(
        "market_event_loaded",
        {"source": "manual fixture", "bars_count": 1, "symbol": SYMBOL},
    )
    event_log.append(
        "signal_emitted",
        {"strategy_id": "scenario_recon_mismatch", "symbol": SYMBOL, "side": "buy", "target_qty": +1},
    )
    event_log.append(
        "portfolio_intent_built",
        {"intent_count": 1, "order_id": order.intent.order_id, "qty": order.intent.qty},
    )
    event_log.append(
        "risk_decision",
        {
            "order_id": order.intent.order_id,
            "accepted": True,
            "code": "accepted",
            "message": "risk checks passed",
        },
    )
    event_log.append(
        "order_submitted",
        {
            "order_id": order.intent.order_id,
            "symbol": order.intent.symbol,
            "qty": order.intent.qty,
            "reference_price": order.intent.reference_price,
        },
    )
    callback_event = event_log.append(
        "provider_callback",
        {
            "order_id": order.callback.order_id if order.callback else order.intent.order_id,
            "symbol": order.callback.symbol if order.callback else order.intent.symbol,
            "state": order.callback.state.value if order.callback else "filled",
            "requested_qty": order.callback.requested_qty if order.callback else order.intent.qty,
            "filled_qty": order.callback.filled_qty if order.callback else order.intent.qty,
            "price": order.callback.price if order.callback else None,
            "reason": order.callback.reason if order.callback else None,
            "provider_confirmed_position": order.callback.provider_confirmed_position if order.callback else None,
        },
    )
    report = reconcile_positions(
        portfolio_position=+1,
        provider_fills=order_manager.fills,
        provider_state_position=order.callback.provider_confirmed_position if order.callback else None,
        related_event_ids=[callback_event.event_id],
    )
    event_log.append(
        "reconciliation_result",
        {
            "target_position": report.target_position,
            "provider_state_position": report.provider_state_position,
            "diff": report.diff,
            "status": report.status.value,
            "suspected_source": report.suspected_source,
            "related_event_ids": list(report.related_event_ids),
        },
    )
    presenter.reconciliation(report)
    trace_path = event_log.write_jsonl(TRACE_PATH)
    presenter.line(f"trace output: {trace_path}")


def run_unexpected_provider_state_scenario(step: bool = False) -> None:
    stepper = Stepper(step)
    event_log = EventLog()
    provider = SimulatedProvider(slippage=0.02)
    provider.queue_unexpected_state(
        provider_confirmed_position=+1,
        reason="simulated provider callback reported unexpected state",
    )
    order_manager = OrderManager(provider)
    order_intent = OrderIntent("ORD-UNEXPECTED", SYMBOL, +1, 82.30, "unexpected state scenario")

    presenter.section("SCENARIO: unexpected-provider-state")
    stepper.pause("Unexpected provider state queued. Next: submit intent.")
    event_log.append(
        "market_event_loaded",
        {"source": "manual fixture", "bars_count": 1, "symbol": SYMBOL},
    )
    event_log.append(
        "signal_emitted",
        {"strategy_id": "scenario_unexpected", "symbol": SYMBOL, "side": "buy", "target_qty": +1},
    )
    intent_event = event_log.append(
        "portfolio_intent_built",
        {"intent_count": 1, "order_id": order_intent.order_id, "qty": order_intent.qty},
    )
    risk_event = event_log.append(
        "risk_decision",
        {
            "order_id": order_intent.order_id,
            "accepted": True,
            "code": "accepted",
            "message": "risk checks passed",
        },
        related_event_ids=[intent_event.event_id],
    )
    order = order_manager.submit(order_intent)
    event_log.append(
        "order_submitted",
        {
            "order_id": order.intent.order_id,
            "symbol": order.intent.symbol,
            "qty": order.intent.qty,
            "reference_price": order.intent.reference_price,
        },
        related_event_ids=[risk_event.event_id],
    )
    callback = order.callback
    callback_event = event_log.append(
        "provider_callback",
        {
            "order_id": callback.order_id if callback else order.intent.order_id,
            "symbol": callback.symbol if callback else order.intent.symbol,
            "state": callback.state.value if callback else order.state.value,
            "requested_qty": callback.requested_qty if callback else order.intent.qty,
            "filled_qty": callback.filled_qty if callback else 0,
            "price": callback.price if callback else None,
            "reason": callback.reason if callback else order.reject_reason,
            "provider_confirmed_position": callback.provider_confirmed_position if callback else None,
        },
        related_event_ids=[risk_event.event_id],
    )

    presenter.workspace(
        [
            ("Execution", order.intent.order_id, f"state={order.state.value}"),
            ("Provider", "callback_reason", order.reject_reason or "-"),
            (
                "Provider",
                "provider_confirmed_position",
                f"{callback.provider_confirmed_position:+d}" if callback and callback.provider_confirmed_position is not None else "-",
            ),
        ]
    )
    report = reconcile_positions(
        portfolio_position=0,
        provider_fills=order_manager.fills,
        provider_state_position=callback.provider_confirmed_position if callback else None,
        related_event_ids=[callback_event.event_id],
    )
    event_log.append(
        "reconciliation_result",
        {
            "target_position": report.target_position,
            "provider_state_position": report.provider_state_position,
            "diff": report.diff,
            "status": report.status.value,
            "suspected_source": report.suspected_source,
            "related_event_ids": list(report.related_event_ids),
        },
        related_event_ids=[callback_event.event_id],
    )
    presenter.reconciliation(report)
    trace_path = event_log.write_jsonl(TRACE_PATH)
    presenter.line(f"trace output: {trace_path}")


def run_trace_replay_scenario(step: bool = False) -> None:
    stepper = Stepper(step)
    presenter.section("SCENARIO: trace-replay")
    stepper.pause("Preparing trace from partial-fill lifecycle.")
    run_partial_fill_scenario(step=False)
    stepper.pause("Trace written. Next: replay provider-confirmed position from JSONL.")
    event_log = EventLog.load_jsonl(TRACE_PATH)
    replayed_position = replay_provider_confirmed_position(event_log)
    presenter.workspace(
        [
            ("Trace", "events", str(len(event_log.events))),
            ("Replay", "provider_confirmed_position", f"{replayed_position:+d}"),
            ("Trace", "path", str(TRACE_PATH)),
        ]
    )


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
    elif order.state == OrderState.PARTIALLY_FILLED and order.fill:
        presenter.line(
            f"order {order.intent.order_id} PARTIAL filled={order.fill.qty:+d} residual={order.residual_qty:+d} "
            f"@ {order.fill.price:.2f}"
        )
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


def _provider_actual_position(order_manager: OrderManager) -> int:
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
