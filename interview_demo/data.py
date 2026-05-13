from __future__ import annotations

import csv
from datetime import datetime, timedelta
from pathlib import Path

from interview_demo.models import SYMBOL, Bar


CSV_PATH = Path(__file__).parent / "data" / "market_fixture_5m.csv"


def load_fixture_bars() -> tuple[list[Bar], str]:
    """Load a local 5-minute fixture CSV, with a deterministic fallback."""
    if CSV_PATH.exists():
        return _load_csv(CSV_PATH), f"local csv: {CSV_PATH}"
    return _fixture_bars(), "deterministic local 5m market fixture"


def _load_csv(path: Path) -> list[Bar]:
    bars: list[Bar] = []
    with path.open(newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            timestamp_text = row.get("timestamp") or row.get("datetime") or row.get("time")
            if not timestamp_text:
                raise ValueError("CSV needs a timestamp, datetime, or time column")
            bars.append(
                Bar(
                    timestamp=_parse_timestamp(timestamp_text),
                    symbol=row.get("symbol") or SYMBOL,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=int(float(row.get("volume") or 0)),
                )
            )
    if not bars:
        raise ValueError(f"No bars loaded from {path}")
    return bars


def _parse_timestamp(value: str) -> datetime:
    value = value.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    return datetime.fromisoformat(value)


def _fixture_bars() -> list[Bar]:
    # Hand-shaped 5-minute bars. The path is deterministic by design:
    # it triggers momentum, mean-reversion, reversal, netting, and exits.
    closes = [
        82.10,
        82.22,
        82.35,
        82.55,
        82.90,
        83.25,
        83.05,
        82.70,
        82.10,
        81.35,
        80.85,
        81.05,
        81.55,
        82.20,
        82.95,
        83.45,
        83.10,
        82.40,
        81.70,
        81.95,
        82.60,
        83.30,
        83.85,
        83.20,
        82.45,
        81.80,
        82.15,
        82.90,
        83.60,
        84.10,
    ]
    start = datetime(2026, 3, 2, 9, 0)
    bars: list[Bar] = []
    previous = closes[0]
    for index, close in enumerate(closes):
        timestamp = start + timedelta(minutes=5 * index)
        open_price = previous
        high = max(open_price, close) + 0.08
        low = min(open_price, close) - 0.08
        bars.append(
            Bar(
                timestamp=timestamp,
                symbol=SYMBOL,
                open=round(open_price, 2),
                high=round(high, 2),
                low=round(low, 2),
                close=round(close, 2),
                volume=1200 + index * 17,
            )
        )
        previous = close
    return bars
