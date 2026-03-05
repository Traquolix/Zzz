from __future__ import annotations

import asyncio
import logging
import os
import threading
import time

# Suppress PyTorch deprecation warnings
import warnings
from collections import OrderedDict
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from opentelemetry import trace

# Import standalone functions from separate module (no PyTorch dependency)
from ai_engine.message_utils import (
    ProcessingContext,
    create_detection_messages,
    extract_channel_metadata,
    messages_to_arrays,
    validate_sampling_rate,
)
from ai_engine.model_vehicle import (
    Args_NN_model_all_channels,
    VehicleSpeedEstimator,
)
from ai_engine.model_vehicle.simple_interval_counter import VehicleCounter, build_counting_network
from ai_engine.model_vehicle.calibration import CalibrationManager

# Unified config loader
from config import (
    get_default_model_name,
    get_model_spec,
    get_service_name,
    load_service_config,
)
from shared import RollingBufferedTransformer
from shared.ai_metrics import AIMetrics
from shared.message import Message
from shared.otel_setup import get_correlation_id, setup_otel

warnings.filterwarnings("ignore", message=".*torch.meshgrid.*")
warnings.filterwarnings("ignore", message=".*NNPACK.*")

try:
    import torch
except ImportError:
    torch = None

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
        calibration_manager: Optional[CalibrationManager] = None,
        max_models: int = 20,
        ai_metrics: Optional[AIMetrics] = None,
    ):
        self._calibration_manager = calibration_manager
        self._max_models = max_models
        self._ai_metrics = ai_metrics
        self._loaded_models: OrderedDict[str, VehicleSpeedEstimator] = OrderedDict()
        self._loaded_counters: Dict[str, VehicleCounter] = {}
        self._lock = threading.Lock()

        # Build default model and counter through the same code path as all others
        self._default_model = self._load_speed_estimator(default_model_name)
        spec = get_model_spec(default_model_name)
        self._default_counter = self._load_counter(default_model_name) if spec.counting.enabled else None

    def get_speed_estimator(self, model_hint: str) -> VehicleSpeedEstimator:
        """Get speed estimator by model hint (lazy-loaded with LRU eviction)."""
        if model_hint == "default" or not model_hint:
            return self._default_model

        with self._lock:
            if model_hint in self._loaded_models:
                self._loaded_models.move_to_end(model_hint)
                if self._ai_metrics:
                    self._ai_metrics.record_cache_hit(model_hint)
                return self._loaded_models[model_hint]

            # Evict oldest if at capacity
            while len(self._loaded_models) >= self._max_models:
                oldest, _ = self._loaded_models.popitem(last=False)
                logger.info(f"Evicted model {oldest} (LRU)")
                if self._ai_metrics:
                    self._ai_metrics.record_cache_eviction(oldest)
                if oldest in self._loaded_counters:
                    del self._loaded_counters[oldest]

            # Load new model
            if self._ai_metrics:
                self._ai_metrics.record_cache_miss(model_hint)
            model = self._load_speed_estimator(model_hint)
            self._loaded_models[model_hint] = model
            return model

    def get_counter(self, model_hint: str, buffer_key: str = "") -> Optional[VehicleCounter]:
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
                N_channels=spec.inference.channels_per_section - 1,  # overlap_space = Nch-1 → step=1 (matches notebook)
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
            )

            logger.info(f"Loaded speed estimator: {model_hint}")
            return estimator

        except Exception as e:
            if not hasattr(self, "_default_model"):
                # Default model itself failed — cannot fall back, must crash
                raise
            logger.error(f"Failed to load model '{model_hint}': {e}. Using default.")
            return self._default_model

    def _load_counter(self, model_hint: str) -> Optional[VehicleCounter]:
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
                    raise ValueError(
                        f"Counting model path escapes module directory: {model_path}"
                    )
                if model_path.exists():
                    nn_model = build_counting_network()
                    # Model file may be full-object (legacy) or state_dict.
                    # Try state_dict first; fall back to full-object load.
                    try:
                        state = torch.load(model_path, map_location="cpu", weights_only=True)
                    except Exception:
                        state = torch.load(model_path, map_location="cpu", weights_only=False).state_dict()
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
            )
            logger.info(f"Loaded counter for model: {model_hint}")
            return counter

        except Exception as e:
            if not hasattr(self, "_default_counter"):
                raise
            logger.warning(f"Failed to load counter for '{model_hint}': {e}")
            return self._default_counter


class AIEngineService(RollingBufferedTransformer):
    """AI Engine with multi-model routing and rolling buffer support.

    Uses a rolling FIFO buffer for seamless overlapping window processing:
    - Window size: 300 samples (30s at 10Hz)
    - Step size: 250 samples (valid output per window after edge trimming)
    - Overlap: 50 samples (2 * edge_trim) - naturally maintained by rolling buffer

    Supports section-aware model routing:
    - Buffers messages by fiber_id:section (compound key)
    - Routes to correct model based on model_hint in message
    - Lazy-loads models on first use
    """

    def __init__(self):
        # Load config from unified loader (fibers.yaml + env vars)
        service_name = get_service_name("ai_engine")
        service_config = load_service_config("ai_engine")

        if torch is None:
            raise RuntimeError("PyTorch is required for AI engine but not available")

        # Get default model spec from fibers.yaml
        default_model_name = get_default_model_name()
        self._model_spec = get_model_spec(default_model_name)

        self._processing_contexts: OrderedDict[str, ProcessingContext] = OrderedDict()
        self._analyses_completed = 0
        self._counts_completed = 0
        self._last_stats_time = time.time()

        super().__init__(service_name, service_config)

        setup_otel(service_name, "1.0.0")
        self.tracer = trace.get_tracer(__name__)

        # Initialize AI-specific metrics
        self.ai_metrics = AIMetrics(service_name)

        # Initialize calibration manager
        calibration_path = os.getenv("CALIBRATION_PATH", "/app/calibration")
        self.calibration_manager = CalibrationManager(calibration_path)
        self.logger.info(f"CalibrationManager initialized: path={calibration_path}")

        # Build all models through a single code path (ModelRegistry)
        self.model_registry = ModelRegistry(
            default_model_name=default_model_name,
            calibration_manager=self.calibration_manager,
            ai_metrics=self.ai_metrics,
        )
        self.speed_processor = self.model_registry._default_model
        self.count_processor = self.model_registry._default_counter

        self._log_init()

    def _log_init(self) -> None:
        window_size = self._model_spec.inference.samples_per_window
        step_size = self._model_spec.inference.step_size
        overlap = window_size - step_size
        self.logger.info(
            f"Initialized with rolling buffer: window={window_size}, "
            f"step={step_size}, overlap={overlap}, "
            f"counting={'enabled' if self._model_spec.counting.enabled else 'disabled'}"
        )

    def get_window_size(self) -> int:
        """Window size for processing (e.g., 300 samples = 30s at 10Hz)."""
        return self._model_spec.inference.samples_per_window

    def get_step_size(self) -> int:
        """Step size for rolling buffer (e.g., 250 = valid output per window).

        This determines how often we process: every step_size new messages.
        The overlap (window_size - step_size = 50) is naturally maintained
        by the rolling FIFO buffer.
        """
        return self._model_spec.inference.step_size

    def get_buffer_key(self, message: Message) -> str:
        """Buffer by fiber_id:section for section-aware batching.

        Messages with same fiber_id and section are buffered together
        so they can be processed with the correct model.
        """
        fiber_id = message.payload.get("fiber_id", "unknown")
        section = message.payload.get("section", "default")
        return f"{fiber_id}:{section}"

    def get_buffer_timeout_seconds(self) -> float:
        return self.config.buffer_timeout

    async def process_buffer(self, messages: List[Message]) -> List[Message]:
        with self.tracer.start_as_current_span("process_buffer") as span:
            try:
                correlation_id = get_correlation_id()
                if correlation_id:
                    span.set_attribute("correlation_id", correlation_id)

                if not messages:
                    span.set_attribute("buffer.empty", True)
                    return []

                start_time = time.time()

                # Extract routing info from first message (all same in buffer)
                first_payload = messages[0].payload
                fiber_id = first_payload.get("fiber_id", "unknown")
                section = first_payload.get("section", "default")
                model_hint = first_payload.get("model_hint", "default")
                buffer_key = self.get_buffer_key(messages[0])

                # Add span attributes for observability
                span.set_attribute("buffer.message_count", len(messages))
                span.set_attribute("fiber_id", fiber_id)
                span.set_attribute("section", section)
                span.set_attribute("model_hint", model_hint)
                span.set_attribute("buffer_key", buffer_key)

                # Get the appropriate model for this section
                speed_processor = self.model_registry.get_speed_estimator(model_hint)
                count_processor = self.model_registry.get_counter(model_hint, buffer_key)

                # Get or create processing context for this buffer
                ctx = self._get_or_create_context(buffer_key)
                data_array, timestamps, timestamps_ns = self._messages_to_arrays(messages, ctx)
                span.set_attribute("data.shape", str(data_array.shape))

                # Validate input dimensions before inference
                # Skip old/incompatible messages gracefully instead of flooding DLQ
                num_channels = data_array.shape[0] if len(data_array.shape) > 0 else 0
                expected_min_channels = self._model_spec.inference.channels_per_section
                if num_channels < expected_min_channels:
                    self.logger.warning(
                        f"Skipping buffer {buffer_key}: insufficient channels "
                        f"({num_channels} < {expected_min_channels}). "
                        f"Likely old data with different configuration."
                    )
                    span.set_attribute("skipped.reason", "insufficient_channels")
                    return []

                # Diagnostic: log input data statistics to debug zero GLRT
                data_min = float(np.min(data_array))
                data_max = float(np.max(data_array))
                data_std = float(np.std(data_array))
                data_absmax = max(abs(data_min), abs(data_max))
                self.logger.info(
                    f"Input diag [{buffer_key}]: shape={data_array.shape}, "
                    f"absmax={data_absmax:.6f}, std={data_std:.6f}, "
                    f"all_zero={data_absmax < 1e-10}"
                )

                # Data capture: save first few buffers to disk for offline comparison
                capture_dir = "/app/data_captures"
                capture_count_attr = "_capture_count"
                if not hasattr(self, capture_count_attr):
                    self._capture_count = 0
                    import os
                    os.makedirs(capture_dir, exist_ok=True)
                if self._capture_count < 5:
                    capture_path = f"{capture_dir}/{buffer_key.replace(':', '_')}_{self._capture_count}.npz"
                    np.savez(
                        capture_path,
                        data=data_array,
                        timestamps_ns=np.array(timestamps_ns),
                        buffer_key=buffer_key,
                        shape=data_array.shape,
                    )
                    self._capture_count += 1
                    self.logger.info(f"Captured data to {capture_path}")

                # Set section name for visualization filename uniqueness
                if hasattr(speed_processor, "set_section"):
                    speed_processor.set_section(section)

                try:
                    detections = (
                        await self._run_ai_inference(
                            data_array,
                            timestamps,
                            timestamps_ns,
                            buffer_key,
                            ctx,
                            speed_processor=speed_processor,
                            count_processor=count_processor,
                        )
                    )
                except RuntimeError as e:
                    # Catch PyTorch dimension mismatches (e.g., "input.size(-1) must be equal to input_size")
                    error_msg = str(e)
                    if "input_size" in error_msg or "size" in error_msg.lower():
                        self.logger.warning(
                            f"Skipping buffer {buffer_key}: model dimension mismatch - {error_msg}. "
                            f"Data shape: {data_array.shape}. Likely old/incompatible data."
                        )
                        span.set_attribute("skipped.reason", "dimension_mismatch")
                        return []
                    raise  # Re-raise other RuntimeErrors

                span.set_attribute("inference.success", len(detections) > 0)
                span.set_attribute("detections.count", len(detections))

                output_messages = self._create_detection_messages(
                    fiber_id, detections, ctx,
                )

                processing_time = (time.time() - start_time) * 1000
                processing_time_seconds = processing_time / 1000.0
                self._analyses_completed += 1

                span.set_attribute("output.message_count", len(output_messages))
                span.set_attribute("processing.time_ms", processing_time)

                # Record AI-specific metrics
                num_detections = len(detections)
                self.ai_metrics.record_inference(
                    duration_seconds=processing_time_seconds,
                    fiber_id=fiber_id,
                    section=section,
                    num_detections=num_detections,
                )

                # Record individual vehicle detections
                for det in detections:
                    self.ai_metrics.record_vehicle(
                        fiber_id=fiber_id,
                        section=section,
                        direction=det["direction"],
                        speed_kmh=det["speed_kmh"],
                    )

                self.logger.info(
                    f"Analysis complete for {buffer_key} (model={model_hint}): "
                    f"{len(output_messages)} messages in {processing_time:.1f}ms"
                )

                if self._analyses_completed % self._STATS_INTERVAL == 0:
                    self._show_stats()

                return output_messages

            except Exception as e:
                span.record_exception(e)
                self.logger.error(f"Error in AI analysis: {e}")
                raise

    def _extract_channel_metadata(self, payload: dict) -> tuple[int, int]:
        """Extract channel_start and channel_step from message payload."""
        return extract_channel_metadata(payload)

    def _validate_sampling_rate(self, payload: dict) -> None:
        """Validate that incoming sampling rate matches expected rate."""
        validate_sampling_rate(payload, self._model_spec.inference.sampling_rate_hz)

    _MAX_PROCESSING_CONTEXTS = 100

    def _get_or_create_context(self, buffer_key: str) -> ProcessingContext:
        """Get or create a processing context for a buffer key (LRU-bounded)."""
        if buffer_key not in self._processing_contexts:
            # Evict oldest if at capacity
            while len(self._processing_contexts) >= self._MAX_PROCESSING_CONTEXTS:
                oldest_key = next(iter(self._processing_contexts))
                del self._processing_contexts[oldest_key]
                logger.debug(f"Evicted processing context: {oldest_key}")

            self._processing_contexts[buffer_key] = ProcessingContext()
        return self._processing_contexts[buffer_key]

    def _messages_to_arrays(self, messages: List[Message], ctx: ProcessingContext) -> tuple:
        """Convert list of messages to numpy arrays for inference."""
        return messages_to_arrays(
            messages, ctx, self._model_spec.inference.sampling_rate_hz, log_fn=self.logger.info
        )

    async def _run_ai_inference(
        self,
        data: np.ndarray,
        timestamp_list: list,
        timestamps_ns: list,
        buffer_key: str,
        ctx: ProcessingContext,
        speed_processor: Optional[VehicleSpeedEstimator] = None,
        count_processor: Optional[VehicleCounter] = None,
    ) -> list[dict]:
        """Run AI inference and return unified detections.

        Returns:
            List of detection dicts with speed, count, and vehicle type.
        """
        return await asyncio.to_thread(
            self._sync_ai_inference,
            data,
            timestamp_list,
            timestamps_ns,
            buffer_key,
            ctx,
            speed_processor or self.speed_processor,
            count_processor,
        )

    def _sync_ai_inference(
        self,
        data: np.ndarray,
        timestamp_list: list,
        timestamps_ns: list,
        buffer_key: str,
        ctx: ProcessingContext,
        speed_processor: VehicleSpeedEstimator,
        count_processor: Optional[VehicleCounter] = None,
    ) -> list[dict]:
        timestamps = np.array(timestamp_list)
        timestamps_ns_array = np.array(timestamps_ns)

        all_detections = []
        min_vehicle_duration_s = self._model_spec.speed_detection.min_vehicle_duration_s
        classify_threshold_factor = self._model_spec.counting.truck_ratio_for_split
        yield_count = 0

        for result in speed_processor.process_file(data, timestamps, timestamps_ns_array):
            yield_count += 1

            direction = int(result.direction_mask[0, 0])

            # Diagnostic: log GLRT statistics to understand detection threshold behavior
            glrt = result.glrt_summed
            glrt_max = float(np.max(glrt)) if glrt.size > 0 else 0.0
            glrt_mean = float(np.mean(glrt)) if glrt.size > 0 else 0.0
            summed_threshold = speed_processor.corr_threshold * (speed_processor.Nch - 1)
            above_count = int(np.sum(glrt >= summed_threshold)) if glrt.size > 0 else 0
            dir_label = "fwd" if direction == 1 else "rev"
            self.logger.info(
                f"GLRT diag [{buffer_key} {dir_label}]: "
                f"max={glrt_max:.0f}, mean={glrt_mean:.0f}, "
                f"threshold={summed_threshold:.0f}, "
                f"samples_above={above_count}/{glrt.shape[-1] if glrt.ndim > 1 else len(glrt)}, "
                f"shape={glrt.shape}"
            )

            detections = speed_processor.extract_detections(
                glrt_summed=result.glrt_summed,
                aligned_speed_pairs=result.aligned_speed_per_pair,
                direction=direction,
                timestamps_ns=result.timestamps_ns,
                min_vehicle_duration_s=min_vehicle_duration_s,
                classify_threshold_factor=classify_threshold_factor,
            )
            all_detections.extend(detections)

            # Optional: feed count data to visualizer (does NOT produce Kafka output)
            if self._model_spec.counting.enabled and count_processor is not None:
                try:
                    chunk_start_ns = int(result.timestamps_ns[0]) if result.timestamps_ns is not None else None
                    for chunk_result in count_processor.process_data_chunk(
                        aligned_speed=result.aligned_speed_per_pair,
                        correlations=result.glrt_summed,
                        aligned_data=result.aligned_data,
                        timestamp_ns=chunk_start_ns,
                    ):
                        counts, intervals, window_start_ns = chunk_result
                        count_timestamps = [window_start_ns] if window_start_ns is not None else ctx.timestamps_ns
                        speed_processor.set_count_data((counts, intervals, count_timestamps))
                except Exception as e:
                    self.logger.error(f"Error in vehicle counting (visualization): {e}")

        if yield_count == 0:
            raise RuntimeError(f"AI model did not yield results for {buffer_key}")

        # Generate notebook-style waterfall visualization every window
        if speed_processor.visualizer is not None:
            try:
                # Offset _t_mid_sample from trimmed window to full window
                edge_trim = speed_processor.edge_trim
                for d in all_detections:
                    if d.get("_t_mid_sample") is not None:
                        d["_t_mid_sample"] += edge_trim
                fwd_dets = [d for d in all_detections if d["direction"] == 1]
                rev_dets = [d for d in all_detections if d["direction"] == 2]
                speed_processor.visualizer.generate_notebook_waterfall(
                    raw_data=data,
                    fwd_detections=fwd_dets,
                    rev_detections=rev_dets,
                    date_window=timestamps,
                    fs=speed_processor.fs,
                    channel_start=ctx.channel_start,
                    channel_step=ctx.channel_step,
                    gauge=speed_processor.model_args.gauge,
                    min_speed_kmh=speed_processor.min_speed,
                    max_speed_kmh=speed_processor.max_speed,
                )
            except Exception as e:
                self.logger.error(f"Notebook waterfall generation failed: {e}")

        return all_detections

    def _create_detection_messages(
        self,
        fiber_id: str,
        detections: list[dict],
        ctx: ProcessingContext,
    ) -> List[Message]:
        """Create unified detection messages (speed + count + vehicle type)."""
        return create_detection_messages(
            fiber_id=fiber_id,
            detections=detections,
            ctx=ctx,
            service_name=self.service_name,
            log_fn=self.logger.info,
        )

    _STATS_INTERVAL = 5  # Log stats every N analyses

    def _show_stats(self) -> None:
        current_time = time.time()
        elapsed = current_time - self._last_stats_time
        rate = self._STATS_INTERVAL / elapsed if elapsed > 0 else 0

        self.logger.info(f"Stats: analyses={self._analyses_completed}, rate={rate:.2f}/sec")
        if self._model_spec.counting.enabled:
            self.logger.info(f"Stats: counts={self._counts_completed}")

        self._last_stats_time = current_time


async def main():
    ai_engine = AIEngineService()
    await ai_engine.start()


if __name__ == "__main__":
    asyncio.run(main())
