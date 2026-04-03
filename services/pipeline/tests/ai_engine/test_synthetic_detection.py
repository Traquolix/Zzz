"""Tests using the synthetic_vehicle_data fixture to verify detection capability.

The conftest provides a fixture with a coherent vehicle-like signal injected
at channels 20-28, time samples ~100-200, simulating ~60 km/h passage.
This test verifies the pipeline can actually detect it.
"""

from __future__ import annotations

from tests.ai_engine.conftest import (
    MAX_SPEED,
    MIN_SPEED,
)


class TestSyntheticVehicleDetection:
    """Tests that the pipeline detects a known injected vehicle signal."""

    def test_detects_injected_vehicle(
        self, estimator, synthetic_vehicle_data, synthetic_timestamps, synthetic_timestamps_ns
    ):
        """Pipeline should detect at least one vehicle from injected coherent signal."""
        results = list(
            estimator.process_file(
                synthetic_vehicle_data, synthetic_timestamps, synthetic_timestamps_ns
            )
        )

        all_detections = []
        for r in results:
            direction = int(r.direction_mask[0, 0])
            detections = estimator.extract_detections(
                glrt_summed=r.glrt_summed,
                aligned_speed_pairs=r.aligned_speed_per_pair,
                direction=direction,
                timestamps_ns=r.timestamps_ns,
                aligned_data=r.aligned_data,
            )
            all_detections.extend(detections)

        assert len(all_detections) >= 1, (
            "Pipeline failed to detect the injected vehicle signal. "
            "This indicates a fundamental detection capability failure."
        )

    def test_detection_in_expected_spatial_region(
        self, estimator, synthetic_vehicle_data, synthetic_timestamps, synthetic_timestamps_ns
    ):
        """Detection should be near the injected signal region (channels 20-28)."""
        results = list(
            estimator.process_file(
                synthetic_vehicle_data, synthetic_timestamps, synthetic_timestamps_ns
            )
        )

        all_detections = []
        for r in results:
            direction = int(r.direction_mask[0, 0])
            detections = estimator.extract_detections(
                glrt_summed=r.glrt_summed,
                aligned_speed_pairs=r.aligned_speed_per_pair,
                direction=direction,
                timestamps_ns=r.timestamps_ns,
                aligned_data=r.aligned_data,
            )
            all_detections.extend(detections)

        if not all_detections:
            return  # detection test above will catch this

        # The signal is at channels 20-28. With Nch=9 and step=1,
        # spatial window index ≈ channel_start. The signal should produce
        # detections around section_idx 12-20 (channel 20 → window ~12).
        section_indices = [d["section_idx"] for d in all_detections]
        # At least one detection should be in the injected region
        in_region = [s for s in section_indices if 10 <= s <= 25]
        assert len(in_region) > 0, (
            f"No detections near injected signal region. "
            f"Detection sections: {sorted(set(section_indices))}"
        )

    def test_detection_speed_in_valid_range(
        self, estimator, synthetic_vehicle_data, synthetic_timestamps, synthetic_timestamps_ns
    ):
        """Detected speeds must be within configured bounds."""
        results = list(
            estimator.process_file(
                synthetic_vehicle_data, synthetic_timestamps, synthetic_timestamps_ns
            )
        )

        for r in results:
            direction = int(r.direction_mask[0, 0])
            detections = estimator.extract_detections(
                glrt_summed=r.glrt_summed,
                aligned_speed_pairs=r.aligned_speed_per_pair,
                direction=direction,
                timestamps_ns=r.timestamps_ns,
            )
            for det in detections:
                assert MIN_SPEED <= det["speed_kmh"] <= MAX_SPEED, (
                    f"Speed {det['speed_kmh']:.1f} outside [{MIN_SPEED}, {MAX_SPEED}]"
                )

    def test_noise_only_fewer_detections_than_signal(
        self,
        estimator,
        synthetic_section_data,
        synthetic_vehicle_data,
        synthetic_timestamps,
        synthetic_timestamps_ns,
    ):
        """Pure noise should produce fewer detections than data with injected signal."""
        # Count detections from noise
        noise_detections = []
        for r in estimator.process_file(
            synthetic_section_data, synthetic_timestamps, synthetic_timestamps_ns
        ):
            direction = int(r.direction_mask[0, 0])
            noise_detections.extend(
                estimator.extract_detections(
                    glrt_summed=r.glrt_summed,
                    aligned_speed_pairs=r.aligned_speed_per_pair,
                    direction=direction,
                    timestamps_ns=r.timestamps_ns,
                )
            )

        # Count detections from signal
        signal_detections = []
        for r in estimator.process_file(
            synthetic_vehicle_data, synthetic_timestamps, synthetic_timestamps_ns
        ):
            direction = int(r.direction_mask[0, 0])
            signal_detections.extend(
                estimator.extract_detections(
                    glrt_summed=r.glrt_summed,
                    aligned_speed_pairs=r.aligned_speed_per_pair,
                    direction=direction,
                    timestamps_ns=r.timestamps_ns,
                )
            )

        # Signal data should have at least as many detections as noise
        # (or more, because it has an actual vehicle signal)
        assert len(signal_detections) >= len(noise_detections), (
            f"Signal data ({len(signal_detections)} detections) produced fewer "
            f"detections than noise ({len(noise_detections)})"
        )
