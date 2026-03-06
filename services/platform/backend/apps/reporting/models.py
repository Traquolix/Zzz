import uuid

from django.conf import settings
from django.db import models


class Report(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("generating", "Generating"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="reports",
    )
    title = models.CharField(max_length=200)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="reports",
    )
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    fiber_ids = models.JSONField(default=list)
    sections = models.JSONField(default=list)
    html_content = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    recipients = models.JSONField(default=list)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.status})"


class ReportSchedule(models.Model):
    """
    Recurring report schedule — generates and optionally emails reports on a cadence.
    """

    FREQUENCY_CHOICES = [
        ("daily", "Daily"),
        ("weekly", "Weekly"),
        ("monthly", "Monthly"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="report_schedules",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="report_schedules",
    )
    title = models.CharField(max_length=200)
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES)
    fiber_ids = models.JSONField(default=list)
    sections = models.JSONField(default=list)
    recipients = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.frequency})"

    def is_due(self) -> bool:
        """Check if this schedule is due to run based on frequency."""
        if not self.is_active:
            return False
        if self.last_run_at is None:
            return True

        from django.utils import timezone

        now = timezone.now()
        delta = now - self.last_run_at

        if self.frequency == "daily":
            return bool(delta >= timezone.timedelta(hours=24))
        elif self.frequency == "weekly":
            return bool(delta >= timezone.timedelta(days=7))
        elif self.frequency == "monthly":
            return bool(delta >= timezone.timedelta(days=30))
        return False
