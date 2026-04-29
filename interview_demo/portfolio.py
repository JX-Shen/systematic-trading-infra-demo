from __future__ import annotations

from dataclasses import dataclass, field

from interview_demo.models import CONTRACT_MULTIPLIER, Fill, PositionIntent, Signal


@dataclass
class StrategyPosition:
    strategy_id: str
    qty: int = 0
    avg_price: float = 0.0
    realized_pnl: float = 0.0
    trade_count: int = 0
    closed_trades: int = 0
    winning_trades: int = 0

    def move_to(self, target_qty: int, price: float) -> None:
        if target_qty == self.qty:
            return

        if self.qty != 0:
            closed_pnl = (price - self.avg_price) * self.qty * CONTRACT_MULTIPLIER
            self.realized_pnl += closed_pnl
            self.closed_trades += 1
            if closed_pnl > 0:
                self.winning_trades += 1

        if target_qty == 0:
            self.avg_price = 0.0
        else:
            self.avg_price = price

        self.qty = target_qty
        self.trade_count += 1

    def mark_to_market(self, price: float) -> float:
        return self.realized_pnl + (price - self.avg_price) * self.qty * CONTRACT_MULTIPLIER


@dataclass
class PortfolioManager:
    positions: dict[str, StrategyPosition] = field(default_factory=dict)
    applied_fills: list[Fill] = field(default_factory=list)

    def build_intents(self, signals: list[Signal]) -> list[PositionIntent]:
        intents: list[PositionIntent] = []
        for signal in signals:
            position = self.positions.setdefault(
                signal.strategy_id, StrategyPosition(strategy_id=signal.strategy_id)
            )
            if signal.target_qty == position.qty:
                continue
            intents.append(
                PositionIntent(
                    strategy_id=signal.strategy_id,
                    symbol=signal.symbol,
                    from_qty=position.qty,
                    to_qty=signal.target_qty,
                )
            )
        return intents

    def apply_intents(self, intents: list[PositionIntent], fill_price: float, source: str) -> None:
        for intent in intents:
            position = self.positions.setdefault(
                intent.strategy_id, StrategyPosition(strategy_id=intent.strategy_id)
            )
            position.move_to(intent.to_qty, fill_price)
            self.applied_fills.append(
                Fill(
                    order_id=f"{source}:{intent.strategy_id}",
                    symbol=intent.symbol,
                    qty=intent.delta_qty,
                    price=fill_price,
                    source=source,
                )
            )

    @property
    def aggregate_position(self) -> int:
        return sum(position.qty for position in self.positions.values())

    @property
    def total_trades(self) -> int:
        return sum(position.trade_count for position in self.positions.values())

    def total_pnl(self, mark_price: float) -> float:
        return sum(position.mark_to_market(mark_price) for position in self.positions.values())

    @property
    def closed_trades(self) -> int:
        return sum(position.closed_trades for position in self.positions.values())

    @property
    def winning_trades(self) -> int:
        return sum(position.winning_trades for position in self.positions.values())

    @property
    def win_rate(self) -> float:
        if self.closed_trades == 0:
            return 0.0
        return self.winning_trades / self.closed_trades

    def pnl_by_strategy(self, mark_price: float) -> dict[str, float]:
        return {
            strategy_id: position.mark_to_market(mark_price)
            for strategy_id, position in sorted(self.positions.items())
        }
