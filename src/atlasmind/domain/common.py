"""Shared domain primitives with stable public failure semantics."""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4


def new_id() -> str:
    return str(uuid4())


def require_id(value: str) -> str:
    UUID(value)
    return value


def utc_now() -> datetime:
    return datetime.now(UTC)


class DomainError(Exception):
    """A typed failure safe to map at the API boundary."""

    code = "DOMAIN_ERROR"
    public_message = "The operation could not be completed."
    status_code = 400
    retryable = False

    def __init__(self, *, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(self.public_message)
        self.details = dict(details or {})


class AuthorizationDenied(DomainError):
    code = "ACTION_NOT_ALLOWED"
    public_message = "The requested action is not available."
    status_code = 403


class AuthenticationRequired(DomainError):
    code = "UNAUTHENTICATED"
    public_message = "A valid enterprise identity is required."
    status_code = 401


class ResourceNotAvailable(DomainError):
    code = "RESOURCE_NOT_AVAILABLE"
    public_message = "The requested resource is not available."
    status_code = 404


class InvalidState(DomainError):
    code = "INVALID_STATE"
    public_message = "The resource cannot accept this operation in its current state."
    status_code = 409


class BudgetExceeded(DomainError):
    code = "BUDGET_EXCEEDED"
    public_message = "The operation exceeded an allowed budget."
    status_code = 429


class ModelCapabilityUnavailable(DomainError):
    code = "MODEL_CAPABILITY_NOT_CONFIGURED"
    public_message = "The required AI model capability is not configured."
    status_code = 503
    reason = "MODEL_CAPABILITY_NOT_CONFIGURED"
