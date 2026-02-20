"""
Time-shifted replay buffer for AI engine inference results.

The AI engine produces 30-second windows of speed/count data as bursts.
This buffer replays them at the original 10 Hz rate with a fixed time
offset, creating continuous flow to the frontend instead of bursts
followed by silence.

Each speed message carries timestamp_ns (original sample time, 100ms apart)
and ai_metadata.time_index (0-299 ordinal within the inference window).
The buffer uses these to schedule each message for replay at:
    wall_start + (msg.timestamp_ns - batch_first_ts_ns) / 1e9

Multiple concurrent inference batches from different fiber sections
naturally interleave in the priority queue.
"""

import asyncio
import heapq
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

logger = logging.getLogger('sequoia.replay_buffer')


@dataclass(order=True)
class ReplayItem:
    """Priority queue item ordered by replay wall-clock time."""
    replay_time: float
    sequence: int = field(compare=True)     # tie-breaker for same replay_time
    channel: str = field(compare=False)     # 'detections' or 'counts'
    data: Any = field(compare=False)        # transformed message payload


class BatchTracker:
    """Timing anchors for an active inference batch on a section."""
    __slots__ = ('wall_start', 'first_ts_ns', 'last_seen')

    def __init__(self, wall_start: float, first_ts_ns: int):
        self.wall_start = wall_start
        self.first_ts_ns = first_ts_ns
        self.last_seen = wall_start


# Type alias for the broadcast callback
BroadcastFn = Callable[[str, Any], Coroutine[Any, Any, None]]


class ReplayBuffer:
    """
    Buffers incoming burst messages and replays them at the original rate.

    Messages are assigned wall-clock replay times based on their original
    timestamp_ns offsets within each inference batch, then drained by
    an asyncio task that sleeps until each message is due.
    """

    def __init__(self):
        self._queue: list[ReplayItem] = []      # heapq min-heap
        self._sequence: int = 0
        self._batches: dict[str, BatchTracker] = {}
        self._event = asyncio.Event()
        self._running: bool = False

    @property
    def queue_size(self) -> int:
        return len(self._queue)

    @property
    def active_batches(self) -> int:
        return len(self._batches)

    def ingest_speed(self, section_key: str, timestamp_ns: int,
                     time_index: int, detections: list[dict]) -> None:
        """
        Add a speed message to the replay queue.

        Args:
            section_key: "{fiber_id}:{channel_start}" identifying the section
            timestamp_ns: Original sample timestamp in nanoseconds
            time_index: Ordinal position (0-299) within inference window
            detections: Transformed Detection[] dicts ready for frontend
        """
        if not detections:
            return

        now = time.time()
        batch = self._batches.get(section_key)

        # Detect new batch: time_index resets to 0 or large timestamp gap
        if (batch is None
                or time_index == 0
                or (timestamp_ns - batch.first_ts_ns) > 35_000_000_000):
            batch = BatchTracker(wall_start=now, first_ts_ns=timestamp_ns)
            self._batches[section_key] = batch
            logger.debug(
                'New batch for %s: wall_start=%.3f, first_ts_ns=%d',
                section_key, now, timestamp_ns,
            )

        batch.last_seen = now

        # Compute replay time: wall_start + offset from batch start
        offset_s = (timestamp_ns - batch.first_ts_ns) / 1e9
        replay_time = batch.wall_start + offset_s

        self._sequence += 1
        heapq.heappush(self._queue, ReplayItem(
            replay_time=replay_time,
            sequence=self._sequence,
            channel='detections',
            data=detections,
        ))
        self._event.set()

    def ingest_count(self, section_key: str, count_timestamp_ns: int,
                     count_data: dict) -> None:
        """
        Add a count message to the replay queue.

        Time-shifted using the corresponding speed batch's anchor if available,
        otherwise broadcast with minimal delay.
        """
        now = time.time()
        batch = self._batches.get(section_key)

        if batch is not None:
            offset_s = (count_timestamp_ns - batch.first_ts_ns) / 1e9
            replay_time = batch.wall_start + offset_s
        else:
            # No active speed batch for this section -- broadcast soon
            replay_time = now + 0.5

        self._sequence += 1
        heapq.heappush(self._queue, ReplayItem(
            replay_time=replay_time,
            sequence=self._sequence,
            channel='counts',
            data=count_data,
        ))
        self._event.set()

    async def drain(self, broadcast_fn: BroadcastFn) -> None:
        """
        Drain loop: pops items from the queue and broadcasts them
        at their scheduled replay times.

        Detections are accumulated and flushed at ~10 Hz (100ms batches).
        Counts are broadcast individually (low volume).

        Args:
            broadcast_fn: async callback(channel: str, data: Any)
        """
        self._running = True
        detection_accumulator: list[dict] = []
        last_detection_flush = time.time()

        logger.info('Replay buffer drain started')

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
                elif item.channel == 'counts':
                    await broadcast_fn('counts', item.data)

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
            except Exception:
                pass

        logger.info('Replay buffer drain stopped')

    def stop(self) -> None:
        """Signal the drain loop to stop."""
        self._running = False
        self._event.set()

    def cleanup_stale_batches(self, max_age_s: float = 60) -> None:
        """Remove batch trackers older than max_age_s."""
        now = time.time()
        stale = [k for k, v in self._batches.items()
                 if now - v.last_seen > max_age_s]
        for k in stale:
            del self._batches[k]
        if stale:
            logger.debug('Cleaned up %d stale batch trackers', len(stale))
