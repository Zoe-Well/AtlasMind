"""Append-only audit access separated from normal run ownership."""

from atlasmind.api.middleware.auth_context import AuthContext
from atlasmind.domain.common import ResourceNotAvailable
from atlasmind.identity.models import Action
from atlasmind.observability.audit import AuditEvent


class InMemoryAuditRepository:
    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def append(self, event: AuditEvent) -> None:
        self._events.append(event)

    def by_correlation(
        self,
        correlation_id: str,
        context: AuthContext,
    ) -> tuple[AuditEvent, ...]:
        if Action.AUDIT not in context.allowed_actions:
            raise ResourceNotAvailable()
        return tuple(event for event in self._events if event.correlation_id == correlation_id)
