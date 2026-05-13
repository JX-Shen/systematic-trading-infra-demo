from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EventRecord:
    event_id: int
    event_type: str
    timestamp: str
    payload: dict[str, Any]
    related_event_ids: tuple[int, ...] = ()


class EventLog:
    def __init__(self) -> None:
        self._next_event_id = 1
        self.events: list[EventRecord] = []

    def append(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
        related_event_ids: list[int] | tuple[int, ...] | None = None,
    ) -> EventRecord:
        record = EventRecord(
            event_id=self._next_event_id,
            event_type=event_type,
            timestamp=datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            payload=payload or {},
            related_event_ids=tuple(related_event_ids or ()),
        )
        self.events.append(record)
        self._next_event_id += 1
        return record

    def to_jsonl(self) -> str:
        return "\n".join(json.dumps(asdict(event), sort_keys=True) for event in self.events) + "\n"

    def write_jsonl(self, path: str | Path) -> Path:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(self.to_jsonl(), encoding="utf-8")
        return output_path

    @classmethod
    def load_jsonl(cls, path: str | Path) -> EventLog:
        event_log = cls()
        event_log.events = []
        max_event_id = 0
        for raw_line in Path(path).read_text(encoding="utf-8").splitlines():
            if not raw_line.strip():
                continue
            data = json.loads(raw_line)
            event = EventRecord(
                event_id=int(data["event_id"]),
                event_type=str(data["event_type"]),
                timestamp=str(data["timestamp"]),
                payload=dict(data.get("payload", {})),
                related_event_ids=tuple(int(event_id) for event_id in data.get("related_event_ids", ())),
            )
            event_log.events.append(event)
            max_event_id = max(max_event_id, event.event_id)
        event_log._next_event_id = max_event_id + 1
        return event_log


def replay_provider_confirmed_position(event_log: EventLog) -> int:
    provider_position = 0
    for event in event_log.events:
        if event.event_type != "provider_callback":
            continue
        payload = event.payload
        if "provider_confirmed_position" in payload and payload["provider_confirmed_position"] is not None:
            provider_position = int(payload["provider_confirmed_position"])
            continue
        provider_position += int(payload.get("filled_qty", 0))
    return provider_position
