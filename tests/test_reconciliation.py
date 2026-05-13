from __future__ import annotations

import unittest

from interview_demo.models import Fill, SYMBOL
from interview_demo.reconciliation import ReconciliationStatus, reconcile_positions


class ReconciliationTests(unittest.TestCase):
    def test_matching_portfolio_and_provider_position_passes(self) -> None:
        result = reconcile_positions(
            +1,
            [
                Fill("ORD-1", SYMBOL, +1, 82.42, "provider_fill"),
                Fill("ORD-2", SYMBOL, -1, 82.90, "provider_fill"),
                Fill("ORD-3", SYMBOL, +1, 83.00, "provider_fill"),
            ],
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.provider_position, +1)
        self.assertEqual(result.status, ReconciliationStatus.MATCH)
        self.assertEqual(result.suspected_source, "none")
        self.assertEqual(result.diff, 0)

    def test_position_mismatch_fails(self) -> None:
        result = reconcile_positions(
            0,
            [Fill("ORD-1", SYMBOL, +1, 82.42, "provider_fill")],
        )

        self.assertFalse(result.passed)
        self.assertEqual(result.portfolio_position, 0)
        self.assertEqual(result.provider_position, +1)
        self.assertIn("position mismatch", result.message)
        self.assertEqual(result.status, ReconciliationStatus.MISMATCH)
        self.assertEqual(result.diff, -1)

    def test_mismatch_identifies_provider_state_drift(self) -> None:
        result = reconcile_positions(
            portfolio_position=+1,
            provider_fills=[Fill("ORD-1", SYMBOL, +1, 82.42, "provider_fill")],
            provider_state_position=+2,
            related_event_ids=[4, 5],
        )

        self.assertFalse(result.passed)
        self.assertEqual(result.suspected_source, "provider_state_drift_or_stale_callback")
        self.assertEqual(result.related_event_ids, (4, 5))


if __name__ == "__main__":
    unittest.main()
