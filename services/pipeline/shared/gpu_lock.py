"""GPU execution context: CUDA streams for intra-process concurrency,
file lock for inter-process exclusion.

Single-container mode (default): each fiber batch gets its own CUDA stream,
allowing concurrent GPU execution across fibers. No file lock is acquired.

Multi-container mode: when GPU_LOCK_PATH points to a shared volume, the file
lock serializes GPU access across containers (legacy behavior).

Usage:
    from shared.gpu_lock import gpu_lock

    with gpu_lock() as timing:
        # GPU work here — runs on a dedicated CUDA stream
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

# Lock file on the shared visualizations volume.
# When this path exists (shared Docker volume), file locking is used for
# inter-container exclusion. When it doesn't exist (single container),
# CUDA streams provide intra-process concurrency.
_LOCK_PATH = os.environ.get("GPU_LOCK_PATH", "/app/visualizations/.gpu_lock")

# CUDA stream pool — one per concurrent fiber, reused across calls.
# Populated lazily on first use if CUDA is available.
_cuda_streams: list = []
_stream_idx = 0

try:
    import torch

    _TORCH_AVAILABLE = True
except ImportError:
    _TORCH_AVAILABLE = False


def _get_cuda_stream():
    """Get the next CUDA stream from a round-robin pool.

    Creates streams lazily on first use. Pool size matches the number of
    concurrent fibers (typically 3-5). Streams are lightweight — each is
    just a command queue on the GPU.
    """
    global _stream_idx

    if not _TORCH_AVAILABLE or not torch.cuda.is_available():
        return None

    # Grow pool on demand (each new concurrent caller gets a stream)
    if _stream_idx >= len(_cuda_streams):
        stream = torch.cuda.Stream()
        _cuda_streams.append(stream)
        logger.info(f"Created CUDA stream {len(_cuda_streams)} for concurrent inference")

    stream = _cuda_streams[_stream_idx % len(_cuda_streams)]
    _stream_idx += 1
    return stream


@dataclass
class GPULockTiming:
    """Timing information from a GPU lock acquisition."""

    wait_seconds: float = 0.0
    held_seconds: float = 0.0


@contextmanager
def gpu_lock(timeout: float = 120.0):
    """Acquire GPU execution context.

    In single-container mode (no shared lock volume): assigns a CUDA stream
    for concurrent execution. Multiple fibers run GPU kernels in parallel.

    In multi-container mode (shared lock volume exists): acquires an exclusive
    file lock to prevent inter-container GPU contention.

    Yields a GPULockTiming object populated after context exit.

    Args:
        timeout: Maximum seconds to wait for file lock (multi-container only).

    Raises:
        TimeoutError: If the file lock cannot be acquired within timeout.
    """
    timing = GPULockTiming()

    lock_dir = os.path.dirname(_LOCK_PATH)
    use_file_lock = os.path.isdir(lock_dir)

    if not use_file_lock:
        # Single-container mode: use CUDA stream for concurrency
        stream = _get_cuda_stream()
        if stream is not None:
            start = time.monotonic()
            with torch.cuda.stream(stream):
                timing.wait_seconds = 0.0
                yield timing
            # Sync this stream to measure actual GPU time
            stream.synchronize()
            timing.held_seconds = time.monotonic() - start
        else:
            # No CUDA — CPU inference, no locking needed
            yield timing
        return

    # Multi-container mode: file lock for inter-process exclusion
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
