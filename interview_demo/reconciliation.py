from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from interview_demo.models import Fill


class ReconciliationStatus(str, Enum):
    MATCH = "match"
    MISMATCH = "mismatch"


@dataclass(frozen=True)
class ReconciliationReport:
    target_position: int
    provider_state_position: int
    diff: int
    status: ReconciliationStatus
    suspected_source: str
    message: str
    related_event_ids: tuple[int, ...] = ()

    @property
    def passed(self) -> bool:
        return self.status == ReconciliationStatus.MATCH

    @property
    def portfolio_position(self) -> int:
        return self.target_position

    @property
    def provider_position(self) -> int:
        return self.provider_state_position


def reconcile_positions(
    portfolio_position: int,
    provider_fills: list[Fill],
    provider_state_position: int | None = None,
    related_event_ids: list[int] | None = None,
) -> ReconciliationReport:
    provider_fills_position = sum(fill.qty for fill in provider_fills)
    provider_position = (
        provider_fills_position if provider_state_position is None else provider_state_position
    )
    diff = portfolio_position - provider_position
    status = ReconciliationStatus.MATCH if diff == 0 else ReconciliationStatus.MISMATCH

    if provider_state_position is not None and provider_state_position != provider_fills_position:
        suspected_source = "provider_state_drift_or_stale_callback"
    elif diff != 0:
        suspected_source = "portfolio_state_mutation_or_missing_fill"
    else:
        suspected_source = "none"

    if status == ReconciliationStatus.MATCH:
        message = "portfolio target matches provider-confirmed state"
    else:
        message = "position mismatch: investigate portfolio state, provider callbacks, or reconciliation timing"

    return ReconciliationReport(
        target_position=portfolio_position,
        provider_state_position=provider_position,
        diff=diff,
        status=status,
        suspected_source=suspected_source,
        message=message,
        related_event_ids=tuple(related_event_ids or ()),
    )
