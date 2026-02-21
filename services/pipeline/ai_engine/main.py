from __future__ import annotations

import asyncio
import logging
import threading
import time

# Suppress PyTorch deprecation warnings
import warnings
from collections import OrderedDict, deque
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from opentelemetry import trace

# Import standalone functions from separate module (no PyTorch dependency)
from ai_engine.message_utils import (
    ProcessingContext,
    create_count_messages,
    create_speed_messages,
    extract_channel_metadata,
    messages_to_arrays,
    validate_sampling_rate,
)
from ai_engine.model_vehicle import (
    Args_NN_model_all_channels,
    VehicleCounter,
    VehicleSpeedEstimator,
)
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


class ModelRegistry:
    """Lazy-loading model registry with LRU eviction for multi-model support.

    Models are loaded on first use and evicted when capacity is reached.
    Thread-safe for concurrent access.

    Args:
        default_model: Fallback model for unknown hints
        default_counter: Fallback counter for unknown hints
        calibration_manager: Manager for loading calibration data
        max_models: Maximum models to keep loaded (LRU eviction when exceeded)
    """

    def __init__(
        self,
        default_model: VehicleSpeedEstimator,
        default_counter: Optional[VehicleCounter] = None,
        calibration_manager: Optional[CalibrationManager] = None,
        max_models: int = 20,
    ):
        self._default_model = default_model
        self._default_counter = default_counter
        self._calibration_manager = calibration_manager
        self._max_models = max_models
        self._loaded_models: OrderedDict[str, VehicleSpeedEstimator] = OrderedDict()
        self._loaded_counters: Dict[str, VehicleCounter] = {}
        self._lock = threading.Lock()

    def get_speed_estimator(self, model_hint: str) -> VehicleSpeedEstimator:
        """Get speed estimator by model hint (lazy-loaded with LRU eviction)."""
        if model_hint == "default" or not model_hint:
            return self._default_model

        with self._lock:
            if model_hint in self._loaded_models:
                # Move to end (most recently used) - O(1)
                self._loaded_models.move_to_end(model_hint)
                return self._loaded_models[model_hint]

            # Evict oldest if at capacity
            while len(self._loaded_models) >= self._max_models:
                oldest, _ = self._loaded_models.popitem(last=False)
                logger.info(f"Evicted model {oldest} (LRU)")
                if oldest in self._loaded_counters:
                    del self._loaded_counters[oldest]

            # Load new model
            model = self._load_speed_estimator(model_hint)
            self._loaded_models[model_hint] = model
            return model

    def get_counter(self, model_hint: str) -> Optional[VehicleCounter]:
        """Get vehicle counter by model hint (lazy-loaded)."""
        if model_hint == "default" or not model_hint:
            return self._default_counter

        with self._lock:
            if model_hint not in self._loaded_counters:
                self._loaded_counters[model_hint] = self._load_counter(model_hint)
            return self._loaded_counters[model_hint]

    def get_loaded_model_count(self) -> int:
        """Get number of currently loaded models."""
        return len(self._loaded_models)

    def get_loaded_models(self) -> List[str]:
        """Get list of currently loaded model names."""
        return list(self._loaded_models.keys())

    def _load_speed_estimator(self, model_hint: str) -> VehicleSpeedEstimator:
        """Load a speed estimator model from fibers.yaml config."""
        try:
            spec = get_model_spec(model_hint)
            logger.info(f"Loading speed estimator model: {model_hint} from {spec.path}")

            model_args = Args_NN_model_all_channels(
                data_window_length=spec.inference.samples_per_window,
                gauge=spec.inference.gauge_meters,
                Nch=spec.inference.channels_per_section,
                N_channels=1,
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
            )

            logger.info(f"Loaded speed estimator: {model_hint}")
            return estimator

        except Exception as e:
            logger.error(f"Failed to load model '{model_hint}': {e}. Using default.")
            return self._default_model

    def _load_counter(self, model_hint: str) -> Optional[VehicleCounter]:
        """Load a vehicle counter model from fibers.yaml config."""
        try:
            spec = get_model_spec(model_hint)
            if not spec.counting.enabled:
                return None

            # For now, counting uses same model path as speed estimation
            # In the future, this could be separate per model
            logger.info(f"Loading counter for model: {model_hint}")
            # TODO: implement per-model counter loading if needed
            return self._default_counter

        except Exception as e:
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

        # Get default model spec from fibers.yaml
        default_model_name = get_default_model_name()
        self._model_spec = get_model_spec(default_model_name)

        self._processing_contexts: Dict[str, ProcessingContext] = {}  # Per-buffer contexts
        self._analyses_completed = 0
        self._counts_completed = 0
        self._last_stats_time = time.time()

        super().__init__(service_name, service_config)

        setup_otel(service_name, "1.0.0")
        self.tracer = trace.get_tracer(__name__)

        # Initialize AI-specific metrics
        self.ai_metrics = AIMetrics(service_name)

        # Initialize calibration manager
        import os

        calibration_path = os.getenv("CALIBRATION_PATH", "/app/calibration")
        self.calibration_manager = CalibrationManager(calibration_path)
        self.logger.info(f"CalibrationManager initialized: path={calibration_path}")

        self._init_ai_models()

        # Initialize model registry for multi-model support
        self.model_registry = ModelRegistry(
            default_model=self.speed_processor,
            default_counter=self.count_processor if self._model_spec.counting.enabled else None,
            calibration_manager=self.calibration_manager,
        )

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

    def _init_ai_models(self) -> None:
        if torch is None:
            raise RuntimeError("PyTorch is required for AI engine but not available")

        spec = self._model_spec

        model_args = Args_NN_model_all_channels(
            data_window_length=spec.inference.samples_per_window,
            gauge=spec.inference.gauge_meters,
            Nch=spec.inference.channels_per_section,
            N_channels=1,
            fs=spec.inference.sampling_rate_hz,
            exp_name=spec.exp_name,
            version=spec.version,
            bidirectional_rnn=spec.inference.bidirectional_rnn,
        )

        # Load calibration for default model if enabled
        calibration_data = None
        if spec.speed_detection.use_calibration:
            fiber_id = spec.fiber_id or "carros"
            calibration_data = self.calibration_manager.load_calibration(fiber_id)
            if calibration_data is None:
                self.logger.warning(
                    f"Calibration enabled but missing for '{fiber_id}', using static threshold"
                )

        self.speed_processor = VehicleSpeedEstimator(
            model_args=model_args,
            ovr_time=spec.speed_detection.time_overlap_ratio,
            glrt_win=spec.speed_detection.glrt_window,
            min_speed=spec.speed_detection.min_speed_kmh,
            max_speed=spec.speed_detection.max_speed_kmh,
            corr_threshold=spec.speed_detection.correlation_threshold,
            verbose=False,
            calibration_data=calibration_data,
        )

        if spec.counting.enabled:
            # Check if using temporary simple counting or neural network counting
            use_simple = getattr(spec.counting, "use_simple_counting_TEMPORARY", False)

            if use_simple:
                # TEMPORARY: Simple interval-based counting (thesis Λ-based method)
                from ai_engine.model_vehicle.simple_interval_counter import (
                    SimpleIntervalCounter,
                )  # noqa: E402

                self.count_processor = SimpleIntervalCounter(
                    fiber_id=spec.fiber_id or "unknown",
                )
                self.logger.warning(
                    "=" * 80 + "\n"
                    "TEMPORARY: Using simple interval-based counting\n"
                    "Neural network counting disabled due to normalization mismatch.\n"
                    "Set 'use_simple_counting_TEMPORARY: false' in config to use NN.\n" + "=" * 80
                )
            else:
                # Original neural network counting
                model_base_path = Path(spec.path)
                model_path = model_base_path / "vehicle_counting_model.pt"
                threshold_path = model_base_path / "detection_thresholds.csv"
                mean_std_path = model_base_path / "mean_std_features.csv"

                self.count_processor = VehicleCounter(
                    vehicle_counting_model=str(model_path),
                    time_window_duration=spec.counting.window_seconds,
                    detection_threshold=str(threshold_path),
                    mean_std_features=str(mean_std_path) if mean_std_path.exists() else None,
                    Nch=spec.inference.channels_per_section,
                    fs=spec.inference.sampling_rate_hz,
                    corr_threshold=spec.speed_detection.correlation_threshold,
                )
                self.logger.info(
                    f"Vehicle counting initialized (NN): window={spec.counting.window_seconds}s"
                )
        else:
            self.count_processor = None

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
                count_processor = self.model_registry.get_counter(model_hint)

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

                # Set section name for visualization filename uniqueness
                if hasattr(speed_processor, "set_section"):
                    speed_processor.set_section(section)

                try:
                    filtered_speeds, count_results, window_timestamps_ns = (
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

                span.set_attribute("inference.success", filtered_speeds is not None)
                if filtered_speeds is not None:
                    span.set_attribute("speeds.shape", str(filtered_speeds.shape))

                # Use window timestamps (trimmed, correct for the actual output data)
                # instead of batch timestamps which don't account for overlap/trimming
                output_timestamps_ns = (
                    window_timestamps_ns.tolist()
                    if window_timestamps_ns is not None
                    else timestamps_ns
                )

                output_messages = self._create_speed_messages(
                    fiber_id, filtered_speeds, timestamps, output_timestamps_ns, ctx
                )
                for msg in output_messages:
                    msg.output_id = "speed"

                if (
                    count_results is not None
                    and self._model_spec.counting.enabled
                    and count_processor is not None
                ):
                    count_messages = self._create_count_messages(fiber_id, count_results, ctx)
                    output_messages.extend(count_messages)
                    span.set_attribute("counting.detections", len(count_messages))

                processing_time = (time.time() - start_time) * 1000
                processing_time_seconds = processing_time / 1000.0
                self._analyses_completed += 1

                span.set_attribute("output.message_count", len(output_messages))
                span.set_attribute("processing.time_ms", processing_time)

                # Record AI-specific metrics
                num_detections = len([m for m in output_messages if m.output_id == "speed"])
                self.ai_metrics.record_inference(
                    duration_seconds=processing_time_seconds,
                    fiber_id=fiber_id,
                    section=section,
                    num_detections=num_detections,
                )

                # Record individual vehicle detections for speed messages
                for msg in output_messages:
                    if msg.output_id == "speed":
                        speed = msg.payload.get("speed_kmh", 0)
                        direction = msg.payload.get("direction", 0)
                        self.ai_metrics.record_vehicle(
                            fiber_id=fiber_id,
                            section=section,
                            direction=direction,
                            speed_kmh=speed,
                        )

                self.logger.info(
                    f"Analysis complete for {buffer_key} (model={model_hint}): "
                    f"{len(output_messages)} messages in {processing_time:.1f}ms"
                )

                if self._analyses_completed % 5 == 0:
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

    def _get_or_create_context(self, buffer_key: str) -> ProcessingContext:
        """Get or create a processing context for a buffer key."""
        if buffer_key not in self._processing_contexts:
            spec = self._model_spec
            buffer_size = (
                spec.counting.samples_per_window(spec.inference.sampling_rate_hz)
                + spec.inference.samples_per_window
            )
            self._processing_contexts[buffer_key] = ProcessingContext(
                counting_buffer=deque(maxlen=buffer_size)
            )
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
    ) -> tuple:
        """Run AI inference and return (filtered_speeds, count_results, window_timestamps_ns).

        Returns:
            Tuple of (filtered_speeds, count_results, window_timestamps_ns)
            - filtered_speeds: Speed array trimmed to valid window region
            - count_results: Vehicle counting results (or None)
            - window_timestamps_ns: Correct timestamps for the output window (trimmed)
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
    ) -> tuple:
        timestamps = np.array(timestamp_list)
        timestamps_ns_array = np.array(timestamps_ns)

        # Collect results from all yields (process_file may yield multiple windows
        # when batch/window size mismatch causes accumulated saved data)
        all_speeds = []
        all_timestamps_ns = []
        all_count_results = []

        for (
            unaligned_speed,
            filtered_speed,
            glrt_res,
            aligned,
            date_window,
            date_window_ns,
        ) in speed_processor.process_file(data, timestamps, timestamps_ns_array):
            all_speeds.append(unaligned_speed)
            if date_window_ns is not None:
                all_timestamps_ns.append(date_window_ns)

            count_results = None
            if self._model_spec.counting.enabled and count_processor is not None:
                try:
                    use_simple = getattr(
                        self._model_spec.counting, "use_simple_counting_TEMPORARY", False
                    )

                    if use_simple:
                        speed_intervals = speed_processor.intervals
                        window_timestamps_ns = (
                            date_window_ns.tolist()
                            if date_window_ns is not None
                            else ctx.timestamps_ns
                        )
                        count_results = count_processor.count_from_intervals(
                            filtered_speed=filtered_speed,
                            intervals_list=speed_intervals,
                            timestamps_ns=window_timestamps_ns,
                        )
                    else:
                        count_results = self._process_counting(
                            filtered_speed, glrt_res, aligned, count_processor, ctx
                        )

                    speed_processor.set_count_data(count_results)
                    if count_results is not None:
                        all_count_results.append(count_results)
                except Exception as e:
                    self.logger.error(f"Error in vehicle counting: {e}")

        if not all_speeds:
            raise RuntimeError(f"AI model did not yield results for {buffer_key}")

        # Concatenate results from multiple windows
        if len(all_speeds) == 1:
            combined_speeds = all_speeds[0]
            combined_timestamps_ns = all_timestamps_ns[0] if all_timestamps_ns else None
        else:
            # Multiple windows: concatenate along time axis
            combined_speeds = np.concatenate(all_speeds, axis=-1)
            combined_timestamps_ns = (
                np.concatenate(all_timestamps_ns) if all_timestamps_ns else None
            )
            self.logger.info(
                f"Processed {len(all_speeds)} windows in single batch for {buffer_key}"
            )

        # For counting, use the last result (or could aggregate)
        combined_count_results = all_count_results[-1] if all_count_results else None

        return combined_speeds, combined_count_results, combined_timestamps_ns

    def _process_counting(
        self,
        filtered_speed,
        glrt_res,
        aligned,
        count_processor: VehicleCounter,
        ctx: ProcessingContext,
    ) -> tuple | None:
        ctx.counting_buffer.extend(ctx.timestamps_ns)
        spec = self._model_spec

        self.logger.debug(
            f"Counting buffer size: {len(ctx.counting_buffer)}, required: {spec.counting.samples_per_window(spec.inference.sampling_rate_hz)}"
        )

        for count, intervals in count_processor.process_data_chunk(
            aligned_speed=filtered_speed, correlations=glrt_res, aligned_data=aligned
        ):
            buffer_list = list(ctx.counting_buffer)
            counting_samples = spec.counting.samples_per_window(spec.inference.sampling_rate_hz)
            window_timestamps = buffer_list[:counting_samples]

            ctx.counting_buffer = deque(
                buffer_list[spec.counting.step_samples :],
                maxlen=ctx.counting_buffer.maxlen,
            )

            self._counts_completed += 1
            return (count, intervals, window_timestamps)

        return None

    def _create_speed_messages(
        self,
        fiber_id: str,
        filtered_speeds: np.ndarray,
        timestamp_list: list,
        timestamps_ns: list,
        ctx: ProcessingContext,
    ) -> List[Message]:
        """Create speed messages from filtered speeds array."""
        spec = self._model_spec
        return create_speed_messages(
            fiber_id=fiber_id,
            filtered_speeds=filtered_speeds,
            timestamps_ns=timestamps_ns,
            ctx=ctx,
            min_speed_kmh=spec.speed_detection.min_speed_kmh,
            max_speed_kmh=spec.speed_detection.max_speed_kmh,
            sampling_rate_hz=spec.inference.sampling_rate_hz,
            service_name=self.service_name,
            log_fn=self.logger.info,
        )

    def _create_count_messages(
        self, fiber_id: str, count_results: tuple, ctx: ProcessingContext
    ) -> List[Message]:
        """Create count messages from counting results."""
        spec = self._model_spec
        counting_samples = spec.counting.samples_per_window(spec.inference.sampling_rate_hz)
        return create_count_messages(
            fiber_id=fiber_id,
            count_results=count_results,
            ctx=ctx,
            sampling_rate_hz=spec.inference.sampling_rate_hz,
            channels_per_section=spec.inference.channels_per_section,
            counting_samples=counting_samples,
            step_samples=spec.counting.step_samples,
            service_name=self.service_name,
            log_fn=self.logger.info,
        )

    def _show_stats(self) -> None:
        current_time = time.time()
        elapsed = current_time - self._last_stats_time
        rate = 5 / elapsed if elapsed > 0 else 0

        self.logger.info(f"Stats: analyses={self._analyses_completed}, rate={rate:.2f}/sec")
        if self._model_spec.counting.enabled:
            self.logger.info(f"Stats: counts={self._counts_completed}")

        self._last_stats_time = current_time


async def main():
    ai_engine = AIEngineService()
    await ai_engine.start()


if __name__ == "__main__":
    asyncio.run(main())
