#!/usr/bin/env python3
"""Test that RollingBufferedTransformer produces continuous timestamps.

This test simulates the new rolling FIFO buffer approach where:
- Buffer is a deque(maxlen=300) - constant size after initial fill
- Processing triggers every 250 new messages
- Natural 50-sample overlap between consecutive windows
"""

import sys
from collections import deque
from pathlib import Path

import numpy as np

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from ai_engine.model_vehicle.constants import GLRT_DEFAULT_WINDOW, GLRT_EDGE_SAFETY_SAMPLES
from ai_engine.model_vehicle.vehicle_speed import compute_edge_trim


def test_rolling_fifo_buffer():
    """Simulate the RollingBufferedTransformer approach.

    Design:
        - Rolling FIFO buffer: deque(maxlen=300)
        - Trigger processing every step_size (250) new messages
        - Buffer is constant at 300 after initial fill
        - Natural 50-sample overlap from FIFO behavior
    """

    # Configuration
    window_size = 300
    edge_trim = compute_edge_trim(GLRT_DEFAULT_WINDOW, GLRT_EDGE_SAFETY_SAMPLES)
    step_size = window_size - 2 * edge_trim  # 250 = valid output per window
    num_messages = 3000  # Total messages to process

    print("Configuration:")
    print(f"  Window size: {window_size}")
    print(f"  Edge trim: {edge_trim}")
    print(f"  Step size: {step_size}")
    print(f"  Overlap: {window_size - step_size}")
    print()

    # Simulate RollingBufferedTransformer
    rolling_buffer = deque(maxlen=window_size)  # FIFO, constant size
    new_count = 0  # Messages since last processing
    all_output_timestamps = []
    windows_processed = 0

    for msg_idx in range(num_messages):
        # Simulate message arrival with timestamp
        timestamp = msg_idx

        # Append to rolling buffer (FIFO auto-removes oldest when full)
        rolling_buffer.append(timestamp)
        new_count += 1

        # Process when: buffer is full AND we've received step_size new messages
        if len(rolling_buffer) >= window_size and new_count >= step_size:
            # Snapshot current window
            window_ts = np.array(list(rolling_buffer))
            assert len(window_ts) == window_size, f"Window size mismatch: {len(window_ts)}"

            # Trim edges (simulating process_file behavior)
            trimmed_ts = window_ts[edge_trim:window_size - edge_trim]
            all_output_timestamps.extend(trimmed_ts.tolist())

            windows_processed += 1
            if windows_processed <= 5 or windows_processed % 10 == 0:
                print(f"Window {windows_processed}: input T{window_ts[0]}-T{window_ts[-1]} → output T{trimmed_ts[0]}-T{trimmed_ts[-1]}")

            # Reset counter (buffer keeps its data for overlap)
            new_count = 0

    print(f"\nProcessed {windows_processed} windows from {num_messages} messages")
    print()

    # Verify continuity
    print("=" * 60)
    print("Verifying timestamp continuity...")

    output_ts = np.array(all_output_timestamps)

    # Check for gaps
    diffs = np.diff(output_ts)
    gaps = np.where(diffs != 1)[0]

    if len(gaps) == 0:
        print(f"✓ SUCCESS: All {len(output_ts)} timestamps are continuous!")
        print(f"  First: T{output_ts[0]}, Last: T{output_ts[-1]}")
    else:
        print(f"✗ FAILURE: Found {len(gaps)} gaps!")
        for gap_idx in gaps[:10]:
            print(f"  Gap at index {gap_idx}: T{output_ts[gap_idx]} -> T{output_ts[gap_idx+1]} (diff={diffs[gap_idx]})")
        return False

    # Check for duplicates
    unique_ts = np.unique(output_ts)
    if len(unique_ts) < len(output_ts):
        duplicates = len(output_ts) - len(unique_ts)
        print(f"✗ WARNING: Found {duplicates} duplicate timestamps!")
        return False
    else:
        print("✓ No duplicate timestamps")

    # Verify expected output length
    # First window starts at T299 (after filling buffer)
    # Each subsequent window advances by step_size (250)
    expected_windows = (num_messages - window_size) // step_size + 1
    expected_output_samples = expected_windows * step_size

    print()
    print(f"Expected ~{expected_windows} windows, got {windows_processed}")
    print(f"Expected ~{expected_output_samples} output samples, got {len(output_ts)}")

    if abs(windows_processed - expected_windows) <= 1:
        print("✓ Window count matches expected")
    else:
        print("⚠ Window count differs from expected (may be edge effect)")

    return True


def test_overlap_correctness():
    """Verify that overlapping windows produce seamless output."""
    print("\n" + "=" * 60)
    print("Testing overlap correctness...")

    window_size = 300
    edge_trim = compute_edge_trim(GLRT_DEFAULT_WINDOW, GLRT_EDGE_SAFETY_SAMPLES)
    step_size = window_size - 2 * edge_trim  # 250

    # Two consecutive windows
    window1 = np.arange(0, window_size)  # T0 - T299
    window2 = np.arange(step_size, step_size + window_size)  # T250 - T549

    # Trim edges
    trimmed1 = window1[edge_trim:window_size - edge_trim]  # T25 - T274
    trimmed2 = window2[edge_trim:window_size - edge_trim]  # T275 - T524

    print(f"Window 1: T{window1[0]}-T{window1[-1]} → trimmed T{trimmed1[0]}-T{trimmed1[-1]}")
    print(f"Window 2: T{window2[0]}-T{window2[-1]} → trimmed T{trimmed2[0]}-T{trimmed2[-1]}")

    # Check that trimmed outputs are adjacent
    gap = trimmed2[0] - trimmed1[-1]
    if gap == 1:
        print(f"✓ Trimmed outputs are adjacent (gap={gap})")
        return True
    else:
        print(f"✗ Trimmed outputs have gap={gap} (expected 1)")
        return False


if __name__ == "__main__":
    success1 = test_rolling_fifo_buffer()
    success2 = test_overlap_correctness()

    if success1 and success2:
        print("\n" + "=" * 60)
        print("ALL TESTS PASSED!")
        sys.exit(0)
    else:
        print("\n" + "=" * 60)
        print("SOME TESTS FAILED!")
        sys.exit(1)
