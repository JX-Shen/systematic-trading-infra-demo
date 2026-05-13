from __future__ import annotations

from dataclasses import dataclass, field

from interview_demo.models import OrderIntent


@dataclass(frozen=True)
class RiskRejectResult:
    code: str
    message: str
    current_position: int
    requested_qty: int
    projected_position: int


@dataclass(frozen=True)
class RiskDecision:
    accepted: bool
    reject: RiskRejectResult | None = None

    @property
    def code(self) -> str:
        if self.accepted:
            return "accepted"
        return self.reject.code if self.reject else "rejected"

    @property
    def message(self) -> str:
        if self.accepted:
            return "risk checks passed"
        return self.reject.message if self.reject else "risk checks rejected"


@dataclass
class RiskGate:
    max_aggregate_position: int
    max_order_size: int
    enabled_symbols: set[str] = field(default_factory=set)
    session_enabled: bool = True

    def evaluate(self, intent: OrderIntent, current_aggregate_position: int) -> RiskDecision:
        projected_position = current_aggregate_position + intent.qty
        if not self.session_enabled:
            return RiskDecision(
                accepted=False,
                reject=RiskRejectResult(
                    code="session_disabled",
                    message="risk gate rejected order: session is disabled",
                    current_position=current_aggregate_position,
                    requested_qty=intent.qty,
                    projected_position=projected_position,
                ),
            )

        if self.enabled_symbols and intent.symbol not in self.enabled_symbols:
            return RiskDecision(
                accepted=False,
                reject=RiskRejectResult(
                    code="symbol_disabled",
                    message="risk gate rejected order: symbol is not enabled",
                    current_position=current_aggregate_position,
                    requested_qty=intent.qty,
                    projected_position=projected_position,
                ),
            )

        if abs(intent.qty) > self.max_order_size:
            return RiskDecision(
                accepted=False,
                reject=RiskRejectResult(
                    code="max_order_size_exceeded",
                    message="risk gate rejected order: max order size exceeded",
                    current_position=current_aggregate_position,
                    requested_qty=intent.qty,
                    projected_position=projected_position,
                ),
            )

        if abs(projected_position) > self.max_aggregate_position:
            return RiskDecision(
                accepted=False,
                reject=RiskRejectResult(
                    code="max_aggregate_position_exceeded",
                    message="risk gate rejected order: max aggregate position exceeded",
                    current_position=current_aggregate_position,
                    requested_qty=intent.qty,
                    projected_position=projected_position,
                ),
            )

        return RiskDecision(accepted=True)
