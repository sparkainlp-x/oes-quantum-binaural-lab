"""Classical-only OES/control summary projection."""
from __future__ import annotations

from .bus import EventBus, OESControlPlane


def publish_metric_summary(bus: EventBus, lane: str, values: dict[str, int | float]) -> None:
    """Publish scalar reported metrics for cross-lane consumers."""
    if lane not in {"quantum_sandbox", "stereo_binaural"}:
        raise ValueError("only simulation lane summaries may be projected")
    for name, value in values.items():
        if not isinstance(value, (int, float)):
            continue
        bus.publish(lane, "reported_metric", {"metric_name": str(name), "metric_value": float(value)})


def build_control_ledger(bus: EventBus, capacity: int = 1024) -> dict:
    """Build OES slots only from timestamped scalar events on the shared bus."""
    metric_events = [
        event
        for lane in ("quantum_sandbox", "stereo_binaural")
        for event in bus.read(lane)
        if event.event_type == "reported_metric"
    ]
    metrics: list[tuple[str, str, float]] = []
    for event in metric_events:
        name = event.payload.get("metric_name")
        value = event.payload.get("metric_value")
        if not isinstance(name, str) or not isinstance(value, (int, float)):
            raise TypeError("bus lane summaries must contain scalar metric_name/metric_value fields")
        metrics.append((event.lane, name, float(value)))
    plane = OESControlPlane(bus, capacity=capacity)
    count = plane.fill_metric_slots(metrics)
    lane_counts = {lane: sum(1 for slot in plane.slots if slot.source_lane == lane) for lane in ("quantum_sandbox", "stereo_binaural")}
    return {
        "capacity_slots": capacity,
        "occupied_slots": count,
        "slot_events_published": count,
        "source_lane_counts": lane_counts,
        "slot_semantics": "classical metrics ledger: scalar measurements/reported metrics only; 1,024 slots are a modeling choice, not an OES detector or physical interpretation of 1,024 interactions",
        "raw_quantum_states_in_oes": False,
        "audio_waveforms_in_oes": False,
        "input_source": "timestamped quantum/audio summary events on the classical event bus only",
    }
