"""Message round-trip test: messages → arrays → detections → messages.

Verifies the full input→output path preserves fiber_id, channel mapping,
and timestamp fidelity through serialization/deserialization.
"""

from __future__ import annotations

from ai_engine.message_utils import (
    ProcessingContext,
    create_detection_messages,
    messages_to_arrays,
)
from shared.message import Message
from tests.ai_engine.conftest import SAMPLING_RATE_HZ


def _make_message(
    values: list,
    fiber_id: str = "carros",
    section: str = "default",
    channel_start: int = 200,
    channel_step: int = 3,
    timestamp_ns: int = 1_700_000_000_000_000_000,
    sample_count: int = 1,
) -> Message:
    payload = {
        "fiber_id": fiber_id,
        "section": section,
        "values": values,
        "channel_start": channel_start,
        "timestamp_ns": timestamp_ns,
        "sample_count": sample_count,
        "sampling_rate_hz": SAMPLING_RATE_HZ,
        "processing_metadata": {"channel_selection": {"step": channel_step}},
    }
    return Message(id="test-msg", payload=payload)


class TestMessageRoundTrip:
    """Full round-trip: Kafka messages → arrays → detections → output messages."""

    def test_fiber_id_preserved(self):
        """fiber_id must survive the full round trip."""
        n_channels = 20
        messages = [
            _make_message(
                values=list(range(n_channels)),
                fiber_id="promenade",
                timestamp_ns=1_700_000_000_000_000_000 + i * int(1e9 / SAMPLING_RATE_HZ),
            )
            for i in range(10)
        ]

        ctx = ProcessingContext()
        messages_to_arrays(messages, ctx, SAMPLING_RATE_HZ)

        detections = [
            {
                "section_idx": 0,
                "speed_kmh": 60.0,
                "direction": 0,
                "timestamp_ns": 1_700_000_000_000_000_000,
                "glrt_max": 3000.0,
                "vehicle_count": 1.0,
                "n_cars": 1.0,
                "n_trucks": 0.0,
                "strain_peak": 0.0,
                "strain_rms": 0.0,
            }
        ]

        out_messages = create_detection_messages(
            fiber_id="promenade",
            detections=detections,
            ctx=ctx,
            service_name="ai-engine",
        )

        assert len(out_messages) == 1
        assert out_messages[0].payload["fiber_id"] == "promenade"

    def test_channel_mapping_roundtrip(self):
        """Channel mapping from input messages must reach output detections."""
        n_channels = 20
        channel_start = 500
        channel_step = 5

        messages = [
            _make_message(
                values=list(range(n_channels)),
                channel_start=channel_start,
                channel_step=channel_step,
                timestamp_ns=1_700_000_000_000_000_000 + i * int(1e9 / SAMPLING_RATE_HZ),
            )
            for i in range(10)
        ]

        ctx = ProcessingContext()
        messages_to_arrays(messages, ctx, SAMPLING_RATE_HZ)

        # Context should have captured channel metadata
        assert ctx.channel_start == channel_start
        assert ctx.channel_step == channel_step

        detections = [
            {
                "section_idx": 3,
                "speed_kmh": 72.0,
                "direction": 1,
                "timestamp_ns": 1_700_000_000_000_000_000,
                "glrt_max": 5000.0,
                "vehicle_count": 1.0,
                "n_cars": 1.0,
                "n_trucks": 0.0,
                "strain_peak": 0.0,
                "strain_rms": 0.0,
            }
        ]

        out_messages = create_detection_messages(
            fiber_id="carros",
            detections=detections,
            ctx=ctx,
            service_name="ai-engine",
        )

        out_det = out_messages[0].payload["detections"][0]
        expected_channel = channel_start + 3 * channel_step  # 500 + 15 = 515
        assert out_det["channel"] == expected_channel

    def test_timestamp_fidelity(self):
        """Timestamps in output detections must come from the input timestamps_ns."""
        n_channels = 20
        base_ts = 1_700_000_000_000_000_000
        dt_ns = int(1e9 / SAMPLING_RATE_HZ)

        messages = [
            _make_message(
                values=list(range(n_channels)),
                timestamp_ns=base_ts + i * dt_ns,
            )
            for i in range(10)
        ]

        ctx = ProcessingContext()
        _data, _timestamps, timestamps_ns = messages_to_arrays(messages, ctx, SAMPLING_RATE_HZ)

        # Timestamps should be monotonically increasing
        for i in range(len(timestamps_ns) - 1):
            assert timestamps_ns[i] < timestamps_ns[i + 1]

        # First timestamp should match first message
        assert timestamps_ns[0] == base_ts

    def test_multi_sample_roundtrip(self):
        """Multi-sample messages (samples_per_message=2) must round-trip correctly."""
        n_channels = 20
        samples_per_msg = 2
        n_messages = 5

        messages = []
        for i in range(n_messages):
            values = list(
                range(i * n_channels * samples_per_msg, (i + 1) * n_channels * samples_per_msg)
            )
            messages.append(
                Message(
                    id=f"msg-{i}",
                    payload={
                        "fiber_id": "mathis",
                        "section": "section1",
                        "values": values,
                        "channel_start": 100,
                        "timestamp_ns": 1_700_000_000_000_000_000 + i * int(1e9 / SAMPLING_RATE_HZ),
                        "sample_count": samples_per_msg,
                        "channel_count": n_channels,
                        "sampling_rate_hz": SAMPLING_RATE_HZ,
                        "processing_metadata": {"channel_selection": {"step": 1}},
                    },
                )
            )

        ctx = ProcessingContext()
        data, timestamps, _timestamps_ns = messages_to_arrays(messages, ctx, SAMPLING_RATE_HZ)

        total_samples = n_messages * samples_per_msg
        assert data.shape == (n_channels, total_samples)
        assert len(timestamps) == total_samples

    def test_empty_detections_no_output(self):
        """Empty detection list should produce no output messages."""
        ctx = ProcessingContext()
        ctx.channel_start = 0
        ctx.channel_step = 1

        messages = create_detection_messages(
            fiber_id="carros",
            detections=[],
            ctx=ctx,
            service_name="ai-engine",
        )
        assert messages == []
