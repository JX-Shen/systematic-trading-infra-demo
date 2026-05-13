from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from interview_demo.events import EventLog, replay_provider_confirmed_position


class EventLogTests(unittest.TestCase):
    def test_event_log_preserves_order_and_related_ids(self) -> None:
        event_log = EventLog()

        first = event_log.append("market_event_loaded", {"symbol": "FIXTURE"})
        second = event_log.append(
            "signal_emitted",
            {"strategy_id": "scenario"},
            related_event_ids=[first.event_id],
        )

        self.assertEqual([event.event_id for event in event_log.events], [1, 2])
        self.assertEqual(second.related_event_ids, (1,))

    def test_jsonl_trace_round_trips_and_replays_provider_position(self) -> None:
        event_log = EventLog()
        event_log.append("provider_callback", {"filled_qty": +2})
        event_log.append(
            "provider_callback",
            {"filled_qty": -1, "provider_confirmed_position": +1},
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "events.jsonl"
            event_log.write_jsonl(path)

            loaded = EventLog.load_jsonl(path)

        self.assertEqual([event.event_id for event in loaded.events], [1, 2])
        self.assertEqual(replay_provider_confirmed_position(loaded), +1)


if __name__ == "__main__":
    unittest.main()
