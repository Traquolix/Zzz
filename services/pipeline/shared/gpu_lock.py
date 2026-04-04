"""Cross-process GPU lock using file-based locking.

When multiple AI engine containers share the same GPU, concurrent inference
causes serialization and escalating latency (8s -> 26s+). This module provides
a file-based lock so only one engine runs GPU inference at a time.

The lock file is placed on a shared volume (/app/visualizations/.gpu_lock)
that all AI engine containers mount.

Usage:
    from shared.gpu_lock import gpu_lock

    with gpu_lock() as timing:
        # GPU-exclusive work here
        model.forward(data)
    # timing.wait_seconds, timing.held_seconds available after exit
"""

import fcntl
import logging
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Lock file on the shared visualizations volume
_LOCK_PATH = os.environ.get("GPU_LOCK_PATH", "/app/visualizations/.gpu_lock")


@dataclass
class GPULockTiming:
    """Timing information from a GPU lock acquisition."""

    wait_seconds: float = 0.0
    held_seconds: float = 0.0


@contextmanager
def gpu_lock(timeout: float = 120.0):
    """Acquire exclusive GPU access via file lock.

    Yields a GPULockTiming object that is populated with wait and held
    durations after the context exits.

    Args:
        timeout: Maximum seconds to wait for the lock (default 120s).

    Raises:
        TimeoutError: If the lock cannot be acquired within timeout.
    """
    timing = GPULockTiming()

    lock_dir = os.path.dirname(_LOCK_PATH)
    if not os.path.isdir(lock_dir):
        # No shared volume available — skip locking (single engine or dev mode)
        yield timing
        return

    start = time.monotonic()
    fd = None
    try:
        fd = os.open(_LOCK_PATH, os.O_CREAT | os.O_RDWR)
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except (OSError, BlockingIOError) as err:
                elapsed = time.monotonic() - start
                if elapsed >= timeout:
                    raise TimeoutError(
                        f"GPU lock acquisition timed out after {timeout:.0f}s"
                    ) from err
                time.sleep(0.05)

        acquired = time.monotonic()
        timing.wait_seconds = acquired - start

        if timing.wait_seconds > 0.1:
            logger.info(f"GPU lock acquired after {timing.wait_seconds:.1f}s wait")

        yield timing
    finally:
        held_end = time.monotonic()
        if fd is not None:
            timing.held_seconds = held_end - start - timing.wait_seconds
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
