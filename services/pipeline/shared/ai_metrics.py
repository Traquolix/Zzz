"""AI Engine metrics for operational observability.

Per-stage latency histograms for the inference pipeline, GPU contention
tracking, and per-window detection summaries. All metrics are per-window
aggregates (not per-detection) to keep cardinality bounded.

Detection-level data (individual speeds, GLRT values) belongs in ClickHouse,
not in the metrics pipeline.

Metrics exported:
- ai.stage.preprocess.duration    — CPU preprocessing (split + normalize)
- ai.stage.predict_theta.duration — DTAN NN forward pass + grid transform
- ai.stage.align.duration         — CPAB or shift alignment
- ai.stage.glrt.duration          — GLRT correlation computation
- ai.stage.postprocess.duration   — speed filtering + detection extraction
- ai.stage.counting.duration      — CNN vehicle counting
- ai.gpu_lock.wait.duration       — time waiting to acquire GPU lock
- ai.gpu_lock.held.duration       — time holding GPU lock (inference)
- ai.window.detections            — detection count per window
- ai.window.glrt_peak             — max GLRT peak per window (quality signal)
- ai.window.speed_median          — median detected speed per window (km/h)
- ai.windows.processed.total      — windows processed counter
- ai.model.fallback.total         — model load failures that fell back to default
- errors.ai.total                 — AI-specific error counter

Query examples:
    # Inference latency waterfall (p95 per stage)
    histogram_quantile(0.95, rate(ai_stage_predict_theta_duration_seconds_bucket[5m]))
    histogram_quantile(0.95, rate(ai_stage_align_duration_seconds_bucket[5m]))

    # GPU contention: how long are fibers waiting?
    histogram_quantile(0.95, rate(ai_gpu_lock_wait_duration_seconds_bucket[5m]))

    # Detection quality: is GLRT degrading over time?
    histogram_quantile(0.5, rate(ai_window_glrt_peak_bucket[5m]))

    # Speed sanity: is the model producing plausible speeds?
    histogram_quantile(0.5, rate(ai_window_speed_median_bucket[5m]))

    # Windows per minute by fiber
    rate(ai_windows_processed_total{fiber_id="carros"}[1m]) * 60
"""

import logging

from opentelemetry import metrics

logger = logging.getLogger(__name__)

# Valid stage names for record_stage(). Typos in calling code are logged
# as warnings instead of silently dropped.
_VALID_STAGES = frozenset(
    ["preprocess", "predict_theta", "align", "glrt", "postprocess", "counting"]
)


class AIMetrics:
    """OpenTelemetry metrics for AI engine inference pipeline."""

    def __init__(self, service_name: str = "ai-engine"):
        self.service_name = service_name
        meter = metrics.get_meter(__name__)

        # --- Per-stage latency histograms ---

        self.preprocess_duration = meter.create_histogram(
            name="ai.stage.preprocess.duration",
            description="CPU preprocessing time (split + normalize)",
            unit="s",
        )

        self.predict_theta_duration = meter.create_histogram(
            name="ai.stage.predict_theta.duration",
            description="DTAN NN forward pass + grid transform",
            unit="s",
        )

        self.align_duration = meter.create_histogram(
            name="ai.stage.align.duration",
            description="Channel alignment (CPAB or shift)",
            unit="s",
        )

        self.glrt_duration = meter.create_histogram(
            name="ai.stage.glrt.duration",
            description="GLRT correlation computation",
            unit="s",
        )

        self.postprocess_duration = meter.create_histogram(
            name="ai.stage.postprocess.duration",
            description="Speed filtering + detection extraction",
            unit="s",
        )

        self.counting_duration = meter.create_histogram(
            name="ai.stage.counting.duration",
            description="CNN vehicle counting pipeline",
            unit="s",
        )

        # --- GPU contention ---

        self.gpu_lock_wait = meter.create_histogram(
            name="ai.gpu_lock.wait.duration",
            description="Time waiting to acquire exclusive GPU access",
            unit="s",
        )

        self.gpu_lock_held = meter.create_histogram(
            name="ai.gpu_lock.held.duration",
            description="Time holding GPU lock (active inference)",
            unit="s",
        )

        # --- Per-window summaries ---

        self.window_detections = meter.create_histogram(
            name="ai.window.detections",
            description="Number of detections per inference window",
            unit="1",
        )

        self.window_glrt_peak = meter.create_histogram(
            name="ai.window.glrt_peak",
            description="Max GLRT summed peak per window (detection quality signal)",
            unit="1",
        )

        self.window_speed_median = meter.create_histogram(
            name="ai.window.speed_median",
            description="Median detected speed per window (correctness signal)",
            unit="km/h",
        )

        self.windows_processed = meter.create_counter(
            name="ai.windows.processed.total",
            description="Total inference windows processed",
            unit="1",
        )

        # --- Model lifecycle ---

        self.model_fallback = meter.create_counter(
            name="ai.model.fallback.total",
            description="Model load failures that fell back to default model",
            unit="1",
        )

        # --- Errors ---

        self.errors = meter.create_counter(
            name="errors.ai.total",
            description="AI engine processing errors",
            unit="1",
        )

        # Stage name → histogram lookup (built once)
        self._stage_histograms: dict = {
            "preprocess": self.preprocess_duration,
            "predict_theta": self.predict_theta_duration,
            "align": self.align_duration,
            "glrt": self.glrt_duration,
            "postprocess": self.postprocess_duration,
            "counting": self.counting_duration,
        }

    def _attrs(self, fiber_id: str, section: str, **extra) -> dict:
        attrs = {
            "fiber_id": fiber_id,
            "section": section,
        }
        attrs.update(extra)
        return attrs

    # --- Stage timing ---

    def record_stage(
        self,
        stage: str,
        duration_seconds: float,
        fiber_id: str,
        section: str,
    ):
        """Record duration for a named pipeline stage.

        Args:
            stage: One of "preprocess", "predict_theta", "align", "glrt",
                   "postprocess", "counting"
            duration_seconds: Wall-clock time for this stage
            fiber_id: Fiber identifier
            section: Section name
        """
        histogram = self._stage_histograms.get(stage)
        if histogram is not None:
            histogram.record(duration_seconds, self._attrs(fiber_id, section))
        elif stage not in _VALID_STAGES:
            logger.warning("record_stage called with unknown stage %r", stage)

    # --- GPU lock ---

    def record_gpu_lock(
        self,
        wait_seconds: float,
        held_seconds: float,
        fiber_id: str = "",
    ):
        """Record GPU lock acquisition and hold times.

        GPU contention is per-fiber (all sections in a fiber batch share one
        lock acquisition), so these metrics are intentionally fiber-scoped
        without a section dimension.

        Args:
            wait_seconds: Time spent waiting for the lock
            held_seconds: Time spent holding the lock (active inference)
            fiber_id: Fiber being processed (for correlation)
        """
        attrs = {"fiber_id": fiber_id}
        self.gpu_lock_wait.record(wait_seconds, attrs)
        self.gpu_lock_held.record(held_seconds, attrs)

    # --- Per-window summary ---

    def record_window(
        self,
        fiber_id: str,
        section: str,
        num_detections: int,
        glrt_peak: float,
        speed_median_kmh: float,
        direction: int,
    ):
        """Record summary metrics for a completed inference window.

        Called once per direction per section — not per detection.

        Args:
            fiber_id: Fiber identifier
            section: Section name
            num_detections: Total detections in this window
            glrt_peak: Maximum GLRT summed value in this window
            speed_median_kmh: Median speed of detections (NaN if none)
            direction: 0=forward, 1=reverse
        """
        attrs = self._attrs(fiber_id, section, direction=str(direction))
        self.windows_processed.add(1, attrs)
        self.window_detections.record(num_detections, attrs)
        self.window_glrt_peak.record(glrt_peak, attrs)
        if speed_median_kmh == speed_median_kmh:  # fast NaN check
            self.window_speed_median.record(speed_median_kmh, attrs)

    # --- Model lifecycle ---

    def record_model_fallback(self, model_hint: str, fiber_id: str = ""):
        """Record that a model load failed and fell back to default."""
        self.model_fallback.add(
            1,
            {"model_hint": model_hint, "fiber_id": fiber_id},
        )

    # --- Errors ---

    def record_error(self, error_type: str, fiber_id: str = "", section: str = ""):
        """Record an AI engine error.

        error_type values: batch_processing, gpu_lock_timeout, counting_failure,
        rolling_buffer_management, inference_error
        """
        self.errors.add(
            1,
            {
                "error_type": error_type,
                "fiber_id": fiber_id,
                "section": section,
            },
        )
