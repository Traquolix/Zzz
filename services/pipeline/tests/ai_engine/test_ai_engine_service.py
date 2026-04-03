"""Tests for AIEngineService (ai_engine/main.py).

Validates the service-level orchestration methods in isolation, without
instantiating the real service (which requires Kafka, fibers.yaml, real models,
and PyTorch GPU resources). All tests use heavy mocking.

Covered methods:
- get_buffer_key: compound buffer key from message payload
- _apply_cnn_counts: mapping counting intervals to detections (most critical)
- _get_or_create_context: LRU eviction at _MAX_PROCESSING_CONTEXTS
- _should_visualize: rate-limited visualization gating
"""

from __future__ import annotations

import sys
import time
from collections import OrderedDict
from pathlib import Path
from unittest.mock import MagicMock

# Ensure pipeline root is on sys.path
_pipeline_root = Path(__file__).resolve().parents[2]
if str(_pipeline_root) not in sys.path:
    sys.path.insert(0, str(_pipeline_root))

from ai_engine.message_utils import ProcessingContext  # noqa: E402
from shared.message import Message  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_message(
    fiber_id: str = "carros",
    section: str = "seg1",
    model_hint: str = "default",
    values: list | None = None,
) -> Message:
    """Create a minimal Message with the payload fields used by get_buffer_key."""
    payload: dict = {
        "fiber_id": fiber_id,
        "section": section,
        "model_hint": model_hint,
    }
    if values is not None:
        payload["values"] = values
    return Message(id=f"{fiber_id}:{section}", payload=payload)


def _make_bare_service():
    """Create a bare AIEngineService without calling __init__.

    Uses object.__new__ to skip the constructor entirely, then patches
    only the attributes needed by the method under test.

    We mock all heavy dependencies (Kafka, PyTorch, config, shared base classes)
    so the module can be imported without a running infrastructure stack.
    The key trick is making RollingBufferedTransformer a real (empty) class
    so that AIEngineService can inherit from it properly.
    """
    import importlib

    # Create a real base class stub so inheritance works
    class _StubRollingBufferedTransformer:
        pass

    # Build mock module objects for 'shared' that expose real-class stubs
    shared_mock = MagicMock()
    shared_mock.RollingBufferedTransformer = _StubRollingBufferedTransformer

    # We need shared.message to resolve `from shared.message import KafkaMessage, Message`
    shared_message_mock = MagicMock()
    shared_message_mock.KafkaMessage = MagicMock
    shared_message_mock.Message = MagicMock

    mock_modules = {
        "ai_engine.model_registry": MagicMock(),
        "ai_engine.model_vehicle": MagicMock(),
        "ai_engine.model_vehicle.calibration": MagicMock(),
        "ai_engine.model_vehicle.simple_interval_counter": MagicMock(),
        "ai_engine.model_vehicle.vehicle_speed": MagicMock(),
        "config": MagicMock(),
        "shared": shared_mock,
        "shared.message": shared_message_mock,
        "shared.ai_metrics": MagicMock(),
        "shared.gpu_lock": MagicMock(),
        "shared.otel_setup": MagicMock(),
        "opentelemetry": MagicMock(),
        "opentelemetry.trace": MagicMock(),
        "torch": MagicMock(),
    }

    # Temporarily swap sys.modules so the import resolves all heavy deps to mocks
    saved = {}
    for key, val in mock_modules.items():
        saved[key] = sys.modules.get(key)
        sys.modules[key] = val

    try:
        # Remove cached module so it re-imports with our mocks
        sys.modules.pop("ai_engine.main", None)
        mod = importlib.import_module("ai_engine.main")
        AIEngineService = mod.AIEngineService
        service = object.__new__(AIEngineService)
    finally:
        # Restore original modules (or remove mock entries)
        for key, original in saved.items():
            if original is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = original
        # Always remove the tainted ai_engine.main so future imports are clean
        sys.modules.pop("ai_engine.main", None)

    return service


# ---------------------------------------------------------------------------
# Tests: get_buffer_key
# ---------------------------------------------------------------------------


class TestGetBufferKey:
    """Test that get_buffer_key produces 'fiber_id:section' from message payloads."""

    def setup_method(self):
        self.service = _make_bare_service()

    def test_standard_key(self):
        """Standard fiber_id and section produce 'fiber_id:section'."""
        msg = _make_message(fiber_id="carros", section="seg1")
        assert self.service.get_buffer_key(msg) == "carros:seg1"

    def test_different_fiber_and_section(self):
        """Different fiber/section combinations produce correct keys."""
        msg = _make_message(fiber_id="mathis", section="202Bis")
        assert self.service.get_buffer_key(msg) == "mathis:202Bis"

    def test_missing_fiber_id_defaults_to_unknown(self):
        """Missing fiber_id in payload defaults to 'unknown'."""
        msg = Message(id="test", payload={"section": "seg1"})
        assert self.service.get_buffer_key(msg) == "unknown:seg1"

    def test_missing_section_defaults_to_default(self):
        """Missing section in payload defaults to 'default'."""
        msg = Message(id="test", payload={"fiber_id": "promenade"})
        assert self.service.get_buffer_key(msg) == "promenade:default"

    def test_both_missing_defaults(self):
        """Both fiber_id and section missing produce 'unknown:default'."""
        msg = Message(id="test", payload={})
        assert self.service.get_buffer_key(msg) == "unknown:default"

    def test_empty_strings_preserved(self):
        """Empty-string fiber_id and section are preserved (not replaced with defaults)."""
        msg = _make_message(fiber_id="", section="")
        assert self.service.get_buffer_key(msg) == ":"

    def test_key_contains_colon_separator(self):
        """The key always uses a single colon as separator."""
        msg = _make_message(fiber_id="a", section="b")
        key = self.service.get_buffer_key(msg)
        assert key.count(":") == 1


# ---------------------------------------------------------------------------
# Tests: _apply_cnn_counts
# ---------------------------------------------------------------------------


class TestApplyCnnCounts:
    """Test _apply_cnn_counts: maps counting intervals to detections.

    The counter operates on a time_window_duration * fs sample window.
    Detections have _t_mid_sample relative to the current batch (trimmed).
    The method offsets detections to the counting window's coordinate system
    (the batch occupies the tail of the counting window) and assigns
    vehicle_count from the matching interval.
    """

    def setup_method(self):
        self.service = _make_bare_service()

    @staticmethod
    def _make_counter(time_window_duration: float = 360.0, fs: float = 10.0):
        """Create a minimal mock counter with the attributes _apply_cnn_counts reads."""
        counter = MagicMock()
        counter.time_window_duration = time_window_duration
        counter.fs = fs
        return counter

    def test_basic_count_assignment(self):
        """Detection within a counting interval gets the interval's count."""
        # Setup: time_window_samples = 360 * 10 = 3600.
        # Single detection at _t_mid_sample=50 -> batch_samples = 51.
        # batch_offset = 3600 - 51 = 3549.
        # t_in_window = 3549 + 50 = 3599 -> falls in [3500, 3600).
        counter = self._make_counter(time_window_duration=360.0, fs=10.0)
        detections = [
            {"_t_mid_sample": 50, "direction": 0, "speed_kmh": 60.0, "vehicle_count": 1.0},
        ]
        counts = [[5.0]]  # section 0 has 1 interval with count=5
        intervals = [([3500], [3600])]  # section 0: starts=[3500], ends=[3600]

        self.service._apply_cnn_counts(detections, counts, intervals, counter)

        assert detections[0]["vehicle_count"] == 5.0

    def test_multiple_intervals_correct_match(self):
        """Detection matches the correct interval among several."""
        counter = self._make_counter(time_window_duration=360.0, fs=10.0)
        # time_window_samples = 3600.
        # batch_samples = max(50, 150) + 1 = 151, batch_offset = 3600 - 151 = 3449.
        detections = [
            {"_t_mid_sample": 50, "direction": 0, "speed_kmh": 60.0, "vehicle_count": 1.0},
            {"_t_mid_sample": 150, "direction": 1, "speed_kmh": 80.0, "vehicle_count": 1.0},
        ]
        # Two intervals in section 0
        counts = [[3.0, 7.0]]
        intervals = [
            ([3400, 3550], [3500, 3600]),  # interval 0: [3400, 3500), interval 1: [3550, 3600)
        ]

        self.service._apply_cnn_counts(detections, counts, intervals, counter)

        # det[0]: t_in_window = 3449 + 50 = 3499, falls in [3400, 3500) -> count=3.0
        assert detections[0]["vehicle_count"] == 3.0
        # det[1]: t_in_window = 3449 + 150 = 3599, falls in [3550, 3600) -> count=7.0
        assert detections[1]["vehicle_count"] == 7.0

    def test_detection_outside_all_intervals_not_modified(self):
        """Detection outside all intervals keeps its original vehicle_count."""
        counter = self._make_counter(time_window_duration=360.0, fs=10.0)
        # time_window_samples = 3600, batch_samples = 121, batch_offset = 3479.
        # t_in_window = 3479 + 120 = 3599 -> NOT in [3400, 3450).
        detections = [
            {"_t_mid_sample": 120, "direction": 0, "speed_kmh": 55.0, "vehicle_count": 1.0},
        ]
        counts = [[2.0]]
        intervals = [([3400], [3450])]

        self.service._apply_cnn_counts(detections, counts, intervals, counter)

        assert detections[0]["vehicle_count"] == 1.0  # unchanged

    def test_empty_detections(self):
        """No detections -> no-op, no error."""
        counter = self._make_counter()
        detections: list = []
        counts = [[5.0]]
        intervals = [([0], [100])]

        # Should not raise
        self.service._apply_cnn_counts(detections, counts, intervals, counter)
        assert detections == []

    def test_empty_counts(self):
        """Empty counts list -> early return, detections unchanged."""
        counter = self._make_counter()
        detections = [
            {"_t_mid_sample": 10, "direction": 0, "speed_kmh": 50.0, "vehicle_count": 1.0},
        ]
        self.service._apply_cnn_counts(detections, [], [([0], [100])], counter)
        assert detections[0]["vehicle_count"] == 1.0

    def test_empty_intervals(self):
        """Empty intervals list -> early return, detections unchanged."""
        counter = self._make_counter()
        detections = [
            {"_t_mid_sample": 10, "direction": 0, "speed_kmh": 50.0, "vehicle_count": 1.0},
        ]
        self.service._apply_cnn_counts(detections, [[5.0]], [], counter)
        assert detections[0]["vehicle_count"] == 1.0

    def test_none_counts_in_section(self):
        """None as section counts -> early return."""
        counter = self._make_counter()
        detections = [
            {"_t_mid_sample": 10, "direction": 0, "speed_kmh": 50.0, "vehicle_count": 1.0},
        ]
        self.service._apply_cnn_counts(detections, [None], [None], counter)
        assert detections[0]["vehicle_count"] == 1.0

    def test_empty_starts_and_ends(self):
        """Empty starts/ends arrays -> early return, detections unchanged."""
        counter = self._make_counter()
        detections = [
            {"_t_mid_sample": 10, "direction": 0, "speed_kmh": 50.0, "vehicle_count": 1.0},
        ]
        self.service._apply_cnn_counts(detections, [[]], [([], [])], counter)
        assert detections[0]["vehicle_count"] == 1.0

    def test_detection_without_t_mid_sample_skipped(self):
        """Detection missing _t_mid_sample is skipped (not modified)."""
        counter = self._make_counter(time_window_duration=360.0, fs=10.0)
        detections = [
            {"direction": 0, "speed_kmh": 60.0, "vehicle_count": 1.0},
            {"_t_mid_sample": None, "direction": 1, "speed_kmh": 70.0, "vehicle_count": 1.0},
        ]
        counts = [[10.0]]
        intervals = [([0], [5000])]

        self.service._apply_cnn_counts(detections, counts, intervals, counter)

        # Neither detection should be modified (first has no key, second has None)
        assert detections[0]["vehicle_count"] == 1.0
        assert detections[1]["vehicle_count"] == 1.0

    def test_count_floor_at_one(self):
        """Counts below 1.0 are floored to 1.0 by max(1.0, count)."""
        counter = self._make_counter(time_window_duration=360.0, fs=10.0)
        # time_window_samples=3600, batch_samples=51, batch_offset=3549.
        # t_in_window = 3549 + 50 = 3599 -> falls in [3500, 3600).
        detections = [
            {"_t_mid_sample": 50, "direction": 0, "speed_kmh": 60.0, "vehicle_count": 1.0},
        ]
        counts = [[0.3]]  # below 1.0
        intervals = [([3500], [3600])]

        self.service._apply_cnn_counts(detections, counts, intervals, counter)

        # max(1.0, 0.3) = 1.0
        assert detections[0]["vehicle_count"] == 1.0

    def test_batch_samples_computed_from_detections(self):
        """batch_samples = max(_t_mid_sample) + 1 across all detections."""
        counter = self._make_counter(time_window_duration=10.0, fs=10.0)
        # time_window_samples = 100
        # batch_samples = max(20, 80) + 1 = 81
        # batch_offset = 100 - 81 = 19
        detections = [
            {"_t_mid_sample": 20, "direction": 0, "speed_kmh": 50.0, "vehicle_count": 1.0},
            {"_t_mid_sample": 80, "direction": 1, "speed_kmh": 60.0, "vehicle_count": 1.0},
        ]
        # det[0]: t_in_window = 19 + 20 = 39 -> interval [30, 50) matches
        # det[1]: t_in_window = 19 + 80 = 99 -> interval [90, 100) matches
        counts = [[2.0, 4.0]]
        intervals = [([30, 90], [50, 100])]

        self.service._apply_cnn_counts(detections, counts, intervals, counter)

        assert detections[0]["vehicle_count"] == 2.0
        assert detections[1]["vehicle_count"] == 4.0

    def test_all_detections_have_no_t_mid_sample(self):
        """When batch_samples=0 (all detections lack _t_mid_sample), early return."""
        counter = self._make_counter()
        detections = [
            {"direction": 0, "speed_kmh": 60.0, "vehicle_count": 1.0},
            {"direction": 1, "speed_kmh": 70.0, "vehicle_count": 1.0},
        ]
        counts = [[5.0]]
        intervals = [([0], [5000])]

        self.service._apply_cnn_counts(detections, counts, intervals, counter)

        assert detections[0]["vehicle_count"] == 1.0
        assert detections[1]["vehicle_count"] == 1.0

    def test_interval_boundary_inclusive_start_exclusive_end(self):
        """The interval check is s <= t_in_window < e (start inclusive, end exclusive)."""
        counter = self._make_counter(time_window_duration=10.0, fs=10.0)
        # time_window_samples=100, batch_samples=51, batch_offset=49

        # Detection exactly at interval start
        det_at_start = {"_t_mid_sample": 1, "direction": 0, "speed_kmh": 60.0, "vehicle_count": 1.0}
        # Detection exactly at interval end (should NOT match)
        det_at_end = {"_t_mid_sample": 50, "direction": 0, "speed_kmh": 60.0, "vehicle_count": 1.0}
        detections = [det_at_start, det_at_end]
        # batch_samples = max(1, 50) + 1 = 51
        # batch_offset = 100 - 51 = 49
        # det_at_start: t_in_window = 49 + 1 = 50
        # det_at_end: t_in_window = 49 + 50 = 99
        counts = [[9.0]]
        intervals = [([50], [99])]  # interval [50, 99)

        self.service._apply_cnn_counts(detections, counts, intervals, counter)

        # det_at_start at 50 is >= 50 and < 99 -> matched
        assert det_at_start["vehicle_count"] == 9.0
        # det_at_end at 99 is not < 99 -> NOT matched
        assert det_at_end["vehicle_count"] == 1.0

    def test_large_count_preserved(self):
        """Large count values are preserved (no upper cap in this method)."""
        counter = self._make_counter(time_window_duration=360.0, fs=10.0)
        detections = [
            {"_t_mid_sample": 50, "direction": 0, "speed_kmh": 60.0, "vehicle_count": 1.0},
        ]
        counts = [[42.0]]
        intervals = [([3500], [3600])]

        self.service._apply_cnn_counts(detections, counts, intervals, counter)

        assert detections[0]["vehicle_count"] == 42.0

    def test_multiple_detections_same_interval(self):
        """Multiple detections in the same interval all get the same count."""
        counter = self._make_counter(time_window_duration=10.0, fs=10.0)
        # time_window_samples=100, batch_samples=31, batch_offset=69
        detections = [
            {"_t_mid_sample": 10, "direction": 0, "speed_kmh": 50.0, "vehicle_count": 1.0},
            {"_t_mid_sample": 20, "direction": 1, "speed_kmh": 55.0, "vehicle_count": 1.0},
            {"_t_mid_sample": 30, "direction": 0, "speed_kmh": 60.0, "vehicle_count": 1.0},
        ]
        # batch_samples = 31, batch_offset = 69
        # det[0]: 69+10=79, det[1]: 69+20=89, det[2]: 69+30=99 -> all in [70, 100)
        counts = [[3.0]]
        intervals = [([70], [100])]

        self.service._apply_cnn_counts(detections, counts, intervals, counter)

        assert detections[0]["vehicle_count"] == 3.0
        assert detections[1]["vehicle_count"] == 3.0
        assert detections[2]["vehicle_count"] == 3.0


# ---------------------------------------------------------------------------
# Tests: _get_or_create_context
# ---------------------------------------------------------------------------


class TestGetOrCreateContext:
    """Test LRU eviction behavior of _get_or_create_context."""

    def setup_method(self):
        self.service = _make_bare_service()
        self.service._processing_contexts = OrderedDict()

    def test_creates_new_context(self):
        """First call for a key creates a fresh ProcessingContext."""
        ctx = self.service._get_or_create_context("carros:seg1")
        assert isinstance(ctx, ProcessingContext)
        assert ctx.channel_start == 0
        assert ctx.channel_step == 1

    def test_returns_existing_context(self):
        """Second call for the same key returns the same object."""
        ctx1 = self.service._get_or_create_context("carros:seg1")
        ctx1.channel_start = 42
        ctx2 = self.service._get_or_create_context("carros:seg1")
        assert ctx2 is ctx1
        assert ctx2.channel_start == 42

    def test_multiple_keys_coexist(self):
        """Different keys get independent contexts."""
        ctx_a = self.service._get_or_create_context("carros:seg1")
        ctx_b = self.service._get_or_create_context("mathis:seg2")
        assert ctx_a is not ctx_b
        assert len(self.service._processing_contexts) == 2

    def test_eviction_at_capacity(self):
        """When _MAX_PROCESSING_CONTEXTS is reached, oldest entries are evicted."""
        max_ctx = self.service._MAX_PROCESSING_CONTEXTS  # 100

        # Fill to capacity
        for i in range(max_ctx):
            self.service._get_or_create_context(f"fiber:{i}")

        assert len(self.service._processing_contexts) == max_ctx
        assert "fiber:0" in self.service._processing_contexts

        # Adding one more should evict the oldest (fiber:0)
        self.service._get_or_create_context("fiber:new")

        assert len(self.service._processing_contexts) == max_ctx
        assert "fiber:0" not in self.service._processing_contexts
        assert "fiber:new" in self.service._processing_contexts

    def test_eviction_removes_oldest_first(self):
        """Multiple evictions remove entries in insertion order."""
        max_ctx = self.service._MAX_PROCESSING_CONTEXTS

        for i in range(max_ctx):
            self.service._get_or_create_context(f"fiber:{i}")

        # Add 5 new keys -> oldest 5 should be evicted
        for i in range(5):
            self.service._get_or_create_context(f"new:{i}")

        assert len(self.service._processing_contexts) == max_ctx
        for i in range(5):
            assert f"fiber:{i}" not in self.service._processing_contexts
        # fiber:5 through fiber:99 and new:0 through new:4 should remain
        assert "fiber:5" in self.service._processing_contexts
        assert "fiber:99" in self.service._processing_contexts
        assert "new:4" in self.service._processing_contexts

    def test_accessing_existing_key_does_not_evict(self):
        """Accessing an existing key doesn't trigger eviction."""
        max_ctx = self.service._MAX_PROCESSING_CONTEXTS

        for i in range(max_ctx):
            self.service._get_or_create_context(f"fiber:{i}")

        # Access fiber:0 again (it already exists)
        self.service._get_or_create_context("fiber:0")

        assert len(self.service._processing_contexts) == max_ctx
        # fiber:0 should still be present
        assert "fiber:0" in self.service._processing_contexts


# ---------------------------------------------------------------------------
# Tests: _should_visualize
# ---------------------------------------------------------------------------


class TestShouldVisualize:
    """Test visualization rate-limiting logic."""

    def setup_method(self):
        self.service = _make_bare_service()
        # _should_visualize reads self._model_spec.visualization.interval_seconds
        mock_viz = MagicMock()
        mock_viz.interval_seconds = 60.0  # 60s interval
        mock_spec = MagicMock()
        mock_spec.visualization = mock_viz
        self.service._model_spec = mock_spec

    def test_first_call_returns_false(self):
        """First call for a new buffer_key returns False (skip first window)."""
        assert self.service._should_visualize("carros:seg1") is False

    def test_second_call_before_interval_returns_false(self):
        """Call within the interval returns False."""
        self.service._should_visualize("carros:seg1")  # first call -> False
        result = self.service._should_visualize("carros:seg1")  # immediate second call
        assert result is False

    def test_returns_true_after_interval(self):
        """Call after the interval has elapsed returns True."""
        self.service._should_visualize("carros:seg1")  # first call -> False, sets timestamp

        # Simulate time passing by patching the last viz time
        self.service._last_viz_time["carros:seg1"] = time.time() - 61.0

        result = self.service._should_visualize("carros:seg1")
        assert result is True

    def test_resets_timer_after_true(self):
        """After returning True, the timer resets and subsequent calls return False."""
        self.service._should_visualize("carros:seg1")
        self.service._last_viz_time["carros:seg1"] = time.time() - 61.0

        assert self.service._should_visualize("carros:seg1") is True
        # Immediately after -> False
        assert self.service._should_visualize("carros:seg1") is False

    def test_independent_per_buffer_key(self):
        """Each buffer_key has its own independent rate limit."""
        self.service._should_visualize("carros:seg1")
        self.service._should_visualize("mathis:seg1")

        # Only carros has elapsed
        self.service._last_viz_time["carros:seg1"] = time.time() - 61.0

        assert self.service._should_visualize("carros:seg1") is True
        assert self.service._should_visualize("mathis:seg1") is False

    def test_zero_interval_always_true_after_first(self):
        """With interval=0, every call after the first should return True."""
        self.service._model_spec.visualization.interval_seconds = 0.0
        self.service._should_visualize("key")  # first -> False
        assert self.service._should_visualize("key") is True
        assert self.service._should_visualize("key") is True

    def test_very_large_interval(self):
        """With a very large interval, calls always return False (after the first)."""
        self.service._model_spec.visualization.interval_seconds = 999999.0
        self.service._should_visualize("key")  # first -> False
        assert self.service._should_visualize("key") is False
