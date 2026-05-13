from __future__ import annotations

import unittest

from interview_demo.execution import OrderManager, OrderState, SimulatedProvider, route_order_intent
from interview_demo.models import OrderIntent, SYMBOL
from interview_demo.risk import RiskGate


class ExecutionTests(unittest.TestCase):
    def test_successful_order_moves_to_filled(self) -> None:
        manager = OrderManager(SimulatedProvider(slippage=0.02))

        order = manager.submit(
            OrderIntent("ORD-TEST", SYMBOL, +1, 82.40, "unit test")
        )

        self.assertEqual(order.state, OrderState.FILLED)
        self.assertIsNotNone(order.fill)
        self.assertEqual(manager.provider_position, +1)
        self.assertEqual(order.fill.price, 82.42)

    def test_provider_reject_is_explicit_state(self) -> None:
        provider = SimulatedProvider()
        provider.queue_provider_reject()
        manager = OrderManager(provider)

        order = manager.submit(
            OrderIntent("ORD-REJECT", SYMBOL, -1, 82.40, "unit test")
        )

        self.assertEqual(order.state, OrderState.REJECTED)
        self.assertIsNone(order.fill)
        self.assertEqual(manager.provider_position, 0)
        self.assertIn("provider reject", order.reject_reason or "")

    def test_partial_fill_tracks_residual(self) -> None:
        provider = SimulatedProvider()
        provider.queue_partial_fill(fill_ratio=0.5)
        manager = OrderManager(provider)

        order = manager.submit(
            OrderIntent("ORD-PARTIAL", SYMBOL, +2, 82.40, "unit test")
        )

        self.assertEqual(order.state, OrderState.PARTIALLY_FILLED)
        self.assertIsNotNone(order.fill)
        self.assertEqual(order.fill.qty, +1)
        self.assertEqual(order.residual_qty, +1)
        self.assertEqual(manager.provider_position, +1)

    def test_unexpected_provider_state_is_explicit(self) -> None:
        provider = SimulatedProvider()
        provider.queue_unexpected_state(provider_confirmed_position=+1)
        manager = OrderManager(provider)

        order = manager.submit(
            OrderIntent("ORD-UNEXPECTED", SYMBOL, +1, 82.40, "unit test")
        )

        self.assertEqual(order.state, OrderState.UNEXPECTED_PROVIDER_STATE)
        self.assertIsNone(order.fill)
        self.assertEqual(manager.provider_position, 0)
        self.assertIsNotNone(order.callback)
        self.assertEqual(order.callback.provider_confirmed_position, +1)

    def test_risk_reject_blocks_provider_routing(self) -> None:
        provider = SimulatedProvider()
        manager = OrderManager(provider)
        risk_gate = RiskGate(
            max_aggregate_position=5,
            max_order_size=1,
            enabled_symbols={SYMBOL},
            session_enabled=True,
        )

        routed = route_order_intent(
            intent=OrderIntent("ORD-RISK", SYMBOL, +2, 82.40, "unit test"),
            current_aggregate_position=0,
            risk_gate=risk_gate,
            order_manager=manager,
        )

        self.assertFalse(routed.routed)
        self.assertFalse(routed.risk_decision.accepted)
        self.assertEqual(routed.risk_decision.code, "max_order_size_exceeded")
        self.assertEqual(provider.submit_count, 0)
        self.assertEqual(manager.provider_position, 0)


if __name__ == "__main__":
    unittest.main()
