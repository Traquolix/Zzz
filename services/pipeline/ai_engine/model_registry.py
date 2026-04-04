"""Lazy-loading model registry with LRU eviction for multi-model support.

Manages VehicleSpeedEstimator and VehicleCounter instances. Models are loaded
on first use from fibers.yaml config and evicted when capacity is reached.
Thread-safe for concurrent access.
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from pathlib import Path

import numpy as np

from ai_engine.model_vehicle import (
    Args_NN_model_all_channels,
    VehicleSpeedEstimator,
)
from ai_engine.model_vehicle.calibration import CalibrationManager
from ai_engine.model_vehicle.simple_interval_counter import VehicleCounter, build_counting_network
from config import get_model_spec
from shared.ai_metrics import AIMetrics

try:
    import torch
except ImportError:
    torch = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# Module directory for resolving relative model paths
_MODULE_DIR = Path(__file__).parent.resolve() / "model_vehicle"


class ModelRegistry:
    """Lazy-loading model registry with LRU eviction for multi-model support.

    Models are loaded on first use and evicted when capacity is reached.
    Thread-safe for concurrent access.

    Args:
        default_model_name: Name of the default model to load from fibers.yaml
        calibration_manager: Manager for loading calibration data
        max_models: Maximum models to keep loaded (LRU eviction when exceeded)
    """

    def __init__(
        self,
        default_model_name: str,
        calibration_manager: CalibrationManager | None = None,
        max_models: int = 20,
        ai_metrics: AIMetrics | None = None,
    ):
        self._calibration_manager = calibration_manager
        self._max_models = max_models
        self._ai_metrics = ai_metrics
        self._loaded_models: OrderedDict[str, VehicleSpeedEstimator] = OrderedDict()
        self._loaded_counters: dict[str, VehicleCounter | None] = {}
        self._lock = threading.Lock()

        # Build default model and counter through the same code path as all others
        self._default_model = self._load_speed_estimator(default_model_name)
        spec = get_model_spec(default_model_name)
        self._default_counter = (
            self._load_counter(default_model_name) if spec.counting.enabled else None
        )

    def get_speed_estimator(self, model_hint: str) -> VehicleSpeedEstimator:
        """Get speed estimator by model hint (lazy-loaded with LRU eviction)."""
        if model_hint == "default" or not model_hint:
            return self._default_model

        with self._lock:
            if model_hint in self._loaded_models:
                self._loaded_models.move_to_end(model_hint)
                return self._loaded_models[model_hint]

            # Evict oldest if at capacity
            while len(self._loaded_models) >= self._max_models:
                oldest, _ = self._loaded_models.popitem(last=False)
                logger.info(f"Evicted model {oldest} (LRU)")
                if oldest in self._loaded_counters:
                    del self._loaded_counters[oldest]

            model = self._load_speed_estimator(model_hint)
            self._loaded_models[model_hint] = model
            return model

    def get_counter(self, model_hint: str, buffer_key: str = "") -> VehicleCounter | None:
        """Get vehicle counter by buffer_key (each buffer gets its own stateful counter).

        Counters accumulate data across calls, so each fiber:section buffer
        must have a separate counter instance. The NN model weights are shared.
        """
        # Use buffer_key for counter identity (stateful per section)
        counter_key = buffer_key or model_hint
        if counter_key == "default" or not counter_key:
            return self._default_counter

        with self._lock:
            if counter_key not in self._loaded_counters:
                self._loaded_counters[counter_key] = self._load_counter(model_hint)
            return self._loaded_counters[counter_key]

    def _load_speed_estimator(self, model_hint: str) -> VehicleSpeedEstimator:
        """Load a speed estimator model from fibers.yaml config."""
        try:
            spec = get_model_spec(model_hint)
            logger.info(f"Loading speed estimator model: {model_hint} from {spec.path}")

            model_args = Args_NN_model_all_channels(
                data_window_length=spec.inference.samples_per_window,
                gauge=spec.inference.gauge_meters,
                Nch=spec.inference.channels_per_section,
                N_channels=spec.inference.channels_per_section
                - 1,  # overlap_space = Nch-1 → step=1 (matches notebook)
                fs=spec.inference.sampling_rate_hz,
                exp_name=spec.exp_name,
                version=spec.version,
                bidirectional_rnn=spec.inference.bidirectional_rnn,
            )

            # Load calibration if enabled and available
            calibration_data = None
            if self._calibration_manager and spec.speed_detection.use_calibration:
                fiber_id = spec.fiber_id or model_hint
                calibration_data = self._calibration_manager.load_calibration(fiber_id)
                if calibration_data is None:
                    logger.warning(
                        f"Calibration enabled but missing for '{fiber_id}', using static threshold"
                    )

            # Prepare visualization config if enabled
            # Note: section name will be set per-buffer-key in process_buffer
            visualization_config = None
            if spec.visualization.enabled:
                visualization_config = {
                    "enabled": True,
                    "interval_seconds": spec.visualization.interval_seconds,
                    "output_dir": spec.visualization.output_dir,
                    "fiber_id": spec.fiber_id or model_hint,
                    "section": None,  # Will be set per section
                }

            estimator = VehicleSpeedEstimator(
                model_args=model_args,
                ovr_time=spec.speed_detection.time_overlap_ratio,
                glrt_win=spec.speed_detection.glrt_window,
                min_speed=spec.speed_detection.min_speed_kmh,
                max_speed=spec.speed_detection.max_speed_kmh,
                corr_threshold=spec.speed_detection.correlation_threshold,
                verbose=False,
                calibration_data=calibration_data,
                visualization_config=visualization_config,
                bidirectional_detection=spec.speed_detection.bidirectional_detection,
                speed_glrt_factor=spec.speed_detection.speed_glrt_factor,
                speed_weighting=spec.speed_detection.speed_weighting,
                speed_positive_glrt_only=spec.speed_detection.speed_positive_glrt_only,
                alignment_method=spec.speed_detection.alignment_method,
                nstepsolver=spec.speed_detection.nstepsolver,
                speed_sampling=spec.speed_detection.speed_sampling,
            )

            logger.info(f"Loaded speed estimator: {model_hint}")
            return estimator

        except Exception as e:
            if not hasattr(self, "_default_model"):
                # Default model itself failed — cannot fall back, must crash
                raise
            logger.error(f"Failed to load model '{model_hint}': {e}. Using default.")
            if self._ai_metrics:
                self._ai_metrics.record_model_fallback(model_hint)
            return self._default_model

    def _load_counter(self, model_hint: str) -> VehicleCounter | None:
        """Load a vehicle counter from fibers.yaml config."""
        try:
            spec = get_model_spec(model_hint)
            if not spec.counting.enabled:
                return None

            # Load counting NN model if path is configured
            nn_model = None
            if spec.counting.model_path:
                model_path = (_MODULE_DIR / spec.counting.model_path).resolve()
                # Validate path is within expected model directory (prevent path traversal)
                if not str(model_path).startswith(str(_MODULE_DIR)):
                    raise ValueError(f"Counting model path escapes module directory: {model_path}")
                if model_path.exists():
                    nn_model = build_counting_network()
                    # Model file may be full-object (legacy) or state_dict.
                    # Try state_dict first; fall back to full-object load.
                    try:
                        state = torch.load(model_path, map_location="cpu", weights_only=True)
                    except Exception:
                        state = torch.load(  # nosec B614
                            model_path, map_location="cpu", weights_only=False
                        ).state_dict()
                    nn_model.load_state_dict(state)
                    nn_model.eval()

            thresholds = None
            if spec.counting.thresholds_path:
                thr_path = _MODULE_DIR / spec.counting.thresholds_path
                if thr_path.exists():
                    thresholds = np.loadtxt(thr_path, delimiter=",")

            mean_std = None
            if spec.counting.mean_std_path:
                ms_path = _MODULE_DIR / spec.counting.mean_std_path
                if ms_path.exists():
                    mean_std = np.loadtxt(ms_path, delimiter=",")

            counter = VehicleCounter(
                fiber_id=spec.fiber_id or model_hint,
                sampling_rate_hz=spec.inference.sampling_rate_hz,
                correlation_threshold=spec.speed_detection.correlation_threshold,
                channels_per_section=spec.inference.channels_per_section,
                classify_threshold_factor=spec.counting.classify_threshold_factor,
                min_peak_distance_s=spec.counting.min_peak_distance_s,
                vehicle_counting_model=nn_model,
                detection_thresholds=thresholds,
                mean_std_features=mean_std,
                time_window_duration=spec.counting.time_window_duration,
                truck_ratio_for_split=spec.counting.truck_ratio_for_split,
                corr_threshold=spec.counting.corr_threshold,
                step_samples=spec.inference.samples_per_window,
            )
            logger.info(f"Loaded counter for model: {model_hint}")
            return counter

        except Exception as e:
            if not hasattr(self, "_default_counter"):
                raise
            logger.warning(f"Failed to load counter for '{model_hint}': {e}")
            return self._default_counter
