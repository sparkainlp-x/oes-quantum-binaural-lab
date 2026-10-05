"""Timestamped classical event bus and classical metrics ledger slots.

The bus deliberately accepts scalar payloads only. String fields are short
label strings (length/pattern limited) so serialized arrays or waveforms cannot
cross lanes as text. It is an interface for reported measurements/metrics, not
quantum states, audio buffers, or samples.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
import re
from threading import RLock
from typing import Any, Iterable

LANES = frozenset({"oes_control", "quantum_sandbox", "stereo_binaural", "observer"})
SCALAR_TYPES = (str, int, float, bool, type(None))
MAX_LABEL_LEN = 64
LABEL_PATTERN = re.compile(r"^[A-Za-z0-9_./+\- ]+$")


@dataclass(frozen=True)
class Event:
    timestamp_utc: str
    lane: str
    event_type: str
    payload: dict[str, str | int | float | bool | None]


class EventBus:
    """In-memory append-only bus; events are classical scalar records."""

    def __init__(self) -> None:
        self._events: list[Event] = []
        self._lock = RLock()

    @staticmethod
    def _require_label(name: str, value: str) -> str:
        if len(value) > MAX_LABEL_LEN or not LABEL_PATTERN.fullmatch(value):
            raise ValueError(
                f"{name} must be a short label string "
                f"(1..{MAX_LABEL_LEN} chars; letters, digits, _./+- space only; "
                "no serialized arrays or free-form blobs)"
            )
        return value

    def publish(self, lane: str, event_type: str, payload: dict[str, Any]) -> Event:
        if lane not in LANES:
            raise ValueError(f"unknown lane label: {lane}")
        if not isinstance(payload, dict):
            raise TypeError("event payload must be a dictionary of scalar fields")
        event_type = self._require_label("event_type", str(event_type))
        safe: dict[str, str | int | float | bool | None] = {}
        for key, value in payload.items():
            if not isinstance(key, str) or not isinstance(value, SCALAR_TYPES):
                raise TypeError("event payloads may contain scalar fields only")
            key = self._require_label("payload key", key)
            if isinstance(value, float) and not isfinite(value):
                raise ValueError("event payload floats must be finite")
            if isinstance(value, str):
                value = self._require_label("payload string", value)
            safe[key] = value
        event = Event(
            timestamp_utc=datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            lane=lane,
            event_type=event_type,
            payload=safe,
        )
        with self._lock:
            self._events.append(event)
        return event

    def read(self, lane: str | None = None) -> tuple[Event, ...]:
        with self._lock:
            events = tuple(self._events)
        return events if lane is None else tuple(e for e in events if e.lane == lane)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


@dataclass(frozen=True)
class ControlSlot:
    slot_index: int
    source_lane: str
    metric_name: str
    metric_value: float


class OESControlPlane:
    """Classical metrics ledger (1,024 scalar slots); capacity is a modeling choice, not an OES detector."""

    def __init__(self, bus: EventBus, capacity: int = 1024) -> None:
        if capacity < 1:
            raise ValueError("capacity must be positive")
        self.bus = bus
        self.capacity = capacity
        self.slots: list[ControlSlot] = []

    def fill_metric_slots(self, metrics: Iterable[tuple[str, str, float]]) -> int:
        """Fill available slots by cycling scalar summaries, never raw lane data.

        ``metrics`` contains (source lane, metric name, scalar value) tuples.
        Cycling is only a capacity demonstration; it does not imply 1,024
        independent physical interactions.
        """
        available = list(metrics)
        if not available:
            raise ValueError("at least one reported metric is required")
        for lane, name, value in available:
            if lane not in {"quantum_sandbox", "stereo_binaural"}:
                raise ValueError("only quantum/audio summary metrics may enter OES")
            if not isinstance(name, str) or not isinstance(value, (int, float)):
                raise TypeError("OES slots accept named numeric metrics only")
            if not isfinite(float(value)):
                raise ValueError("OES metric values must be finite")
        while len(self.slots) < self.capacity:
            source_lane, metric_name, metric_value = available[len(self.slots) % len(available)]
            idx = len(self.slots)
            slot = ControlSlot(idx, source_lane, metric_name, float(metric_value))
            self.slots.append(slot)
            self.bus.publish(
                "oes_control",
                "metric_slot",
                {
                    "slot_index": idx,
                    "source_lane": source_lane,
                    "metric_name": metric_name,
                    "metric_value": float(metric_value),
                },
            )
        return len(self.slots)
