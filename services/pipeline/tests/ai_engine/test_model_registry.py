"""Tests for ModelRegistry (lazy-loading with LRU eviction, thread-safe).

Validates:
- Default model retrieval via "default" and empty string hints
- Lazy loading of unknown model hints
- Cache hits for previously loaded models
- LRU eviction when capacity is exceeded
- Fallback to default model on load failure
- Thread-safe concurrent access
- Per-buffer-key counter instances
"""

from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_pipeline_root = Path(__file__).resolve().parents[2]
if str(_pipeline_root) not in sys.path:
    sys.path.insert(0, str(_pipeline_root))

from ai_engine.model_registry import ModelRegistry  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_spec(*, counting_enabled: bool = False) -> MagicMock:
    """Build a minimal mock ModelSpec that satisfies ModelRegistry.__init__."""
    spec = MagicMock()
    spec.path = "/fake/model/path"
    spec.counting.enabled = counting_enabled
    spec.inference.samples_per_window = 312
    spec.inference.gauge_meters = 15.3846
    spec.inference.channels_per_section = 9
    spec.inference.sampling_rate_hz = 10.4167
    spec.inference.bidirectional_rnn = True
    spec.exp_name = "test_exp"
    spec.version = "best"
    spec.speed_detection.time_overlap_ratio = 0.25
    spec.speed_detection.glrt_window = 20
    spec.speed_detection.min_speed_kmh = 20.0
    spec.speed_detection.max_speed_kmh = 120.0
    spec.speed_detection.correlation_threshold = 300.0
    spec.speed_detection.use_calibration = False
    spec.speed_detection.bidirectional_detection = True
    spec.speed_detection.speed_glrt_factor = 1.0
    spec.speed_detection.speed_weighting = False
    spec.speed_detection.speed_positive_glrt_only = False
    spec.visualization.enabled = False
    spec.fiber_id = "test_fiber"
    return spec


def _build_registry(
    *,
    max_models: int = 20,
    counting_enabled: bool = False,
) -> tuple[ModelRegistry, MagicMock, MagicMock, MagicMock]:
    """Build a ModelRegistry with all heavy dependencies mocked out.

    Returns (registry, mock_get_model_spec, mock_Args, mock_VehicleSpeedEstimator).
    """
    mock_spec = _make_mock_spec(counting_enabled=counting_enabled)

    with (
        patch("ai_engine.model_registry.get_model_spec", return_value=mock_spec) as mock_gms,
        patch("ai_engine.model_registry.Args_NN_model_all_channels") as mock_args,
        patch("ai_engine.model_registry.VehicleSpeedEstimator") as mock_vse,
        patch("ai_engine.model_registry.VehicleCounter", return_value=MagicMock(name="counter")),
        patch("ai_engine.model_registry.build_counting_network"),
    ):
        # Each call to VehicleSpeedEstimator() returns a distinct MagicMock
        mock_vse.side_effect = lambda **kwargs: MagicMock(name="estimator_instance")

        registry = ModelRegistry(
            default_model_name="default_model",
            max_models=max_models,
        )

    return registry, mock_gms, mock_args, mock_vse


# ---------------------------------------------------------------------------
# Speed estimator tests
# ---------------------------------------------------------------------------


class TestGetSpeedEstimatorDefault:
    """Tests for retrieving the default speed estimator."""

    def test_default_hint_returns_default_model(self) -> None:
        registry, *_ = _build_registry()
        result = registry.get_speed_estimator("default")
        assert result is registry._default_model

    def test_empty_hint_returns_default_model(self) -> None:
        registry, *_ = _build_registry()
        result = registry.get_speed_estimator("")
        assert result is registry._default_model


class TestGetSpeedEstimatorLazyLoading:
    """Tests for lazy loading of non-default models."""

    def test_unknown_hint_triggers_load(self) -> None:
        registry, *_ = _build_registry()

        mock_spec = _make_mock_spec()
        mock_estimator = MagicMock(name="lazy_loaded_estimator")

        with (
            patch("ai_engine.model_registry.get_model_spec", return_value=mock_spec),
            patch("ai_engine.model_registry.Args_NN_model_all_channels"),
            patch(
                "ai_engine.model_registry.VehicleSpeedEstimator",
                return_value=mock_estimator,
            ),
        ):
            result = registry.get_speed_estimator("custom_model")

        assert result is mock_estimator
        assert "custom_model" in registry._loaded_models

    def test_cached_model_not_reloaded(self) -> None:
        registry, *_ = _build_registry()

        mock_spec = _make_mock_spec()
        call_count = 0

        def _counting_factory(**kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            return MagicMock(name=f"estimator_{call_count}")

        with (
            patch("ai_engine.model_registry.get_model_spec", return_value=mock_spec),
            patch("ai_engine.model_registry.Args_NN_model_all_channels"),
            patch(
                "ai_engine.model_registry.VehicleSpeedEstimator",
                side_effect=_counting_factory,
            ),
        ):
            first = registry.get_speed_estimator("model_a")
            second = registry.get_speed_estimator("model_a")

        assert first is second
        assert call_count == 1, "Model should be loaded only once"


class TestLRUEviction:
    """Tests for LRU eviction when max_models capacity is reached."""

    def test_eviction_at_capacity(self) -> None:
        registry, *_ = _build_registry(max_models=2)

        models: dict[str, MagicMock] = {}

        def _make_estimator(**kwargs: object) -> MagicMock:
            name = f"estimator_{len(models)}"
            m = MagicMock(name=name)
            return m

        mock_spec = _make_mock_spec()
        with (
            patch("ai_engine.model_registry.get_model_spec", return_value=mock_spec),
            patch("ai_engine.model_registry.Args_NN_model_all_channels"),
            patch(
                "ai_engine.model_registry.VehicleSpeedEstimator",
                side_effect=_make_estimator,
            ),
        ):
            # Load model_a and model_b (fills capacity)
            models["a"] = registry.get_speed_estimator("model_a")
            models["b"] = registry.get_speed_estimator("model_b")
            assert len(registry._loaded_models) == 2

            # Load model_c — should evict model_a (oldest)
            models["c"] = registry.get_speed_estimator("model_c")

        assert "model_a" not in registry._loaded_models, "model_a should be evicted"
        assert "model_b" in registry._loaded_models
        assert "model_c" in registry._loaded_models
        assert len(registry._loaded_models) == 2

    def test_lru_access_refreshes_order(self) -> None:
        """Accessing a model moves it to end, so it is not evicted first."""
        registry, *_ = _build_registry(max_models=2)

        mock_spec = _make_mock_spec()
        with (
            patch("ai_engine.model_registry.get_model_spec", return_value=mock_spec),
            patch("ai_engine.model_registry.Args_NN_model_all_channels"),
            patch(
                "ai_engine.model_registry.VehicleSpeedEstimator",
                side_effect=lambda **kw: MagicMock(),
            ),
        ):
            registry.get_speed_estimator("model_a")
            registry.get_speed_estimator("model_b")

            # Re-access model_a to refresh its LRU position
            registry.get_speed_estimator("model_a")

            # Now load model_c — model_b should be evicted (it is oldest)
            registry.get_speed_estimator("model_c")

        assert "model_b" not in registry._loaded_models, "model_b should be evicted"
        assert "model_a" in registry._loaded_models
        assert "model_c" in registry._loaded_models


class TestLoadFailureFallback:
    """Tests for fallback behavior when model loading fails."""

    def test_load_failure_falls_back_to_default(self, caplog: pytest.LogCaptureFixture) -> None:
        registry, *_ = _build_registry()

        with (
            patch(
                "ai_engine.model_registry.get_model_spec",
                side_effect=RuntimeError("model not found"),
            ),
            caplog.at_level(logging.DEBUG, logger="ai_engine.model_registry"),
        ):
            result = registry.get_speed_estimator("bad_model")

        assert result is registry._default_model
        assert "bad_model" in registry._loaded_models
        # The fallback should be the default model instance stored in the cache
        assert registry._loaded_models["bad_model"] is registry._default_model
        # Verify the error was logged
        assert any("bad_model" in r.message and r.levelno == logging.ERROR for r in caplog.records)

    def test_default_model_failure_raises(self) -> None:
        """If the default model itself fails to load, the error must propagate."""
        _make_mock_spec()

        with (
            patch(
                "ai_engine.model_registry.get_model_spec",
                side_effect=RuntimeError("fatal error"),
            ),
            patch("ai_engine.model_registry.Args_NN_model_all_channels"),
            patch("ai_engine.model_registry.VehicleSpeedEstimator"),
            pytest.raises(RuntimeError, match="fatal error"),
        ):
            ModelRegistry(default_model_name="default_model")


class TestThreadSafety:
    """Tests for concurrent access to the registry."""

    def test_concurrent_access(self) -> None:
        """10 threads hitting get_speed_estimator simultaneously must not corrupt state."""
        registry, *_ = _build_registry(max_models=20)

        mock_spec = _make_mock_spec()
        errors: list[Exception] = []
        results: dict[str, MagicMock] = {}
        results_lock = threading.Lock()

        def _worker(hint: str) -> None:
            try:
                model = registry.get_speed_estimator(hint)
                with results_lock:
                    results[hint] = model
            except Exception as exc:
                errors.append(exc)

        with (
            patch("ai_engine.model_registry.get_model_spec", return_value=mock_spec),
            patch("ai_engine.model_registry.Args_NN_model_all_channels"),
            patch(
                "ai_engine.model_registry.VehicleSpeedEstimator",
                side_effect=lambda **kw: MagicMock(),
            ),
        ):
            threads = [threading.Thread(target=_worker, args=(f"model_{i}",)) for i in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5)

        assert not errors, f"Threads raised errors: {errors}"
        assert len(results) == 10
        # Each distinct hint should have its own model in the cache
        assert len(registry._loaded_models) == 10

    def test_concurrent_same_model(self) -> None:
        """Multiple threads requesting the same hint should all get the same instance."""
        registry, *_ = _build_registry()

        mock_spec = _make_mock_spec()
        results: list[MagicMock] = []
        results_lock = threading.Lock()

        def _worker() -> None:
            model = registry.get_speed_estimator("shared_model")
            with results_lock:
                results.append(model)

        with (
            patch("ai_engine.model_registry.get_model_spec", return_value=mock_spec),
            patch("ai_engine.model_registry.Args_NN_model_all_channels"),
            patch(
                "ai_engine.model_registry.VehicleSpeedEstimator",
                side_effect=lambda **kw: MagicMock(),
            ),
        ):
            threads = [threading.Thread(target=_worker) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5)

        # All threads should get the same cached instance
        assert len(results) == 10
        first = results[0]
        assert all(r is first for r in results), "All threads should receive the same instance"


# ---------------------------------------------------------------------------
# Counter tests
# ---------------------------------------------------------------------------


class TestGetCounter:
    """Tests for per-buffer-key counter retrieval."""

    def test_default_counter_for_default_hint(self) -> None:
        registry, *_ = _build_registry(counting_enabled=True)

        with patch(
            "ai_engine.model_registry.VehicleCounter",
            return_value=MagicMock(name="counter"),
        ):
            result = registry.get_counter("default")

        assert result is registry._default_counter

    def test_different_buffer_keys_get_different_counters(self) -> None:
        registry, *_ = _build_registry(counting_enabled=True)

        mock_spec = _make_mock_spec(counting_enabled=True)
        counter_instances: list[MagicMock] = []

        def _make_counter(**kwargs: object) -> MagicMock:
            c = MagicMock(name=f"counter_{len(counter_instances)}")
            counter_instances.append(c)
            return c

        with (
            patch("ai_engine.model_registry.get_model_spec", return_value=mock_spec),
            patch(
                "ai_engine.model_registry.VehicleCounter",
                side_effect=_make_counter,
            ),
            patch("ai_engine.model_registry.build_counting_network"),
        ):
            c1 = registry.get_counter("model_x", buffer_key="fiber1:section_a")
            c2 = registry.get_counter("model_x", buffer_key="fiber1:section_b")

        assert c1 is not c2, "Different buffer_keys must produce different counters"

    def test_same_buffer_key_returns_cached_counter(self) -> None:
        registry, *_ = _build_registry(counting_enabled=True)

        mock_spec = _make_mock_spec(counting_enabled=True)

        with (
            patch("ai_engine.model_registry.get_model_spec", return_value=mock_spec),
            patch(
                "ai_engine.model_registry.VehicleCounter",
                return_value=MagicMock(name="cached_counter"),
            ),
            patch("ai_engine.model_registry.build_counting_network"),
        ):
            c1 = registry.get_counter("model_x", buffer_key="fiber1:section_a")
            c2 = registry.get_counter("model_x", buffer_key="fiber1:section_a")

        assert c1 is c2, "Same buffer_key should return the cached counter"

    def test_empty_buffer_key_uses_model_hint(self) -> None:
        """When buffer_key is empty, the counter_key falls back to model_hint."""
        registry, *_ = _build_registry(counting_enabled=True)

        mock_spec = _make_mock_spec(counting_enabled=True)

        with (
            patch("ai_engine.model_registry.get_model_spec", return_value=mock_spec),
            patch(
                "ai_engine.model_registry.VehicleCounter",
                return_value=MagicMock(name="hint_counter"),
            ),
            patch("ai_engine.model_registry.build_counting_network"),
        ):
            c1 = registry.get_counter("model_x")
            c2 = registry.get_counter("model_x")

        assert c1 is c2
