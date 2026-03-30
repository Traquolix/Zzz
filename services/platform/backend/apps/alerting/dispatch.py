"""
Alert dispatch — sends alerts via configured channels.

Enforces cooldown to prevent alert storms: if an alert was dispatched
for the same rule + fiber + channel within the cooldown period, skip.

Webhook features:
- HMAC-SHA256 signing via X-Sequoia-Signature header
- Retry with exponential backoff (3 retries, non-blocking via thread pool)
- Delivery status tracking on AlertLog
- SSRF protection: blocks private/reserved IP targets
"""

import concurrent.futures
import hashlib
import hmac
import ipaddress
import json
import logging
import socket
import time
from urllib.parse import urlparse

import requests as http_requests
from django.utils import timezone

from apps.alerting.models import AlertLog, AlertRule

logger = logging.getLogger("sequoia.alerting.dispatch")

_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)

# When True, webhook dispatch runs synchronously (for testing)
_SYNC_MODE = False

# Retry configuration
WEBHOOK_MAX_RETRIES = 3
WEBHOOK_RETRY_DELAYS = [1, 5, 25]  # seconds


def validate_webhook_url(url: str) -> str | None:
    """Validate a webhook URL is safe (not targeting internal/private networks).

    Returns None if valid, or an error message string if blocked.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return "Invalid URL format"

    if parsed.scheme not in ("http", "https"):
        return "URL must use http or https"

    hostname = parsed.hostname
    if not hostname:
        return "URL must include a hostname"

    try:
        resolved = socket.getaddrinfo(hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return f"Cannot resolve hostname: {hostname}"

    for _, _, _, _, sockaddr in resolved:
        ip = ipaddress.ip_address(sockaddr[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return f"URL resolves to blocked address: {ip}"

    return None


def _is_in_cooldown(rule: AlertRule, fiber_id: str, channel: int) -> bool:
    """Check if this rule+fiber+channel combination is within its cooldown window."""
    if rule.cooldown_seconds <= 0:
        return False

    cutoff = timezone.now() - timezone.timedelta(seconds=rule.cooldown_seconds)
    return bool(
        AlertLog.objects.filter(
            rule=rule,
            fiber_id=fiber_id,
            channel=channel,
            dispatched_at__gte=cutoff,
        ).exists()
    )


def dispatch_alert(
    rule: AlertRule,
    incident_id: str,
    fiber_id: str,
    channel: int,
    detail: str,
) -> bool:
    """
    Dispatch an alert and create a log entry.

    Returns True if the alert was dispatched, False if skipped (cooldown).
    """
    if _is_in_cooldown(rule, fiber_id, channel):
        logger.debug(
            "Alert cooldown active for rule %s on %s:%d",
            rule.name,
            fiber_id,
            channel,
        )
        return False

    # Always create the log entry (serves as audit trail + cooldown reference)
    log_entry = AlertLog.objects.create(
        rule=rule,
        incident_id=incident_id,
        fiber_id=fiber_id,
        channel=channel,
        detail=detail,
    )

    # Dispatch based on channel
    if rule.dispatch_channel == "webhook" and rule.webhook_url:
        # Validate URL against SSRF before dispatching
        ssrf_error = validate_webhook_url(rule.webhook_url)
        if ssrf_error:
            logger.warning("Webhook URL blocked for rule %s: %s", rule.name, ssrf_error)
            log_entry.delivery_status = "failed"
            log_entry.error_message = f"URL blocked: {ssrf_error}"
            log_entry.save(update_fields=["delivery_status", "error_message"])
            return True
        # Submit to thread pool so retries don't block the calling thread
        if _SYNC_MODE:
            _dispatch_webhook(rule, incident_id, fiber_id, channel, detail, log_entry=log_entry)
        else:
            _executor.submit(
                _dispatch_webhook,
                rule,
                incident_id,
                fiber_id,
                channel,
                detail,
                log_entry=log_entry,
            )
    elif rule.dispatch_channel == "email" and rule.email_recipients:
        _dispatch_email(rule, incident_id, fiber_id, channel, detail, log_entry=log_entry)
    else:
        # 'log' channel — the AlertLog entry above is sufficient
        log_entry.delivery_status = "success"
        log_entry.save(update_fields=["delivery_status"])
        logger.info(
            "Alert [%s]: %s (fiber=%s ch=%d)",
            rule.name,
            detail,
            fiber_id,
            channel,
        )

    return True


def _dispatch_webhook(
    rule: AlertRule,
    incident_id: str,
    fiber_id: str,
    channel: int,
    detail: str,
    log_entry: AlertLog | None = None,
    test: bool = False,
) -> None:
    """POST alert payload to the configured webhook URL with HMAC signing and retries."""
    payload = {
        "rule": rule.name,
        "ruleId": str(rule.pk),
        "incidentId": incident_id,
        "fiberId": fiber_id,
        "channel": channel,
        "detail": detail,
        "organization": rule.organization.name,
        "timestamp": timezone.now().isoformat(),
    }
    if test:
        payload["test"] = True

    payload_bytes = json.dumps(payload, separators=(",", ":")).encode()

    headers = {"Content-Type": "application/json"}

    # HMAC signing
    if rule.webhook_secret:
        signature = hmac.new(
            rule.webhook_secret.encode(),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()
        headers["X-Sequoia-Signature"] = f"sha256={signature}"

    # Attempt delivery with retries
    last_error = None
    total_attempts = 1 + WEBHOOK_MAX_RETRIES  # 1 original + 3 retries

    for attempt in range(total_attempts):
        try:
            resp = http_requests.post(
                rule.webhook_url,
                data=payload_bytes,
                headers=headers,
                timeout=10,
            )
            if resp.status_code < 400:
                # Success
                if log_entry:
                    log_entry.delivery_status = "success"
                    log_entry.save(update_fields=["delivery_status"])
                return
            else:
                last_error = f"HTTP {resp.status_code}"
                logger.warning(
                    "Webhook dispatch failed for rule %s (attempt %d/%d): HTTP %d",
                    rule.name,
                    attempt + 1,
                    total_attempts,
                    resp.status_code,
                )
        except http_requests.RequestException as e:
            last_error = str(e)
            logger.warning(
                "Webhook dispatch error for rule %s (attempt %d/%d): %s",
                rule.name,
                attempt + 1,
                total_attempts,
                e,
            )

        # Wait before retry (except on last attempt)
        if attempt < WEBHOOK_MAX_RETRIES:
            time.sleep(WEBHOOK_RETRY_DELAYS[attempt])

    # All attempts failed
    if log_entry:
        log_entry.delivery_status = "failed"
        log_entry.error_message = last_error or "Unknown error"
        log_entry.save(update_fields=["delivery_status", "error_message"])
    logger.error(
        "Webhook dispatch gave up for rule %s after %d attempts", rule.name, total_attempts
    )


def _dispatch_email(
    rule: AlertRule,
    incident_id: str,
    fiber_id: str,
    channel: int,
    detail: str,
    log_entry: AlertLog | None = None,
) -> None:
    """Send alert email to configured recipients."""
    from django.conf import settings
    from django.core.mail import send_mail

    subject = f"[SequoIA Alert] {rule.name}"
    body = (
        f"Alert Rule: {rule.name}\n"
        f"Organization: {rule.organization.name}\n"
        f"Incident: {incident_id}\n"
        f"Fiber: {fiber_id}, Channel: {channel}\n"
        f"Detail: {detail}\n"
        f"Time: {timezone.now().isoformat()}\n"
    )
    try:
        send_mail(
            subject,
            body,
            getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@sequoia.io"),
            rule.email_recipients,
            fail_silently=False,
        )
        if log_entry:
            log_entry.delivery_status = "success"
            log_entry.save(update_fields=["delivery_status"])
    except Exception as e:
        logger.error("Email dispatch error for rule %s: %s", rule.name, e)
        if log_entry:
            log_entry.delivery_status = "failed"
            log_entry.error_message = str(e)
            log_entry.save(update_fields=["delivery_status", "error_message"])
