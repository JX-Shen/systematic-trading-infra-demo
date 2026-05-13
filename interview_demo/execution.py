from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from interview_demo.models import Fill, OrderIntent
from interview_demo.risk import RiskDecision, RiskGate


class OrderState(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    WORKING = "working"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    REJECTED = "rejected"
    UNEXPECTED_PROVIDER_STATE = "unexpected_provider_state"


class ProviderCallbackState(str, Enum):
    FILLED = "filled"
    REJECTED = "provider_rejected"
    PARTIAL_FILL = "partial_fill"
    UNEXPECTED_STATE = "unexpected_provider_state"


@dataclass(frozen=True)
class ProviderCallback:
    order_id: str
    symbol: str
    requested_qty: int
    filled_qty: int
    price: float | None
    state: ProviderCallbackState
    reason: str | None = None
    provider_confirmed_position: int | None = None


@dataclass(frozen=True)
class ProviderBehavior:
    state: ProviderCallbackState
    reason: str | None = None
    fill_ratio: float = 1.0
    provider_confirmed_position: int | None = None


@dataclass
class ManagedOrder:
    intent: OrderIntent
    state: OrderState = OrderState.PENDING
    fill: Fill | None = None
    reject_reason: str | None = None
    callback: ProviderCallback | None = None
    residual_qty: int = 0


@dataclass(frozen=True)
class RoutedOrder:
    routed: bool
    risk_decision: RiskDecision
    order: ManagedOrder | None


class SimulatedProvider:
    def __init__(self, slippage: float = 0.02) -> None:
        self.slippage = slippage
        self.reject_next = False
        self.submit_count = 0
        self.provider_confirmed_position = 0
        self._queued_behaviors: list[ProviderBehavior] = []

    def queue_behavior(self, behavior: ProviderBehavior) -> None:
        self._queued_behaviors.append(behavior)

    def queue_partial_fill(self, fill_ratio: float = 0.5) -> None:
        self.queue_behavior(
            ProviderBehavior(
                state=ProviderCallbackState.PARTIAL_FILL,
                fill_ratio=fill_ratio,
            )
        )

    def queue_provider_reject(self, reason: str | None = None) -> None:
        self.queue_behavior(
            ProviderBehavior(
                state=ProviderCallbackState.REJECTED,
                reason=reason or "simulated provider reject: provider temporarily unavailable",
            )
        )

    def queue_unexpected_state(
        self,
        provider_confirmed_position: int | None = None,
        reason: str | None = None,
    ) -> None:
        self.queue_behavior(
            ProviderBehavior(
                state=ProviderCallbackState.UNEXPECTED_STATE,
                provider_confirmed_position=provider_confirmed_position,
                reason=reason or "simulated provider callback had unexpected provider state",
            )
        )

    def submit(self, intent: OrderIntent) -> ProviderCallback:
        self.submit_count += 1

        if self.reject_next:
            self.reject_next = False
            return ProviderCallback(
                order_id=intent.order_id,
                symbol=intent.symbol,
                requested_qty=intent.qty,
                filled_qty=0,
                price=None,
                state=ProviderCallbackState.REJECTED,
                reason="simulated provider reject: provider temporarily unavailable",
                provider_confirmed_position=self.provider_confirmed_position,
            )

        behavior = self._queued_behaviors.pop(0) if self._queued_behaviors else ProviderBehavior(
            state=ProviderCallbackState.FILLED
        )
        signed_slippage = self.slippage if intent.qty > 0 else -self.slippage
        fill_price = round(intent.reference_price + signed_slippage, 2)

        if behavior.state == ProviderCallbackState.REJECTED:
            return ProviderCallback(
                order_id=intent.order_id,
                symbol=intent.symbol,
                requested_qty=intent.qty,
                filled_qty=0,
                price=None,
                state=ProviderCallbackState.REJECTED,
                reason=behavior.reason,
                provider_confirmed_position=behavior.provider_confirmed_position
                if behavior.provider_confirmed_position is not None
                else self.provider_confirmed_position,
            )

        if behavior.state == ProviderCallbackState.PARTIAL_FILL:
            partial_qty = int(abs(intent.qty) * behavior.fill_ratio)
            if partial_qty <= 0:
                partial_qty = 1
            if partial_qty > abs(intent.qty):
                partial_qty = abs(intent.qty)
            filled_qty = partial_qty if intent.qty > 0 else -partial_qty
            self.provider_confirmed_position += filled_qty
            return ProviderCallback(
                order_id=intent.order_id,
                symbol=intent.symbol,
                requested_qty=intent.qty,
                filled_qty=filled_qty,
                price=fill_price,
                state=ProviderCallbackState.PARTIAL_FILL,
                reason=behavior.reason,
                provider_confirmed_position=behavior.provider_confirmed_position
                if behavior.provider_confirmed_position is not None
                else self.provider_confirmed_position,
            )

        if behavior.state == ProviderCallbackState.UNEXPECTED_STATE:
            return ProviderCallback(
                order_id=intent.order_id,
                symbol=intent.symbol,
                requested_qty=intent.qty,
                filled_qty=0,
                price=None,
                state=ProviderCallbackState.UNEXPECTED_STATE,
                reason=behavior.reason,
                provider_confirmed_position=behavior.provider_confirmed_position,
            )

        self.provider_confirmed_position += intent.qty
        return ProviderCallback(
            order_id=intent.order_id,
            symbol=intent.symbol,
            requested_qty=intent.qty,
            filled_qty=intent.qty,
            price=fill_price,
            state=ProviderCallbackState.FILLED,
            provider_confirmed_position=behavior.provider_confirmed_position
            if behavior.provider_confirmed_position is not None
            else self.provider_confirmed_position,
        )


class OrderManager:
    def __init__(self, provider: SimulatedProvider) -> None:
        self.provider = provider
        self.orders: list[ManagedOrder] = []
        self.fills: list[Fill] = []
        self.callbacks: list[ProviderCallback] = []

    def submit(self, intent: OrderIntent) -> ManagedOrder:
        order = ManagedOrder(intent=intent)
        self.orders.append(order)

        order.state = OrderState.SUBMITTED
        order.state = OrderState.WORKING
        callback = self.provider.submit(intent)
        order.callback = callback
        self.callbacks.append(callback)

        if callback.state == ProviderCallbackState.REJECTED:
            order.state = OrderState.REJECTED
            order.reject_reason = callback.reason or "provider rejected order"
            return order

        if callback.state == ProviderCallbackState.UNEXPECTED_STATE:
            order.state = OrderState.UNEXPECTED_PROVIDER_STATE
            order.reject_reason = callback.reason or "provider callback had unexpected state"
            return order

        if callback.filled_qty != 0 and callback.price is not None:
            order.fill = Fill(
                order_id=callback.order_id,
                symbol=callback.symbol,
                qty=callback.filled_qty,
                price=callback.price,
                source="provider_fill",
            )
            self.fills.append(order.fill)

        if callback.state == ProviderCallbackState.PARTIAL_FILL:
            order.state = OrderState.PARTIALLY_FILLED
            order.residual_qty = intent.qty - callback.filled_qty
            return order

        order.state = OrderState.FILLED
        return order

    @property
    def provider_position(self) -> int:
        return sum(fill.qty for fill in self.fills)


def route_order_intent(
    intent: OrderIntent,
    current_aggregate_position: int,
    risk_gate: RiskGate,
    order_manager: OrderManager,
) -> RoutedOrder:
    risk_decision = risk_gate.evaluate(intent, current_aggregate_position=current_aggregate_position)
    if not risk_decision.accepted:
        return RoutedOrder(routed=False, risk_decision=risk_decision, order=None)
    order = order_manager.submit(intent)
    return RoutedOrder(routed=True, risk_decision=risk_decision, order=order)
