"""
Background task runner for report generation.

Uses threading for simplicity — no external dependency (Celery, django-q).
For production at scale, replace with a proper task queue.
"""

import logging
import threading
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger("sequoia.reporting.task_runner")


def generate_report_async(report_id) -> None:
    """
    Generate a report's HTML content. Can be called from a thread or directly.

    Updates the Report's status and html_content fields.
    """
    from apps.reporting.models import Report
    from apps.reporting.report_builder import build_report_html

    # Atomically claim the report: only proceed if status is still 'pending'.
    # This prevents two concurrent threads from generating the same report.
    updated = Report.objects.filter(pk=report_id, status="pending").update(status="generating")
    if updated == 0:
        logger.info("Report %s already being generated or completed, skipping", report_id)
        return

    try:
        report = Report.objects.get(pk=report_id)
    except Report.DoesNotExist:
        logger.error("Report %s not found for generation", report_id)
        return

    try:
        report.html_content = build_report_html(report)
        report.status = "completed"
        logger.info("Report %s generated successfully", report_id)
    except Exception as e:
        report.status = "failed"
        logger.error("Report %s generation failed: %s", report_id, e)

    report.save(update_fields=["status", "html_content"])


def enqueue_report_generation(report_id) -> None:
    """
    Spawn a background thread to generate the report.

    The thread is a daemon so it won't prevent shutdown, but the
    report will be marked 'failed' on next check if the process dies.
    """
    thread = threading.Thread(
        target=generate_report_async,
        args=(report_id,),
        daemon=True,
        name=f"report-gen-{report_id}",
    )
    thread.start()
    logger.info("Enqueued report %s for background generation", report_id)


def run_scheduled_reports() -> int:
    """
    Check all active schedules, generate reports for those that are due.

    Returns the number of reports triggered.

    Intended to be called from a management command or periodic task.
    """
    from apps.reporting.models import Report, ReportSchedule

    schedules = ReportSchedule.objects.filter(is_active=True)
    triggered = 0

    for schedule in schedules:
        if not schedule.is_due():
            continue

        now = timezone.now()

        # Compute time range based on frequency
        if schedule.frequency == "daily":
            start_time = now - timedelta(hours=24)
        elif schedule.frequency == "weekly":
            start_time = now - timedelta(days=7)
        elif schedule.frequency == "monthly":
            start_time = now - timedelta(days=30)
        else:
            continue

        # Create the report
        report = Report.objects.create(
            organization=schedule.organization,
            title=f"{schedule.title} — {now.strftime('%Y-%m-%d')}",
            created_by=schedule.created_by,
            start_time=start_time,
            end_time=now,
            fiber_ids=schedule.fiber_ids,
            sections=schedule.sections,
            recipients=schedule.recipients,
            status="pending",
        )

        # Generate synchronously (caller decides threading)
        generate_report_async(report.pk)

        # Update schedule
        schedule.last_run_at = now
        schedule.save(update_fields=["last_run_at"])

        triggered += 1
        logger.info(
            "Scheduled report triggered: %s (schedule=%s)",
            report.pk,
            schedule.pk,
        )

    return triggered
