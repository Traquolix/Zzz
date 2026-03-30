"""
Alerting integration — async wrappers for evaluating alerts in realtime consumers.

Called from simulation.py and kafka_bridge.py when detections/incidents are broadcast.
Runs rule evaluation and dispatch in a non-blocking way to avoid slowing the main loop.
"""

import logging

from asgiref.sync import sync_to_async

from apps.alerting.dispatch import dispatch_alert
from apps.alerting.evaluator import evaluate_detection, evaluate_incident
from apps.alerting.models import AlertRule

logger = logging.getLogger("sequoia.alerting.integration")


async def check_alerts_for_detections(detection_dicts: list[dict], org_id: str) -> int:
    """
    Evaluate active alert rules against a batch of detections for a given org.
    Returns the number of alerts dispatched.
    """
    rules = await sync_to_async(
        lambda: list(AlertRule.objects.filter(organization_id=org_id, is_active=True))
    )()
    if not rules:
        return 0

    dispatched = 0
    for detection in detection_dicts:
        triggered = evaluate_detection(detection, rules)
        for rule, detail in triggered:
            success = await sync_to_async(dispatch_alert)(
                rule,
                detection.get("incident_id", ""),
                detection.get("fiberId", ""),
                detection.get("channel", 0),
                detail,
            )
            if success:
                dispatched += 1
    return dispatched


async def check_alerts_for_incident(incident_data: dict, fiber_org_map: dict) -> int:
    """
    Evaluate active alert rules against a single incident.
    Looks up owning orgs from fiber_org_map and checks each org's rules.
    Returns the number of alerts dispatched.
    """
    fiber_id = incident_data.get("fiberId", "")
    org_ids = fiber_org_map.get(fiber_id, [])
    if not org_ids:
        return 0

    dispatched = 0
    for org_id in org_ids:
        rules = await sync_to_async(
            lambda oid=org_id: list(AlertRule.objects.filter(organization_id=oid, is_active=True))
        )()
        if not rules:
            continue
        triggered = evaluate_incident(incident_data, rules)
        for rule, detail in triggered:
            success = await sync_to_async(dispatch_alert)(
                rule,
                incident_data.get("id", ""),
                fiber_id,
                incident_data.get("channel", 0),
                detail,
            )
            if success:
                dispatched += 1
    return dispatched
