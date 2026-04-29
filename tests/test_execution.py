from __future__ import annotations

import unittest

from interview_demo.execution import MockBroker, OrderManager, OrderState
from interview_demo.models import OrderIntent, SYMBOL


class ExecutionTests(unittest.TestCase):
    def test_successful_order_moves_to_filled(self) -> None:
        manager = OrderManager(MockBroker(slippage=0.02))

        order = manager.submit(
            OrderIntent("ORD-TEST", SYMBOL, +1, 82.40, "unit test")
        )

        self.assertEqual(order.state, OrderState.FILLED)
        self.assertIsNotNone(order.fill)
        self.assertEqual(manager.broker_position, +1)
        self.assertEqual(order.fill.price, 82.42)

    def test_broker_reject_is_explicit_state(self) -> None:
        broker = MockBroker()
        broker.reject_next = True
        manager = OrderManager(broker)

        order = manager.submit(
            OrderIntent("ORD-REJECT", SYMBOL, -1, 82.40, "unit test")
        )

        self.assertEqual(order.state, OrderState.REJECTED)
        self.assertIsNone(order.fill)
        self.assertEqual(manager.broker_position, 0)
        self.assertIn("simulated broker reject", order.reject_reason or "")


if __name__ == "__main__":
    unittest.main()
