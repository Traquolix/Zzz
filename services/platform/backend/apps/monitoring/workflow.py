"""
Incident workflow state machine.

Defines valid state transitions and provides helpers for querying
the current workflow status of a ClickHouse incident.
"""

from apps.monitoring.models import IncidentAction


class InvalidTransitionError(Exception):
    """Raised when a workflow transition is not allowed."""
    def __init__(self, from_status: str, to_status: str):
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(
            f'Cannot transition from {from_status!r} to {to_status!r}'
        )


# State machine: from_status → set of allowed to_statuses
VALID_TRANSITIONS: dict[str, set[str]] = {
    'active': {'acknowledged', 'resolved'},
    'acknowledged': {'investigating', 'resolved'},
    'investigating': {'resolved'},
    'resolved': set(),
}


def validate_transition(from_status: str, to_status: str) -> None:
    """
    Raise InvalidTransitionError if the transition is not allowed.
    """
    allowed = VALID_TRANSITIONS.get(from_status, set())
    if to_status not in allowed:
        raise InvalidTransitionError(from_status, to_status)


def get_current_status(incident_id: str) -> str:
    """
    Return the current workflow status for an incident.

    Looks at the most recent IncidentAction. If none exist, the incident
    is still in its ClickHouse-native 'active' state.
    """
    latest = (
        IncidentAction.objects
        .filter(incident_id=incident_id)
        .order_by('-performed_at')
        .values_list('to_status', flat=True)
        .first()
    )
    return latest or 'active'
