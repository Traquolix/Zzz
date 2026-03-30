"""Standalone utility functions for AI engine message processing.

These functions are extracted for testability - they have no PyTorch dependencies
and can be tested without mocking.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# Version constants
ENGINE_VERSION = "1.0"


@dataclass
class ProcessingContext:
    """Context passed through processing pipeline."""

    channel_start: int = 0
    channel_step: int = 1
    timestamps_ns: list[int] = field(default_factory=list)
    logged_channel_example: bool = False


def extract_channel_metadata(payload: dict) -> tuple[int, int]:
    """Extract channel_start and channel_step from message payload."""
    channel_start = payload.get("channel_start", 0)
    processing_metadata = payload.get("processing_metadata", {})
    channel_selection = (
        processing_metadata.get("channel_selection") if processing_metadata else None
    )
    channel_step = (channel_selection.get("step", 1) if channel_selection else 1) or 1
    return channel_start, channel_step


def validate_sampling_rate(payload: dict, expected_rate: float) -> None:
    """Validate that incoming sampling rate matches expected rate."""
    rate = payload.get("sampling_rate_hz")
    if rate is not None and abs(float(rate) - expected_rate) > 0.1:
        raise ValueError(f"AI engine expects {expected_rate}Hz but received {rate}Hz")


def messages_to_arrays(
    messages: list, ctx: ProcessingContext, expected_sampling_rate: float, log_fn=None
) -> tuple:
    """Convert list of messages to numpy arrays for inference."""
    from shared.time_utils import (
        current_time_nanoseconds,
        nanoseconds_to_datetime,
        sample_duration_nanoseconds,
    )

    if not messages:
        ctx.channel_start = 0
        ctx.channel_step = 1
        return np.array([]).T, [], []

    first_payload = messages[0].payload
    channel_start, channel_step = extract_channel_metadata(first_payload)
    ctx.channel_start = channel_start
    ctx.channel_step = channel_step
    validate_sampling_rate(first_payload, expected_sampling_rate)

    if log_fn:
        log_fn(f"Channel mapping: start={channel_start}, step={channel_step}")

    data_list: list[list] = []
    timestamp_ns_list: list[int] = []

    for message in messages:
        payload = message.payload
        values = payload.get("values", [])
        if not values:
            continue

        if data_list and len(values) != len(data_list[0]):
            raise ValueError(
                f"Channel count mismatch: expected {len(data_list[0])}, got {len(values)}"
            )

        msg_channel_start = payload.get("channel_start")
        if msg_channel_start is not None and msg_channel_start != channel_start:
            raise ValueError(
                f"channel_start mismatch: expected {channel_start}, got {msg_channel_start}"
            )

        data_list.append(values)
        timestamp_ns = payload.get("timestamp_ns")
        if timestamp_ns is None or timestamp_ns <= 0:
            if len(data_list) == 1 and log_fn:
                log_fn("Missing timestamps, using fallback")
            sample_duration = sample_duration_nanoseconds(expected_sampling_rate)
            timestamp_ns = current_time_nanoseconds() - len(data_list) * sample_duration
        timestamp_ns_list.append(timestamp_ns)

    ctx.timestamps_ns = timestamp_ns_list
    data_array = np.array(data_list).T
    timestamp_list = [nanoseconds_to_datetime(ts) for ts in timestamp_ns_list]
    return data_array, timestamp_list, timestamp_ns_list


def create_detection_messages(
    fiber_id: str,
    detections: list[dict],
    ctx: ProcessingContext,
    service_name: str,
    log_fn=None,
) -> list:
    """Create a single batched detection message per call.

    All detections for a section/window are packed into one Kafka message
    with a ``detections`` array, reducing message rate from ~500/s to ~11/s.

    Args:
        detections: List of dicts with keys:
            section_idx, speed_kmh, direction, timestamp_ns, glrt_max,
            vehicle_count, n_cars, n_trucks
        ctx: ProcessingContext with channel_start and channel_step
    """
    from shared.message import Message
    from shared.time_utils import current_time_nanoseconds

    if not detections:
        return []

    channel_start = ctx.channel_start
    channel_step = ctx.channel_step

    det_records = []
    for det in detections:
        actual_channel = channel_start + (det["section_idx"] * channel_step)
        timestamp_ns = det.get("timestamp_ns") or current_time_nanoseconds()

        det_records.append(
            {
                "timestamp_ns": timestamp_ns,
                "channel": actual_channel,
                "speed_kmh": det["speed_kmh"],
                "direction": det["direction"],
                "vehicle_count": det.get("vehicle_count", 1.0),
                "n_cars": det.get("n_cars", 1.0),
                "n_trucks": det.get("n_trucks", 0.0),
                "glrt_max": det.get("glrt_max", 0.0),
            }
        )

    payload = {
        "fiber_id": fiber_id,
        "engine_version": ENGINE_VERSION,
        "detections": det_records,
    }

    messages = [
        Message(
            id=fiber_id,
            payload=payload,
            headers={
                "source": "ai_engine",
                "fiber_id": fiber_id,
                "engine_id": service_name,
            },
            output_id="default",
        )
    ]

    if log_fn:
        n_fwd = sum(1 for d in detections if d["direction"] == 0)
        n_rev = sum(1 for d in detections if d["direction"] == 1)
        total_count = sum(d.get("vehicle_count", 1) for d in detections)
        log_fn(
            f"Detections: {len(det_records)} intervals ({n_fwd} fwd, {n_rev} rev), "
            f"{total_count:.0f} vehicles total"
        )

    return messages
