"""Standalone utility functions for AI engine message processing.

These functions are extracted for testability - they have no PyTorch dependencies
and can be tested without mocking.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import List

import numpy as np


@dataclass
class ProcessingContext:
    """Context passed through processing pipeline."""

    channel_start: int = 0
    channel_step: int = 1
    timestamps_ns: List[int] = field(default_factory=list)
    counting_buffer: deque = field(default_factory=lambda: deque(maxlen=1))
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
    messages: List, ctx: ProcessingContext, expected_sampling_rate: float, log_fn=None
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

    data_list = []
    timestamp_ns_list = []

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


def create_speed_messages(
    fiber_id: str,
    filtered_speeds: np.ndarray,
    timestamps_ns: List[int],
    ctx: ProcessingContext,
    min_speed_kmh: float,
    max_speed_kmh: float,
    sampling_rate_hz: float,
    service_name: str,
    log_fn=None,
) -> List:
    """Create speed messages from filtered speeds array."""
    from shared.message import Message
    from shared.time_utils import current_time_nanoseconds, sample_duration_nanoseconds

    messages = []

    if len(filtered_speeds.shape) == 3:
        num_sections, num_channels, num_time_points = filtered_speeds.shape
        total_spatial_points = num_sections * num_channels
    else:
        num_sections, num_time_points = filtered_speeds.shape
        num_channels = 1
        total_spatial_points = num_sections

    channel_start = ctx.channel_start
    channel_step = ctx.channel_step
    total_measurements = 0
    non_zero_measurements = 0

    if not ctx.logged_channel_example:
        ctx.logged_channel_example = True
        example_channels = [
            channel_start + (i * channel_step) for i in range(min(10, total_spatial_points))
        ]
        if log_fn:
            log_fn(
                f"Speed channel output example: first 10 channels = {example_channels} (step={channel_step})"
            )

    for time_idx in range(num_time_points):
        if len(filtered_speeds.shape) == 3:
            speeds_at_time = filtered_speeds[:, :, time_idx].flatten()
        else:
            speeds_at_time = filtered_speeds[:, time_idx]

        speeds = []
        for channel_idx, speed in enumerate(speeds_at_time):
            total_measurements += 1
            # Preserve sign for direction, but validate using absolute value
            abs_speed = abs(speed) if not np.isnan(speed) else float("nan")
            if not np.isnan(abs_speed) and min_speed_kmh <= abs_speed <= max_speed_kmh:
                actual_channel = channel_start + (channel_idx * channel_step)
                # Store signed speed to preserve direction
                speeds.append({"channel_number": actual_channel, "speed": float(speed)})
                non_zero_measurements += 1

        if not speeds:
            continue

        if timestamps_ns and time_idx < len(timestamps_ns):
            timestamp_ns = timestamps_ns[time_idx]
        elif timestamps_ns:
            last_ts = timestamps_ns[-1]
            sample_duration = sample_duration_nanoseconds(sampling_rate_hz)
            timestamp_ns = last_ts + ((time_idx - len(timestamps_ns) + 1) * sample_duration)
        else:
            timestamp_ns = current_time_nanoseconds()

        payload = {
            "fiber_id": fiber_id,
            "timestamp_ns": timestamp_ns,
            "speeds": speeds,
            "channel_start": channel_start,
            "ai_metadata": {
                "engine_version": "1.0",
                "spatial_points": total_spatial_points,
                "time_index": time_idx,
            },
        }

        messages.append(
            Message(
                id=fiber_id,
                payload=payload,
                headers={
                    "source": "ai_engine",
                    "fiber_id": fiber_id,
                    "time_idx": str(time_idx),
                    "engine_id": service_name,
                },
            )
        )

    if total_measurements > 0 and log_fn:
        compression = (1 - non_zero_measurements / total_measurements) * 100
        log_fn(
            f"Speed filtering: {non_zero_measurements}/{total_measurements} ({compression:.1f}% reduction)"
        )

    return messages


def create_count_messages(
    fiber_id: str,
    count_results: tuple,
    ctx: ProcessingContext,
    sampling_rate_hz: float,
    channels_per_section: int,
    counting_samples: int,
    step_samples: int,
    service_name: str,
    log_fn=None,
) -> List:
    """Create count messages from counting results."""
    from shared.message import Message
    from shared.time_utils import current_time_nanoseconds, sample_duration_nanoseconds

    messages = []
    counts, intervals, window_timestamps = count_results

    new_data_start = counting_samples - step_samples
    window_start_ns = window_timestamps[0] if window_timestamps else current_time_nanoseconds()

    base_channel_start = ctx.channel_start
    channel_step = ctx.channel_step

    total_intervals = sum(len(c) if c is not None else 0 for c in counts)
    total_filtered_out = 0

    for section_idx, (section_counts, section_intervals) in enumerate(zip(counts, intervals)):
        if section_counts is None or len(section_counts) == 0:
            continue

        if len(section_intervals) != 2:
            continue

        starts, ends = section_intervals

        for count, start, end in zip(section_counts, starts, ends):
            if start < new_data_start:
                total_filtered_out += 1
                continue
            if count <= 0:
                total_filtered_out += 1
                continue

            if start < len(window_timestamps):
                count_timestamp_ns = window_timestamps[start]
            else:
                sample_duration = sample_duration_nanoseconds(sampling_rate_hz)
                count_timestamp_ns = window_start_ns + int(start * sample_duration)

            count_timestamp_ns = round(count_timestamp_ns / 1_000_000_000) * 1_000_000_000

            section_array_start = section_idx * channels_per_section
            section_array_end = section_array_start + (channels_per_section - 1)
            actual_channel_start = base_channel_start + (section_array_start * channel_step)
            actual_channel_end = base_channel_start + (section_array_end * channel_step)

            messages.append(
                Message(
                    id=fiber_id,
                    payload={
                        "fiber_id": fiber_id,
                        "channel_start": int(actual_channel_start),
                        "channel_end": int(actual_channel_end),
                        "count_timestamp_ns": count_timestamp_ns,
                        "vehicle_count": float(count),
                        "engine_version": "1.0",
                        "model_type": "neural_network",
                    },
                    headers={
                        "source": "ai_engine_count",
                        "fiber_id": fiber_id,
                        "channel_start": str(actual_channel_start),
                        "channel_end": str(actual_channel_end),
                        "engine_id": service_name,
                    },
                    output_id="counting",
                )
            )

    if log_fn:
        log_fn(
            f"Count message creation: {total_intervals} total intervals → {total_filtered_out} filtered out → {len(messages)} messages sent"
        )

    if messages and log_fn:
        log_fn(f"Created {len(messages)} vehicle count messages")

    return messages
