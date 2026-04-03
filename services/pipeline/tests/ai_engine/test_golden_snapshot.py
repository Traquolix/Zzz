"""Golden snapshot tests: change detection for AI engine inference.

These tests run inference on real post-preprocessed DAS data and compare
the output to a saved reference. If output changes (due to model update,
preprocessing change, parameter change), the test fails with a detailed
diagnostic message.

Platform-specific references: float32 accumulation differs ~10% between
ARM (macOS) and x86 (Linux). Each platform maintains its own reference
file. If the reference for the current platform is missing, it is
auto-generated on first run and committed for future comparisons.

To force regeneration after an intentional change:
    make snapshot-confirm
"""

from __future__ import annotations

import logging
import platform
from pathlib import Path

import numpy as np
import pytest
import torch

from ai_engine.model_vehicle.utils import normalize_channel_energy

logger = logging.getLogger(__name__)

FIXTURE_DIR = Path(__file__).parent / "fixtures"
GOLDEN_INPUT = FIXTURE_DIR / "golden_input.npz"

_ARCH = platform.machine()  # "arm64" or "x86_64"
GOLDEN_REF = FIXTURE_DIR / f"golden_reference_{_ARCH}.npz"
GOLDEN_NORM = FIXTURE_DIR / f"golden_normalization_{_ARCH}.npz"

_SNAPSHOT_HELP = f"""
SNAPSHOT MISMATCH -- AI engine golden test (platform: {_ARCH})

  This test fails when AI engine output changes. This is expected after:
    - Model weight updates (.pth file)
    - Preprocessing changes (normalization, filtering)
    - Detection parameter changes (thresholds, speed bounds)

  To accept the new baseline:
    make snapshot-confirm

  Then commit the updated files in tests/ai_engine/fixtures/
"""


def _require_golden_input():
    """The golden input (platform-independent) must exist."""
    if not GOLDEN_INPUT.exists():
        raise FileNotFoundError(
            f"Golden input missing: {GOLDEN_INPUT}\nGenerate with: make snapshot-confirm"
        )


_require_golden_input()


def _generate_reference(estimator, golden_input_data):
    """Run inference and save platform-specific reference files.

    Called automatically when the reference for this platform is missing.
    """
    data_window, timestamps, timestamps_ns = golden_input_data

    torch.manual_seed(42)
    results = list(estimator.process_file(data_window, timestamps, timestamps_ns))

    all_detections = []
    result_arrays = {}
    for result in results:
        direction = int(result.direction_mask[0, 0])
        dir_key = "fwd" if direction == 0 else "rev"
        result_arrays[f"{dir_key}_glrt_summed"] = result.glrt_summed
        result_arrays[f"{dir_key}_filtered_speed"] = result.filtered_speed
        result_arrays[f"{dir_key}_aligned_speed_per_pair"] = result.aligned_speed_per_pair

        detections = estimator.extract_detections(
            glrt_summed=result.glrt_summed,
            aligned_speed_pairs=result.aligned_speed_per_pair,
            direction=direction,
            timestamps_ns=result.timestamps_ns,
            aligned_data=result.aligned_data,
        )
        all_detections.extend(detections)

    n_det = len(all_detections)

    def _det_array(key, dtype=np.float64):
        if not all_detections:
            return np.array([], dtype=dtype)
        return np.array([d[key] for d in all_detections], dtype=dtype)

    np.savez_compressed(
        GOLDEN_REF,
        n_detections=np.int32(n_det),
        det_speeds=_det_array("speed_kmh"),
        det_directions=_det_array("direction", np.int32),
        det_glrt_max=_det_array("glrt_max"),
        det_vehicle_count=_det_array("vehicle_count"),
        det_n_cars=_det_array("n_cars"),
        det_n_trucks=_det_array("n_trucks"),
        det_section_idx=_det_array("section_idx", np.int32),
        det_t_mid=_det_array("_t_mid_sample", np.int32),
        det_strain_peak=_det_array("strain_peak"),
        det_strain_rms=_det_array("strain_rms"),
        **result_arrays,
    )

    # Normalization reference
    space_split = estimator.split_channel_overlap(data_window)
    norm_ref = normalize_channel_energy(space_split[0])
    np.savez_compressed(GOLDEN_NORM, normalized_first_window=norm_ref)

    logger.warning(
        "AUTO-GENERATED golden reference for %s (%d detections). "
        "Commit the new files:\n"
        "  git add %s %s\n"
        "  git commit -m 'test: auto-generate %s golden snapshots'",
        _ARCH,
        n_det,
        GOLDEN_REF,
        GOLDEN_NORM,
        _ARCH,
    )

    return results, all_detections


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def golden_input():
    data = np.load(GOLDEN_INPUT)
    return data["data_window"], data["timestamps"], data["timestamps_ns"]


@pytest.fixture(scope="module")
def golden_results(estimator, golden_input):
    """Run inference and return results + detections.

    If the platform reference is missing, auto-generate it.
    """
    if not GOLDEN_REF.exists():
        results, detections = _generate_reference(estimator, golden_input)
        return results, detections

    data_window, timestamps, timestamps_ns = golden_input
    torch.manual_seed(42)
    results = list(estimator.process_file(data_window, timestamps, timestamps_ns))

    all_detections = []
    for result in results:
        direction = int(result.direction_mask[0, 0])
        detections = estimator.extract_detections(
            glrt_summed=result.glrt_summed,
            aligned_speed_pairs=result.aligned_speed_per_pair,
            direction=direction,
            timestamps_ns=result.timestamps_ns,
            aligned_data=result.aligned_data,
        )
        all_detections.extend(detections)

    return results, all_detections


@pytest.fixture(scope="module")
def golden_ref():
    """Load golden reference. Skip comparison tests if just auto-generated."""
    if not GOLDEN_REF.exists():
        pytest.skip(f"Reference was just auto-generated for {_ARCH} — run tests again to compare")
    return np.load(GOLDEN_REF)


# ---------------------------------------------------------------------------
# Snapshot comparison tests
# ---------------------------------------------------------------------------


class TestGoldenSnapshotDetections:
    """Snapshot tests comparing detection output to saved reference."""

    def test_detection_count(self, golden_results, golden_ref):
        _, detections = golden_results
        expected_count = int(golden_ref["n_detections"])
        actual_count = len(detections)

        if actual_count != expected_count:
            pytest.fail(
                f"Detection count changed: expected {expected_count}, got {actual_count} "
                f"(delta: {actual_count - expected_count:+d})\n{_SNAPSHOT_HELP}"
            )

    def test_detection_speeds(self, golden_results, golden_ref):
        _, detections = golden_results
        if not detections:
            return

        actual_speeds = np.array(sorted(d["speed_kmh"] for d in detections))
        expected_speeds = np.sort(golden_ref["det_speeds"])

        if len(actual_speeds) != len(expected_speeds):
            return

        max_diff = np.abs(actual_speeds - expected_speeds).max()
        if max_diff > 0.5:
            pytest.fail(
                f"Detection speeds changed:\n"
                f"  Max difference: {max_diff:.2f} km/h\n"
                f"  Expected range: [{expected_speeds.min():.1f}, {expected_speeds.max():.1f}]\n"
                f"  Actual range:   [{actual_speeds.min():.1f}, {actual_speeds.max():.1f}]\n"
                f"{_SNAPSHOT_HELP}"
            )

    def test_detection_directions(self, golden_results, golden_ref):
        _, detections = golden_results
        if not detections:
            return

        actual_fwd = sum(1 for d in detections if d["direction"] == 0)
        actual_rev = sum(1 for d in detections if d["direction"] == 1)
        expected_fwd = int(np.sum(golden_ref["det_directions"] == 0))
        expected_rev = int(np.sum(golden_ref["det_directions"] == 1))

        if actual_fwd != expected_fwd or actual_rev != expected_rev:
            pytest.fail(
                f"Direction split changed:\n"
                f"  Expected: fwd={expected_fwd}, rev={expected_rev}\n"
                f"  Actual:   fwd={actual_fwd}, rev={actual_rev}\n"
                f"{_SNAPSHOT_HELP}"
            )

    def test_detection_glrt_range(self, golden_results, golden_ref):
        _, detections = golden_results
        if not detections:
            return

        actual_glrt = np.array(sorted(d["glrt_max"] for d in detections))
        expected_glrt = np.sort(golden_ref["det_glrt_max"])

        if len(actual_glrt) != len(expected_glrt):
            return

        rel_diff = np.abs(actual_glrt - expected_glrt) / (expected_glrt + 1e-8)
        max_rel = rel_diff.max()

        if max_rel > 0.01:
            pytest.fail(f"GLRT peaks changed (max relative diff: {max_rel:.4f})\n{_SNAPSHOT_HELP}")


class TestGoldenSnapshotArrays:
    """Snapshot tests for intermediate array outputs (GLRT, speed)."""

    def _check_glrt_array(self, actual, expected, direction_label):
        if actual.shape != expected.shape:
            pytest.fail(
                f"{direction_label} GLRT shape changed: {expected.shape} -> {actual.shape}\n{_SNAPSHOT_HELP}"
            )

        abs_diff = np.abs(actual - expected)
        scale = np.maximum(np.abs(expected), 1.0)
        rel_diff = abs_diff / scale
        max_rel = rel_diff.max()

        if max_rel > 0.001:
            max_abs = abs_diff.max()
            pytest.fail(
                f"{direction_label} GLRT values changed:\n"
                f"  Max absolute diff: {max_abs:.4f}\n"
                f"  Max relative diff: {max_rel:.6f} ({max_rel * 100:.4f}%)\n"
                f"{_SNAPSHOT_HELP}"
            )

    def test_fwd_glrt_summed(self, golden_results, golden_ref):
        results, _ = golden_results
        fwd_results = [r for r in results if int(r.direction_mask[0, 0]) == 0]
        if not fwd_results or "fwd_glrt_summed" not in golden_ref:
            return
        self._check_glrt_array(fwd_results[0].glrt_summed, golden_ref["fwd_glrt_summed"], "Forward")

    def test_rev_glrt_summed(self, golden_results, golden_ref):
        results, _ = golden_results
        rev_results = [r for r in results if int(r.direction_mask[0, 0]) == 1]
        if not rev_results or "rev_glrt_summed" not in golden_ref:
            return
        self._check_glrt_array(rev_results[0].glrt_summed, golden_ref["rev_glrt_summed"], "Reverse")


class TestGoldenNormalization:
    """Snapshot test for preprocessing normalization parity."""

    def test_normalization_matches_reference(self, estimator, golden_input):
        if not GOLDEN_NORM.exists():
            pytest.skip(
                f"Normalization reference auto-generated for {_ARCH} — run again to compare"
            )

        data_window, _, _ = golden_input
        ref = np.load(GOLDEN_NORM)
        expected = ref["normalized_first_window"]

        space_split = estimator.split_channel_overlap(data_window)
        actual = normalize_channel_energy(space_split[0])

        np.testing.assert_allclose(
            actual,
            expected,
            rtol=1e-6,
            atol=1e-10,
            err_msg=f"Normalization output changed.\n{_SNAPSHOT_HELP}",
        )


class TestGoldenInvariants:
    """Tests that must always hold regardless of model version.

    These do NOT compare to a snapshot -- they test properties that should
    be true for any valid model on real data.
    """

    def test_all_speeds_in_bounds(self, golden_results):
        _, detections = golden_results
        for det in detections:
            assert 20.0 <= det["speed_kmh"] <= 120.0, (
                f"Detection speed {det['speed_kmh']:.1f} outside [20, 120] bounds"
            )

    def test_all_directions_valid(self, golden_results):
        _, detections = golden_results
        for det in detections:
            assert det["direction"] in (0, 1)

    def test_all_fields_present(self, golden_results):
        required = {
            "section_idx",
            "speed_kmh",
            "direction",
            "timestamp_ns",
            "glrt_max",
            "vehicle_count",
            "n_cars",
            "n_trucks",
            "strain_peak",
            "strain_rms",
            "_t_mid_sample",
        }
        _, detections = golden_results
        for det in detections:
            missing = required - set(det.keys())
            assert not missing, f"Detection missing fields: {missing}"

    def test_all_values_finite(self, golden_results):
        _, detections = golden_results
        numeric_fields = [
            "speed_kmh",
            "glrt_max",
            "vehicle_count",
            "n_cars",
            "n_trucks",
            "strain_peak",
            "strain_rms",
        ]
        for det in detections:
            for field in numeric_fields:
                assert np.isfinite(det[field]), f"Non-finite {field}={det[field]}"

    def test_vehicle_count_at_least_one(self, golden_results):
        _, detections = golden_results
        for det in detections:
            assert det["vehicle_count"] >= 1.0

    def test_glrt_positive(self, golden_results):
        _, detections = golden_results
        for det in detections:
            assert det["glrt_max"] > 0

    def test_real_data_produces_detections(self, golden_results):
        _, detections = golden_results
        assert len(detections) > 0, "Real DAS data produced zero detections."

    def test_both_directions_detected(self, golden_results):
        _, detections = golden_results
        directions = {d["direction"] for d in detections}
        assert 0 in directions, "No forward detections on real data"
        assert 1 in directions, "No reverse detections on real data"
