from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


SYMBOL = "FIXTURE-A"
CONTRACT_MULTIPLIER = 1000


@dataclass(frozen=True)
class Bar:
    timestamp: datetime
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class SignalSide(str, Enum):
    BUY = "buy"
    SELL = "sell"
    FLAT = "flat"


@dataclass(frozen=True)
class Signal:
    strategy_id: str
    symbol: str
    side: SignalSide
    reason: str

    @property
    def target_qty(self) -> int:
        if self.side == SignalSide.BUY:
            return 1
        if self.side == SignalSide.SELL:
            return -1
        return 0


@dataclass(frozen=True)
class PositionIntent:
    strategy_id: str
    symbol: str
    from_qty: int
    to_qty: int

    @property
    def delta_qty(self) -> int:
        return self.to_qty - self.from_qty


@dataclass(frozen=True)
class OrderIntent:
    order_id: str
    symbol: str
    qty: int
    reference_price: float
    reason: str


@dataclass(frozen=True)
class Fill:
    order_id: str
    symbol: str
    qty: int
    price: float
    source: str
