#!/usr/bin/env python3
"""Entry point for the trading infrastructure proof artifact."""

from __future__ import annotations

import argparse

from interview_demo.runner import (
    run_execution_scenario,
    run_full_demo,
    run_market_signal_scenario,
    run_netting_scenario,
    run_partial_fill_scenario,
    run_provider_reject_scenario,
    run_reconciliation_scenario,
    run_reconciliation_mismatch_scenario,
    run_risk_reject_scenario,
    run_trace_replay_scenario,
    run_unexpected_provider_state_scenario,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the self-contained trading infrastructure proof artifact."
    )
    parser.add_argument(
        "scenario",
        nargs="?",
        default="full",
        choices=[
            "full",
            "market-signal",
            "netting",
            "execution",
            "reconciliation",
            "risk-reject",
            "provider-reject",
            "partial-fill",
            "reconciliation-mismatch",
            "trace-replay",
            "unexpected-provider-state",
        ],
        help="Scenario to run. Defaults to the full end-to-end demo.",
    )
    parser.add_argument(
        "--step",
        action="store_true",
        help="Pause at key boundaries for an operator-console walkthrough.",
    )
    args = parser.parse_args()

    runners = {
        "full": run_full_demo,
        "market-signal": run_market_signal_scenario,
        "netting": run_netting_scenario,
        "execution": run_execution_scenario,
        "reconciliation": run_reconciliation_scenario,
        "risk-reject": run_risk_reject_scenario,
        "provider-reject": run_provider_reject_scenario,
        "partial-fill": run_partial_fill_scenario,
        "reconciliation-mismatch": run_reconciliation_mismatch_scenario,
        "trace-replay": run_trace_replay_scenario,
        "unexpected-provider-state": run_unexpected_provider_state_scenario,
    }
    runners[args.scenario](step=args.step)


if __name__ == "__main__":
    main()
