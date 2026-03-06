"""Tests for AI engine orchestration: ModelRegistry caching, dimension mismatch handling."""

import threading
from collections import OrderedDict
from unittest.mock import MagicMock, patch

from shared.ai_metrics import AIMetrics


class TestModelRegistryCaching:
    """Test ModelRegistry LRU cache behavior and metrics."""

    def test_cache_hit_returns_same_model(self):
        registry = _make_mock_registry(max_models=5)
        model1 = MagicMock()
        registry._loaded_models["model_a"] = model1

        result = registry.get_speed_estimator("model_a")
        assert result is model1

    def test_cache_hit_records_metric(self):
        metrics = AIMetrics("test")
        registry = _make_mock_registry(max_models=5, ai_metrics=metrics)
        registry._loaded_models["model_a"] = MagicMock()

        with patch.object(metrics, "record_cache_hit") as mock_hit:
            registry.get_speed_estimator("model_a")
            mock_hit.assert_called_once_with("model_a")

    def test_cache_miss_loads_model(self):
        registry = _make_mock_registry(max_models=5)
        mock_model = MagicMock()
        registry._load_speed_estimator = MagicMock(return_value=mock_model)

        result = registry.get_speed_estimator("new_model")
        assert result is mock_model
        registry._load_speed_estimator.assert_called_once_with("new_model")

    def test_cache_miss_records_metric(self):
        metrics = AIMetrics("test")
        registry = _make_mock_registry(max_models=5, ai_metrics=metrics)
        registry._load_speed_estimator = MagicMock(return_value=MagicMock())

        with patch.object(metrics, "record_cache_miss") as mock_miss:
            registry.get_speed_estimator("new_model")
            mock_miss.assert_called_once_with("new_model")

    def test_eviction_at_capacity(self):
        registry = _make_mock_registry(max_models=2)
        registry._loaded_models["old1"] = MagicMock()
        registry._loaded_models["old2"] = MagicMock()
        registry._load_speed_estimator = MagicMock(return_value=MagicMock())

        registry.get_speed_estimator("new_model")

        assert "old1" not in registry._loaded_models
        assert "new_model" in registry._loaded_models
        assert len(registry._loaded_models) == 2

    def test_eviction_records_metric(self):
        metrics = AIMetrics("test")
        registry = _make_mock_registry(max_models=1, ai_metrics=metrics)
        registry._loaded_models["old"] = MagicMock()
        registry._load_speed_estimator = MagicMock(return_value=MagicMock())

        with patch.object(metrics, "record_cache_eviction") as mock_evict:
            registry.get_speed_estimator("new_model")
            mock_evict.assert_called_once_with("old")

    def test_default_model_bypasses_cache(self):
        default_model = MagicMock()
        registry = _make_mock_registry(max_models=5)
        registry._default_model = default_model

        result = registry.get_speed_estimator("default")
        assert result is default_model

        result2 = registry.get_speed_estimator("")
        assert result2 is default_model

    def test_lru_order_maintained(self):
        registry = _make_mock_registry(max_models=3)
        registry._loaded_models["a"] = MagicMock()
        registry._loaded_models["b"] = MagicMock()
        registry._loaded_models["c"] = MagicMock()

        # Access 'a' to make it most recently used
        registry.get_speed_estimator("a")

        # Add new model — should evict 'b' (oldest after 'a' was moved)
        registry._load_speed_estimator = MagicMock(return_value=MagicMock())
        registry.get_speed_estimator("d")

        assert "b" not in registry._loaded_models
        assert "a" in registry._loaded_models


class TestAIMetricsCache:
    """Test AIMetrics cache counters exist."""

    def test_cache_counters_created(self):
        metrics = AIMetrics("test")
        assert hasattr(metrics, "model_cache_hits")
        assert hasattr(metrics, "model_cache_misses")
        assert hasattr(metrics, "model_cache_evictions")

    def test_record_methods_exist(self):
        metrics = AIMetrics("test")
        # Should not raise
        metrics.record_cache_hit("model_a")
        metrics.record_cache_miss("model_b")
        metrics.record_cache_eviction("model_c")


# --- Helpers ---


def _make_mock_registry(max_models=20, ai_metrics=None):
    """Create a ModelRegistry-like object without loading real models."""
    from ai_engine.main import ModelRegistry

    # Create a minimal mock that skips __init__
    registry = ModelRegistry.__new__(ModelRegistry)
    registry._calibration_manager = None
    registry._max_models = max_models
    registry._ai_metrics = ai_metrics
    registry._loaded_models = OrderedDict()
    registry._loaded_counters = {}
    registry._lock = threading.Lock()
    registry._default_model = MagicMock()
    registry._default_counter = None
    return registry
