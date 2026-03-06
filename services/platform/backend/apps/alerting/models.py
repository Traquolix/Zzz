"""
Alerting models — rule definitions and dispatch logs.

AlertRule: per-org configuration for what triggers an alert and how it's dispatched.
AlertLog: audit trail of dispatched alerts with cooldown enforcement.
"""

import uuid

from django.db import models

RULE_TYPES = [
    ("speed_below", "Speed Below Threshold"),
    ("incident_type", "Incident Type Match"),
]

DISPATCH_CHANNELS = [
    ("log", "Log Only"),
    ("webhook", "Webhook"),
    ("email", "Email"),
]


class AlertRule(models.Model):
    """
    A configurable alerting rule scoped to an organization.

    Supports two rule types:
    - speed_below: triggers when detection speed < threshold
    - incident_type: triggers when a new incident matches type + severity filters

    Optional filters narrow the scope to specific fibers and channel ranges.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="alert_rules",
    )
    name = models.CharField(max_length=200)
    rule_type = models.CharField(max_length=30, choices=RULE_TYPES)
    is_active = models.BooleanField(default=True)

    # Speed threshold (for speed_below rules)
    threshold = models.FloatField(null=True, blank=True)

    # Incident type filter (for incident_type rules)
    incident_type_filter = models.JSONField(
        default=list,
        blank=True,
        help_text="List of incident types to match: accident, congestion, anomaly, slowdown",
    )

    # Severity filter (applies to both rule types)
    severity_filter = models.JSONField(
        default=list,
        blank=True,
        help_text="Only alert for these severities. Empty = all.",
    )

    # Scope filters
    fiber_id_filter = models.JSONField(
        default=list,
        blank=True,
        help_text="Restrict to these fiber IDs (plain, no direction suffix). Empty = all.",
    )
    channel_start = models.IntegerField(null=True, blank=True)
    channel_end = models.IntegerField(null=True, blank=True)

    # Dispatch configuration
    dispatch_channel = models.CharField(
        max_length=20,
        choices=DISPATCH_CHANNELS,
        default="log",
    )
    webhook_url = models.URLField(blank=True, default="")
    webhook_secret = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="HMAC secret for webhook signature verification.",
    )
    email_recipients = models.JSONField(
        default=list,
        blank=True,
        help_text="Email addresses to notify.",
    )

    # Cooldown to prevent alert storms
    cooldown_seconds = models.PositiveIntegerField(
        default=300,
        help_text="Minimum seconds between alerts from this rule for the same fiber+channel.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.rule_type})"


class AlertLog(models.Model):
    """
    Audit log of dispatched alerts. Used for cooldown enforcement and history.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rule = models.ForeignKey(AlertRule, on_delete=models.CASCADE, related_name="logs")
    incident_id = models.CharField(max_length=100, blank=True, default="")
    fiber_id = models.CharField(max_length=100)
    channel = models.IntegerField()
    detail = models.TextField(blank=True, default="")
    delivery_status = models.CharField(
        max_length=20,
        choices=[("pending", "Pending"), ("success", "Success"), ("failed", "Failed")],
        default="pending",
    )
    error_message = models.TextField(blank=True, default="")
    dispatched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-dispatched_at"]
        indexes = [
            models.Index(fields=["rule", "fiber_id", "channel", "-dispatched_at"]),
        ]

    def __str__(self):
        return f"Alert {self.rule.name} @ {self.fiber_id}:{self.channel}"
