from __future__ import annotations

from math import sqrt
from statistics import mean, pstdev


def max_drawdown(equity_curve: list[float]) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    worst = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        worst = min(worst, value - peak)
    return worst


def sharpe_like(equity_curve: list[float]) -> float:
    if len(equity_curve) < 3:
        return 0.0
    returns = [
        equity_curve[index] - equity_curve[index - 1]
        for index in range(1, len(equity_curve))
    ]
    volatility = pstdev(returns)
    if volatility == 0:
        return 0.0
    return mean(returns) / volatility * sqrt(len(returns))
