"""
Time-shifted replay buffer for AI engine detection results.

Detections arrive in bursts (30-second inference windows). Instead of
forwarding them immediately, we replay each detection exactly 60 seconds
after its original timestamp_ns. This produces a continuous, smooth
stream on the frontend where vehicle traces form proper oblique lines
in the waterfall view.

Each detection is scheduled for broadcast at:
    detection.timestamp_ns / 1e6 + REPLAY_DELAY_MS  (in wall-clock ms)

The drain loop pops due items and flushes accumulated detections at ~10 Hz.
"""

import asyncio
import heapq
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

logger = logging.getLogger('sequoia.replay_buffer')

# Fixed delay: detections are sent 60 seconds after their original timestamp
REPLAY_DELAY_S = 60.0

# Type alias for the broadcast callback
BroadcastFn = Callable[[str, Any], Coroutine[Any, Any, None]]


@dataclass(order=True)
class ReplayItem:
    """Priority queue item ordered by replay wall-clock time."""
    replay_time: float
    sequence: int = field(compare=True)     # tie-breaker for same replay_time
    channel: str = field(compare=False)     # 'detections'
    data: Any = field(compare=False)        # transformed message payload


class ReplayBuffer:
    """
    Buffers incoming detection messages and replays them 60 seconds after
    their original timestamp.

    Messages are individually scheduled based on their timestamp_ns,
    producing a smooth continuous stream on the frontend.
    """

    def __init__(self):
        self._queue: list[ReplayItem] = []      # heapq min-heap
        self._sequence: int = 0
        self._event = asyncio.Event()
        self._running: bool = False
        self._last_sent_timestamp_ms: int = 0   # track for frontend display

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

    def ingest_detection(self, section_key: str, timestamp_ns: int,
                         detections: list[dict]) -> None:
        """
        Add a detection message to the replay queue.

        Each detection is scheduled for replay at its original timestamp
        plus the fixed 60-second delay.

        Args:
            section_key: "{fiber_id}:{channel}" identifying the section
            timestamp_ns: Original sample timestamp in nanoseconds
            detections: Transformed Detection[] dicts ready for frontend
        """
        if not detections:
            return

        # Schedule at: original_time + 60 seconds
        original_time_s = timestamp_ns / 1e9
        replay_time = original_time_s + REPLAY_DELAY_S

        self._sequence += 1
        heapq.heappush(self._queue, ReplayItem(
            replay_time=replay_time,
            sequence=self._sequence,
            channel='detections',
            data=detections,
        ))
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

        logger.info('Replay buffer drain started (delay=%.0fs)', REPLAY_DELAY_S)

        while self._running:
            # Wait for items if queue is empty
            if not self._queue:
                self._event.clear()
                try:
                    await asyncio.wait_for(self._event.wait(), timeout=1.0)
                except asyncio.TimeoutError:
                    pass
                continue

            now = time.time()
            next_item = self._queue[0]

            if next_item.replay_time > now:
                # Sleep until next item is due, but wake on new items
                delay = min(next_item.replay_time - now, 0.1)
                self._event.clear()
                try:
                    await asyncio.wait_for(self._event.wait(), timeout=delay)
                except asyncio.TimeoutError:
                    pass
                continue

            # Pop all items that are currently due
            while self._queue and self._queue[0].replay_time <= time.time():
                item = heapq.heappop(self._queue)

                if item.channel == 'detections':
                    detection_accumulator.extend(item.data)
                    # Track the latest original detection timestamp
                    for det in item.data:
                        ts = det.get('timestamp', 0)
                        if ts > self._last_sent_timestamp_ms:
                            self._last_sent_timestamp_ms = ts

            # Flush detections at ~10 Hz
            now = time.time()
            if detection_accumulator and (now - last_detection_flush) >= 0.1:
                await broadcast_fn('detections', detection_accumulator)
                detection_accumulator = []
                last_detection_flush = now

        # Flush any remaining detections on shutdown
        if detection_accumulator:
            try:
                await broadcast_fn('detections', detection_accumulator)
            except Exception as e:
                logger.warning('Failed to flush remaining detections on shutdown: %s', e)

        logger.info('Replay buffer drain stopped')

    def stop(self) -> None:
        """Signal the drain loop to stop."""
        self._running = False
        self._event.set()

    def cleanup_stale_batches(self, max_age_s: float = 60) -> None:
        """No-op: batch tracking removed. Kept for API compatibility."""
        pass
