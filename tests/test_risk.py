from __future__ import annotations

import unittest

from interview_demo.models import OrderIntent, SYMBOL
from interview_demo.risk import RiskGate


class RiskGateTests(unittest.TestCase):
    def test_rejects_when_session_disabled(self) -> None:
        risk_gate = RiskGate(
            max_aggregate_position=5,
            max_order_size=2,
            enabled_symbols={SYMBOL},
            session_enabled=False,
        )

        decision = risk_gate.evaluate(
            OrderIntent("ORD-RISK", SYMBOL, +1, 82.40, "unit test"),
            current_aggregate_position=0,
        )

        self.assertFalse(decision.accepted)
        self.assertEqual(decision.code, "session_disabled")

    def test_rejects_projected_position_limit(self) -> None:
        risk_gate = RiskGate(
            max_aggregate_position=2,
            max_order_size=2,
            enabled_symbols={SYMBOL},
            session_enabled=True,
        )

        decision = risk_gate.evaluate(
            OrderIntent("ORD-RISK", SYMBOL, +2, 82.40, "unit test"),
            current_aggregate_position=+1,
        )

        self.assertFalse(decision.accepted)
        self.assertEqual(decision.code, "max_aggregate_position_exceeded")


if __name__ == "__main__":
    unittest.main()
