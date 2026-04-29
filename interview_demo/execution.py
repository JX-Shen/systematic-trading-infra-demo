from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from interview_demo.models import Fill, OrderIntent


class OrderState(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    WORKING = "working"
    FILLED = "filled"
    REJECTED = "rejected"


@dataclass
class ManagedOrder:
    intent: OrderIntent
    state: OrderState = OrderState.PENDING
    fill: Fill | None = None
    reject_reason: str | None = None


class MockBroker:
    def __init__(self, slippage: float = 0.02) -> None:
        self.slippage = slippage
        self.reject_next = False

    def submit(self, intent: OrderIntent) -> Fill:
        if self.reject_next:
            self.reject_next = False
            raise BrokerReject("simulated broker reject: market temporarily unavailable")

        signed_slippage = self.slippage if intent.qty > 0 else -self.slippage
        return Fill(
            order_id=intent.order_id,
            symbol=intent.symbol,
            qty=intent.qty,
            price=round(intent.reference_price + signed_slippage, 2),
            source="mock_broker",
        )


class BrokerReject(Exception):
    pass


class OrderManager:
    def __init__(self, broker: MockBroker) -> None:
        self.broker = broker
        self.orders: list[ManagedOrder] = []
        self.fills: list[Fill] = []

    def submit(self, intent: OrderIntent) -> ManagedOrder:
        order = ManagedOrder(intent=intent)
        self.orders.append(order)

        order.state = OrderState.SUBMITTED
        order.state = OrderState.WORKING
        try:
            order.fill = self.broker.submit(intent)
        except BrokerReject as exc:
            order.state = OrderState.REJECTED
            order.reject_reason = str(exc)
            return order

        order.state = OrderState.FILLED
        self.fills.append(order.fill)
        return order

    @property
    def broker_position(self) -> int:
        return sum(fill.qty for fill in self.fills)
