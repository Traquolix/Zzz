from __future__ import annotations

import asyncio
import logging
import os
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
    get_ai_engine_fiber_id,
    get_default_model_name,
    get_model_spec,
    get_service_name,
    load_service_config,
)
from shared import RollingBufferedTransformer
from shared.ai_metrics import AIMetrics
from shared.message import KafkaMessage, Message
from shared.gpu_lock import gpu_lock
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

        # Per-fiber filtering: if FIBER_ID is set, only process that fiber's messages
        self._fiber_filter = get_ai_engine_fiber_id()
        if self._fiber_filter:
            self.logger.info(f"Fiber filter active: processing only fiber '{self._fiber_filter}'")

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

    async def _start_service_loops(self):
        """Override to initialize batch collection state before starting loops."""
        self._pending_ready: dict = {}
        self._msgs_since_first_ready = 0
        await super()._start_service_loops()

    async def _handle_rolling_message(self, message: Message) -> None:
        """Filter by FIBER_ID, buffer, and batch-process ready sections together.

        Instead of dispatching immediately when one section is ready, we collect
        ready sections and dispatch after all sections in the fiber have had a
        chance to become ready. Since messages arrive interleaved (seg1, seg2,
        seg3, seg4, seg1, ...), all sections become ready within num_sections
        messages of each other.
        """
        if self._fiber_filter:
            msg_fiber = message.payload.get("fiber_id", "")
            if msg_fiber != self._fiber_filter:
                return

        try:
            buffer_key = self.get_buffer_key(message)

            # Evict LRU buffer if at capacity
            if (
                buffer_key not in self._rolling_buffers
                and len(self._rolling_buffers) >= self._max_active_buffers
            ):
                lru_key, lru_buffer = self._rolling_buffers.popitem(last=False)
                self._buffers_evicted += 1
                self.metrics.record_buffer_eviction(lru_key)
                messages = list(lru_buffer["deque"])
                if messages:
                    self.logger.warning(
                        f"Buffer limit ({self._max_active_buffers}) reached, "
                        f"evicting LRU buffer '{lru_key}' with {len(messages)} messages"
                    )
                    await self._process_rolling_buffer(messages, lru_key, partial=True)

            is_new_buffer = buffer_key not in self._rolling_buffers
            if is_new_buffer:
                self._rolling_buffers[buffer_key] = {
                    "deque": deque(maxlen=self._window_size),
                    "new_count": 0,
                    "last_update": time.time(),
                }
                self.metrics.update_buffer_count(len(self._rolling_buffers))
            else:
                self._rolling_buffers.move_to_end(buffer_key)

            buffer_info = self._rolling_buffers[buffer_key]
            buffer_info["deque"].append(message)
            buffer_info["new_count"] += 1
            buffer_info["last_update"] = time.time()

            # Mark section as ready if threshold reached
            if (
                len(buffer_info["deque"]) >= self._window_size
                and buffer_info["new_count"] >= self._step_size
            ):
                self._pending_ready[buffer_key] = list(buffer_info["deque"])
                buffer_info["new_count"] = 0

            # Track messages since first section became ready
            if self._pending_ready:
                self._msgs_since_first_ready += 1

                # Dispatch when we've waited long enough for all sections.
                # num_buffers = total sections for this fiber. After processing
                # num_buffers more messages, all sections have had a chance.
                num_buffers = len(self._rolling_buffers)
                if self._msgs_since_first_ready >= num_buffers:
                    ready = dict(self._pending_ready)
                    self._pending_ready.clear()
                    self._msgs_since_first_ready = 0
                    self.logger.info(
                        f"Dispatching batch: {len(ready)} sections: "
                        f"{list(ready.keys())}"
                    )
                    task = asyncio.create_task(
                        self._process_sections_batch(ready)
                    )
                    self._processing_tasks.add(task)

        except Exception as e:
            self.logger.error(f"Error handling rolling message {message.id}: {e}")
            self.metrics.record_error("rolling_buffer_management")
            raise

    async def _process_sections_batch(self, ready_sections: dict) -> None:
        """Process multiple sections in a single batched GPU pass."""
        async with self._semaphore:
            start_time = time.time()

            try:
                # Prepare data arrays for each section
                section_inputs = []
                section_meta = []
                for buffer_key, messages in ready_sections.items():
                    first_payload = messages[0].payload
                    fiber_id = first_payload.get("fiber_id", "unknown")
                    section = first_payload.get("section", "default")
                    model_hint = first_payload.get("model_hint", "default")

                    ctx = self._get_or_create_context(buffer_key)
                    data_array, timestamps, timestamps_ns = self._messages_to_arrays(messages, ctx)

                    num_channels = data_array.shape[0] if len(data_array.shape) > 0 else 0
                    expected_min = self._model_spec.inference.channels_per_section
                    if num_channels < expected_min:
                        self.logger.warning(
                            f"Skipping {buffer_key}: insufficient channels "
                            f"({num_channels} < {expected_min})"
                        )
                        continue

                    section_inputs.append((
                        data_array,
                        np.array(timestamps),
                        np.array(timestamps_ns),
                    ))
                    section_meta.append({
                        "buffer_key": buffer_key,
                        "fiber_id": fiber_id,
                        "section": section,
                        "model_hint": model_hint,
                        "messages": messages,
                        "ctx": ctx,
                    })

                if not section_inputs:
                    return

                speed_processor = self.model_registry.get_speed_estimator(
                    section_meta[0]["model_hint"]
                )

                # Run batched inference
                batch_results = await asyncio.to_thread(
                    self._sync_batch_inference,
                    section_inputs,
                    section_meta,
                    speed_processor,
                )

                processing_time = (time.time() - start_time) * 1000

                # Send outputs and record metrics for each section
                total_outputs = 0
                for meta, (detections, output_messages) in zip(section_meta, batch_results):
                    for msg in output_messages:
                        await self._internal_send(msg)
                    total_outputs += len(output_messages)

                    self._analyses_completed += 1
                    self.ai_metrics.record_inference(
                        duration_seconds=processing_time / 1000.0 / len(section_meta),
                        fiber_id=meta["fiber_id"],
                        section=meta["section"],
                        num_detections=len(detections),
                    )
                    for det in detections:
                        self.ai_metrics.record_vehicle(
                            fiber_id=meta["fiber_id"],
                            section=meta["section"],
                            direction=det["direction"],
                            speed_kmh=det["speed_kmh"],
                        )

                self.logger.info(
                    f"Batched analysis complete: {len(section_meta)} sections, "
                    f"{total_outputs} total outputs in {processing_time:.1f}ms"
                )

                processing_time_s = processing_time / 1000.0
                self.metrics.record_message_processed(processing_time_s)
                for meta in section_meta:
                    self.metrics.record_buffer_processed(
                        len(meta["messages"]), meta["buffer_key"], partial=False
                    )

                # Commit last message per section
                for meta in section_meta:
                    messages = meta["messages"]
                    if messages:
                        last_msg = messages[-1]
                        if isinstance(last_msg, KafkaMessage):
                            await self._commit_message(last_msg)

                if self._analyses_completed % self._STATS_INTERVAL == 0:
                    self._show_stats()

            except Exception as e:
                self.logger.error(f"Error in batched AI analysis: {e}")
                self.metrics.record_error("batch_processing")

    def _sync_batch_inference(
        self,
        section_inputs: list,
        section_meta: list,
        speed_processor: VehicleSpeedEstimator,
    ) -> list:
        """Run batched inference across multiple sections."""
        min_vehicle_duration_s = self._model_spec.speed_detection.min_vehicle_duration_s
        classify_threshold_factor = self._model_spec.counting.truck_ratio_for_split

        # Use process_batch for batched GPU pass (exclusive GPU access)
        with gpu_lock():
            batch_results = speed_processor.process_batch(section_inputs)

        results = []
        for i, (section_results, meta) in enumerate(zip(batch_results, section_meta)):
            all_detections = []
            for result in section_results:
                direction = int(result.direction_mask[0, 0])
                detections = speed_processor.extract_detections(
                    glrt_summed=result.glrt_summed,
                    aligned_speed_pairs=result.aligned_speed_per_pair,
                    direction=direction,
                    timestamps_ns=result.timestamps_ns,
                    min_vehicle_duration_s=min_vehicle_duration_s,
                    classify_threshold_factor=classify_threshold_factor,
                )
                all_detections.extend(detections)

            # Count processing (visualization only)
            buffer_key = meta["buffer_key"]
            ctx = meta["ctx"]
            count_processor = self.model_registry.get_counter(
                meta["model_hint"], buffer_key
            )
            if self._model_spec.counting.enabled and count_processor is not None:
                for result in section_results:
                    try:
                        chunk_start_ns = (
                            int(result.timestamps_ns[0])
                            if result.timestamps_ns is not None else None
                        )
                        for chunk_result in count_processor.process_data_chunk(
                            aligned_speed=result.aligned_speed_per_pair,
                            correlations=result.glrt_summed,
                            aligned_data=result.aligned_data,
                            timestamp_ns=chunk_start_ns,
                        ):
                            counts, intervals, window_start_ns = chunk_result
                            count_timestamps = (
                                [window_start_ns] if window_start_ns is not None
                                else ctx.timestamps_ns
                            )
                            speed_processor.set_count_data(
                                (counts, intervals, count_timestamps)
                            )
                    except Exception as e:
                        logger.error(f"Error in vehicle counting: {e}")

            output_messages = self._create_detection_messages(
                meta["fiber_id"], all_detections, ctx,
            )
            results.append((all_detections, output_messages))

        return results

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

        with gpu_lock():
            inference_results = list(speed_processor.process_file(data, timestamps, timestamps_ns_array))

        for result in inference_results:
            yield_count += 1

            direction = int(result.direction_mask[0, 0])

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

        # Generate notebook-style waterfall visualization at configured interval
        if speed_processor.visualizer is not None and self._should_visualize(buffer_key):
            try:
                # Use actual fiber_id from buffer_key (e.g. "carros:default" -> "carros")
                # instead of model_hint which may be "dtan_unified"
                actual_fiber_id = buffer_key.split(":")[0] if ":" in buffer_key else buffer_key
                if actual_fiber_id != speed_processor.visualizer.fiber_id:
                    speed_processor.visualizer.fiber_id = actual_fiber_id
                    speed_processor.visualizer.output_dir = (
                        Path(speed_processor.visualizer.output_dir).parent / actual_fiber_id
                    )
                    speed_processor.visualizer.output_dir.mkdir(parents=True, exist_ok=True)

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

    def _should_visualize(self, buffer_key: str) -> bool:
        """Rate-limit visualization to the configured interval per buffer key."""
        if not hasattr(self, "_last_viz_time"):
            self._last_viz_time: Dict[str, float] = {}
        now = time.time()
        interval = self._model_spec.visualization.interval_seconds
        if buffer_key not in self._last_viz_time:
            self._last_viz_time[buffer_key] = now
            return False  # Skip first window
        last = self._last_viz_time[buffer_key]
        if now - last >= interval:
            self._last_viz_time[buffer_key] = now
            return True
        return False

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
