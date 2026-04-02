"""Message transforms for real-time data streams.

Converts between pipeline/ClickHouse shapes and frontend-ready shapes.
Used by both the Kafka bridge (live) and simulation engine (sim).
"""


def transform_detection_message(data: dict) -> list[dict]:
    """
    Transform a parsed das.detections message into frontend Detection[] shape.

    Kafka Avro schema (das.detections) — batched format:
        { fiber_id, engine_version, detections: [
            { timestamp_ns, channel, speed_kmh, direction,
              vehicle_count, n_cars, n_trucks, glrt_max,
              strain_peak, strain_rms }, ...
        ]}

    Frontend Detection:
        { fiberId, direction, channel, speed, count, nCars, nTrucks,
          glrtMax, strainPeak, strainRms, timestamp }

    Direction convention: 0 = forward, 1 = reverse (unified across pipeline and platform).
    """
    fiber_id = data.get("fiber_id", "")
    det_list = data.get("detections", [])

    # Fallback for legacy single-detection format (no 'detections' array)
    if not det_list and "timestamp_ns" in data:
        det_list = [data]

    results = []
    for det in det_list:
        timestamp_ns = det.get("timestamp_ns", 0)
        channel = det.get("channel", 0)
        speed = det.get("speed_kmh", 0.0)
        vehicle_count = det.get("vehicle_count", 1.0)
        n_cars = det.get("n_cars", 0.0)
        n_trucks = det.get("n_trucks", 0.0)
        timestamp_ms = timestamp_ns // 1_000_000

        direction = det.get("direction", 0)

        results.append(
            {
                "fiberId": fiber_id,
                "direction": direction,
                "channel": int(channel),
                "speed": round(abs(speed), 1),
                "count": round(float(vehicle_count), 1),
                "nCars": round(float(n_cars), 1),
                "nTrucks": round(float(n_trucks), 1),
                "glrtMax": round(float(det.get("glrt_max", 0.0)), 1),
                "strainPeak": round(float(det.get("strain_peak", 0.0)), 6),
                "strainRms": round(float(det.get("strain_rms", 0.0)), 6),
                "timestamp": timestamp_ms,
            }
        )
    return results


def transform_incident_row(row: dict) -> dict:
    """
    Transform a ClickHouse fiber_incidents row into frontend Incident shape.

    Delegates to the centralized IncidentService transform.
    """
    from apps.shared.incident_service import transform_row

    return transform_row(row)
