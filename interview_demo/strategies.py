from __future__ import annotations

from collections import deque
from statistics import mean

from interview_demo.models import Bar, Signal, SignalSide


class Strategy:
    strategy_id: str

    def on_bar(self, bar: Bar) -> Signal | None:
        raise NotImplementedError


class MomentumCrossStrategy(Strategy):
    strategy_id = "dummy1_momentum"

    def __init__(self, fast: int = 3, slow: int = 5) -> None:
        self.fast = fast
        self.slow = slow
        self.closes: deque[float] = deque(maxlen=slow)
        self.last_side = SignalSide.FLAT

    def on_bar(self, bar: Bar) -> Signal | None:
        self.closes.append(bar.close)
        if len(self.closes) < self.slow:
            return None

        fast_mean = mean(list(self.closes)[-self.fast :])
        slow_mean = mean(self.closes)
        side = SignalSide.BUY if fast_mean > slow_mean else SignalSide.SELL
        if side == self.last_side:
            return None

        self.last_side = side
        return Signal(
            self.strategy_id,
            bar.symbol,
            side,
            f"fast_ma={fast_mean:.2f} vs slow_ma={slow_mean:.2f}",
        )


class MeanReversionStrategy(Strategy):
    strategy_id = "dummy2_meanrev"

    def __init__(self, window: int = 5, threshold: float = 0.007, exit_band: float = 0.002) -> None:
        self.window = window
        self.threshold = threshold
        self.exit_band = exit_band
        self.closes: deque[float] = deque(maxlen=window)
        self.last_side = SignalSide.FLAT

    def on_bar(self, bar: Bar) -> Signal | None:
        self.closes.append(bar.close)
        if len(self.closes) < self.window:
            return None

        anchor = mean(self.closes)
        deviation = (bar.close - anchor) / anchor
        if deviation > self.threshold:
            side = SignalSide.SELL
        elif deviation < -self.threshold:
            side = SignalSide.BUY
        elif abs(deviation) < self.exit_band:
            side = SignalSide.FLAT
        else:
            return None

        if side == self.last_side:
            return None

        self.last_side = side
        return Signal(
            self.strategy_id,
            bar.symbol,
            side,
            f"deviation={deviation:.2%} from rolling_mean={anchor:.2f}",
        )


class ScheduledReversalStrategy(Strategy):
    strategy_id = "dummy3_reversal"

    def __init__(self, interval: int = 7) -> None:
        self.interval = interval
        self.bar_count = 0
        self.last_side = SignalSide.FLAT

    def on_bar(self, bar: Bar) -> Signal | None:
        self.bar_count += 1
        if self.bar_count % self.interval != 0:
            return None

        if self.last_side == SignalSide.BUY:
            side = SignalSide.SELL
        elif self.last_side == SignalSide.SELL:
            side = SignalSide.FLAT
        else:
            side = SignalSide.BUY

        self.last_side = side
        return Signal(
            self.strategy_id,
            bar.symbol,
            side,
            f"scheduled check every {self.interval} bars",
        )


def default_strategies() -> list[Strategy]:
    return [
        MomentumCrossStrategy(),
        MeanReversionStrategy(),
        ScheduledReversalStrategy(),
    ]
