from __future__ import annotations

import asyncio
import logging
import os
import time

# Suppress PyTorch deprecation warnings
import warnings
from collections import OrderedDict, defaultdict, deque
from pathlib import Path

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
from ai_engine.model_registry import ModelRegistry
from ai_engine.model_vehicle import VehicleSpeedEstimator
from ai_engine.model_vehicle.calibration import CalibrationManager
from ai_engine.model_vehicle.simple_interval_counter import VehicleCounter

# Unified config loader
from config import (
    get_default_model_name,
    get_model_spec,
    get_service_name,
    load_service_config,
)
from shared import RollingBufferedTransformer
from shared.ai_metrics import AIMetrics
from shared.gpu_lock import gpu_lock
from shared.message import KafkaMessage, Message
from shared.otel_setup import get_correlation_id, setup_otel

warnings.filterwarnings("ignore", message=".*torch.meshgrid.*")
warnings.filterwarnings("ignore", message=".*NNPACK.*")

try:
    import torch
except ImportError:
    torch = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class AIEngineService(RollingBufferedTransformer):
    """AI Engine with multi-model routing and rolling buffer support.

    Uses a rolling FIFO buffer for seamless overlapping window processing.
    Buffer is sized in messages (each message may contain multiple time samples,
    configured via samples_per_message). Window and step sizes are derived from
    inference config: messages_per_window and step_size.

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

        # Per-fiber pending sections for batch dispatch
        self._pending_per_fiber: dict[str, dict] = {}

        self._log_init()

    def _log_init(self) -> None:
        inf = self._model_spec.inference
        window_msgs = inf.messages_per_window
        step_msgs = inf.step_size
        overlap_msgs = window_msgs - step_msgs
        spm = inf.samples_per_message
        self.logger.info(
            f"Initialized with rolling buffer: window={window_msgs} msgs "
            f"({inf.samples_per_window} samples, {spm} samples/msg), "
            f"step={step_msgs} msgs, overlap={overlap_msgs} msgs, "
            f"counting={'enabled' if self._model_spec.counting.enabled else 'disabled'}"
        )

    def get_window_size(self) -> int:
        """Window size in messages for rolling buffer.

        With multi-sample messages (samples_per_message > 1), fewer messages
        are needed to fill the processing window.
        """
        return int(self._model_spec.inference.messages_per_window)

    def get_step_size(self) -> int:
        """Step size in messages for rolling buffer.

        This determines how often we process: every step_size new messages.
        """
        return int(self._model_spec.inference.step_size)

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
        await super()._start_service_loops()

    async def _handle_rolling_message(self, message: Message) -> None:
        """Buffer messages and batch-process ready sections per fiber.

        Messages arrive interleaved across fibers and sections (carros:seg1,
        carros:seg2, mathis:seg1, ...). We group pending sections by fiber_id
        and dispatch each fiber's batch independently when all its sections
        are ready.
        """
        try:
            buffer_key = self.get_buffer_key(message)
            fiber_id = message.payload.get("fiber_id", "unknown")

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
                    "fiber_id": fiber_id,
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
                self._window_size is not None
                and self._step_size is not None
                and len(buffer_info["deque"]) >= self._window_size
                and buffer_info["new_count"] >= self._step_size
            ):
                if fiber_id not in self._pending_per_fiber:
                    self._pending_per_fiber[fiber_id] = {}
                self._pending_per_fiber[fiber_id][buffer_key] = list(buffer_info["deque"])
                buffer_info["new_count"] = 0

            # Dispatch when all sections for a fiber are ready
            for fid in list(self._pending_per_fiber):
                # Count how many sections this fiber has (active buffers)
                fiber_section_count = sum(
                    1 for info in self._rolling_buffers.values() if info.get("fiber_id") == fid
                )

                # Dispatch when all sections are pending
                pending_count = len(self._pending_per_fiber[fid])
                if pending_count >= fiber_section_count:
                    ready = self._pending_per_fiber.pop(fid)
                    self.logger.info(
                        f"Dispatching batch: {len(ready)} sections: {list(ready.keys())}"
                    )
                    task = asyncio.create_task(self._process_sections_batch(ready))
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
                t_deser = time.time()
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

                    section_inputs.append(
                        (
                            data_array,
                            np.array(timestamps),
                            np.array(timestamps_ns),
                        )
                    )
                    section_meta.append(
                        {
                            "buffer_key": buffer_key,
                            "fiber_id": fiber_id,
                            "section": section,
                            "model_hint": model_hint,
                            "messages": messages,
                            "ctx": ctx,
                        }
                    )

                if not section_inputs:
                    return
                t_deser = (time.time() - t_deser) * 1000

                # Group sections by model_hint for batched GPU passes.
                # Sections sharing a model are processed together; different
                # models get separate passes (future: per-fiber models).
                model_groups: dict[str, tuple[list, list]] = defaultdict(lambda: ([], []))
                for inp, meta in zip(section_inputs, section_meta, strict=False):
                    hint = meta["model_hint"]
                    model_groups[hint][0].append(inp)
                    model_groups[hint][1].append(meta)

                # Run batched inference per model group
                t_infer = time.time()
                all_batch_results: list[tuple[list, list]] = []
                all_batch_meta: list[dict] = []
                for model_hint, (group_inputs, group_meta) in model_groups.items():
                    speed_processor = self.model_registry.get_speed_estimator(model_hint)
                    batch_results = await asyncio.to_thread(
                        self._sync_batch_inference,
                        group_inputs,
                        group_meta,
                        speed_processor,
                    )
                    all_batch_results.extend(batch_results)
                    all_batch_meta.extend(group_meta)
                t_infer = (time.time() - t_infer) * 1000

                processing_time = (time.time() - start_time) * 1000

                # Send outputs and record metrics for each section
                total_outputs = 0
                for meta, (detections, output_messages) in zip(
                    all_batch_meta, all_batch_results, strict=False
                ):
                    for msg in output_messages:
                        await self._internal_send(msg)
                    total_outputs += len(output_messages)
                    self._analyses_completed += 1

                    # Per-window summary metrics (not per-detection)
                    fwd_dets = [d for d in detections if d["direction"] == 0]
                    rev_dets = [d for d in detections if d["direction"] == 1]
                    fwd_peak = max((d["glrt_max"] for d in fwd_dets), default=0)
                    rev_peak = max((d["glrt_max"] for d in rev_dets), default=0)

                    if fwd_dets or not rev_dets:
                        self.ai_metrics.record_window(
                            fiber_id=meta["fiber_id"],
                            section=meta["section"],
                            num_detections=len(fwd_dets),
                            glrt_peak=fwd_peak,
                            direction=0,
                        )
                    if rev_dets:
                        self.ai_metrics.record_window(
                            fiber_id=meta["fiber_id"],
                            section=meta["section"],
                            num_detections=len(rev_dets),
                            glrt_peak=rev_peak,
                            direction=1,
                        )

                t_send = processing_time - t_deser - t_infer
                self.logger.info(
                    f"Batched analysis complete: {len(all_batch_meta)} sections, "
                    f"{total_outputs} total outputs in {processing_time:.1f}ms "
                    f"(deser={t_deser:.0f}ms, infer={t_infer:.0f}ms, send={t_send:.0f}ms)"
                )

                processing_time_s = processing_time / 1000.0
                self.metrics.record_message_processed(processing_time_s)
                for meta in all_batch_meta:
                    self.metrics.record_buffer_processed(
                        len(meta["messages"]), meta["buffer_key"], partial=False
                    )

                # Commit last message per section
                for meta in all_batch_meta:
                    messages = meta["messages"]
                    if messages:
                        last_msg = messages[-1]
                        if isinstance(last_msg, KafkaMessage):
                            await self._commit_message(last_msg)

                if self._analyses_completed % self._STATS_INTERVAL == 0:
                    self._show_stats()

            except Exception as e:
                self.logger.error(f"Error in batched AI analysis: {e}", exc_info=True)
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

        # Preprocess on CPU (no GPU needed), then lock only for inference
        fiber_id = section_meta[0]["fiber_id"] if section_meta else ""
        section_name = section_meta[0]["section"] if section_meta else ""

        t_pre = time.time()
        prepared, valid_indices, fwd_combined, rev_combined, window_counts = (
            speed_processor._preprocess_batch(section_inputs)
        )
        t_pre = time.time() - t_pre
        self.ai_metrics.record_stage("preprocess", t_pre, fiber_id, section_name)

        if fwd_combined is None:
            return []

        with gpu_lock() as lock_timing:
            batch_results, stage_times = speed_processor._run_inference_and_postprocess(
                section_inputs,
                prepared,
                valid_indices,
                fwd_combined,
                rev_combined,
                window_counts,
            )
        self.ai_metrics.record_gpu_lock(
            lock_timing.wait_seconds,
            lock_timing.held_seconds,
            fiber_id,
        )
        for stage, duration in stage_times.items():
            self.ai_metrics.record_stage(stage, duration, fiber_id, section_name)

        t_post = time.time()
        results = []
        for _i, (section_results, meta) in enumerate(
            zip(batch_results, section_meta, strict=False)
        ):
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
                    aligned_data=result.aligned_data,
                )
                all_detections.extend(detections)

            # CNN counting: aggregate sub-windows → 1 section, feed to counter.
            # The counter accumulates a 360s sliding window and yields CNN counts
            # per interval. We apply those counts to detections in the last batch slice.
            ctx = meta["ctx"]
            count_processor = self.model_registry.get_counter(
                meta["model_hint"], meta["buffer_key"]
            )
            if self._model_spec.counting.enabled and count_processor is not None:
                for result in section_results:
                    try:
                        # Aggregate 164 sub-windows → 1 section (matches notebook pattern)
                        agg_corr = np.mean(result.glrt_summed, axis=0, keepdims=True)
                        agg_speed = np.nanmedian(
                            result.aligned_speed_per_pair, axis=0, keepdims=True
                        )
                        agg_data = np.mean(result.aligned_data, axis=0, keepdims=True)

                        chunk_start_ns = (
                            int(result.timestamps_ns[0])
                            if result.timestamps_ns is not None
                            else None
                        )
                        for (
                            counts,
                            intervals,
                            _window_start_ns,
                        ) in count_processor.process_data_chunk(
                            aligned_speed=agg_speed,
                            correlations=agg_corr,
                            aligned_data=agg_data,
                            timestamp_ns=chunk_start_ns,
                        ):
                            # Apply CNN counts to detections whose timestamps fall
                            # within counting intervals. The counter's intervals are
                            # in sample indices relative to the 360s window; we match
                            # detections by checking if they overlap the last batch
                            # slice of the counting window.
                            self._apply_cnn_counts(
                                all_detections, counts, intervals, count_processor
                            )
                    except Exception as e:
                        logger.error(f"Error in vehicle counting: {e}")

            output_messages = self._create_detection_messages(
                meta["fiber_id"],
                all_detections,
                ctx,
            )
            results.append((all_detections, output_messages))
        t_post = time.time() - t_post
        self.ai_metrics.record_stage("postprocess", t_post, fiber_id, section_name)

        self.logger.info(
            f"Inference breakdown: "
            f"gpu_wait={lock_timing.wait_seconds * 1000:.0f}ms, "
            f"gpu_held={lock_timing.held_seconds * 1000:.0f}ms, "
            f"post={t_post * 1000:.0f}ms"
        )

        return results

    def _apply_cnn_counts(
        self,
        detections: list[dict],
        counts: list,
        intervals: list,
        count_processor: VehicleCounter,
    ) -> None:
        """Overwrite detection vehicle_count/n_cars/n_trucks with CNN counter results.

        The CNN counter operates on a 360s window with 1 aggregated section.
        We take the counts from section 0 and match them to detections by
        checking if the detection's sample position falls within a counting interval.
        Only detections in the last batch slice (recent data) get updated.
        """
        if not counts or not intervals or not detections:
            return

        # Section 0 (we aggregated to 1 section)
        sec_counts = counts[0] if len(counts) > 0 else None
        sec_intervals = intervals[0] if len(intervals) > 0 else None
        if sec_counts is None or sec_intervals is None:
            return

        starts, ends = sec_intervals
        if not starts or not ends:
            return

        sec_counts_arr = np.asarray(sec_counts, dtype=float)

        # The counting window is time_window_samples long. The last batch of data
        # sits at the end of this window. Detections have _t_mid_sample relative to
        # the current 30s batch (trimmed). We offset them to the counting window's
        # coordinate system: the batch occupies the tail of the counting window.
        time_window_samples = int(count_processor.time_window_duration * count_processor.fs)
        # Current batch length in samples (from the trimmed detection window)
        batch_samples = 0
        for det in detections:
            if det.get("_t_mid_sample") is not None:
                batch_samples = max(batch_samples, det["_t_mid_sample"] + 1)
        if batch_samples == 0:
            return

        batch_offset = time_window_samples - batch_samples

        for det in detections:
            t_mid = det.get("_t_mid_sample")
            if t_mid is None:
                continue
            # Map detection position to counting window coordinates
            t_in_window = batch_offset + t_mid

            # Find which counting interval contains this detection
            for idx, (s, e) in enumerate(zip(starts, ends, strict=False)):
                if s <= t_in_window < e and idx < len(sec_counts_arr):
                    det["vehicle_count"] = float(max(1.0, sec_counts_arr[idx]))
                    break

    async def process_buffer(self, messages: list[Message]) -> list[Message]:
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
                    detections = await self._run_ai_inference(
                        data_array,
                        timestamps,
                        timestamps_ns,
                        buffer_key,
                        ctx,
                        speed_processor=speed_processor,
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
                    fiber_id,
                    detections,
                    ctx,
                )

                processing_time = (time.time() - start_time) * 1000
                self._analyses_completed += 1

                span.set_attribute("output.message_count", len(output_messages))
                span.set_attribute("processing.time_ms", processing_time)

                # Per-window summary metrics
                fwd_dets = [d for d in detections if d["direction"] == 0]
                rev_dets = [d for d in detections if d["direction"] == 1]
                if fwd_dets or not rev_dets:
                    self.ai_metrics.record_window(
                        fiber_id=fiber_id,
                        section=section,
                        num_detections=len(fwd_dets),
                        glrt_peak=max((d["glrt_max"] for d in fwd_dets), default=0),
                        direction=0,
                    )
                if rev_dets:
                    self.ai_metrics.record_window(
                        fiber_id=fiber_id,
                        section=section,
                        num_detections=len(rev_dets),
                        glrt_peak=max((d["glrt_max"] for d in rev_dets), default=0),
                        direction=1,
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

    def _messages_to_arrays(self, messages: list[Message], ctx: ProcessingContext) -> tuple:
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
        speed_processor: VehicleSpeedEstimator | None = None,
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
        )

    def _sync_ai_inference(
        self,
        data: np.ndarray,
        timestamp_list: list,
        timestamps_ns: list,
        buffer_key: str,
        ctx: ProcessingContext,
        speed_processor: VehicleSpeedEstimator,
    ) -> list[dict]:
        timestamps = np.array(timestamp_list)
        timestamps_ns_array = np.array(timestamps_ns)

        all_detections = []
        min_vehicle_duration_s = self._model_spec.speed_detection.min_vehicle_duration_s
        classify_threshold_factor = self._model_spec.counting.truck_ratio_for_split
        yield_count = 0

        with gpu_lock():
            inference_results = list(
                speed_processor.process_file(data, timestamps, timestamps_ns_array)
            )

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
                aligned_data=result.aligned_data,
            )
            all_detections.extend(detections)

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
                fwd_dets = [d for d in all_detections if d["direction"] == 0]
                rev_dets = [d for d in all_detections if d["direction"] == 1]
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
    ) -> list[Message]:
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
            self._last_viz_time: dict[str, float] = {}
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
