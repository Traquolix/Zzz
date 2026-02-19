"""AI Engine specific metrics for observability.

Provides detailed metrics for DTAN inference, vehicle detection,
and rolling buffer performance. Complements the base MessageMetrics.

Metrics exported:
- ai.inference.duration (histogram) - DTAN model inference latency
- ai.vehicles.detected.total (counter) - Vehicles detected by fiber/direction
- ai.windows.processed.total (counter) - Rolling buffer windows processed
- ai.detections.per_window (histogram) - Detection density per window
- ai.glrt.peak.value (histogram) - GLRT correlation peak values

Query examples in Prometheus:
    # p99 inference latency
    histogram_quantile(0.99, rate(ai_inference_duration_bucket[5m]))

    # Vehicles per minute by fiber
    rate(ai_vehicles_detected_total{fiber_id="carros"}[1m]) * 60

    # Detection density
    histogram_quantile(0.5, rate(ai_detections_per_window_bucket[5m]))
"""

from opentelemetry import metrics


class AIMetrics:
    """OpenTelemetry metrics for AI engine inference and detection."""

    def __init__(self, service_name: str = "ai-engine"):
        """Initialize AI-specific metrics.

        Args:
            service_name: Service name for metric labels
        """
        self.service_name = service_name
        meter = metrics.get_meter(__name__)

        # Histogram: DTAN inference duration (seconds)
        self.inference_duration = meter.create_histogram(
            name="ai.inference.duration",
            description="Time spent in DTAN model inference",
            unit="s",
        )

        # Counter: Vehicles detected
        self.vehicles_detected = meter.create_counter(
            name="ai.vehicles.detected.total",
            description="Total vehicles detected",
            unit="1",
        )

        # Counter: Windows processed by rolling buffer
        self.windows_processed = meter.create_counter(
            name="ai.windows.processed.total",
            description="Total inference windows processed",
            unit="1",
        )

        # Histogram: Detections per window
        self.detections_per_window = meter.create_histogram(
            name="ai.detections.per_window",
            description="Number of vehicle detections per inference window",
            unit="1",
        )

        # Histogram: GLRT peak correlation values
        self.glrt_peak_values = meter.create_histogram(
            name="ai.glrt.peak.value",
            description="Peak GLRT correlation values",
            unit="1",
        )

        # Gauge: Calibration status (0=static, 1=calibrated)
        self.calibration_status = meter.create_up_down_counter(
            name="ai.calibration.enabled",
            description="Whether calibration is active (1) or static threshold (0)",
            unit="1",
        )

        # Histogram: Speed values detected
        self.speed_values = meter.create_histogram(
            name="ai.speed.detected",
            description="Detected vehicle speeds",
            unit="km/h",
        )

    def record_inference(
        self,
        duration_seconds: float,
        fiber_id: str,
        section: str,
        num_detections: int,
    ):
        """Record a completed inference window.

        Args:
            duration_seconds: Time taken for DTAN inference
            fiber_id: Fiber identifier
            section: Section name
            num_detections: Number of vehicles detected in window
        """
        attributes = {
            "service_name": self.service_name,
            "fiber_id": fiber_id,
            "section": section,
        }

        self.inference_duration.record(duration_seconds, attributes)
        self.windows_processed.add(1, attributes)
        self.detections_per_window.record(num_detections, attributes)

    def record_vehicle(
        self,
        fiber_id: str,
        section: str,
        direction: int,
        speed_kmh: float,
    ):
        """Record a single vehicle detection.

        Args:
            fiber_id: Fiber identifier
            section: Section name
            direction: Direction (0 or 1)
            speed_kmh: Detected speed in km/h
        """
        attributes = {
            "service_name": self.service_name,
            "fiber_id": fiber_id,
            "section": section,
            "direction": str(direction),
        }

        self.vehicles_detected.add(1, attributes)
        self.speed_values.record(abs(speed_kmh), attributes)

    def record_glrt_peak(self, fiber_id: str, section: str, peak_value: float):
        """Record GLRT correlation peak for quality monitoring.

        Args:
            fiber_id: Fiber identifier
            section: Section name
            peak_value: Peak correlation value
        """
        attributes = {
            "service_name": self.service_name,
            "fiber_id": fiber_id,
            "section": section,
        }
        self.glrt_peak_values.record(peak_value, attributes)

    def set_calibration_status(self, fiber_id: str, enabled: bool):
        """Update calibration status gauge.

        Args:
            fiber_id: Fiber identifier
            enabled: Whether calibration is active
        """
        attributes = {
            "service_name": self.service_name,
            "fiber_id": fiber_id,
        }
        # Set to 1 if enabled, 0 if not
        self.calibration_status.add(1 if enabled else 0, attributes)
