from __future__ import annotations

import unittest

from interview_demo.models import Fill, SYMBOL
from interview_demo.reconciliation import reconcile_positions


class ReconciliationTests(unittest.TestCase):
    def test_matching_portfolio_and_broker_position_passes(self) -> None:
        result = reconcile_positions(
            +1,
            [
                Fill("ORD-1", SYMBOL, +1, 82.42, "mock_broker"),
                Fill("ORD-2", SYMBOL, -1, 82.90, "mock_broker"),
                Fill("ORD-3", SYMBOL, +1, 83.00, "mock_broker"),
            ],
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.broker_position, +1)

    def test_position_mismatch_fails(self) -> None:
        result = reconcile_positions(
            0,
            [Fill("ORD-1", SYMBOL, +1, 82.42, "mock_broker")],
        )

        self.assertFalse(result.passed)
        self.assertEqual(result.portfolio_position, 0)
        self.assertEqual(result.broker_position, +1)
        self.assertIn("position mismatch", result.message)


if __name__ == "__main__":
    unittest.main()
