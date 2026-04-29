from __future__ import annotations

from dataclasses import dataclass

from interview_demo.models import Fill


@dataclass(frozen=True)
class ReconciliationResult:
    passed: bool
    portfolio_position: int
    broker_position: int
    message: str


def reconcile_positions(portfolio_position: int, broker_fills: list[Fill]) -> ReconciliationResult:
    broker_position = sum(fill.qty for fill in broker_fills)
    if portfolio_position == broker_position:
        return ReconciliationResult(
            passed=True,
            portfolio_position=portfolio_position,
            broker_position=broker_position,
            message="portfolio position matches broker-confirmed fills",
        )
    return ReconciliationResult(
        passed=False,
        portfolio_position=portfolio_position,
        broker_position=broker_position,
        message="position mismatch: investigate fills, state mutation, or data snapshot",
    )
