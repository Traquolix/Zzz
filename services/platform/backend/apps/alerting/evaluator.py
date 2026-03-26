"""
Alert rule evaluator — checks detections and incidents against active rules.

Returns a list of (rule, reason) tuples for rules that fired.
Callers are responsible for dispatching.
"""

import logging

from apps.alerting.models import AlertRule

logger = logging.getLogger("sequoia.alerting")


def _passes_scope_filters(rule: AlertRule, fiber_id: str, channel: int) -> bool:
    """Check if the data point falls within the rule's fiber/channel scope."""
    # Fiber filter
    if rule.fiber_id_filter and fiber_id not in rule.fiber_id_filter:
        return False

    # Channel range filter
    if rule.channel_start is not None and channel < rule.channel_start:
        return False
    return not (rule.channel_end is not None and channel > rule.channel_end)


def evaluate_detection(
    detection: dict,
    rules: list[AlertRule],
) -> list[tuple[AlertRule, str]]:
    """
    Evaluate a single detection against a list of rules.

    detection shape: {fiberId, direction, channel, speed, ...}
    Returns: [(rule, reason_string), ...]
    """
    triggered: list[tuple[AlertRule, str]] = []

    fiber_id = detection.get("fiberId", "")
    channel = detection.get("channel", 0)
    speed = detection.get("speed", 0.0)

    for rule in rules:
        if not rule.is_active:
            continue

        if rule.rule_type != "speed_below":
            continue

        if not _passes_scope_filters(rule, fiber_id, channel):
            continue

        if rule.threshold is not None and speed < rule.threshold:
            reason = f"Speed {speed:.1f} km/h below threshold {rule.threshold:.1f} km/h"
            triggered.append((rule, reason))

    return triggered


def evaluate_incident(
    incident: dict,
    rules: list[AlertRule],
) -> list[tuple[AlertRule, str]]:
    """
    Evaluate a new incident against a list of rules.

    incident shape: {id, type, severity, fiberId, direction, channel, ...}
    Returns: [(rule, reason_string), ...]
    """
    triggered: list[tuple[AlertRule, str]] = []

    fiber_id = incident.get("fiberId", "")
    channel = incident.get("channel", 0)
    inc_type = incident.get("type", "")
    severity = incident.get("severity", "")

    for rule in rules:
        if not rule.is_active:
            continue

        if rule.rule_type != "incident_type":
            continue

        if not _passes_scope_filters(rule, fiber_id, channel):
            continue

        # Type filter
        if rule.incident_type_filter and inc_type not in rule.incident_type_filter:
            continue

        # Severity filter
        if rule.severity_filter and severity not in rule.severity_filter:
            continue

        reason = f"Incident {incident.get('id', '?')} type={inc_type} severity={severity}"
        triggered.append((rule, reason))

    return triggered
