"""
Self-tuning replay buffer for AI engine detection results.

Detections arrive in bursts (inference windows). Instead of forwarding
them immediately, we replay each detection at:
    detection.timestamp + estimated_pipeline_delay

The pipeline delay is measured dynamically: when a detection arrives,
we observe (wall_clock - detection_timestamp) and maintain a rolling
estimate. A safety margin (default 15s) is added so detections never
appear "from the future" on the frontend.

If detections arrive late (pipeline hiccup), they are already overdue
and flush immediately — this provides automatic catch-up.

The drain loop pops due items and flushes at ~10 Hz.
"""

import asyncio
import contextlib
import heapq
import logging
import time
from collections import deque
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("sequoia.replay_buffer")

# Safety margin above observed pipeline delay
SAFETY_MARGIN_S = 15.0
# Initial estimate before we have observations
INITIAL_DELAY_S = 90.0
# Rolling window size for delay estimation
DELAY_WINDOW_SIZE = 50

# Type alias for the broadcast callback
BroadcastFn = Callable[[str, Any], Coroutine[Any, Any, None]]


@dataclass(order=True)
class ReplayItem:
    """Priority queue item ordered by replay wall-clock time."""

    replay_time: float
    sequence: int = field(compare=True)  # tie-breaker for same replay_time
    channel: str = field(compare=False)  # 'detections'
    data: Any = field(compare=False)  # transformed message payload


class ReplayBuffer:
    """
    Self-tuning replay buffer that measures pipeline delay and schedules
    detections for smooth, in-order playback as close to real-time as
    the pipeline permits.
    """

    def __init__(self):
        self._queue: list[ReplayItem] = []  # heapq min-heap
        self._sequence: int = 0
        self._event = asyncio.Event()
        self._running: bool = False
        self._last_sent_timestamp_ms: int = 0
        # Self-tuning delay estimation
        self._observed_delays: deque[float] = deque(maxlen=DELAY_WINDOW_SIZE)
        self._estimated_delay_s: float = INITIAL_DELAY_S

    @property
    def queue_size(self) -> int:
        return len(self._queue)

    @property
    def active_batches(self) -> int:
        """Kept for compatibility with cleanup_stale_batches calls."""
        return 0

    @property
    def last_sent_timestamp_ms(self) -> int:
        """Timestamp (ms) of the most recently sent detection."""
        return self._last_sent_timestamp_ms

    @property
    def estimated_delay_s(self) -> float:
        """Current estimated pipeline delay (including safety margin)."""
        return self._estimated_delay_s

    def _update_delay_estimate(self, timestamp_ns: int) -> None:
        """Update pipeline delay estimate from an observed detection."""
        now = time.time()
        original_time_s = timestamp_ns / 1e9
        observed_delay = now - original_time_s

        if observed_delay < 0:
            return  # Clock skew — ignore

        self._observed_delays.append(observed_delay)

        # Use the 90th percentile of recent observations + safety margin
        sorted_delays = sorted(self._observed_delays)
        p90_idx = int(len(sorted_delays) * 0.9)
        p90_delay = sorted_delays[min(p90_idx, len(sorted_delays) - 1)]
        new_estimate = p90_delay + SAFETY_MARGIN_S

        if abs(new_estimate - self._estimated_delay_s) > 5.0:
            logger.info(
                "Replay delay adjusted: %.1fs -> %.1fs (p90=%.1fs, margin=%.1fs, samples=%d)",
                self._estimated_delay_s,
                new_estimate,
                p90_delay,
                SAFETY_MARGIN_S,
                len(self._observed_delays),
            )
        self._estimated_delay_s = new_estimate

    def ingest_detection(self, section_key: str, timestamp_ns: int, detections: list[dict]) -> None:
        """
        Add a detection to the replay queue.

        Scheduled for: detection_timestamp + estimated_pipeline_delay.
        If already overdue (pipeline was slow), it will flush immediately
        on the next drain cycle.

        Args:
            section_key: "{fiber_id}:{channel}" identifying the section
            timestamp_ns: Original sample timestamp in nanoseconds
            detections: Transformed Detection[] dicts ready for frontend
        """
        if not detections:
            return

        self._update_delay_estimate(timestamp_ns)

        original_time_s = timestamp_ns / 1e9
        replay_time = original_time_s + self._estimated_delay_s

        self._sequence += 1
        heapq.heappush(
            self._queue,
            ReplayItem(
                replay_time=replay_time,
                sequence=self._sequence,
                channel="detections",
                data=detections,
            ),
        )
        self._event.set()

    async def drain(self, broadcast_fn: BroadcastFn) -> None:
        """
        Drain loop: pops items from the queue and broadcasts them
        at their scheduled replay times.

        Detections are accumulated and flushed at ~10 Hz (100ms batches).

        Args:
            broadcast_fn: async callback(channel: str, data: Any)
        """
        self._running = True
        detection_accumulator: list[dict] = []
        last_detection_flush = time.time()

        logger.info(
            "Replay buffer drain started (initial delay=%.0fs, margin=%.0fs)",
            INITIAL_DELAY_S,
            SAFETY_MARGIN_S,
        )

        while self._running:
            # Wait for items if queue is empty
            if not self._queue:
                self._event.clear()
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(self._event.wait(), timeout=1.0)
                continue

            now = time.time()
            next_item = self._queue[0]

            if next_item.replay_time > now:
                # Sleep until next item is due, but wake on new items
                delay = min(next_item.replay_time - now, 0.1)
                self._event.clear()
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(self._event.wait(), timeout=delay)
                continue

            # Pop all items that are currently due
            while self._queue and self._queue[0].replay_time <= time.time():
                item = heapq.heappop(self._queue)

                if item.channel == "detections":
                    detection_accumulator.extend(item.data)
                    # Track the latest original detection timestamp
                    for det in item.data:
                        ts = det.get("timestamp", 0)
                        if ts > self._last_sent_timestamp_ms:
                            self._last_sent_timestamp_ms = ts

            # Flush detections at ~10 Hz
            now = time.time()
            if detection_accumulator and (now - last_detection_flush) >= 0.1:
                await broadcast_fn("detections", detection_accumulator)
                detection_accumulator = []
                last_detection_flush = now

        # Flush any remaining detections on shutdown
        if detection_accumulator:
            try:
                await broadcast_fn("detections", detection_accumulator)
            except Exception as e:
                logger.warning("Failed to flush remaining detections on shutdown: %s", e)

        logger.info("Replay buffer drain stopped")

    def stop(self) -> None:
        """Signal the drain loop to stop."""
        self._running = False
        self._event.set()

    def cleanup_stale_batches(self, max_age_s: float = 60) -> None:
        """No-op: batch tracking removed. Kept for API compatibility."""
        pass
