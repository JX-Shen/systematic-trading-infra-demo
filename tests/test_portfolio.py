from __future__ import annotations

import unittest

from interview_demo.models import Signal, SignalSide, SYMBOL
from interview_demo.portfolio import PortfolioManager


class PortfolioTests(unittest.TestCase):
    def test_opposing_strategy_demand_nets_to_zero_provider_flow(self) -> None:
        portfolio = PortfolioManager()
        signals = [
            Signal("strategy_A", SYMBOL, SignalSide.BUY, "unit test"),
            Signal("strategy_B", SYMBOL, SignalSide.SELL, "unit test"),
        ]

        intents = portfolio.build_intents(signals)
        net_qty = sum(intent.delta_qty for intent in intents)
        portfolio.apply_intents(intents, fill_price=82.50, source="internal_netting")

        self.assertEqual(net_qty, 0)
        self.assertEqual(portfolio.aggregate_position, 0)
        self.assertEqual(portfolio.positions["strategy_A"].qty, +1)
        self.assertEqual(portfolio.positions["strategy_B"].qty, -1)

    def test_win_rate_tracks_closed_profitable_trades(self) -> None:
        portfolio = PortfolioManager()
        open_signal = [Signal("strategy_A", SYMBOL, SignalSide.BUY, "open")]
        close_signal = [Signal("strategy_A", SYMBOL, SignalSide.FLAT, "close")]

        portfolio.apply_intents(
            portfolio.build_intents(open_signal),
            fill_price=82.00,
            source="provider_fill",
        )
        portfolio.apply_intents(
            portfolio.build_intents(close_signal),
            fill_price=83.00,
            source="provider_fill",
        )

        self.assertEqual(portfolio.closed_trades, 1)
        self.assertEqual(portfolio.winning_trades, 1)
        self.assertEqual(portfolio.win_rate, 1.0)


if __name__ == "__main__":
    unittest.main()
