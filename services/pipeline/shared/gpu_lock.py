"""Cross-process GPU lock using file-based locking.

When multiple AI engine containers share the same GPU, concurrent inference
causes serialization and escalating latency (8s -> 26s+). This module provides
a file-based lock so only one engine runs GPU inference at a time.

The lock file is placed on a shared volume (/app/visualizations/.gpu_lock)
that all AI engine containers mount.

Usage:
    from shared.gpu_lock import gpu_lock

    with gpu_lock():
        # GPU-exclusive work here
        model.forward(data)
"""

import fcntl
import logging
import os
import time
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Lock file on the shared visualizations volume
_LOCK_PATH = os.environ.get("GPU_LOCK_PATH", "/app/visualizations/.gpu_lock")


@contextmanager
def gpu_lock(timeout: float = 120.0):
    """Acquire exclusive GPU access via file lock.

    Args:
        timeout: Maximum seconds to wait for the lock (default 120s).

    Raises:
        TimeoutError: If the lock cannot be acquired within timeout.
    """
    lock_dir = os.path.dirname(_LOCK_PATH)
    if not os.path.isdir(lock_dir):
        # No shared volume available — skip locking (single engine or dev mode)
        yield
        return

    start = time.monotonic()
    fd = None
    try:
        fd = os.open(_LOCK_PATH, os.O_CREAT | os.O_RDWR)
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except (OSError, BlockingIOError):
                elapsed = time.monotonic() - start
                if elapsed >= timeout:
                    raise TimeoutError(
                        f"GPU lock acquisition timed out after {timeout:.0f}s"
                    )
                time.sleep(0.05)

        wait_time = time.monotonic() - start
        if wait_time > 0.1:
            logger.info(f"GPU lock acquired after {wait_time:.1f}s wait")

        yield
    finally:
        if fd is not None:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
