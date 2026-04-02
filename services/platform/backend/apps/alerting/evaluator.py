"""
Alert rule evaluator — checks detections and incidents against active rules.

Returns a list of (rule, reason) tuples for rules that fired.
Callers are responsible for dispatching.
"""

import logging

from apps.alerting.models import AlertRule

logger = logging.getLogger("sequoia.alerting.evaluator")


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

    incident shape: {id, type, tags, fiberId, direction, channel, ...}
    Returns: [(rule, reason_string), ...]
    """
    triggered: list[tuple[AlertRule, str]] = []

    fiber_id = incident.get("fiberId", "")
    channel = incident.get("channel", 0)
    inc_type = incident.get("type", "")
    tags = incident.get("tags", [])

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

        # Tags filter — fire if any incident tag matches any rule tag
        if rule.tags_filter and not any(t in rule.tags_filter for t in tags):
            continue

        reason = f"Incident {incident.get('id', '?')} type={inc_type} tags={tags}"
        triggered.append((rule, reason))

    return triggered
