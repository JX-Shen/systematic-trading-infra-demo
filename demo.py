#!/usr/bin/env python3
"""Entry point for the trading workflow demo."""

from __future__ import annotations

import argparse

from interview_demo.runner import (
    run_execution_scenario,
    run_full_demo,
    run_market_signal_scenario,
    run_netting_scenario,
    run_reconciliation_scenario,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the self-contained trading system demo."
    )
    parser.add_argument(
        "scenario",
        nargs="?",
        default="full",
        choices=["full", "market-signal", "netting", "execution", "reconciliation"],
        help="Scenario to run. Defaults to the full end-to-end demo.",
    )
    parser.add_argument(
        "--step",
        action="store_true",
        help="Pause at key boundaries so the demo can be walked through during screen share.",
    )
    args = parser.parse_args()

    runners = {
        "full": run_full_demo,
        "market-signal": run_market_signal_scenario,
        "netting": run_netting_scenario,
        "execution": run_execution_scenario,
        "reconciliation": run_reconciliation_scenario,
    }
    runners[args.scenario](step=args.step)


if __name__ == "__main__":
    main()
