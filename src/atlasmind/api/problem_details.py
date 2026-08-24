"""RFC 9457 errors with stable, non-enumerating public semantics."""

from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse

from atlasmind.domain.common import DomainError, ResourceNotAvailable


def problem_response(
    error: Exception,
    correlation_id: str,
    *,
    conceal_authorization: bool = True,
) -> JSONResponse:
    if not isinstance(error, DomainError):
        error = DomainError()
    if error.status_code == 404 or (error.status_code == 403 and conceal_authorization):
        error = ResourceNotAvailable()
    body: dict[str, Any] = {
        "type": f"urn:atlasmind:error:{error.code.casefold()}",
        "title": error.public_message,
        "status": error.status_code,
        "code": error.code,
        "correlationId": correlation_id,
    }
    return JSONResponse(body, status_code=error.status_code, media_type="application/problem+json")
