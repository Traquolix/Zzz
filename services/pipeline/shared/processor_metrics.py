"""Processor service metrics for operational observability.

Per-step latency histograms for the preprocessing pipeline, plus
phase-level timing (parse, pipeline, send) for bottleneck diagnosis.

Metrics exported:
- processor.step.spatial_decimation.duration
- processor.step.scale.duration
- processor.step.common_mode_removal.duration
- processor.step.bandpass_filter.duration
- processor.step.temporal_decimation.duration
- processor.phase.parse.duration        — raw message parsing + reshape
- processor.phase.pipeline.duration     — all processing steps for one section
- processor.phase.send.duration         — output serialization + produce
- processor.phase.total.duration        — full transform() wall time
- processor.sections.produced           — sections produced per message
- errors.processor.total                — processor-specific error counter

Query examples:
    # Per-step latency waterfall (p95)
    histogram_quantile(0.95, rate(processor_step_bandpass_filter_duration_seconds_bucket[5m]))

    # Where is time going? parse vs pipeline vs send
    histogram_quantile(0.95, rate(processor_phase_parse_duration_seconds_bucket[5m]))
    histogram_quantile(0.95, rate(processor_phase_pipeline_duration_seconds_bucket[5m]))
    histogram_quantile(0.95, rate(processor_phase_send_duration_seconds_bucket[5m]))

    # Total processing time per message
    histogram_quantile(0.95, rate(processor_phase_total_duration_seconds_bucket[5m]))
"""

import logging

from opentelemetry import metrics

logger = logging.getLogger(__name__)

_VALID_STEPS = frozenset(
    [
        "spatial_decimation",
        "scale",
        "common_mode_removal",
        "bandpass_filter",
        "temporal_decimation",
    ]
)


class ProcessorMetrics:
    """OpenTelemetry metrics for the DAS processor pipeline."""

    def __init__(self, service_name: str = "das-processor"):
        self.service_name = service_name
        meter = metrics.get_meter(__name__)

        # --- Per-step latency histograms ---

        self.spatial_decimation_duration = meter.create_histogram(
            name="processor.step.spatial_decimation.duration",
            description="Spatial decimation (channel selection + stride)",
            unit="s",
        )

        self.scale_duration = meter.create_histogram(
            name="processor.step.scale.duration",
            description="Value scaling (physical units to ADC counts)",
            unit="s",
        )

        self.common_mode_removal_duration = meter.create_histogram(
            name="processor.step.common_mode_removal.duration",
            description="Common mode removal (spatial median subtraction)",
            unit="s",
        )

        self.bandpass_filter_duration = meter.create_histogram(
            name="processor.step.bandpass_filter.duration",
            description="Bandpass filter (Butterworth SOS)",
            unit="s",
        )

        self.temporal_decimation_duration = meter.create_histogram(
            name="processor.step.temporal_decimation.duration",
            description="Temporal decimation (sample selection)",
            unit="s",
        )

        # --- Phase-level timing ---

        self.parse_duration = meter.create_histogram(
            name="processor.phase.parse.duration",
            description="Raw message parsing and reshape",
            unit="s",
        )

        self.pipeline_duration = meter.create_histogram(
            name="processor.phase.pipeline.duration",
            description="Processing pipeline for one section",
            unit="s",
        )

        self.send_duration = meter.create_histogram(
            name="processor.phase.send.duration",
            description="Output message construction + serialization",
            unit="s",
        )

        self.total_duration = meter.create_histogram(
            name="processor.phase.total.duration",
            description="Full transform() wall time per raw message",
            unit="s",
        )

        # --- Counters ---

        self.sections_produced = meter.create_histogram(
            name="processor.sections.produced",
            description="Number of section outputs per raw message",
            unit="1",
        )

        self.errors = meter.create_counter(
            name="errors.processor.total",
            description="Processor-specific errors",
            unit="1",
        )

        # Step name → histogram lookup
        self._step_histograms: dict = {
            "spatial_decimation": self.spatial_decimation_duration,
            "scale": self.scale_duration,
            "common_mode_removal": self.common_mode_removal_duration,
            "bandpass_filter": self.bandpass_filter_duration,
            "temporal_decimation": self.temporal_decimation_duration,
        }

    def _attrs(self, fiber_id: str, section: str, **extra) -> dict:
        attrs = {
            "fiber_id": fiber_id,
            "section": section,
        }
        attrs.update(extra)
        return attrs

    def record_step(
        self,
        step_name: str,
        duration_seconds: float,
        fiber_id: str,
        section: str,
    ):
        """Record duration for a named processing step."""
        histogram = self._step_histograms.get(step_name)
        if histogram is not None:
            histogram.record(duration_seconds, self._attrs(fiber_id, section))
        elif step_name not in _VALID_STEPS:
            logger.warning("record_step called with unknown step %r", step_name)

    def record_phase(
        self,
        phase: str,
        duration_seconds: float,
        fiber_id: str,
    ):
        """Record duration for a processing phase (parse, pipeline, send, total)."""
        histogram = getattr(self, f"{phase}_duration", None)
        if histogram is not None:
            histogram.record(duration_seconds, {"fiber_id": fiber_id})

    def record_error(self, error_type: str, fiber_id: str = ""):
        """Record a processor error."""
        self.errors.add(1, {"error_type": error_type, "fiber_id": fiber_id})
