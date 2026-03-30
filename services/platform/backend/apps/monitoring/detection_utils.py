"""
Shared utilities for detection data access — tier selection, fiber access checks,
and time constants.

Used by both the bulk export views and the public v1 API.
"""

from datetime import datetime, timedelta
from typing import Any

from apps.fibers.utils import get_org_fiber_ids

# Maximum time ranges per tier
MAX_HIRES_DAYS = 7
MAX_AGGREGATE_DAYS = 365

# Tier thresholds
HIRES_THRESHOLD = timedelta(hours=48)
MEDIUM_THRESHOLD = timedelta(days=90)

# ClickHouse table names — single source of truth.
# The CH client already connects to the correct database, so no prefix needed.
TIER_TABLES: dict[str, str] = {
    "hires": "detection_hires",
    "1m": "detection_1m",
    "1h": "detection_1h",
}

CH_INCIDENTS = "fiber_incidents"
CH_FIBER_CABLES = "fiber_cables"


def check_fiber_access(user: Any, fiber_id: str) -> bool:
    """Check if user has access to the specified fiber. Returns True/False."""
    if user.is_superuser:
        return True
    fiber_ids = get_org_fiber_ids(user.organization)
    return fiber_id in fiber_ids


def select_tier(
    start: datetime, end: datetime, explicit_tier: str | None = None
) -> tuple[str | None, str | None]:
    """Select the appropriate data tier based on time range.

    Args:
        start: Start datetime.
        end: End datetime.
        explicit_tier: Explicit tier override ('hires', '1m', '1h', or 'raw'/'auto').

    Returns:
        (tier, error) tuple. If error is not None, tier is None.
    """
    duration = end - start

    # Normalize 'raw' to 'hires' for public API compatibility
    if explicit_tier == "raw":
        explicit_tier = "hires"

    if explicit_tier == "hires":
        if duration > timedelta(days=MAX_HIRES_DAYS):
            return None, f"Hires tier limited to {MAX_HIRES_DAYS} days"
        return "hires", None

    if explicit_tier and explicit_tier != "auto":
        if explicit_tier not in ("hires", "1m", "1h"):
            return None, f"resolution must be one of: raw, 1m, 1h, auto (got '{explicit_tier}')"
        return explicit_tier, None

    # Auto-select
    if duration <= HIRES_THRESHOLD:
        return "hires", None
    elif duration <= MEDIUM_THRESHOLD:
        return "1m", None
    else:
        return "1h", None
